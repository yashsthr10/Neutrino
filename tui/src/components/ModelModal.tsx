import React, { useCallback, useEffect, useState } from "react";
import { Box, Text } from "ink";
import TextInput from "ink-text-input";

import type {
  InferenceCatalogProvider,
  InferenceCatalogResult,
} from "../rpc/types.js";
import { useRuntime } from "../state/RuntimeContext.js";
import { colors } from "../theme/colors.js";

type ModelEntry = { id: string; ownedBy?: string | null };

type Step =
  | { name: "providers" }
  | { name: "models"; providerId: string; models: ModelEntry[] };

const MODEL_DISPLAY_LIMIT = 20;

/** Parse a 1-based index into a 0-based offset, or null if invalid. */
function parseIndex(raw: string, length: number): number | null {
  if (!/^\d+$/.test(raw)) return null;
  const n = Number(raw);
  if (!Number.isInteger(n) || n < 1 || n > length) return null;
  return n - 1;
}

export function ModelModal() {
  const { inferenceCatalog, inferenceListModels, setModel, dispatch } = useRuntime();
  const [catalog, setCatalog] = useState<InferenceCatalogResult | null>(null);
  const [step, setStep] = useState<Step>({ name: "providers" });
  const [value, setValue] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const reload = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const result = await inferenceCatalog();
      setCatalog(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }, [inferenceCatalog]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const providers: InferenceCatalogProvider[] = catalog?.providers ?? [];

  const selectProvider = async (match: InferenceCatalogProvider) => {
    setBusy(true);
    try {
      const listed = await inferenceListModels(match.providerId);
      setStep({
        name: "models",
        providerId: match.providerId,
        models: listed.models,
      });
      setValue("");
      if (listed.warning && listed.source === "catalog") {
        setStatus(`catalog fallback (${listed.models.length} models)`);
      } else {
        setStatus(`${listed.source}: ${listed.models.length} models`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const onSubmit = async (raw: string) => {
    const line = raw.trim();
    if (!line || busy) return;
    setError(null);
    setStatus(null);

    const lower = line.toLowerCase();
    if (lower === "done" || lower === "close" || lower === "q") {
      dispatch({ type: "set_overlay", overlay: "none" });
      return;
    }

    if (step.name === "providers") {
      if (providers.length === 0) {
        setError("no providers with credentials — use /auth first");
        return;
      }
      const idx = parseIndex(line, providers.length);
      if (idx === null) {
        setError(`enter an index 1–${providers.length}`);
        return;
      }
      await selectProvider(providers[idx]!);
      return;
    }

    // models step
    if (lower === "b" || lower === "back") {
      setStep({ name: "providers" });
      setValue("");
      setStatus(null);
      return;
    }

    const idx = parseIndex(line, step.models.length);
    if (idx === null) {
      setError(
        step.models.length === 0
          ? "no models listed — b back"
          : `enter an index 1–${step.models.length}`,
      );
      return;
    }
    const modelId = step.models[idx]!.id;
    setBusy(true);
    try {
      await setModel(step.providerId, modelId);
      setStatus(`active ${step.providerId}/${modelId}`);
      setStep({ name: "providers" });
      setValue("");
      await reload();
      dispatch({ type: "set_overlay", overlay: "none" });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Box flexDirection="column">
      <Text color={colors.muted}>── model ──────────────────────────────</Text>
      {catalog?.active ? (
        <Text>
          active{" "}
          <Text color={colors.running}>
            {catalog.active.providerId}/{catalog.active.model}
          </Text>
          {busy ? "  …" : ""}
        </Text>
      ) : (
        <Text color={colors.muted}>{busy ? "loading…" : "—"}</Text>
      )}

      {step.name === "providers" ? (
        <>
          <Text color={colors.muted}>providers with credentials</Text>
          {providers.length === 0 ? (
            <Text color={colors.warning}>none — run /auth (Ctrl+K) first</Text>
          ) : (
            providers.map((p, i) => (
              <Text key={p.providerId} color={colors.completed}>
                [{i + 1}] {p.providerId}
                {p.source ? ` (${p.source})` : ""}
              </Text>
            ))
          )}
        </>
      ) : (
        <>
          <Text color={colors.muted}>models for {step.providerId}</Text>
          {step.models.length === 0 ? (
            <Text color={colors.warning}>none listed</Text>
          ) : (
            step.models.slice(0, MODEL_DISPLAY_LIMIT).map((m, i) => (
              <Text key={m.id} color={colors.muted}>
                [{i + 1}] {m.id}
              </Text>
            ))
          )}
          {step.models.length > MODEL_DISPLAY_LIMIT ? (
            <Text color={colors.muted}>
              {"  "}… +{step.models.length - MODEL_DISPLAY_LIMIT} more (indices 1–
              {step.models.length})
            </Text>
          ) : null}
        </>
      )}

      {status ? <Text color={colors.completed}>{status}</Text> : null}
      {error ? <Text color={colors.failure}>{error}</Text> : null}
      <Box>
        <Text color={colors.muted}>index: </Text>
        <TextInput
          value={value}
          onChange={setValue}
          onSubmit={(v) => void onSubmit(v)}
          focus
        />
      </Box>
      <Text color={colors.muted}>
        {step.name === "providers"
          ? "enter index · esc close"
          : "enter index · b back · esc close"}
      </Text>
    </Box>
  );
}
