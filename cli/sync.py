"""Stride for Claude — session sync from JSONL logs to SQLite."""

from datetime import datetime, timezone

from .database import get_db
from .parser import find_jsonl_files, parse_jsonl_session


def _upsert_fields():
    """Fields updated on re-sync of an existing session (not ratings/tags/notes)."""
    return (
        "total_input_tokens", "total_output_tokens",
        "cache_read_tokens", "cache_creation_tokens",
        "total_messages", "user_messages", "assistant_messages",
        "tool_calls", "tools_used", "code_generated",
        "languages_detected", "duration_ms", "estimated_cost_usd",
        "ended_at", "model", "models_used",
    )


def sync_sessions(since: str | None = None) -> int:
    conn = get_db()
    existing = {
        row["session_id"]: row["tags"]
        for row in conn.execute("SELECT session_id, tags FROM sessions").fetchall()
    }

    files = find_jsonl_files(since)
    new_count = 0
    updated_count = 0
    auto_tagged = 0
    now = datetime.now(timezone.utc).isoformat()

    for f in files:
        session = parse_jsonl_session(f)
        if not session:
            continue

        sid = session["session_id"]
        auto_tags = session.get("auto_tags")
        fields = _upsert_fields()

        if sid in existing:
            # Field names are hardcoded tuples, not user input — safe for f-string SQL
            set_clause = ", ".join(f"{f}=?" for f in fields) + ", synced_at=?"
            values = [session[f] for f in fields] + [now, sid]
            conn.execute(f"UPDATE sessions SET {set_clause} WHERE session_id=?", values)
            # Refresh auto-tags only when no manual tags have been set
            if not existing[sid] and auto_tags:
                conn.execute("UPDATE sessions SET tags=? WHERE session_id=?", (auto_tags, sid))
                auto_tagged += 1
            updated_count += 1
        else:
            insert_fields = (
                "session_id", "project_dir", "project_name", "git_branch",
                "started_at", "ended_at", "model", "models_used",
                "total_input_tokens", "total_output_tokens",
                "cache_read_tokens", "cache_creation_tokens",
                "total_messages", "user_messages", "assistant_messages",
                "tool_calls", "tools_used", "code_generated",
                "languages_detected", "duration_ms", "estimated_cost_usd",
                "exit_status", "prompt_summary", "tags", "synced_at",
            )
            placeholders = ",".join("?" * len(insert_fields))
            values = [session.get(f) for f in insert_fields[:-2]] + [auto_tags, now]
            conn.execute(
                f"INSERT INTO sessions ({','.join(insert_fields)}) VALUES ({placeholders})",
                values,
            )
            if auto_tags:
                auto_tagged += 1
            new_count += 1
            existing[sid] = auto_tags

    conn.commit()
    conn.close()
    print(f"Synced: {new_count} new, {updated_count} updated from {len(files)} JSONL files.")
    if auto_tagged:
        print(f"Auto-tagged: {auto_tagged} sessions.")
    return new_count + updated_count
