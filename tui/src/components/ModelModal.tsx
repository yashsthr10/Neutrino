import React, { useCallback, useEffect, useState } from "react";
import { Box, Text } from "ink";
import TextInput from "ink-text-input";

import type {
  InferenceCatalogProvider,
  InferenceCatalogResult,
} from "../rpc/types.js";
import { useRuntime } from "../state/RuntimeContext.js";
import { colors } from "../theme/colors.js";

type Step =
  | { name: "providers" }
  | { name: "models"; providerId: string; models: { id: string; ownedBy?: string | null }[] };

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

  const onSubmit = async (raw: string) => {
    const line = raw.trim();
    if (!line || busy) return;
    setError(null);
    setStatus(null);

    if (step.name === "providers") {
      const lower = line.toLowerCase();
      if (lower === "done" || lower === "close" || lower === "q") {
        dispatch({ type: "set_overlay", overlay: "none" });
        return;
      }
      const match = providers.find((p) => p.providerId === lower);
      if (!match) {
        setError(
          providers.length === 0
            ? "no providers with credentials — use /auth first"
            : `not eligible: ${lower} (add keys with /auth)`,
        );
        return;
      }
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
      return;
    }

    // models step
    const modelId = line;
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
            providers.map((p) => (
              <Text key={p.providerId} color={colors.completed}>
                [x] {p.providerId}
                {p.source ? ` (${p.source})` : ""}
              </Text>
            ))
          )}
        </>
      ) : (
        <>
          <Text color={colors.muted}>models for {step.providerId}</Text>
          {step.models.slice(0, 12).map((m) => (
            <Text key={m.id} color={colors.muted}>
              {"  "}
              {m.id}
            </Text>
          ))}
          {step.models.length > 12 ? (
            <Text color={colors.muted}>  … +{step.models.length - 12} more</Text>
          ) : null}
          <Text color={colors.muted}>type a model id (listed or custom)</Text>
        </>
      )}

      {status ? <Text color={colors.completed}>{status}</Text> : null}
      {error ? <Text color={colors.failure}>{error}</Text> : null}
      <Box>
        <Text color={colors.muted}>
          {step.name === "providers" ? "provider" : "model"}:{" "}
        </Text>
        <TextInput
          value={value}
          onChange={setValue}
          onSubmit={(v) => void onSubmit(v)}
          focus
        />
      </Box>
      <Text color={colors.muted}>
        {step.name === "providers"
          ? "only providers with keys · esc close"
          : "enter select · esc close"}
      </Text>
    </Box>
  );
}
