import { describe, expect, it } from "vitest";

import {
  formatTokens,
  initialState,
  runtimeReducer,
  type RuntimeViewState,
} from "./reducer.js";
import type { UiEventEnvelope } from "../rpc/types.js";

function apply(state: RuntimeViewState, event: UiEventEnvelope): RuntimeViewState {
  return runtimeReducer(state, { type: "ui_event", event });
}

describe("runtimeReducer", () => {
  it("starts disconnected with empty transcript", () => {
    const s = initialState();
    expect(s.connected).toBe(false);
    expect(s.transcript).toHaveLength(0);
    expect(s.pipeline).toHaveLength(5);
  });

  it("handles connected", () => {
    const s = runtimeReducer(initialState(), {
      type: "connected",
      projectName: "Demo",
      model: "dummy",
      branch: "main",
    });
    expect(s.connected).toBe(true);
    expect(s.projectName).toBe("Demo");
  });

  it("opens credentials overlay", () => {
    const s = runtimeReducer(initialState(), {
      type: "set_overlay",
      overlay: "credentials",
    });
    expect(s.overlay).toBe("credentials");
  });

  it("applies model.changed", () => {
    let s = initialState();
    s = apply(s, {
      type: "model.changed",
      payload: { model: "gpt-4o", providerId: "openai" },
    });
    expect(s.model).toBe("gpt-4o");
    expect(s.transcript.some((t) => t.kind === "line" && t.text.includes("gpt-4o"))).toBe(
      true,
    );
  });

  it("streams execution into a chat-like transcript", () => {
    let s = initialState();
    s = apply(s, { type: "execution.started", payload: { task: "OAuth" } });
    expect(s.currentTask).toBe("OAuth");
    expect(s.running).toBe(true);
    expect(s.transcript.some((t) => t.kind === "user")).toBe(true);

    s = apply(s, {
      type: "pipeline.progress",
      payload: { phase: "PLAN", status: "running", step: 1, total: 5 },
    });
    expect(s.pipeline.find((p) => p.name === "PLAN")?.status).toBe("running");

    s = apply(s, {
      type: "activity.delta",
      payload: { phaseId: "PLAN", text: "thinking", newline: true },
    });
    expect(s.transcript.some((t) => t.kind === "line")).toBe(true);

    s = apply(s, {
      type: "diff.updated",
      payload: { path: "a.py", oldText: "x", newText: "y" },
    });
    expect(s.transcript.some((t) => t.kind === "diff")).toBe(true);

    s = apply(s, {
      type: "execution.finished",
      payload: { ok: true, message: "done" },
    });
    expect(s.running).toBe(false);
  });

  it("renders plan.tasks_updated as a checklist", () => {
    let s = initialState();
    s = apply(s, {
      type: "plan.tasks_updated",
      payload: {
        tasks: [
          { id: "1", content: "Add endpoint", status: "completed" },
          { id: "2", content: "Write tests", status: "in_progress" },
        ],
      },
    });
    const lines = s.transcript.filter((t) => t.kind === "line").map((t) => t.text);
    expect(lines.some((t) => t.includes("[x] Add endpoint"))).toBe(true);
    expect(lines.some((t) => t.includes("[~] Write tests"))).toBe(true);
  });

  it("formatTokens", () => {
    expect(formatTokens(8200, 32000)).toBe("8.2k tokens");
  });
});
