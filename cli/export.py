"""Stride for Claude — export and statistics."""

import csv
import json
from pathlib import Path

from .config import DEFAULT_EXPORT_PATH, STRIDE_DIR
from .database import get_db


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
