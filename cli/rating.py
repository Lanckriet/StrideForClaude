"""Stride for Claude — interactive session rating."""

from .config import TASK_TAGS
from .database import get_db


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

    rating_prompt = f"  Rating (1-5, Enter to keep [{existing_rating or '-'}]): "
    rating_input = input(rating_prompt).strip()
    rating = int(rating_input) if rating_input.isdigit() and 1 <= int(rating_input) <= 5 else None

    print(f"  Available tags: {', '.join(TASK_TAGS)}")
    tags_prompt = f"  Tags (comma-sep, Enter to keep [{existing_tags or '-'}], 'clear' to remove): "
    tags_input = input(tags_prompt).strip().lower()
    if tags_input == "clear":
        tags = ""  # sentinel: explicitly clear
    elif tags_input:
        tags = tags_input
    else:
        tags = None  # keep existing

    note_prompt = f"  Note (Enter to keep, 'clear' to remove): "
    note_input = input(note_prompt).strip()
    if note_input.lower() == "clear":
        note = ""  # sentinel: explicitly clear
    elif note_input:
        note = note_input
    else:
        note = None  # keep existing

    updates = {}
    if rating is not None:
        updates["rating"] = rating
    if tags is not None:
        updates["tags"] = tags if tags else None
    if note is not None:
        updates["note"] = note if note else None

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
