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

import sys
import os

# Support both direct execution (python stride.py) and package execution (python -m cli).
# When run directly, the package's parent directory isn't on sys.path, so relative imports
# would fail. This block adds it so that `from cli.x import y` works, then we use the
# relative import form for consistency.
if __name__ == "__main__" and __package__ is None:
    _cli_dir = os.path.dirname(os.path.abspath(__file__))
    _project_dir = os.path.dirname(_cli_dir)
    if _project_dir not in sys.path:
        sys.path.insert(0, _project_dir)
    __package__ = "cli"

try:
    import readline  # noqa: F401 — Unix: enables arrow-key history in input()
except ImportError:
    pass  # Windows: not available, input() still works fine without it

from .config import STRIDE_VERSION
from .export import export_db, print_stats
from .hooks import handle_hook, install_hook, uninstall_hook
from .parser import _validate_since
from .rating import rate_session
from .sync import sync_sessions


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
