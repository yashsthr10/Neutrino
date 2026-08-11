# Neutrino Presentation Protocol

Newline-delimited JSON-RPC 2.0 over stdio between presentation clients (Ink TUI, future VS Code/web) and the Python runtime.

**Protocol version:** `1.0.0`

## Framing

- One JSON object per line (NDJSON).
- Requests and responses include `"jsonrpc": "2.0"` and `"id"`.
- Notifications omit `"id"` (runtime → client events).
- Runtime diagnostics must go to **stderr**, never stdout.

## Handshake

### `session.hello`

Request:

```json
{"jsonrpc":"2.0","id":1,"method":"session.hello","params":{"protocolVersion":"1.0.0","cwd":"/path/to/repo"}}
```

Result:

```json
{
  "protocolVersion": "1.0.0",
  "projectName": "NeutrinoCLI",
  "model": "llama3.2",
  "branch": "main",
  "capabilities": ["execute", "cancel", "approve", "status", "undo"]
}
```

Mismatched major protocol versions return a JSON-RPC error (`-32000`).

## Requests (client → runtime)

| Method | Params | Maps to |
|--------|--------|---------|
| `session.hello` | `{ protocolVersion, cwd }` | handshake |
| `runtime.execute` | `{ task }` | `submit_task` |
| `runtime.cancel` | `{}` | `cancel_run` |
| `runtime.approve` | `{ requestId, action }` | `send_approval_action` |
| `runtime.submitEdit` | `{ requestId, text }` | `submit_approval_edit` |
| `runtime.setMode` | `{ mode }` | `set_runtime_mode` (`fast`\|`deep`\|`auto`) |
| `runtime.retry` | `{}` | `request_retry` |
| `runtime.refreshContext` | `{}` | `request_context_refresh` |
| `runtime.requestRepoTree` | `{}` | `request_repo_tree` |
| `runtime.selectRecovery` | `{ optionId }` | `select_recovery_option` |
| `runtime.undo` | `{}` | stub (dummy) |
| `runtime.status` | `{}` | last status snapshot |
| `credentials.list` | `{ profile? }` | CredentialManager status (never secret values) |
| `credentials.set` | `{ providerId, fields, kind?, profile? }` | store credentials via Credential Manager |
| `credentials.remove` | `{ providerId, profile? }` | delete stored credentials |
| `inference.catalog` | `{ profile? }` | Active model + **eligible** providers (creds configured; openai-compatible always) |
| `inference.listModels` | `{ providerId, baseUrl?, profile? }` | Models for one eligible provider (live + catalog) |
| `runtime.setModel` | `{ providerId, model, baseUrl?, profile? }` | Session inference selection (creds-gated) |

Successful command methods return `{ "ok": true }` (or status payload for `runtime.status` / `session.hello` / `credentials.list`).

### Credentials

Secrets travel only in `credentials.set` request params (stdio between TUI and runtime). Responses and `ui.event` must never echo secret field values. Persistence uses the OS keyring (or encrypted fallback), same as `neutrino-auth`.

### Model selection

`inference.catalog` / `inference.listModels` / `runtime.setModel` only offer providers that have credentials (plus local `openai-compatible`). Add keys via `credentials.*` or `/auth` first. `runtime.setModel` applies for the RPC session and emits `model.changed`.

## Notifications (runtime → client)

```json
{"jsonrpc":"2.0","method":"ui.event","params":{"type":"state.changed","payload":{...}}}
```

| `type` | Payload (summary) |
|--------|-------------------|
| `execution.started` | `{ task }` |
| `state.changed` | `{ from, to }` |
| `pipeline.progress` | `{ phase, status, step?, total? }` — dummy/smoke may use PLAN/EXECUTE/VERIFY; live agent uses soft phases under hard `AGENT` |
| `activity.delta` | `{ phaseId, text, newline? }` |
| `log.line` | `{ message, level }` |
| `diff.updated` | `{ path, oldText, newText }` |
| `repo.tree` | `{ rootLabel, paths }` |
| `status.snapshot` | `{ modeLabel, tokensUsed, fsmState, taskComplexity }` — `fsmState` may show soft phase (`DISCOVER`/…) while hard status is `AGENT` |
| `context.summary` | `{ files, edges, tokensUsed, tokenBudget }` |
| `approval.requested` | `{ requestId, summary, previewSnippet, fullFileText? }` |
| `recovery.requested` | `{ message, options: [{id,label}] }` |
| `tokens.updated` | `{ used, budget? }` |
| `execution.finished` | `{ ok, message }` |
| `tool.called` | `{ name, argsSummary, success }` |
| `agent.message` | `{ content, final }` |
| `reasoning.block` | `{ content, collapsedDefault }` |
| `phase.step_complete` | `{ phaseId, message }` |
| `explanation.available` | `{ bullets }` |
| `model.changed` | `{ model, providerId, type?, vendor?, baseUrl? }` |

## Running the server alone

```bash
python -m src.rpc
# then write NDJSON to stdin
```
