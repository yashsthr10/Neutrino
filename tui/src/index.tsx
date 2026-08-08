#!/usr/bin/env node
import React from "react";
import { render } from "ink";

import { App } from "./app/App.js";
import { RuntimeProvider } from "./state/RuntimeContext.js";

function parseArgs(argv: string[]): { cwd: string; help: boolean; version: boolean } {
  let cwd = process.cwd();
  let help = false;
  let version = false;
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--help" || a === "-h") help = true;
    else if (a === "--version" || a === "-V") version = true;
    else if (a === "--cwd" && argv[i + 1]) {
      cwd = argv[++i]!;
    }
  }
  return { cwd, help, version };
}

const args = parseArgs(process.argv.slice(2));

if (args.help) {
  console.log(`neutrino-tui — Ink presentation layer for Neutrino

Usage:
  neutrino-tui [--cwd <path>]

Environment:
  NEUTRINO_PYTHON   Python executable (default: .venv/bin/python or python3)

Shortcuts:
  Tab           cycle panels
  Ctrl+P        command palette
  Ctrl+R        runtime inspector
  Ctrl+D / L    focus diff / logs
  Ctrl+C        cancel run (or quit)
  Ctrl+U        undo (stub)
  Esc           close overlay
`);
  process.exit(0);
}

if (args.version) {
  console.log("0.1.0");
  process.exit(0);
}

render(
  <RuntimeProvider cwd={args.cwd}>
    <App />
  </RuntimeProvider>,
);
