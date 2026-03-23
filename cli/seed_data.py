#!/usr/bin/env python3
"""Seed the Stride database with realistic sample data for dashboard dev."""

import json
import random
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Import config and schema from the CLI to avoid duplication.
# Falls back to inline defaults if cctrack isn't importable (e.g. standalone run).
try:
    from cctrack import STRIDE_DIR, DB_PATH, DEFAULT_EXPORT_PATH, SCHEMA, get_db
    _HAS_CCTRACK = True
except ImportError:
    _HAS_CCTRACK = False
    STRIDE_DIR = Path.home() / ".stride"
    DB_PATH = STRIDE_DIR / "usage.db"
    DEFAULT_EXPORT_PATH = STRIDE_DIR / "export.json"

PROMPTS_BY_TAG = {
    "apex": [
        "Write a bulk trigger handler for Contact after insert",
        "Create an Apex batch class for Account data cleanup",
        "Write test class for OpportunityTriggerHandler with 90% coverage",
        "Implement a queueable for external API callout to ERP system",
        "Fix SOQL 101 error in AccountService.getRelatedContacts",
        "Write Apex REST endpoint for case creation from external portal",
        "Refactor this trigger to use DotFetch TriggerHandler pattern",
        "Create selector class for Opportunity with related line items",
    ],
    "lwc": [
        "Build a datatable component with inline editing for Contacts",
        "Create a custom lookup component with recent items",
        "Wire service component to display Account hierarchy",
        "Build a file upload component with drag-and-drop",
        "Fix reactivity issue in opportunityList component",
        "Create a reusable modal component with slot support",
    ],
    "flow": [
        "Design a screen flow for case escalation with approval",
        "Debug this record-triggered flow that fires twice on update",
        "Convert this Process Builder to a record-triggered flow",
        "Build an autolaunched flow for lead assignment rules",
    ],
    "config": [
        "Set up field-level security for new custom fields on Account",
        "Create validation rule: require Closed Date when Stage is Closed Won",
        "Design page layout for Service Console with compact case view",
        "Configure duplicate rules for Lead matching",
    ],
    "scripting": [
        "Write a Python script to compare two SFDX project manifests",
        "Bash script to deploy metadata from specific package directory",
        "Create a pre-commit hook for Apex PMD linting",
        "Write a script to bulk-update user permissions via CSV",
    ],
    "docs": [
        "Document the trigger framework architecture for onboarding",
        "Write release notes for Spring 26 deployment",
        "Create a data dictionary for the custom objects in this org",
        "Draft technical design doc for the integration with NetSuite",
    ],
    "review": [
        "Review this Apex class for governor limit risks",
        "Check this LWC for accessibility compliance",
        "Review the sharing model for the Case object hierarchy",
        "Audit this flow for infinite loop potential",
    ],
}

MODELS = ["claude-sonnet-4-20250514", "claude-opus-4-20250514", "claude-haiku-4-5-20251001"]
MODEL_WEIGHTS = [0.70, 0.20, 0.10]

PROJECTS = [
    ("/Users/dev/projects/client-crm", "client-crm"),
    ("/Users/dev/projects/internal-tools", "internal-tools"),
    ("/Users/dev/projects/data-migration", "data-migration"),
    ("/Users/dev/projects/partner-portal", "partner-portal"),
]

BRANCHES = ["main", "feature/dedup-logic", "feature/lwc-refresh", "bugfix/flow-loop",
            "release/spring-26", "feature/rest-api", "feature/batch-cleanup"]

TOOLS_BY_TAG = {
    "apex": ["Write", "Edit", "Bash", "Read", "Grep", "Glob"],
    "lwc": ["Write", "Edit", "Bash", "Read", "Grep", "WebFetch"],
    "flow": ["Read", "Bash", "Grep"],
    "config": ["Read", "Bash"],
    "scripting": ["Write", "Edit", "Bash", "Read"],
    "docs": ["Write", "Edit", "Read"],
    "review": ["Read", "Grep", "Glob", "Bash"],
}

LANGUAGES_BY_TAG = {
    "apex": ["apex"], "lwc": ["javascript", "html"], "flow": [],
    "config": [], "scripting": ["python", "bash"], "docs": ["markdown"], "review": [],
}

MODEL_PRICING = {
    "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0, "cache_read": 0.30, "cache_create": 3.75},
    "claude-opus-4-20250514":   {"input": 15.0, "output": 75.0, "cache_read": 1.50, "cache_create": 18.75},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.0, "cache_read": 0.08, "cache_create": 1.0},
}


def generate_sample_data(n_records: int = 200) -> list[dict]:
    records = []
    start_date = datetime.now(timezone.utc) - timedelta(days=60)

    for i in range(n_records):
        tag = random.choice(list(PROMPTS_BY_TAG.keys()))
        prompt = random.choice(PROMPTS_BY_TAG[tag])
        model = random.choices(MODELS, MODEL_WEIGHTS)[0]
        project_dir, project_name = random.choice(PROJECTS)
        branch = random.choice(BRANCHES)

        base_input = {"apex": 12000, "lwc": 15000, "flow": 8000, "config": 5000,
                      "scripting": 9000, "docs": 10000, "review": 14000}
        base_output = {"apex": 4000, "lwc": 5000, "flow": 2000, "config": 1500,
                       "scripting": 3000, "docs": 3500, "review": 2500}

        tokens_in = max(500, int(random.gauss(base_input[tag], base_input[tag] * 0.3)))
        tokens_out = max(200, int(random.gauss(base_output[tag], base_output[tag] * 0.3)))
        cache_read = int(tokens_in * random.uniform(0.3, 0.7))
        cache_create = int(tokens_in * random.uniform(0.05, 0.15))

        if "opus" in model:
            tokens_out = int(tokens_out * 1.4)
        elif "haiku" in model:
            tokens_out = int(tokens_out * 0.7)

        base_duration = {"apex": 180000, "lwc": 240000, "flow": 120000, "config": 60000,
                         "scripting": 150000, "docs": 200000, "review": 300000}
        duration_ms = max(30000, int(random.gauss(base_duration[tag], base_duration[tag] * 0.3)))

        if "haiku" in model:
            duration_ms = int(duration_ms * 0.5)

        user_msgs = random.randint(1, 6)
        assistant_msgs = user_msgs + random.randint(0, 3)
        tool_calls = random.randint(3, 25)
        tools = random.sample(TOOLS_BY_TAG[tag], min(len(TOOLS_BY_TAG[tag]), random.randint(2, 5)))
        code_gen = tag in ("apex", "lwc", "scripting")
        langs = LANGUAGES_BY_TAG[tag]

        pricing = MODEL_PRICING[model]
        cost = (tokens_in * pricing["input"] + tokens_out * pricing["output"] +
                cache_read * pricing["cache_read"] + cache_create * pricing["cache_create"]) / 1_000_000

        exit_status = "error" if random.random() < {"apex": 0.15, "lwc": 0.18, "flow": 0.10,
            "config": 0.06, "scripting": 0.12, "docs": 0.04, "review": 0.08}[tag] else None

        progress = i / n_records
        day_offset = 60 * (progress ** 0.7)

        rating_means = {"apex": 3.6, "lwc": 3.3, "flow": 3.8, "config": 4.2,
                        "scripting": 3.9, "docs": 4.0, "review": 3.7}
        rating = None
        if random.random() < 0.65:
            r = random.gauss(rating_means[tag], 0.8)
            rating = max(1, min(5, round(r)))
            if exit_status:
                rating = max(1, rating - 1)
            if day_offset > 30 and random.random() < 0.15:
                rating = min(5, rating + 1)

        ts_start = start_date + timedelta(
            days=day_offset + random.gauss(0, 0.3),
            hours=random.randint(8, 18), minutes=random.randint(0, 59),
        )
        ts_end = ts_start + timedelta(milliseconds=duration_ms)

        note = None
        if exit_status and random.random() < 0.7:
            error_notes = [
                "Hallucinated a nonexistent method",
                "Governor limit not handled in generated code",
                "Generated code had syntax errors",
                "Missed edge case for null handling",
                "Output was incomplete, had to re-run",
                "Wrong object referenced, needed manual fix",
                "Test class didn't compile on first attempt",
            ]
            note = random.choice(error_notes)
        elif not exit_status and random.random() < 0.15:
            success_notes = [
                "Clean first attempt, no edits needed",
                "Good structure but renamed a few variables",
                "Needed minor prompt refinement",
                "Solid output, saved to snippets library",
                "Reused pattern from previous session",
            ]
            note = random.choice(success_notes)

        records.append({
            "session_id": str(uuid.uuid4()),
            "project_dir": project_dir,
            "project_name": project_name,
            "git_branch": branch,
            "started_at": ts_start.isoformat(),
            "ended_at": ts_end.isoformat(),
            "model": model,
            "models_used": model,
            "total_input_tokens": tokens_in,
            "total_output_tokens": tokens_out,
            "cache_read_tokens": cache_read,
            "cache_creation_tokens": cache_create,
            "total_messages": user_msgs + assistant_msgs,
            "user_messages": user_msgs,
            "assistant_messages": assistant_msgs,
            "tool_calls": tool_calls,
            "tools_used": ",".join(sorted(tools)),
            "code_generated": int(code_gen),
            "languages_detected": ",".join(langs) if langs else None,
            "duration_ms": duration_ms,
            "estimated_cost_usd": round(cost, 4),
            "exit_status": exit_status,
            "rating": rating,
            "tags": tag,
            "note": note,
            "prompt_summary": prompt,
            "synced_at": datetime.now(timezone.utc).isoformat(),
        })

    records.sort(key=lambda r: r["started_at"])
    return records


def main():
    records = generate_sample_data(150)

    if _HAS_CCTRACK:
        conn = get_db()
    else:
        STRIDE_DIR.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(DB_PATH))
        # Minimal inline schema as fallback only
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT UNIQUE NOT NULL,
                project_dir TEXT, project_name TEXT, git_branch TEXT,
                started_at TEXT, ended_at TEXT, model TEXT, models_used TEXT,
                total_input_tokens INTEGER DEFAULT 0, total_output_tokens INTEGER DEFAULT 0,
                cache_read_tokens INTEGER DEFAULT 0, cache_creation_tokens INTEGER DEFAULT 0,
                total_messages INTEGER DEFAULT 0, user_messages INTEGER DEFAULT 0,
                assistant_messages INTEGER DEFAULT 0, tool_calls INTEGER DEFAULT 0,
                tools_used TEXT, code_generated INTEGER DEFAULT 0,
                languages_detected TEXT, duration_ms INTEGER, estimated_cost_usd REAL,
                exit_status TEXT, rating INTEGER, tags TEXT, note TEXT,
                prompt_summary TEXT, synced_at TEXT NOT NULL
            );
        """)

    conn.execute("DELETE FROM sessions")

    for r in records:
        fields = list(r.keys())
        placeholders = ",".join("?" * len(fields))
        conn.execute(
            f"INSERT INTO sessions ({','.join(fields)}) VALUES ({placeholders})",
            [r[f] for f in fields],
        )

    conn.commit()
    conn.close()

    DEFAULT_EXPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_EXPORT_PATH.write_text(json.dumps(records, indent=2))
    print(f"Seeded {len(records)} sessions into {DB_PATH}")
    print(f"Exported to {DEFAULT_EXPORT_PATH}")


if __name__ == "__main__":
    main()
