"""Stride for Claude — database schema, migrations, and connection."""

import sqlite3

from .config import STRIDE_DIR, DB_PATH

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
