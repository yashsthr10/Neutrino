import React, { useCallback, useState } from "react";
import { Box, Text } from "ink";
import TextInput from "ink-text-input";

import { useRuntime } from "../state/RuntimeContext.js";
import { colors } from "../theme/colors.js";

const HELP =
  "/help  /status  /auth  /model  /cancel  /approve  /reject  /undo  /context  /plan  /explain   ·  Ctrl+P  Ctrl+K keys  Ctrl+M model  Ctrl+R";

export function CommandBar({
  history,
  historyIndex,
  onHistoryIndexChange,
  onHistoryPush,
}: {
  history: string[];
  historyIndex: number | null;
  onHistoryIndexChange: (idx: number | null) => void;
  onHistoryPush: (line: string) => void;
}) {
  const {
    state,
    dispatch,
    execute,
    cancel,
    approve,
    undo,
    refreshContext,
    status,
  } = useRuntime();
  const [value, setValue] = useState("");

  React.useEffect(() => {
    if (historyIndex === null) return;
    setValue(history[historyIndex] ?? "");
  }, [historyIndex, history]);

  const submit = useCallback(
    async (raw: string) => {
      const line = raw.trim();
      if (!line) return;
      onHistoryPush(line);
      onHistoryIndexChange(null);
      setValue("");

      if (line.startsWith("/")) {
        const [cmd] = line.slice(1).split(/\s+/);
        switch ((cmd || "").toLowerCase()) {
          case "help":
            dispatch({ type: "set_help", text: HELP });
            return;
          case "status": {
            const s = await status();
            dispatch({ type: "set_help", text: JSON.stringify(s) });
            return;
          }
          case "cancel":
            await cancel();
            return;
          case "approve":
            await approve("accept");
            return;
          case "reject":
            await approve("reject");
            return;
          case "undo":
            await undo();
            return;
          case "context":
            await refreshContext();
            return;
          case "auth":
          case "keys":
          case "credentials":
            dispatch({ type: "set_overlay", overlay: "credentials" });
            return;
          case "model":
          case "models":
            dispatch({ type: "set_overlay", overlay: "model" });
            return;
          case "plan":
            dispatch({
              type: "set_help",
              text: state.currentTask ? state.currentTask : "no active task",
            });
            return;
          case "explain":
            dispatch({
              type: "set_help",
              text: "Ctrl+R opens the runtime inspector. Ctrl+K manages API keys.",
            });
            return;
          default:
            dispatch({ type: "set_help", text: `unknown: /${cmd}` });
            return;
        }
      }

      dispatch({ type: "set_help", text: null });
      await execute(line);
    },
    [
      approve,
      cancel,
      dispatch,
      execute,
      onHistoryIndexChange,
      onHistoryPush,
      refreshContext,
      state.currentTask,
      status,
      undo,
    ],
  );

  return (
    <Box flexDirection="column" paddingX={1} marginTop={1}>
      {state.helpText ? <Text color={colors.muted}>{state.helpText}</Text> : null}
      {state.approval ? (
        <Text color={colors.warning}>
          ? {state.approval.summary}  (/approve · /reject)
        </Text>
      ) : null}
      {state.running ? (
        <Text color={colors.muted}>esc cancel overlay · ctrl+c cancel run</Text>
      ) : null}
      <Box>
        <Text bold color={state.running ? colors.muted : colors.accent}>
          {"> "}
        </Text>
        <TextInput
          value={value}
          onChange={(v) => {
            setValue(v);
            onHistoryIndexChange(null);
          }}
          onSubmit={submit}
          focus={state.overlay === "none"}
          placeholder={state.running ? "working…" : ""}
        />
      </Box>
    </Box>
  );
}
