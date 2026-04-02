"""Stride for Claude — shared configuration and constants."""

import os
import sys
from pathlib import Path

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

STRIDE_VERSION = "0.2.1"

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

STRIDE_DIR = Path(os.environ.get("STRIDE_DIR", os.environ.get("CCTRACK_DIR", Path.home() / ".stride")))
DB_PATH = STRIDE_DIR / "usage.db"
DEFAULT_EXPORT_PATH = STRIDE_DIR / "export.json"

CLAUDE_PROJECTS_DIRS = [
    Path.home() / ".claude" / "projects",
    Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "claude" / "projects",
]

CLAUDE_SETTINGS_PATH = Path.home() / ".claude" / "settings.json"

# ---------------------------------------------------------------------------
# Tags & hook detection
# ---------------------------------------------------------------------------

TASK_TAGS = ["apex", "lwc", "flow", "config", "scripting", "docs", "review", "other"]

# Used by hook detection — matches against command strings in settings.json
# to identify Stride hooks regardless of filename.
_HOOK_MARKERS = ("hook-handler",)

# ---------------------------------------------------------------------------
# Pricing & language detection
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

# ---------------------------------------------------------------------------
# Hook command template (needs sys/os at import time)
# ---------------------------------------------------------------------------

HOOK_COMMAND = f"{sys.executable} {os.path.abspath(os.path.join(os.path.dirname(__file__), 'stride.py'))} hook-handler"
