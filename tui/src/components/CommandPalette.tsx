import React, { useState } from "react";
import { Box, Text } from "ink";
import TextInput from "ink-text-input";

import { useRuntime } from "../state/RuntimeContext.js";
import { colors } from "../theme/colors.js";

const COMMANDS = [
  { id: "help", label: "/help" },
  { id: "status", label: "/status" },
  { id: "auth", label: "/auth (API keys)" },
  { id: "model", label: "/model" },
  { id: "cancel", label: "/cancel" },
  { id: "approve", label: "/approve" },
  { id: "reject", label: "/reject" },
  { id: "context", label: "/context" },
  { id: "inspector", label: "runtime inspector" },
];

export function CommandPalette() {
  const { dispatch, cancel, approve, refreshContext, status } = useRuntime();
  const [query, setQuery] = useState("");
  const filtered = COMMANDS.filter((c) =>
    c.label.toLowerCase().includes(query.toLowerCase()),
  );

  const run = async (id: string) => {
    dispatch({ type: "set_overlay", overlay: "none" });
    switch (id) {
      case "help":
        dispatch({
          type: "set_help",
          text: COMMANDS.map((c) => c.label).join("  "),
        });
        break;
      case "status": {
        const s = await status();
        dispatch({ type: "set_help", text: JSON.stringify(s) });
        break;
      }
      case "cancel":
        await cancel();
        break;
      case "approve":
        await approve("accept");
        break;
      case "reject":
        await approve("reject");
        break;
      case "context":
        await refreshContext();
        break;
      case "auth":
        dispatch({ type: "set_overlay", overlay: "credentials" });
        break;
      case "model":
        dispatch({ type: "set_overlay", overlay: "model" });
        break;
      case "inspector":
        dispatch({ type: "set_overlay", overlay: "inspector" });
        break;
      default:
        break;
    }
  };

  return (
    <Box flexDirection="column">
      <Text color={colors.muted}>── commands ───────────────────────────</Text>
      <Box>
        <Text color={colors.muted}>{"> "}</Text>
        <TextInput
          value={query}
          onChange={setQuery}
          onSubmit={() => {
            if (filtered[0]) void run(filtered[0].id);
          }}
          focus
        />
      </Box>
      {filtered.slice(0, 8).map((c) => (
        <Text key={c.id} color={colors.muted}>
          {"  "}
          {c.label}
        </Text>
      ))}
    </Box>
  );
}
