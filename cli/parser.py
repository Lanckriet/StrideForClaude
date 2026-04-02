"""Stride for Claude — JSONL parsing and session extraction."""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .config import (
    CLAUDE_PROJECTS_DIRS,
    CODE_TOOLS,
    EXT_LANG,
    MODEL_PRICING,
    TASK_TAGS,
)


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


def auto_tag(
    languages: set[str],
    tools_used: set[str],
    file_paths: set[str],
    user_text: str,
    code_generated: bool,
) -> str | None:
    """Infer task tags from session signals. Returns comma-separated tags or None."""
    tags = set()
    paths_lower = {p.lower().replace("\\", "/") for p in file_paths}

    # --- Salesforce: Apex ---
    if "apex" in languages:
        tags.add("apex")
    if any(p.endswith((".cls", ".trigger")) for p in paths_lower):
        tags.add("apex")
    apex_kw = re.search(r"\b(apex|soql|sobject|trigger|@istest|testmethod|auraenabled)\b", user_text)
    if apex_kw:
        tags.add("apex")

    # --- Salesforce: LWC ---
    if any("/lwc/" in p for p in paths_lower):
        tags.add("lwc")
    lwc_kw = re.search(r"\b(lwc|lightning web component|lightning-\w+|@api|@track|@wire)\b", user_text)
    if lwc_kw:
        tags.add("lwc")
    # JS/HTML inside an LWC folder → lwc, not scripting
    if any("/lwc/" in p and p.endswith((".js", ".html", ".css")) for p in paths_lower):
        tags.add("lwc")

    # --- Salesforce: Flow ---
    if any(p.endswith(".flow-meta.xml") for p in paths_lower):
        tags.add("flow")
    if any("/flows/" in p or "/flow/" in p for p in paths_lower):
        tags.add("flow")
    flow_kw = re.search(r"\b(flow|screen flow|record-triggered|autolaunched flow|flow builder|subflow)\b", user_text)
    if flow_kw:
        tags.add("flow")

    # --- Salesforce: Config (metadata, admin, declarative) ---
    config_exts = (".object-meta.xml", ".field-meta.xml", ".profile-meta.xml",
                   ".permissionset-meta.xml", ".layout-meta.xml", ".app-meta.xml",
                   ".flexipage-meta.xml", ".tab-meta.xml", ".quickAction-meta.xml",
                   ".labels-meta.xml", ".remoteSite-meta.xml", ".namedCredential-meta.xml")
    if any(any(p.endswith(ext) for ext in config_exts) for p in paths_lower):
        tags.add("config")
    config_kw = re.search(
        r"\b(metadata|custom object|custom field|permission set|profile|page layout|"
        r"validation rule|sfdx|sf deploy|scratch org|sandbox|package\.xml)\b", user_text
    )
    if config_kw:
        tags.add("config")

    # --- Scripting (Python, Bash, general JS/TS not in LWC) ---
    scripting_langs = {"python", "bash", "sql", "soql"}
    if languages & scripting_langs:
        tags.add("scripting")
    # JS/TS that is NOT inside lwc folders → scripting
    non_lwc_js = any(
        p.endswith((".js", ".ts", ".jsx", ".tsx")) and "/lwc/" not in p
        for p in paths_lower
    )
    if non_lwc_js and ("javascript" in languages or "typescript" in languages):
        tags.add("scripting")
    script_kw = re.search(r"\b(script|automate|cron|batch|etl|migration|data load|anonymous apex)\b", user_text)
    if script_kw:
        tags.add("scripting")

    # --- Docs ---
    if "markdown" in languages:
        tags.add("docs")
    if any(p.endswith((".md", ".txt", ".rst")) for p in paths_lower):
        tags.add("docs")
    docs_kw = re.search(r"\b(readme|documentation|doc|wiki|changelog|release notes|comment)\b", user_text)
    if docs_kw:
        tags.add("docs")

    # --- Review (read-heavy, no code gen) ---
    read_tools = {"Read", "Grep", "Glob", "Search"}
    if not code_generated and tools_used and tools_used <= (read_tools | {"Bash", "Agent"}):
        tags.add("review")
    review_kw = re.search(r"\b(review|explain|understand|analyze|audit|investigate|debug|diagnose|what does)\b", user_text)
    if review_kw and not code_generated:
        tags.add("review")

    # --- Fallback: if nothing matched, tag as 'other' ---
    if not tags:
        tags.add("other")

    # Only keep tags that are in the canonical set
    tags &= set(TASK_TAGS)
    return ",".join(sorted(tags)) if tags else None


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
    # Richer signals for auto-tagging
    user_text_parts = []          # all user message text (for keyword matching)
    file_paths_touched = set()    # every file path seen in tool calls (read + write)

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
            content = msg.get("content", "")
            if isinstance(content, str):
                if first_user_prompt is None:
                    first_user_prompt = content
                user_text_parts.append(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text = block.get("text", "")
                        if first_user_prompt is None:
                            first_user_prompt = text
                        user_text_parts.append(text)
                    elif isinstance(block, str):
                        if first_user_prompt is None:
                            first_user_prompt = block
                        user_text_parts.append(block)

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
                        tool_input = block.get("input", {})
                        # Collect file paths from any tool that references files
                        file_path = tool_input.get("file_path", "") or tool_input.get("path", "")
                        if file_path:
                            file_paths_touched.add(file_path)
                            ext = Path(file_path).suffix.lower()
                            if ext in EXT_LANG:
                                languages.add(EXT_LANG[ext])
                        if tool_name in CODE_TOOLS:
                            code_generated = True

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

    # Combine all user text for keyword analysis (cap at 5000 chars to stay lean)
    user_text_blob = " ".join(user_text_parts)[:5000].lower()

    session_data = {
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

    # Auto-tag using all available signals
    session_data["auto_tags"] = auto_tag(
        languages=languages,
        tools_used=tools_used,
        file_paths=file_paths_touched,
        user_text=user_text_blob,
        code_generated=code_generated,
    )

    return session_data


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
