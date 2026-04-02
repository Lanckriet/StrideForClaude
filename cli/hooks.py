"""Stride for Claude — Claude Code Stop hook integration."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .config import CLAUDE_SETTINGS_PATH, HOOK_COMMAND, _HOOK_MARKERS
from .database import get_db
from .parser import parse_jsonl_session
from .sync import _upsert_fields

HOOK_CONFIG = {
    "matcher": "",
    "hooks": [
        {
            "type": "command",
            "command": HOOK_COMMAND,
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
