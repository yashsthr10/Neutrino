"""Centralized tunable constants for the Neutrino runtime.

Import from here instead of scattering magic numbers across packages.

Notes
-----
* This lives under ``src/config/constants.py`` (not ``src/config.py``) because
  ``src/config/`` is already a Python package for settings load/schema.
* User-overridable settings still live in ``src.config.schema`` (TOML / env);
  those Field defaults should reference the values defined here.
* Keep this module free of imports from other ``src.*`` packages to avoid cycles.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Protocol (RPC handshake)
# ---------------------------------------------------------------------------

PROTOCOL_VERSION = "1.0.0"
PROTOCOL_MAJOR = 1

RPC_CAPABILITIES = (
    "execute",
    "cancel",
    "approve",
    "status",
    "undo",
    "retry",
    "refreshContext",
    "requestRepoTree",
    "selectRecovery",
    "setMode",
    "submitEdit",
    "credentials.list",
    "credentials.set",
    "credentials.remove",
    "inference.catalog",
    "inference.listModels",
    "runtime.setModel",
)

# ---------------------------------------------------------------------------
# Agent / session history (multi-turn memory)
# ---------------------------------------------------------------------------

# Dual caps: prune oldest messages first when either limit is hit.
SESSION_HISTORY_MAX_MESSAGES = 15
SESSION_HISTORY_MAX_TOKENS = 128_000

# ---------------------------------------------------------------------------
# Agent policy / completion defaults (mirrored by CliRules)
# ---------------------------------------------------------------------------

DEFAULT_MAX_ITERATIONS = 25
DEFAULT_TOKEN_BUDGET = 100_000
DEFAULT_MAX_VERIFY_CYCLES = 2
DEFAULT_INFERENCE_TEMPERATURE = 0.2
DEFAULT_INFERENCE_TIMEOUT_S = 60.0

# ---------------------------------------------------------------------------
# Inference endpoints & timeouts
# ---------------------------------------------------------------------------

OPENROUTER_DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
OLLAMA_DEFAULT_HOST = "http://127.0.0.1:11434"
OLLAMA_DEFAULT_BASE_URL = "http://127.0.0.1:11434/v1"
# Local CPU inference with a full tool catalog can exceed 60s before first token.
OLLAMA_DEFAULT_TIMEOUT_S = 600.0
# OpenRouter streaming: chunks can pause while upstream models think.
OPENROUTER_DEFAULT_TIMEOUT_S = 180.0

LOCAL_INFERENCE_HOST_MARKERS = (
    "127.0.0.1",
    "localhost",
    "0.0.0.0",
    ":11434",
    "/ollama",
)

OPENROUTER_HTTP_REFERER = "https://github.com/neutrino-cli/neutrino"
OPENROUTER_X_TITLE = "Neutrino"

# Providers that may appear without a stored secret (local / AWS profile chain).
ALWAYS_ELIGIBLE_PROVIDERS = frozenset({"ollama", "openai-compatible"})

# ---------------------------------------------------------------------------
# Credential / provider catalog
# ---------------------------------------------------------------------------

KNOWN_PROVIDERS = (
    "openai",
    "anthropic",
    "azure_openai",
    "bedrock",
    "google_genai",
    "groq",
    "openrouter",
    "ollama",
    "openai-compatible",
)

CREDENTIAL_SERVICE_NAME = "neutrino"

# Shown when live list_models is unavailable (native SDKs / offline).
CATALOG_MODELS: dict[str, tuple[str, ...]] = {
    "openai": ("gpt-4o", "gpt-4o-mini", "o1", "o3-mini", "o4-mini"),
    "anthropic": (
        "claude-sonnet-4-20250514",
        "claude-opus-4-20250514",
        "claude-haiku-4-5-20251001",
    ),
    "azure_openai": ("gpt-4o", "gpt-4o-mini", "gpt-4.1"),
    "bedrock": (
        "anthropic.claude-sonnet-4-20250514-v1:0",
        "anthropic.claude-3-5-sonnet-20241022-v2:0",
    ),
    "google_genai": (
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-flash-latest",
        "gemini-pro-latest",
        "gemini-2.5-flash-lite",
        "gemini-2.5-pro",
    ),
    "groq": (
        "qwen/qwen3.6-27b",
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "openai/gpt-oss-20b",
        "meta-llama/llama-4-scout-17b-16e-instruct",
        "mixtral-8x7b-32768",
    ),
    "openrouter": (
        "deepseek/deepseek-v4-flash",
        "deepseek/deepseek-v4-flash-0731",
        "~deepseek/deepseek-v4-flash-latest",
        "deepseek/deepseek-v4-pro",
        "openai/gpt-4o",
        "anthropic/claude-sonnet-4",
        "google/gemini-2.5-flash",
    ),
    "ollama": ("llama3.2", "qwen2.5-coder", "codellama", "mistral", "gemma2"),
    "openai-compatible": ("llama3.2", "qwen2.5-coder", "codellama", "mistral"),
}

# Human labels for curated catalog ids (model picker).
CATALOG_MODEL_LABELS: dict[str, str] = {
    "deepseek/deepseek-v4-flash": "DeepSeek V4 Flash 0423",
    "deepseek/deepseek-v4-flash-0731": "DeepSeek V4 Flash 0731",
    "~deepseek/deepseek-v4-flash-latest": "DeepSeek V4 Flash Latest",
    "deepseek/deepseek-v4-pro": "DeepSeek V4 Pro 0423",
}

# ---------------------------------------------------------------------------
# Tool engine validation & serialization
# ---------------------------------------------------------------------------

TOOL_MAX_STRING_LEN = 16_384
TOOL_MAX_LIST_LEN = 256
EXECUTOR_APPLY_PATCH_MAX_LENGTH = 512_000

TOOL_MAX_RESULT_BYTES = 48_000
TOOL_MAX_FILE_CHARS = 4_000
TOOL_MAX_REPO_ITEMS = 20
TOOL_MAX_SERIALIZED_MESSAGES = 12

# ---------------------------------------------------------------------------
# Shell / execution
# ---------------------------------------------------------------------------

SHELL_MAX_OUTPUT_CHARS = 32_000
