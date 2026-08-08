import { ChildProcessWithoutNullStreams, spawn } from "node:child_process";
import { createInterface } from "node:readline";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { sessionHelloResultSchema, uiEventSchema } from "./schemas.js";
import {
  PROTOCOL_VERSION,
  type CredentialsListResult,
  type InferenceCatalogResult,
  type InferenceListModelsResult,
  type JsonRpcInbound,
  type SessionHelloResult,
  type UiEventEnvelope,
} from "./types.js";

export type RpcClientHandlers = {
  onEvent: (event: UiEventEnvelope) => void;
  onError: (message: string) => void;
  onExit: (code: number | null) => void;
};

function findRepoRoot(): string {
  // tui/src/rpc -> tui/src -> tui -> repo root
  const here = path.dirname(fileURLToPath(import.meta.url));
  const candidate = path.resolve(here, "../../..");
  if (existsSync(path.join(candidate, "pyproject.toml"))) {
    return candidate;
  }
  return process.cwd();
}

function resolvePython(): string {
  if (process.env.NEUTRINO_PYTHON) {
    return process.env.NEUTRINO_PYTHON;
  }
  const root = findRepoRoot();
  const venvPython = path.join(root, ".venv", "bin", "python");
  if (existsSync(venvPython)) {
    return venvPython;
  }
  return process.platform === "win32" ? "python" : "python3";
}

export class JsonRpcClient {
  private child: ChildProcessWithoutNullStreams | null = null;
  private nextId = 1;
  private pending = new Map<
    number | string,
    { resolve: (v: unknown) => void; reject: (e: Error) => void }
  >();
  private bufferClosed = false;

  constructor(
    private readonly cwd: string,
    private readonly handlers: RpcClientHandlers,
  ) {}

  async start(): Promise<SessionHelloResult> {
    const python = resolvePython();
    const repoRoot = findRepoRoot();
    this.child = spawn(
      python,
      [
        "-m",
        "src.rpc",
        "--repo",
        this.cwd,
        ...(process.env.NEUTRINO_RPC_VERBOSE ? ["-v"] : []),
      ],
      {
      cwd: repoRoot,
      env: {
        ...process.env,
        PYTHONUNBUFFERED: "1",
        PYTHONPATH: [repoRoot, process.env.PYTHONPATH].filter(Boolean).join(path.delimiter),
      },
      stdio: ["pipe", "pipe", "pipe"],
    },
    );

    this.child.stderr.on("data", (chunk: Buffer) => {
      const text = chunk.toString("utf8").trim();
      if (text) {
        this.handlers.onError(text);
      }
    });

    this.child.on("exit", (code) => {
      this.bufferClosed = true;
      for (const [, p] of this.pending) {
        p.reject(new Error(`Runtime exited (code ${code})`));
      }
      this.pending.clear();
      this.handlers.onExit(code);
    });

    const rl = createInterface({ input: this.child.stdout });
    rl.on("line", (line) => this.onLine(line));

    return this.hello();
  }

  private onLine(line: string): void {
    const trimmed = line.trim();
    if (!trimmed) return;
    let msg: JsonRpcInbound;
    try {
      msg = JSON.parse(trimmed) as JsonRpcInbound;
    } catch {
      this.handlers.onError(`Invalid JSON from runtime: ${trimmed.slice(0, 120)}`);
      return;
    }

    if ("method" in msg && msg.method === "ui.event") {
      const parsed = uiEventSchema.safeParse(msg.params);
      if (parsed.success) {
        this.handlers.onEvent(parsed.data as UiEventEnvelope);
      }
      return;
    }

    if ("id" in msg && msg.id !== null && msg.id !== undefined) {
      const pending = this.pending.get(msg.id);
      if (!pending) return;
      this.pending.delete(msg.id);
      if ("error" in msg && msg.error) {
        pending.reject(new Error(msg.error.message));
      } else if ("result" in msg) {
        pending.resolve(msg.result);
      }
    }
  }

  private request(method: string, params: Record<string, unknown> = {}): Promise<unknown> {
    if (!this.child || this.bufferClosed) {
      return Promise.reject(new Error("Runtime not connected"));
    }
    const id = this.nextId++;
    const payload = JSON.stringify({
      jsonrpc: "2.0",
      id,
      method,
      params,
    });
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.child!.stdin.write(payload + "\n", (err) => {
        if (err) {
          this.pending.delete(id);
          reject(err);
        }
      });
    });
  }

  async hello(): Promise<SessionHelloResult> {
    const result = await this.request("session.hello", {
      protocolVersion: PROTOCOL_VERSION,
      cwd: this.cwd,
    });
    return sessionHelloResultSchema.parse(result);
  }

  execute(task: string): Promise<unknown> {
    return this.request("runtime.execute", { task });
  }

  cancel(): Promise<unknown> {
    return this.request("runtime.cancel", {});
  }

  approve(requestId: string, action: string): Promise<unknown> {
    return this.request("runtime.approve", { requestId, action });
  }

  submitEdit(requestId: string, text: string): Promise<unknown> {
    return this.request("runtime.submitEdit", { requestId, text });
  }

  setMode(mode: string): Promise<unknown> {
    return this.request("runtime.setMode", { mode });
  }

  retry(): Promise<unknown> {
    return this.request("runtime.retry", {});
  }

  refreshContext(): Promise<unknown> {
    return this.request("runtime.refreshContext", {});
  }

  requestRepoTree(): Promise<unknown> {
    return this.request("runtime.requestRepoTree", {});
  }

  selectRecovery(optionId: string): Promise<unknown> {
    return this.request("runtime.selectRecovery", { optionId });
  }

  undo(): Promise<unknown> {
    return this.request("runtime.undo", {});
  }

  status(): Promise<unknown> {
    return this.request("runtime.status", {});
  }

  async credentialsList(profile = "default"): Promise<CredentialsListResult> {
    const result = (await this.request("credentials.list", { profile })) as CredentialsListResult;
    return {
      profile: String(result.profile ?? profile),
      providers: Array.isArray(result.providers)
        ? result.providers.map((p) => ({
            providerId: String(p.providerId ?? ""),
            configured: Boolean(p.configured),
            source: p.source == null ? null : String(p.source),
            kind: p.kind == null ? null : String(p.kind),
          }))
        : [],
    };
  }

  credentialsSet(
    providerId: string,
    fields: Record<string, string>,
    opts?: { kind?: string; profile?: string },
  ): Promise<unknown> {
    return this.request("credentials.set", {
      providerId,
      fields,
      kind: opts?.kind,
      profile: opts?.profile ?? "default",
    });
  }

  credentialsRemove(providerId: string, profile = "default"): Promise<unknown> {
    return this.request("credentials.remove", { providerId, profile });
  }

  async inferenceCatalog(profile = "default"): Promise<InferenceCatalogResult> {
    const result = (await this.request("inference.catalog", {
      profile,
    })) as InferenceCatalogResult;
    const active = result.active ?? {
      providerId: "openai-compatible",
      model: "llama3.2",
      type: "openai-compatible",
      vendor: null,
      baseUrl: null,
    };
    return {
      profile: String(result.profile ?? profile),
      active: {
        providerId: String(active.providerId ?? ""),
        model: String(active.model ?? ""),
        type: String(active.type ?? ""),
        vendor: active.vendor == null ? null : String(active.vendor),
        baseUrl: active.baseUrl == null ? null : String(active.baseUrl),
      },
      providers: Array.isArray(result.providers)
        ? result.providers.map((p) => ({
            providerId: String(p.providerId ?? ""),
            configured: Boolean(p.configured),
            source: p.source == null ? null : String(p.source),
            kind: p.kind == null ? null : String(p.kind),
            type: String(p.type ?? ""),
            vendor: p.vendor == null ? null : String(p.vendor),
          }))
        : [],
    };
  }

  async inferenceListModels(
    providerId: string,
    opts?: { baseUrl?: string; profile?: string },
  ): Promise<InferenceListModelsResult> {
    const result = (await this.request("inference.listModels", {
      providerId,
      baseUrl: opts?.baseUrl,
      profile: opts?.profile ?? "default",
    })) as InferenceListModelsResult;
    return {
      providerId: String(result.providerId ?? providerId),
      models: Array.isArray(result.models)
        ? result.models.map((m) => ({
            id: String(m.id ?? ""),
            ownedBy: m.ownedBy == null ? null : String(m.ownedBy),
          }))
        : [],
      source: String(result.source ?? "catalog"),
      warning: result.warning == null ? null : String(result.warning),
    };
  }

  setModel(
    providerId: string,
    model: string,
    opts?: { baseUrl?: string; profile?: string },
  ): Promise<unknown> {
    return this.request("runtime.setModel", {
      providerId,
      model,
      baseUrl: opts?.baseUrl,
      profile: opts?.profile ?? "default",
    });
  }

  stop(): void {
    if (this.child && !this.child.killed) {
      this.child.kill("SIGTERM");
    }
  }
}
