# Inference Subsystem — provider-agnostic chat for Neutrino

Runtime code talks only to **Inference Manager** via **Inference Port**. Providers (OpenAI-compatible HTTP, LangChain natives) stay behind the factory. Secrets come from Credential Manager — never from TOML or Inference internals.

```text
Execution Runtime
       │
       ▼
InferenceManager  →  InferencePort
       │
       ├─ ProviderFactory
       │     ├─ OpenAICompatibleProvider  (httpx)
       │     └─ LangChainProvider         (optional extras)
       │
       └─ CredentialManager.get / resolve
```

Test doubles live in `tests/doubles/inference.py` — not shipped in production.

- **Library:** `from src.inference import build_inference, InferenceManager, InferencePort`
- **Context bridge:** `InferenceChatModelAdapter` implements Context `ChatModelPort.complete`
- Design notes: [`docs/`](docs/)

---

## Install

```bash
pip install -e .

# optional native vendors
pip install -e '.[inference-openai]'
pip install -e '.[inference-anthropic]'
pip install -e '.[inference-azure]'
pip install -e '.[inference-bedrock]'
pip install -e '.[inference-google]'
pip install -e '.[inference-groq]'
# or
pip install -e '.[inference-all]'
```

Core OpenAI-compatible needs no LangChain extras.

---

## Quick start

```python
from src.config.schema import InferenceProviderConfig
from src.credentials import CredentialManager, MemoryStore
from src.inference import InferenceRequest, Message, build_inference

mgr = build_inference(
    InferenceProviderConfig(
        type="openai-compatible",
        model="llama3.2",
        base_url="http://127.0.0.1:11434/v1",
    ),
    CredentialManager(store=MemoryStore()),
    start=True,
)

resp = mgr.chat(
    InferenceRequest(messages=(Message(role="user", content="Hello"),))
)
print(resp.content)
print(resp.usage.input_tokens, resp.usage.output_tokens)
mgr.close()
```

Tests:

```python
from src.inference import build_inference
from tests.doubles import FakeInferenceProvider

mgr = build_inference(
    InferenceProviderConfig(),
    CredentialManager(store=MemoryStore()),
    provider=FakeInferenceProvider(response_text="pong"),
)
```

Context summarizer bridge:

```python
from src.inference import InferenceChatModelAdapter, build_inference

mgr = build_inference(settings, credentials)
chat_model = InferenceChatModelAdapter(mgr)
# pass chat_model into build_context_subsystem(...), or use:
# build_context_subsystem_with_inference(rna, session_id, settings)
```

---

## Port surface

| Method | Role |
|--------|------|
| `health()` | Provider reachability / auth probe |
| `list_models()` | Available model ids when supported |
| `chat(request)` | One-shot completion |
| `stream(request)` | Iterator of stream events |
| `supports_tools()` / `supports_structured_output()` | Capability flags |
| `close()` | Release HTTP / SDK resources |

---

## Request / response shape

**Request:** messages (`role` / `content` / `tool_call_id` / …), optional tools, tool_choice, temperature, max_tokens, model override, metadata.

**Response:** `content`, `tool_calls` (`id`, `name`, `arguments` JSON string), `usage` (`input_tokens`, `output_tokens`), `finish_reason`, `metadata`.

**Stream events:** `delta_text`, `tool_call_delta`, `usage`, `done`, `error`.

---

## Provider matrix (Phase A)

| Config | Backend | Credentials |
|--------|---------|-------------|
| `type=openai-compatible` | httpx → `/v1/chat/completions` | optional bearer / `NEUTRINO_INFERENCE_API_KEY` |
| `type=native`, `vendor=openai` | LangChain ChatOpenAI | `api_key` / `OPENAI_API_KEY` |
| `vendor=anthropic` | LangChain ChatAnthropic | `ANTHROPIC_API_KEY` |
| `vendor=azure_openai` | AzureChatOpenAI | Azure key + config `azure_endpoint`, `api_version`, `deployment` |
| `vendor=bedrock` | ChatBedrockConverse | `region` + AWS keys **or** `aws_profile` |
| `vendor=google_genai` | ChatGoogleGenerativeAI | `GOOGLE_API_KEY` / `GEMINI_API_KEY` |
| `vendor=groq` | ChatGroq | `GROQ_API_KEY` |
| `vendor=openrouter` | OpenAI-compatible HTTP (SSE streaming) | `OPENROUTER_API_KEY` |

Test doubles: `tests/doubles/inference.py` (`FakeInferenceProvider`, etc.) — not a production provider.

### Azure

Non-secrets in config: `azure_endpoint` (or `base_url`), `api_version`, `deployment` (or `model`). Secrets: Credential kind `azure`. Do not treat Azure as plain openai-compatible unless you intentionally point at a gateway.

### Bedrock

Non-secrets: `region`, `model` (Bedrock model id), optional `aws_profile`. Missing `region` fails validation before network.

---

## Config

See `InferenceProviderConfig` / `ProfileConfig` in [`src/config/schema.py`](../config/schema.py). Legacy `model.provider=ollama` maps to openai-compatible `…/v1`. Never put API keys in TOML.

---

## Errors

| Exception | When |
|-----------|------|
| `InferenceConfigError` | Missing Azure/Bedrock fields, bad config |
| `AuthenticationError` | 401/403 / bad key |
| `ModelNotFound` | Unknown model |
| `RateLimitExceeded` | HTTP 429 (manager may retry) |
| `UnsupportedCapability` | Missing optional SDK / unknown vendor |
| `InferenceConnectionError` | Transport / health failure |

---

## Observability

Logger name `"inference"`. Events: started/completed/failed, tokens, latency, health — same JSON style as RNA / Tool Engine. Secrets are never logged.
