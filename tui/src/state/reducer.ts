import type { LogLevel, UiEventEnvelope } from "../rpc/types.js";

export type PhaseName = "PLAN" | "CONTEXT" | "EXECUTE" | "VERIFY" | "REVIEW";
export type PhaseStatus = "idle" | "running" | "completed" | "failed";

export interface PipelinePhase {
  name: PhaseName;
  status: PhaseStatus;
}

export type TranscriptTone = "dim" | "info" | "success" | "warn" | "error" | "user" | "diffAdd" | "diffDel";

export type TranscriptItem =
  | { id: number; kind: "user"; text: string }
  | { id: number; kind: "line"; text: string; tone: TranscriptTone; prefix?: string }
  | { id: number; kind: "diff"; path: string; lines: { text: string; tone: TranscriptTone }[] }
  | { id: number; kind: "blank" };

export interface DiffFile {
  path: string;
  oldText: string;
  newText: string;
}

export interface ApprovalState {
  requestId: string;
  summary: string;
  previewSnippet: string;
}

export interface RecoveryState {
  message: string;
  options: { id: string; label: string }[];
}

export interface RuntimeViewState {
  connected: boolean;
  fatalError: string | null;
  projectName: string;
  model: string;
  branch: string;
  tokensUsed: number;
  tokenBudget: number | null;
  modeLabel: string;
  fsmState: string;
  taskComplexity: string;
  currentTask: string;
  pipeline: PipelinePhase[];
  pipelineStep: number;
  pipelineTotal: number;
  transcript: TranscriptItem[];
  diffs: DiffFile[];
  activeDiffPath: string | null;
  contextFiles: { path: string; lineCount: number }[];
  approval: ApprovalState | null;
  recovery: RecoveryState | null;
  running: boolean;
  recentEventTypes: string[];
  helpText: string | null;
  overlay: "none" | "palette" | "inspector" | "credentials" | "model";
}

export type RuntimeAction =
  | { type: "connected"; projectName: string; model: string; branch: string }
  | { type: "fatal"; message: string }
  | { type: "ui_event"; event: UiEventEnvelope }
  | { type: "set_overlay"; overlay: RuntimeViewState["overlay"] }
  | { type: "set_help"; text: string | null }
  | { type: "set_model"; model: string }
  | { type: "clear_approval" }
  | { type: "clear_recovery" };

const PHASES: PhaseName[] = ["PLAN", "CONTEXT", "EXECUTE", "VERIFY", "REVIEW"];

let seq = 0;
function nextId(): number {
  seq += 1;
  return seq;
}

function line(text: string, tone: TranscriptTone = "info", prefix?: string): TranscriptItem {
  return { id: nextId(), kind: "line", text, tone, prefix };
}

function push(transcript: TranscriptItem[], ...items: TranscriptItem[]): TranscriptItem[] {
  return [...transcript, ...items].slice(-400);
}

export function initialState(): RuntimeViewState {
  return {
    connected: false,
    fatalError: null,
    projectName: "Neutrino",
    model: "—",
    branch: "—",
    tokensUsed: 0,
    tokenBudget: null,
    modeLabel: "—",
    fsmState: "INIT",
    taskComplexity: "—",
    currentTask: "",
    pipeline: PHASES.map((name) => ({ name, status: "idle" })),
    pipelineStep: 0,
    pipelineTotal: PHASES.length,
    transcript: [],
    diffs: [],
    activeDiffPath: null,
    contextFiles: [],
    approval: null,
    recovery: null,
    running: false,
    recentEventTypes: [],
    helpText: null,
    overlay: "none",
  };
}

function markPipeline(
  pipeline: PipelinePhase[],
  phase: string,
  status: PhaseStatus,
): PipelinePhase[] {
  const upper = phase.toUpperCase() as PhaseName;
  return pipeline.map((p) => {
    if (p.name === upper) {
      return { ...p, status };
    }
    if (
      status === "running" &&
      PHASES.indexOf(p.name) < PHASES.indexOf(upper) &&
      p.status === "running"
    ) {
      return { ...p, status: "completed" };
    }
    return p;
  });
}

function completePrior(pipeline: PipelinePhase[], phase: string): PipelinePhase[] {
  const upper = phase.toUpperCase() as PhaseName;
  const idx = PHASES.indexOf(upper);
  return pipeline.map((p) => {
    const i = PHASES.indexOf(p.name);
    if (i >= 0 && i < idx && p.status !== "failed") {
      return { ...p, status: "completed" };
    }
    return p;
  });
}

function unifiedDiffLines(
  oldText: string,
  newText: string,
): { text: string; tone: TranscriptTone }[] {
  const out: { text: string; tone: TranscriptTone }[] = [];
  for (const l of oldText.split("\n")) {
    if (l.length) out.push({ text: `- ${l}`, tone: "diffDel" });
  }
  for (const l of newText.split("\n")) {
    if (l.length) out.push({ text: `+ ${l}`, tone: "diffAdd" });
  }
  return out.slice(0, 16);
}

export function runtimeReducer(state: RuntimeViewState, action: RuntimeAction): RuntimeViewState {
  switch (action.type) {
    case "connected":
      return {
        ...state,
        connected: true,
        projectName: action.projectName,
        model: action.model,
        branch: action.branch,
        fatalError: null,
      };
    case "fatal":
      return { ...state, fatalError: action.message, connected: false, running: false };
    case "set_overlay":
      return { ...state, overlay: action.overlay };
    case "set_help":
      return { ...state, helpText: action.text };
    case "set_model":
      return { ...state, model: action.model };
    case "clear_approval":
      return { ...state, approval: null };
    case "clear_recovery":
      return { ...state, recovery: null };
    case "ui_event":
      return applyUiEvent(state, action.event);
    default:
      return state;
  }
}

function applyUiEvent(state: RuntimeViewState, event: UiEventEnvelope): RuntimeViewState {
  const payload = event.payload;
  const recentEventTypes = [...state.recentEventTypes, event.type].slice(-40);

  switch (event.type) {
    case "execution.started": {
      const task = String(payload.task ?? "");
      return {
        ...state,
        currentTask: task,
        running: true,
        diffs: [],
        activeDiffPath: null,
        approval: null,
        recovery: null,
        pipeline: PHASES.map((name) => ({ name, status: "idle" as PhaseStatus })),
        pipelineStep: 0,
        transcript: push(
          state.transcript,
          { id: nextId(), kind: "blank" },
          { id: nextId(), kind: "user", text: task },
        ),
        recentEventTypes,
        helpText: null,
      };
    }
    case "state.changed": {
      const to = String(payload.to ?? state.fsmState);
      return { ...state, fsmState: to, recentEventTypes };
    }
    case "pipeline.progress": {
      const phase = String(payload.phase ?? "");
      let pipeline = completePrior(state.pipeline, phase);
      pipeline = markPipeline(pipeline, phase, "running");
      return {
        ...state,
        pipeline,
        pipelineStep: Number(payload.step ?? state.pipelineStep),
        pipelineTotal: Number(payload.total ?? state.pipelineTotal),
        transcript: push(state.transcript, line(phase, "dim", "●")),
        recentEventTypes,
      };
    }
    case "phase.step_complete": {
      const phaseId = String(payload.phaseId ?? "");
      const pipeline = markPipeline(state.pipeline, phaseId, "completed");
      const msg = String(payload.message ?? "done");
      return {
        ...state,
        pipeline,
        transcript: push(state.transcript, line(`${phaseId.toLowerCase()} ${msg}`, "success", "✓")),
        recentEventTypes,
      };
    }
    case "activity.delta": {
      const text = String(payload.text ?? "");
      return {
        ...state,
        transcript: push(state.transcript, line(text, "dim", "·")),
        recentEventTypes,
      };
    }
    case "log.line": {
      const level = (String(payload.level ?? "info") as LogLevel) || "info";
      const tone: TranscriptTone =
        level === "error" ? "error" : level === "warning" ? "warn" : "success";
      const prefix = level === "error" ? "✗" : level === "warning" ? "!" : "✓";
      // Skip noisy internal recovery/approval chatter in the main stream
      const message = String(payload.message ?? "");
      if (
        message.startsWith("Recovery option") ||
        message.startsWith("Approval action") ||
        message.startsWith("Approval ") ||
        message.startsWith("Model set to ")
      ) {
        return { ...state, recentEventTypes };
      }
      return {
        ...state,
        transcript: push(state.transcript, line(message, tone, prefix)),
        recentEventTypes,
      };
    }
    case "diff.updated": {
      const path = String(payload.path ?? "");
      const oldText = String(payload.oldText ?? "");
      const newText = String(payload.newText ?? "");
      const entry: DiffFile = { path, oldText, newText };
      const others = state.diffs.filter((d) => d.path !== path);
      return {
        ...state,
        diffs: [...others, entry],
        activeDiffPath: path,
        transcript: push(state.transcript, {
          id: nextId(),
          kind: "diff",
          path,
          lines: unifiedDiffLines(oldText, newText),
        }),
        recentEventTypes,
      };
    }
    case "repo.tree":
      return { ...state, recentEventTypes };
    case "status.snapshot": {
      return {
        ...state,
        modeLabel: String(payload.modeLabel ?? state.modeLabel),
        tokensUsed: Number(payload.tokensUsed ?? state.tokensUsed),
        fsmState: String(payload.fsmState ?? state.fsmState),
        taskComplexity: String(payload.taskComplexity ?? state.taskComplexity),
        recentEventTypes,
      };
    }
    case "tokens.updated": {
      return {
        ...state,
        tokensUsed: Number(payload.used ?? state.tokensUsed),
        tokenBudget:
          payload.budget === null || payload.budget === undefined
            ? state.tokenBudget
            : Number(payload.budget),
        recentEventTypes,
      };
    }
    case "context.summary": {
      const files = Array.isArray(payload.files)
        ? payload.files.map((f) => {
            const row = f as Record<string, unknown>;
            return { path: String(row.path ?? ""), lineCount: Number(row.lineCount ?? 0) };
          })
        : [];
      return { ...state, contextFiles: files, recentEventTypes };
    }
    case "approval.requested": {
      return {
        ...state,
        approval: {
          requestId: String(payload.requestId ?? ""),
          summary: String(payload.summary ?? ""),
          previewSnippet: String(payload.previewSnippet ?? ""),
        },
        transcript: push(
          state.transcript,
          line(String(payload.summary ?? "Approval needed"), "warn", "?"),
        ),
        recentEventTypes,
      };
    }
    case "recovery.requested": {
      const options = Array.isArray(payload.options)
        ? payload.options.map((o) => {
            const row = o as Record<string, unknown>;
            return { id: String(row.id ?? ""), label: String(row.label ?? "") };
          })
        : [];
      return {
        ...state,
        recovery: { message: String(payload.message ?? ""), options },
        recentEventTypes,
      };
    }
    case "execution.finished": {
      const ok = Boolean(payload.ok);
      const message = String(payload.message ?? (ok ? "Done" : "Failed"));
      const pipeline = state.pipeline.map((p) =>
        p.status === "running" ? { ...p, status: (ok ? "completed" : "failed") as PhaseStatus } : p,
      );
      return {
        ...state,
        running: false,
        pipeline,
        transcript: push(
          state.transcript,
          line(message, ok ? "success" : "error", ok ? "✓" : "✗"),
        ),
        recentEventTypes,
      };
    }
    case "tool.called": {
      const name = String(payload.name ?? "tool");
      const args = String(payload.argsSummary ?? "");
      return {
        ...state,
        transcript: push(state.transcript, line(`${name} ${args}`.trim(), "dim", "⚙")),
        recentEventTypes,
      };
    }
    case "agent.message": {
      return {
        ...state,
        transcript: push(state.transcript, line(String(payload.content ?? ""), "info")),
        recentEventTypes,
      };
    }
    case "reasoning.block": {
      return {
        ...state,
        transcript: push(state.transcript, line(String(payload.content ?? ""), "dim", "…")),
        recentEventTypes,
      };
    }
    case "explanation.available": {
      const bullets = Array.isArray(payload.bullets) ? payload.bullets.map(String) : [];
      return {
        ...state,
        transcript: push(
          state.transcript,
          ...bullets.map((b) => line(b, "dim", "•")),
        ),
        recentEventTypes,
      };
    }
    case "plan.tasks_updated": {
      const items = Array.isArray(payload.tasks)
        ? payload.tasks.map((t) => {
            const row = t as Record<string, unknown>;
            return {
              id: String(row.id ?? ""),
              content: String(row.content ?? ""),
              status: String(row.status ?? "pending"),
            };
          })
        : [];
      const rows = items.map((t) => {
        const box =
          t.status === "completed" ? "[x]" : t.status === "in_progress" ? "[~]" : t.status === "cancelled" ? "[-]" : "[ ]";
        const tone: TranscriptTone = t.status === "completed" ? "dim" : "info";
        return line(`${box} ${t.content}`, tone);
      });
      return {
        ...state,
        transcript: push(state.transcript, line("Todos", "dim", "≡"), ...rows),
        recentEventTypes,
      };
    }
    case "model.changed": {
      const model = String(payload.model ?? state.model);
      const providerId = String(payload.providerId ?? "");
      const label = providerId ? `${providerId}/${model}` : model;
      return {
        ...state,
        model,
        transcript: push(state.transcript, line(`model ${label}`, "success", "✓")),
        recentEventTypes,
      };
    }
    default:
      return { ...state, recentEventTypes };
  }
}

export function formatTokens(used: number, budget: number | null): string {
  const fmt = (n: number) => (n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n));
  if (budget == null) return `${fmt(used)} tokens`;
  return `${fmt(used)} tokens`;
}

export function pipelineSummary(pipeline: PipelinePhase[]): string {
  return pipeline
    .map((p) => {
      if (p.status === "completed") return p.name[0];
      if (p.status === "running") return p.name[0]?.toLowerCase();
      return "·";
    })
    .join("");
}
