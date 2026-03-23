# Stride for Claude

Claude Code performance insights. Track usage, rate sessions, spot patterns.

**[Open Dashboard](https://YOUR_USERNAME.github.io/stride/)** -- drop your `export.json` to view your data. Nothing leaves your browser.

## What it does

Stride reads Claude Code's native JSONL session logs from `~/.claude/projects/`, aggregates per-session metrics into a local SQLite database, and surfaces performance insights via a browser dashboard. Optionally annotate sessions with quality ratings, task tags, and notes.

## Quick start

```bash
# 1. Get the CLI
git clone https://github.com/YOUR_USERNAME/stride.git
chmod +x stride/cli/stride.py
ln -s "$(pwd)/stride/cli/stride.py" ~/.local/bin/stride

# 2. Sync your Claude Code sessions
stride sync

# 3. (Optional) Install auto-sync hook
stride install-hook

# 4. Export and view
stride export
# Open the dashboard URL above, drop export.json
```

## CLI commands

```
stride sync                      Parse JSONL logs into the Stride DB
stride sync --since 2026-03-01   Only sync sessions modified after a date
stride rate                      Rate the most recent session
stride rate abc123               Rate a specific session (partial ID match)
stride stats                     Print summary statistics
stride export                    Export to ~/.stride/export.json
stride export --csv              Export to CSV
stride install-hook              Add Stop hook for auto-sync
stride uninstall-hook            Remove the Stop hook
```

## Dashboard

The dashboard is a single static HTML page hosted on GitHub Pages. It runs entirely client-side -- your data never leaves your browser. Load your export.json via drag-and-drop.

Features: performance by tag, token efficiency, failure patterns, cost tracking, weekly trends, model usage breakdown, quality ratings over time.

## How data flows

```
Claude Code writes JSONL  ->  stride sync  ->  SQLite DB  ->  stride export  ->  Dashboard
    ~/.claude/projects/         (parse)      ~/.stride/        (JSON file)      (browser)
```

## Requirements

- Python 3.10+ (stdlib only, no pip dependencies)
- Claude Code (any version that writes JSONL session logs)

## Project structure

```
index.html                  Dashboard (GitHub Pages root)
cli/
  stride.py                 CLI tool
  seed_data.py              Sample data generator for development
dashboard/
  stride_dashboard.jsx      Dashboard source (React/JSX, for Claude artifact use)
VERSION                     Canonical version
```

## Deploying the dashboard

1. Push this repo to GitHub
2. Go to Settings > Pages
3. Set Source to "Deploy from a branch", branch `main`, folder `/ (root)`
4. Your dashboard will be live at `https://YOUR_USERNAME.github.io/stride/`

Update the URL in this README once deployed.

## License

MIT
