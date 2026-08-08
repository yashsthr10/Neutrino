import React from "react";
import { Box, Text } from "ink";

import { useRuntime } from "../state/RuntimeContext.js";
import { formatTokens } from "../state/reducer.js";
import { colors } from "../theme/colors.js";

/** Read-only runtime dump — progressive disclosure, not always on screen. */
export function RuntimeInspector() {
  const { state } = useRuntime();
  const tokens = formatTokens(state.tokensUsed, state.tokenBudget);
  const pipe = state.pipeline
    .map((p) => {
      const mark =
        p.status === "completed" ? "✓" : p.status === "running" ? "▶" : "○";
      return `${mark}${p.name}`;
    })
    .join(" ");

  return (
    <Box flexDirection="column">
      <Text color={colors.muted}>── runtime ─────────────────────────────</Text>
      <Text>
        state <Text color={colors.running}>{state.fsmState}</Text>
        {"  "}
        step {state.pipelineStep}/{state.pipelineTotal}
        {"  "}
        {tokens}
      </Text>
      <Text color={colors.muted}>{pipe}</Text>
      {state.currentTask ? <Text>task {state.currentTask}</Text> : null}
      {state.contextFiles.length > 0 ? (
        <Text color={colors.muted}>
          context {state.contextFiles.map((f) => f.path).join(", ")}
        </Text>
      ) : null}
      <Text color={colors.muted}>
        events {state.recentEventTypes.slice(-8).join(" · ") || "—"}
      </Text>
      <Text color={colors.muted}>esc close</Text>
    </Box>
  );
}
