# Credential Manager — secrets for Inference (and later RNA/web)

Stores and resolves provider secrets. Inference never reads keyring or credential files itself — it calls `CredentialManager.resolve(...)`.

**Priority (highest first):** CLI override → environment variables → OS keyring → encrypted file fallback → error (or `kind=none` for local openai-compatible / Bedrock `aws_profile`).

Never store secrets in TOML. `list` never prints secret values.

---

## Install

```bash
pip install -e .
# pulls keyring + cryptography
```

CLI entry:

```bash
neutrino-auth list
neutrino-auth set openai --profile work
neutrino-auth remove openai --profile work
# or: python -m src.credentials list
```

---

## Quick start

```python
from src.credentials import CredentialManager, CredentialRecord, MemoryStore

mgr = CredentialManager(store=MemoryStore())
mgr.set("openai", CredentialRecord(kind="api_key", fields={"api_key": "sk-..."}))

resolved = mgr.resolve("openai", profile="default")
assert resolved.fields["api_key"]  # use immediately; do not log
```

Env-only (no store write):

```bash
export OPENAI_API_KEY=sk-...
```

```python
mgr = CredentialManager(store=MemoryStore())
print(mgr.resolve("openai").source)  # "env"
```

---

## Credential kinds

| Kind | Fields | Used by |
|------|--------|---------|
| `api_key` | `api_key` | OpenAI, Anthropic, Groq, OpenRouter, Gemini |
| `bearer` | `token` | Generic OpenAI-compatible |
| `azure` | `api_key` (optional `aad_token`) | Azure OpenAI |
| `aws` | `access_key_id`, `secret_access_key`, `session_token?` | Bedrock without aws_profile |
| `none` | — | Local Ollama / AWS profile chain |

Storage key: service `"neutrino"`, username `"{profile}:{provider_id}"` (e.g. `default:openai`).

---

## Env map

| Provider id | Env vars |
|-------------|----------|
| `openai` | `OPENAI_API_KEY` |
| `anthropic` | `ANTHROPIC_API_KEY` |
| `azure_openai` | `AZURE_OPENAI_API_KEY` (+ endpoint may be config) |
| `bedrock` | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN` |
| `google_genai` | `GOOGLE_API_KEY` / `GEMINI_API_KEY` |
| `groq` | `GROQ_API_KEY` |
| `openrouter` | `OPENROUTER_API_KEY` |
| `openai-compatible` | `NEUTRINO_INFERENCE_API_KEY` (optional) |

Non-secret hints (region, endpoint, org) prefer config; env may supplement via `resolve` hints.

---

## Stores

1. **KeyringStore** — OS keyring (JSON blob for multi-field kinds).
2. **EncryptedFileStore** — `~/.config/neutrino/credentials.enc` when keyring unavailable.
3. **MemoryStore** — tests / ephemeral.

`default_store()` picks keyring then encrypted fallback.

---

## Public API

```python
class CredentialManager:
    def get(self, provider_id: str, *, profile: str = "default") -> CredentialRecord: ...
    def set(self, provider_id: str, record: CredentialRecord, *, profile: str = "default") -> None: ...
    def delete(self, provider_id: str, *, profile: str = "default") -> None: ...
    def list_status(self, *, profile: str = "default") -> list[ProviderAuthStatus]: ...
    def resolve(self, provider_id: str, *, profile: str, config_hints: dict) -> ResolvedCredentials: ...
```

`resolve` merges config hints (Azure endpoint, Bedrock region / aws_profile) with secrets from the priority chain.
