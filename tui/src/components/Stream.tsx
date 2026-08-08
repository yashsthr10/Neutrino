import React from "react";
import { Box, Text } from "ink";

import { useRuntime } from "../state/RuntimeContext.js";
import type { TranscriptItem, TranscriptTone } from "../state/reducer.js";
import { colors } from "../theme/colors.js";

function toneColor(tone: TranscriptTone): string | undefined {
  switch (tone) {
    case "success":
      return colors.completed;
    case "warn":
      return colors.warning;
    case "error":
      return colors.failure;
    case "dim":
      return colors.muted;
    case "user":
      return colors.user;
    case "diffAdd":
      return colors.diffAdd;
    case "diffDel":
      return colors.diffDel;
    default:
      return undefined;
  }
}

function TranscriptRow({ item }: { item: TranscriptItem }) {
  if (item.kind === "blank") {
    return <Text> </Text>;
  }
  if (item.kind === "user") {
    return (
      <Box flexDirection="column" marginTop={0}>
        <Text color={colors.accent} bold>
          {"> "}
          {item.text}
        </Text>
      </Box>
    );
  }
  if (item.kind === "diff") {
    return (
      <Box flexDirection="column" marginLeft={2} marginY={0}>
        <Text color={colors.muted}>{item.path}</Text>
        {item.lines.map((l, i) => (
          <Text key={`${item.id}-${i}`} color={toneColor(l.tone)}>
            {"  "}
            {l.text}
          </Text>
        ))}
      </Box>
    );
  }
  return (
    <Text color={toneColor(item.tone)}>
      {item.prefix ? `${item.prefix} ` : "  "}
      {item.text}
    </Text>
  );
}

/** Chronological chat/runtime stream — Claude Code / Codex style. */
export function Stream() {
  const { state } = useRuntime();
  const items = state.transcript.slice(-36);

  if (!state.connected && state.transcript.length === 0) {
    return (
      <Box flexDirection="column" flexGrow={1} paddingX={1}>
        <Text color={colors.muted}>Connecting to runtime…</Text>
      </Box>
    );
  }

  if (items.length === 0) {
    return (
      <Box flexDirection="column" flexGrow={1} paddingX={1}>
        <Text color={colors.muted}>
          Describe a task, or type /help. Ctrl+R opens the runtime inspector.
        </Text>
      </Box>
    );
  }

  return (
    <Box flexDirection="column" flexGrow={1} paddingX={1}>
      {items.map((item) => (
        <TranscriptRow key={item.id} item={item} />
      ))}
    </Box>
  );
}
