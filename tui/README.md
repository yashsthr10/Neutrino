# Neutrino Ink TUI

Presentation layer for the Neutrino execution runtime. Renders state and dispatches commands over **newline-delimited JSON-RPC** to `python -m src.rpc`.

## Prerequisites

- Node.js **>= 20**
- Python **>= 3.11**
- From the repo root: `pip install -e .` (or `pip install -e ".[dev]"`)

## Setup

```bash
cd tui
npm install
npm run build
```

## Run

From `tui/`:

```bash
npm start
# or during development:
npm run dev
```

From the repo root (after install + TUI build):

```bash
neutrino
# or
neutrino --cwd /path/to/repo
```

The TUI owns the terminal and spawns `python -m src.rpc` as a child on pipes.

## Debug the runtime alone

```bash
python -m src.rpc --repo .
# then write NDJSON, e.g.:
# {"jsonrpc":"2.0","id":1,"method":"session.hello","params":{"protocolVersion":"1.0.0","cwd":"."}}
# {"jsonrpc":"2.0","id":2,"method":"runtime.execute","params":{"task":"Implement OAuth"}}
```

See [`../protocol/README.md`](../protocol/README.md) for the wire protocol.

## UI

Claude Code / Codex-style: quiet status line, chronological stream, `>` prompt. No sidebar or multi-panel dashboard. Runtime details live behind **Ctrl+R**. API keys: **Ctrl+K** / `/auth`. Model picker: **Ctrl+M** / `/model` (only providers with credentials).

## Shortcuts

| Key | Action |
|-----|--------|
| Ctrl+P | Command palette |
| Ctrl+K | Credentials (API keys) |
| Ctrl+M | Model selection |
| Ctrl+R | Runtime Inspector |
| Ctrl+C | Cancel run (or quit if idle) |
| Ctrl+U | Undo (stub) |
| ↑ / ↓ | Prompt history |
| Esc | Close overlay |
| Enter | Submit command / task |

## Slash commands

`/help` `/status` `/cancel` `/approve` `/reject` `/undo` `/context` `/plan` `/explain`
