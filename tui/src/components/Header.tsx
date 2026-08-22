import React from "react";
import { Box, Text } from "ink";

import { useRuntime } from "../state/RuntimeContext.js";
import { formatModelLabel, formatTokens } from "../state/reducer.js";
import { colors } from "../theme/colors.js";

/** Single quiet status line — no chrome. */
export function Header() {
  const { state } = useRuntime();
  const tokens = formatTokens(state.tokensUsed, state.tokenBudget);
  const phase = state.running ? state.fsmState : state.connected ? "ready" : "…";
  const modelLabel = formatModelLabel(state);

  return (
    <Box paddingX={1} marginBottom={1}>
      <Text color={colors.muted}>
        <Text bold color={colors.accent}>
          neutrino
        </Text>
        {"  "}
        {modelLabel}
        {" · "}
        {state.branch}
        {" · "}
        {tokens}
        {" · "}
        <Text color={state.running ? colors.running : colors.muted}>{phase}</Text>
      </Text>
    </Box>
  );
}
