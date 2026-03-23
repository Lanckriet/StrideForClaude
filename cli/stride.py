#!/usr/bin/env python3
"""
Stride for Claude — Claude Code usage tracker.

Reads session data directly from Claude Code's native JSONL logs
(~/.claude/projects/) and enriches it with optional human ratings via
a Claude Code Stop hook.

Usage:
    stride sync                      Parse JSONL logs into the Stride DB
    stride sync --since 2026-01-01   Only sync sessions after a date
    stride rate [session_id]         Rate a session (defaults to most recent)
    stride stats                     Print summary statistics
    stride export [path]             Export DB to JSON for the dashboard
    stride export --csv [path]       Export DB to CSV (opens in Excel/Sheets)
    stride install-hook              Install the Stop hook for auto-sync + rating
    stride uninstall-hook            Remove the Stride Stop hook
    stride hook-handler              (internal) Called by the Stop hook
    stride version                   Show version
    stride help                      Show this help text

Data flow:
    Claude Code writes JSONL -> stride sync reads it -> SQLite DB -> export -> dashboard

No wrapper needed. No stdout parsing. Uses the same data source as ccusage/tokscale.
"""

# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------
# VERSIONING GUIDELINES (semver: MAJOR.MINOR.PATCH)
#
# This constant is the single authoritative version for the CLI.
# The dashboard has its own STRIDE_VERSION constant that must be kept in sync.
# The VERSION file in the project root is the canonical source of truth.
#
# When to bump:
#   PATCH (0.1.x)  Bug fixes, cosmetic dashboard changes, seed data tweaks.
#                   No schema changes, no new CLI commands, no breaking changes.
#   MINOR (0.x.0)  New features: new CLI commands, new dashboard tabs, new
#                   DB columns (with backwards-compatible migrations), new
#                   export fields. Existing exports still load in new dashboard.
#   MAJOR (x.0.0)  Breaking changes: DB schema changes that require migration,
#                   export format changes that break old dashboards, CLI
#                   command renames or removals.
#
# Checklist when bumping:
#   1. Update VERSION file in project root
#   2. Update STRIDE_VERSION below
#   3. Update STRIDE_VERSION in stride_dashboard.jsx
#   4. Update CHANGELOG.md (create if first release)
#   5. Tag the commit: git tag v0.x.x
# ---------------------------------------------------------------------------

STRIDE_VERSION = "0.1.1"

import sys
import os
import json
import csv
import sqlite3
import readline  # noqa: F401 — imported for side effect: enables arrow-key history in input()
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

STRIDE_DIR = Path(os.environ.get("STRIDE_DIR", os.environ.get("CCTRACK_DIR", Path.home() / ".stride")))
DB_PATH = STRIDE_DIR / "usage.db"
DEFAULT_EXPORT_PATH = STRIDE_DIR / "export.json"

CLAUDE_PROJECTS_DIRS = [
    Path.home() / ".claude" / "projects",
    Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "claude" / "projects",
]

CLAUDE_SETTINGS_PATH = Path.home() / ".claude" / "settings.json"

TASK_TAGS = ["apex", "lwc", "flow", "config", "scripting", "docs", "review", "other"]

# Used by hook detection — matches against command strings in settings.json
# to identify Stride hooks regardless of filename.
_HOOK_MARKERS = ("hook-handler",)

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS _stride_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT    UNIQUE NOT NULL,
    project_dir     TEXT,
    project_name    TEXT,
    git_branch      TEXT,
    started_at      TEXT,
    ended_at        TEXT,
    model           TEXT,
    models_used     TEXT,
    total_input_tokens    INTEGER DEFAULT 0,
    total_output_tokens   INTEGER DEFAULT 0,
    cache_read_tokens     INTEGER DEFAULT 0,
    cache_creation_tokens INTEGER DEFAULT 0,
    total_messages        INTEGER DEFAULT 0,
    user_messages         INTEGER DEFAULT 0,
    assistant_messages    INTEGER DEFAULT 0,
    tool_calls            INTEGER DEFAULT 0,
    tools_used            TEXT,
    code_generated        INTEGER DEFAULT 0,
    languages_detected    TEXT,
    duration_ms           INTEGER,
    estimated_cost_usd    REAL,
    exit_status           TEXT,
    rating                INTEGER,
    tags                  TEXT,
    note                  TEXT,
    prompt_summary        TEXT,
    synced_at             TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_started ON sessions(started_at);
CREATE INDEX IF NOT EXISTS idx_sessions_tags ON sessions(tags);
CREATE INDEX IF NOT EXISTS idx_sessions_session_id ON sessions(session_id);
"""


def _migrate(conn: sqlite3.Connection) -> None:
    """Run forward-only schema migrations based on stored schema version."""
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}

    if "_stride_meta" not in tables:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS _stride_meta (key TEXT PRIMARY KEY, value TEXT)"
        )
        conn.commit()

    row = conn.execute(
        "SELECT value FROM _stride_meta WHERE key='schema_version'"
    ).fetchone()
    current = int(row[0]) if row else 0

    # -- Migration 0 -> 1: initial schema (nothing to alter, just stamp) -----
    # Future migrations go here as elif blocks:
    #   if current < 2:
    #       conn.execute("ALTER TABLE sessions ADD COLUMN new_col TEXT")
    #       current = 2

    if current < SCHEMA_VERSION:
        conn.execute(
            "INSERT OR REPLACE INTO _stride_meta (key, value) VALUES ('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
        conn.commit()


def get_db() -> sqlite3.Connection:
    STRIDE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


# ---------------------------------------------------------------------------
# JSONL parsing — reads Claude Code's native session logs
# ---------------------------------------------------------------------------

MODEL_PRICING = {
    "claude-sonnet": {"input": 3.0, "output": 15.0, "cache_read": 0.30, "cache_create": 3.75},
    "claude-opus":   {"input": 15.0, "output": 75.0, "cache_read": 1.50, "cache_create": 18.75},
    "claude-haiku":  {"input": 0.80, "output": 4.0, "cache_read": 0.08, "cache_create": 1.0},
    "default":       {"input": 3.0, "output": 15.0, "cache_read": 0.30, "cache_create": 3.75},
}

CODE_TOOLS = {"Write", "Edit", "MultiEdit", "CreateFile"}

EXT_LANG = {
    ".cls": "apex", ".trigger": "apex", ".js": "javascript", ".html": "html",
    ".css": "css", ".xml": "xml", ".json": "json", ".py": "python",
    ".sh": "bash", ".ts": "typescript", ".yaml": "yaml", ".yml": "yaml",
    ".md": "markdown", ".sql": "sql", ".soql": "soql", ".jsx": "javascript",
    ".tsx": "typescript", ".vue": "vue", ".svelte": "svelte",
}


def get_pricing(model_name: str) -> dict:
    if not model_name:
        return MODEL_PRICING["default"]
    ml = model_name.lower()
    if "opus" in ml:
        return MODEL_PRICING["claude-opus"]
    if "haiku" in ml:
        return MODEL_PRICING["claude-haiku"]
    if "sonnet" in ml:
        return MODEL_PRICING["claude-sonnet"]
    return MODEL_PRICING["default"]


def estimate_cost(tokens: dict, model: str) -> float:
    p = get_pricing(model)
    cost = 0.0
    cost += tokens.get("input", 0) * p["input"] / 1_000_000
    cost += tokens.get("output", 0) * p["output"] / 1_000_000
    cost += tokens.get("cache_read", 0) * p["cache_read"] / 1_000_000
    cost += tokens.get("cache_create", 0) * p["cache_create"] / 1_000_000
    return round(cost, 6)


def parse_jsonl_session(filepath: Path) -> dict | None:
    """Parse a Claude Code JSONL session file into a session summary."""
    lines = []
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            for raw_line in f:
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    lines.append(json.loads(raw_line))
                except json.JSONDecodeError:
                    continue
    except (OSError, IOError):
        return None

    if not lines:
        return None

    session_id = None
    project_dir = None
    git_branch = None
    timestamps = []
    models = set()
    primary_model = None
    tokens = {"input": 0, "output": 0, "cache_read": 0, "cache_create": 0}
    user_msgs = 0
    assistant_msgs = 0
    tool_call_count = 0
    tools_used = set()
    languages = set()
    code_generated = False
    first_user_prompt = None

    for entry in lines:
        if "sessionId" in entry:
            session_id = entry["sessionId"]
        if "cwd" in entry:
            project_dir = entry["cwd"]
        if "gitBranch" in entry:
            git_branch = entry["gitBranch"]

        ts = entry.get("timestamp")
        if ts:
            timestamps.append(ts)

        msg = entry.get("message", {})
        role = msg.get("role")

        if role == "user":
            user_msgs += 1
            if first_user_prompt is None:
                content = msg.get("content", "")
                if isinstance(content, str):
                    first_user_prompt = content
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            first_user_prompt = block.get("text", "")
                            break
                        elif isinstance(block, str):
                            first_user_prompt = block
                            break

        elif role == "assistant":
            assistant_msgs += 1
            model = msg.get("model")
            if model:
                models.add(model)
                primary_model = model

            usage = msg.get("usage", {})
            tokens["input"] += usage.get("input_tokens", 0)
            tokens["output"] += usage.get("output_tokens", 0)
            tokens["cache_read"] += usage.get("cache_read_input_tokens", 0)
            tokens["cache_create"] += usage.get("cache_creation_input_tokens", 0)

            content = msg.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "tool_use":
                        tool_call_count += 1
                        tool_name = block.get("name", "")
                        tools_used.add(tool_name)
                        if tool_name in CODE_TOOLS:
                            code_generated = True
                            tool_input = block.get("input", {})
                            file_path = tool_input.get("file_path", "")
                            if file_path:
                                ext = Path(file_path).suffix.lower()
                                if ext in EXT_LANG:
                                    languages.add(EXT_LANG[ext])

    if not session_id:
        session_id = filepath.stem

    started_at = min(timestamps) if timestamps else None
    ended_at = max(timestamps) if timestamps else None
    duration_ms = None
    if started_at and ended_at:
        try:
            t0 = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            t1 = datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
            duration_ms = int((t1 - t0).total_seconds() * 1000)
        except (ValueError, TypeError):
            pass

    project_name = Path(project_dir).name if project_dir else None
    prompt_summary = None
    if first_user_prompt:
        line = first_user_prompt.strip().split("\n")[0]
        prompt_summary = line[:150] + "..." if len(line) > 150 else line

    cost = estimate_cost(tokens, primary_model)

    return {
        "session_id": session_id,
        "project_dir": project_dir,
        "project_name": project_name,
        "git_branch": git_branch,
        "started_at": started_at,
        "ended_at": ended_at,
        "model": primary_model,
        "models_used": ",".join(sorted(models)) if models else None,
        "total_input_tokens": tokens["input"],
        "total_output_tokens": tokens["output"],
        "cache_read_tokens": tokens["cache_read"],
        "cache_creation_tokens": tokens["cache_create"],
        "total_messages": user_msgs + assistant_msgs,
        "user_messages": user_msgs,
        "assistant_messages": assistant_msgs,
        "tool_calls": tool_call_count,
        "tools_used": ",".join(sorted(tools_used)) if tools_used else None,
        "code_generated": int(code_generated),
        "languages_detected": ",".join(sorted(languages)) if languages else None,
        "duration_ms": duration_ms,
        "estimated_cost_usd": cost,
        "exit_status": None,
        "prompt_summary": prompt_summary,
    }


def _validate_since(since: str) -> str | None:
    """Validate a --since date string. Returns the value or None with a warning."""
    try:
        datetime.fromisoformat(since)
        return since
    except ValueError:
        print(f"Warning: '{since}' is not a valid ISO date (expected YYYY-MM-DD). Ignoring --since filter.")
        return None


def find_jsonl_files(since: str | None = None) -> list[Path]:
    """Find JSONL session files, optionally filtered by file modification time."""
    files = []
    seen_stems = set()
    for base in CLAUDE_PROJECTS_DIRS:
        if not base.exists():
            continue
        for jsonl in base.rglob("*.jsonl"):
            stem = jsonl.stem
            if stem in seen_stems:
                continue
            seen_stems.add(stem)
            if since:
                try:
                    mtime = datetime.fromtimestamp(jsonl.stat().st_mtime, tz=timezone.utc)
                    cutoff = datetime.fromisoformat(since).replace(tzinfo=timezone.utc)
                    if mtime < cutoff:
                        continue
                except (ValueError, OSError):
                    pass
            files.append(jsonl)
    return files


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------

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
    existing = set(
        row["session_id"]
        for row in conn.execute("SELECT session_id FROM sessions").fetchall()
    )

    files = find_jsonl_files(since)
    new_count = 0
    updated_count = 0
    now = datetime.now(timezone.utc).isoformat()

    for f in files:
        session = parse_jsonl_session(f)
        if not session:
            continue

        sid = session["session_id"]
        fields = _upsert_fields()

        if sid in existing:
            # Field names are hardcoded tuples, not user input — safe for f-string SQL
            set_clause = ", ".join(f"{f}=?" for f in fields) + ", synced_at=?"
            values = [session[f] for f in fields] + [now, sid]
            conn.execute(f"UPDATE sessions SET {set_clause} WHERE session_id=?", values)
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
                "exit_status", "prompt_summary", "synced_at",
            )
            placeholders = ",".join("?" * len(insert_fields))
            values = [session.get(f) for f in insert_fields[:-1]] + [now]
            conn.execute(
                f"INSERT INTO sessions ({','.join(insert_fields)}) VALUES ({placeholders})",
                values,
            )
            new_count += 1
            existing.add(sid)

    conn.commit()
    conn.close()
    print(f"Synced: {new_count} new, {updated_count} updated from {len(files)} JSONL files.")
    return new_count + updated_count


# ---------------------------------------------------------------------------
# Hook integration
# ---------------------------------------------------------------------------

HOOK_CONFIG = {
    "matcher": "",
    "hooks": [
        {
            "type": "command",
            "command": f"{sys.executable} {os.path.abspath(__file__)} hook-handler",
        }
    ],
}


def _is_stride_hook(hook_entry: dict) -> bool:
    """Check if a hook entry belongs to Stride, regardless of filename."""
    for sub in hook_entry.get("hooks", []):
        cmd = sub.get("command", "")
        if all(marker in cmd for marker in _HOOK_MARKERS):
            if "stride" in cmd.lower() or "cctrack" in cmd.lower():
                return True
    return False


def install_hook() -> None:
    settings = {}
    if CLAUDE_SETTINGS_PATH.exists():
        try:
            settings = json.loads(CLAUDE_SETTINGS_PATH.read_text())
        except json.JSONDecodeError:
            pass

    hooks = settings.setdefault("hooks", {})
    stop_hooks = hooks.setdefault("Stop", [])

    for h in stop_hooks:
        if _is_stride_hook(h):
            print("Stride Stop hook is already installed.")
            return

    stop_hooks.append(HOOK_CONFIG)
    CLAUDE_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    CLAUDE_SETTINGS_PATH.write_text(json.dumps(settings, indent=2))
    print(f"Installed Stride Stop hook in {CLAUDE_SETTINGS_PATH}")
    print("Claude Code will now auto-sync session data when tasks complete.")


def uninstall_hook() -> None:
    if not CLAUDE_SETTINGS_PATH.exists():
        print("No settings file found.")
        return
    try:
        settings = json.loads(CLAUDE_SETTINGS_PATH.read_text())
    except json.JSONDecodeError:
        print("Could not parse settings file.")
        return

    stop_hooks = settings.get("hooks", {}).get("Stop", [])
    original_len = len(stop_hooks)
    stop_hooks[:] = [h for h in stop_hooks if not _is_stride_hook(h)]

    if len(stop_hooks) < original_len:
        settings["hooks"]["Stop"] = stop_hooks
        CLAUDE_SETTINGS_PATH.write_text(json.dumps(settings, indent=2))
        print("Removed Stride Stop hook.")
    else:
        print("Stride hook not found in settings.")


def handle_hook() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        payload = {}

    transcript_path = payload.get("transcript_path")
    if not (transcript_path and Path(transcript_path).exists()):
        return

    session = parse_jsonl_session(Path(transcript_path))
    if not session:
        return

    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()
    existing = conn.execute(
        "SELECT id FROM sessions WHERE session_id=?", (session["session_id"],)
    ).fetchone()

    fields = _upsert_fields()
    if existing:
        # Field names are hardcoded tuples, not user input — safe for f-string SQL
        set_clause = ", ".join(f"{f}=?" for f in fields) + ", synced_at=?"
        values = [session[f] for f in fields] + [now, session["session_id"]]
        conn.execute(f"UPDATE sessions SET {set_clause} WHERE session_id=?", values)
    else:
        insert_fields = (
            "session_id", "project_dir", "project_name", "git_branch",
            "started_at", "ended_at", "model", "models_used",
            "total_input_tokens", "total_output_tokens",
            "cache_read_tokens", "cache_creation_tokens",
            "total_messages", "user_messages", "assistant_messages",
            "tool_calls", "tools_used", "code_generated",
            "languages_detected", "duration_ms", "estimated_cost_usd",
            "exit_status", "prompt_summary", "synced_at",
        )
        placeholders = ",".join("?" * len(insert_fields))
        values = [session.get(f) for f in insert_fields[:-1]] + [now]
        conn.execute(
            f"INSERT INTO sessions ({','.join(insert_fields)}) VALUES ({placeholders})",
            values,
        )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Rating
# ---------------------------------------------------------------------------

def rate_session(session_id: str | None = None) -> None:
    conn = get_db()
    if session_id:
        row = conn.execute(
            "SELECT id, session_id, prompt_summary, rating, tags, note "
            "FROM sessions WHERE session_id LIKE ?",
            (f"%{session_id}%",),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT id, session_id, prompt_summary, rating, tags, note "
            "FROM sessions ORDER BY ended_at DESC LIMIT 1"
        ).fetchone()

    if not row:
        print("No session found.")
        conn.close()
        return

    print(f"Session: {row['session_id'][:12]}...")
    print(f"Summary: {row['prompt_summary'] or '(none)'}")

    existing_rating = row["rating"]
    existing_tags = row["tags"]
    existing_note = row["note"]

    if existing_rating or existing_tags or existing_note:
        parts = []
        if existing_rating:
            parts.append(f"rating={existing_rating}")
        if existing_tags:
            parts.append(f"tags={existing_tags}")
        if existing_note:
            parts.append(f'note="{existing_note}"')
        print(f"  Current: {', '.join(parts)}")
    print()

    rating_input = input("  Rating (1-5, Enter to keep): ").strip()
    rating = int(rating_input) if rating_input.isdigit() and 1 <= int(rating_input) <= 5 else None

    print(f"  Tags: {', '.join(TASK_TAGS)}")
    tags_input = input("  Tags (comma-sep, Enter to keep): ").strip()
    tags = tags_input if tags_input else None

    note = input("  Note (Enter to keep): ").strip() or None

    updates = {}
    if rating is not None:
        updates["rating"] = rating
    if tags is not None:
        updates["tags"] = tags
    if note is not None:
        updates["note"] = note

    if updates:
        set_clause = ", ".join(f"{k}=?" for k in updates)
        conn.execute(
            f"UPDATE sessions SET {set_clause} WHERE id=?",
            list(updates.values()) + [row["id"]],
        )
        conn.commit()
        print("  Saved.")
    else:
        print("  No changes.")
    conn.close()


# ---------------------------------------------------------------------------
# Export / Stats
# ---------------------------------------------------------------------------

def export_db(path: str | None = None, fmt: str = "json") -> None:
    conn = get_db()
    rows = conn.execute("SELECT * FROM sessions ORDER BY started_at").fetchall()
    conn.close()

    if not rows:
        print("No sessions to export. Run: stride sync")
        return

    data = [dict(r) for r in rows]

    if fmt == "csv":
        default_csv = STRIDE_DIR / "export.csv"
        out = Path(path) if path else default_csv
        out.parent.mkdir(parents=True, exist_ok=True)

        csv_columns = [
            "started_at", "ended_at", "project_name", "git_branch", "model",
            "prompt_summary", "tags", "rating", "note",
            "total_input_tokens", "total_output_tokens",
            "cache_read_tokens", "cache_creation_tokens",
            "estimated_cost_usd", "duration_ms",
            "total_messages", "user_messages", "assistant_messages",
            "tool_calls", "tools_used", "code_generated", "languages_detected",
            "exit_status", "session_id", "models_used", "project_dir",
        ]

        header_map = {
            "started_at": "Started",
            "ended_at": "Ended",
            "project_name": "Project",
            "git_branch": "Branch",
            "model": "Model",
            "prompt_summary": "Prompt summary",
            "tags": "Tags",
            "rating": "Rating (1-5)",
            "note": "Note",
            "total_input_tokens": "Input tokens",
            "total_output_tokens": "Output tokens",
            "cache_read_tokens": "Cache read tokens",
            "cache_creation_tokens": "Cache creation tokens",
            "estimated_cost_usd": "Est. cost (USD)",
            "duration_ms": "Duration (ms)",
            "total_messages": "Total messages",
            "user_messages": "User messages",
            "assistant_messages": "Assistant messages",
            "tool_calls": "Tool calls",
            "tools_used": "Tools used",
            "code_generated": "Code generated",
            "languages_detected": "Languages",
            "exit_status": "Exit status",
            "session_id": "Session ID",
            "models_used": "All models used",
            "project_dir": "Project path",
        }

        with open(out, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([header_map.get(c, c) for c in csv_columns])
            for row in data:
                writer.writerow([row.get(c, "") for c in csv_columns])

        print(f"Exported {len(data)} sessions to {out}")
    else:
        out = Path(path) if path else DEFAULT_EXPORT_PATH
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data, indent=2))
        print(f"Exported {len(data)} sessions to {out}")


def _explode_tags(tags_str: str | None) -> list[str]:
    """Split a comma-separated tag string into individual tags."""
    if not tags_str:
        return []
    return [t.strip() for t in tags_str.split(",") if t.strip()]


def print_stats() -> None:
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) as c FROM sessions").fetchone()["c"]
    if total == 0:
        print("No sessions synced yet. Run: stride sync")
        conn.close()
        return

    rated = conn.execute("SELECT COUNT(*) as c FROM sessions WHERE rating IS NOT NULL").fetchone()["c"]
    avg_rating = conn.execute("SELECT AVG(rating) as a FROM sessions WHERE rating IS NOT NULL").fetchone()["a"]
    total_cost = conn.execute("SELECT SUM(estimated_cost_usd) as s FROM sessions").fetchone()["s"] or 0
    total_in = conn.execute("SELECT SUM(total_input_tokens) as s FROM sessions").fetchone()["s"] or 0
    total_out = conn.execute("SELECT SUM(total_output_tokens) as s FROM sessions").fetchone()["s"] or 0
    total_cache = conn.execute("SELECT SUM(cache_read_tokens) as s FROM sessions").fetchone()["s"] or 0
    avg_duration = conn.execute("SELECT AVG(duration_ms) as a FROM sessions WHERE duration_ms IS NOT NULL").fetchone()["a"]
    code_count = conn.execute("SELECT COUNT(*) as c FROM sessions WHERE code_generated = 1").fetchone()["c"]

    print(f"Total sessions:        {total}")
    print(f"Rated:                 {rated} ({rated/total*100:.0f}%)")
    if avg_rating:
        print(f"Avg rating:            {avg_rating:.1f}/5")
    print(f"Estimated total cost:  ${total_cost:.2f}")
    print(f"Total input tokens:    {total_in:,}")
    print(f"Total output tokens:   {total_out:,}")
    print(f"Cache read tokens:     {total_cache:,}")
    if avg_duration:
        print(f"Avg session duration:  {avg_duration/1000/60:.1f}min")
    print(f"Code generated:        {code_count/total*100:.0f}% of sessions")

    all_rows = conn.execute(
        "SELECT tags, rating, estimated_cost_usd FROM sessions"
    ).fetchall()

    tag_agg: dict[str, dict] = {}
    for r in all_rows:
        tags = _explode_tags(r["tags"])
        if not tags:
            continue
        for tag in tags:
            if tag not in tag_agg:
                tag_agg[tag] = {"count": 0, "ratings": [], "cost": 0.0}
            tag_agg[tag]["count"] += 1
            if r["rating"] is not None:
                tag_agg[tag]["ratings"].append(r["rating"])
            tag_agg[tag]["cost"] += r["estimated_cost_usd"] or 0

    if tag_agg:
        print("\nBy tag:")
        for tag in sorted(tag_agg, key=lambda t: tag_agg[t]["count"], reverse=True):
            s = tag_agg[tag]
            avg_r = sum(s["ratings"]) / len(s["ratings"]) if s["ratings"] else None
            rating_str = f"avg {avg_r:.1f}" if avg_r else "unrated"
            print(f"  {tag:25s}  {s['count']:>4d} sessions  ({rating_str}, ${s['cost']:.2f})")

    proj_rows = conn.execute(
        "SELECT project_name, COUNT(*) as c, SUM(estimated_cost_usd) as cost "
        "FROM sessions WHERE project_name IS NOT NULL "
        "GROUP BY project_name ORDER BY c DESC LIMIT 10"
    ).fetchall()
    if proj_rows:
        print("\nTop projects:")
        for r in proj_rows:
            print(f"  {r['project_name']:25s}  {r['c']:>4d} sessions  (${r['cost']:.2f})")

    model_rows = conn.execute(
        "SELECT model, COUNT(*) as c, AVG(total_output_tokens) as avg_out "
        "FROM sessions WHERE model IS NOT NULL "
        "GROUP BY model ORDER BY c DESC"
    ).fetchall()
    if model_rows:
        print("\nBy model:")
        for r in model_rows:
            print(f"  {r['model']:40s}  {r['c']:>4d} sessions  (avg {int(r['avg_out'] or 0):,} output tokens)")

    conn.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] == "help":
        print(f"Stride for Claude v{STRIDE_VERSION}")
        print(__doc__)
        sys.exit(0)

    cmd = args[0]
    if cmd == "version" or cmd == "--version" or cmd == "-v":
        print(f"Stride for Claude v{STRIDE_VERSION}")
        sys.exit(0)
    elif cmd == "sync":
        since = None
        if "--since" in args:
            idx = args.index("--since")
            if idx + 1 < len(args):
                since = _validate_since(args[idx + 1])
        sync_sessions(since)
    elif cmd == "rate":
        rate_session(args[1] if len(args) > 1 else None)
    elif cmd == "stats":
        print_stats()
    elif cmd == "export":
        is_csv = "--csv" in args
        remaining = [a for a in args[1:] if a != "--csv"]
        path = remaining[0] if remaining else None
        export_db(path, fmt="csv" if is_csv else "json")
    elif cmd == "install-hook":
        install_hook()
    elif cmd == "uninstall-hook":
        uninstall_hook()
    elif cmd == "hook-handler":
        handle_hook()
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
