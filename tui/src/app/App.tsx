import React, { useState } from "react";
import { Box, Text, useApp, useInput } from "ink";

import { CommandBar } from "../components/CommandBar.js";
import { CommandPalette } from "../components/CommandPalette.js";
import { CredentialsModal } from "../components/CredentialsModal.js";
import { Header } from "../components/Header.js";
import { RuntimeInspector } from "../components/InspectorModal.js";
import { ModelModal } from "../components/ModelModal.js";
import { Stream } from "../components/Stream.js";
import { useRuntime } from "../state/RuntimeContext.js";
import { colors } from "../theme/colors.js";

export function App() {
  const { state, dispatch, cancel, undo } = useRuntime();
  const { exit } = useApp();
  const [history, setHistory] = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState<number | null>(null);

  useInput((input, key) => {
    if (state.fatalError) {
      if (key.escape || (key.ctrl && input === "c")) {
        exit();
      }
      return;
    }

    if (key.escape) {
      if (state.overlay !== "none") {
        dispatch({ type: "set_overlay", overlay: "none" });
        return;
      }
      dispatch({ type: "set_help", text: null });
      return;
    }

    if (key.ctrl && input === "c") {
      if (state.running) {
        void cancel();
        return;
      }
      exit();
      return;
    }

    if (key.ctrl && input === "p") {
      dispatch({
        type: "set_overlay",
        overlay: state.overlay === "palette" ? "none" : "palette",
      });
      return;
    }

    if (key.ctrl && input === "r") {
      dispatch({
        type: "set_overlay",
        overlay: state.overlay === "inspector" ? "none" : "inspector",
      });
      return;
    }

    if (key.ctrl && input === "k") {
      dispatch({
        type: "set_overlay",
        overlay: state.overlay === "credentials" ? "none" : "credentials",
      });
      return;
    }

    if (key.ctrl && input === "m") {
      dispatch({
        type: "set_overlay",
        overlay: state.overlay === "model" ? "none" : "model",
      });
      return;
    }

    if (key.ctrl && input === "u") {
      void undo();
      return;
    }

    if (state.overlay !== "none") {
      return;
    }

    if (key.upArrow) {
      if (history.length === 0) return;
      const next =
        historyIndex === null ? history.length - 1 : Math.max(0, historyIndex - 1);
      setHistoryIndex(next);
      return;
    }

    if (key.downArrow) {
      if (historyIndex === null) return;
      if (historyIndex >= history.length - 1) {
        setHistoryIndex(null);
        return;
      }
      setHistoryIndex(historyIndex + 1);
    }
  });

  if (state.fatalError) {
    return (
      <Box flexDirection="column" padding={1}>
        <Text color={colors.failure} bold>
          runtime error
        </Text>
        <Text>{state.fatalError}</Text>
        <Text color={colors.muted}>esc or ctrl+c to exit</Text>
      </Box>
    );
  }

  return (
    <Box flexDirection="column" width="100%" paddingY={0}>
      <Header />
      <Stream />
      <CommandBar
        history={history}
        historyIndex={historyIndex}
        onHistoryIndexChange={setHistoryIndex}
        onHistoryPush={(line) => setHistory((h) => [...h, line].slice(-50))}
      />
      {state.overlay === "palette" ? (
        <Box flexDirection="column" paddingX={1} marginTop={1}>
          <CommandPalette />
        </Box>
      ) : null}
      {state.overlay === "inspector" ? (
        <Box flexDirection="column" paddingX={1} marginTop={1}>
          <RuntimeInspector />
        </Box>
      ) : null}
      {state.overlay === "credentials" ? (
        <Box flexDirection="column" paddingX={1} marginTop={1}>
          <CredentialsModal />
        </Box>
      ) : null}
      {state.overlay === "model" ? (
        <Box flexDirection="column" paddingX={1} marginTop={1}>
          <ModelModal />
        </Box>
      ) : null}
    </Box>
  );
}
