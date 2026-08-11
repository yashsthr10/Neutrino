import React, { useCallback, useEffect, useState } from "react";
import { Box, Text } from "ink";
import TextInput from "ink-text-input";

import type { CredentialProviderStatus } from "../rpc/types.js";
import { useRuntime } from "../state/RuntimeContext.js";
import { colors } from "../theme/colors.js";

type Step =
  | { name: "menu" }
  | { name: "secret"; providerId: string; kind: string }
  | { name: "aws_secret"; providerId: string; accessKeyId: string };

const MENU_HINT = "enter index to set · rm <index> · esc close";

function kindFor(providerId: string): string {
  if (providerId === "azure_openai") return "azure";
  if (providerId === "bedrock") return "aws";
  return "api_key";
}

function secretPrompt(kind: string, step: Step): string {
  if (step.name === "aws_secret") return "AWS secret access key";
  if (kind === "aws") return "AWS access key id";
  if (kind === "azure") return "Azure OpenAI API key";
  if (kind === "bearer") return "bearer token";
  return "API key";
}

/** Parse a 1-based index into a 0-based offset, or null if invalid. */
function parseIndex(raw: string, length: number): number | null {
  if (!/^\d+$/.test(raw)) return null;
  const n = Number(raw);
  if (!Number.isInteger(n) || n < 1 || n > length) return null;
  return n - 1;
}

export function CredentialsModal() {
  const { credentialsList, credentialsSet, credentialsRemove, dispatch } =
    useRuntime();
  const [providers, setProviders] = useState<CredentialProviderStatus[]>([]);
  const [profile, setProfile] = useState("default");
  const [step, setStep] = useState<Step>({ name: "menu" });
  const [value, setValue] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const reload = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const result = await credentialsList(profile);
      setProviders(result.providers);
      setProfile(result.profile);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }, [credentialsList, profile]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const finishSaved = async (providerId: string) => {
    setStatus(`stored ${profile}:${providerId}`);
    setStep({ name: "menu" });
    setValue("");
    await reload();
  };

  const onSubmit = async (raw: string) => {
    const line = raw.trim();
    if (!line || busy) return;
    setError(null);
    setStatus(null);

    if (step.name === "menu") {
      const lower = line.toLowerCase();
      if (lower === "done" || lower === "close" || lower === "q") {
        dispatch({ type: "set_overlay", overlay: "none" });
        return;
      }
      if (lower.startsWith("remove ") || lower.startsWith("rm ")) {
        if (providers.length === 0) {
          setError("no providers listed");
          return;
        }
        const token = lower.replace(/^(remove|rm)\s+/, "").trim();
        const idx = parseIndex(token, providers.length);
        if (idx === null) {
          setError(`rm <index> — use 1–${providers.length}`);
          return;
        }
        const providerId = providers[idx]!.providerId;
        setBusy(true);
        try {
          await credentialsRemove(providerId, profile);
          setStatus(`removed ${profile}:${providerId}`);
          setValue("");
          await reload();
        } catch (err) {
          setError(err instanceof Error ? err.message : String(err));
        } finally {
          setBusy(false);
        }
        return;
      }
      if (providers.length === 0) {
        setError("no providers listed");
        return;
      }
      const idx = parseIndex(line, providers.length);
      if (idx === null) {
        setError(`enter an index 1–${providers.length}`);
        return;
      }
      const providerId = providers[idx]!.providerId;
      setValue("");
      setStep({ name: "secret", providerId, kind: kindFor(providerId) });
      return;
    }

    if (step.name === "secret") {
      if (lowerIsBack(line)) {
        setStep({ name: "menu" });
        setValue("");
        return;
      }
      if (step.kind === "aws") {
        setValue("");
        setStep({
          name: "aws_secret",
          providerId: step.providerId,
          accessKeyId: line,
        });
        return;
      }
      setBusy(true);
      try {
        const fields: Record<string, string> =
          step.kind === "bearer" ? { token: line } : { api_key: line };
        await credentialsSet(step.providerId, fields, {
          kind: step.kind,
          profile,
        });
        await finishSaved(step.providerId);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setBusy(false);
      }
      return;
    }

    if (step.name === "aws_secret") {
      if (lowerIsBack(line)) {
        setStep({
          name: "secret",
          providerId: step.providerId,
          kind: "aws",
        });
        setValue("");
        return;
      }
      setBusy(true);
      try {
        await credentialsSet(
          step.providerId,
          {
            access_key_id: step.accessKeyId,
            secret_access_key: line,
          },
          { kind: "aws", profile },
        );
        await finishSaved(step.providerId);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setBusy(false);
      }
    }
  };

  const promptLabel =
    step.name === "menu"
      ? "index"
      : secretPrompt(step.name === "secret" ? step.kind : "aws", step);

  return (
    <Box flexDirection="column">
      <Text color={colors.muted}>── credentials ────────────────────────</Text>
      <Text color={colors.muted}>
        profile {profile}
        {busy ? "  …" : ""}
      </Text>
      {providers.map((p, i) => {
        const src = p.source ? ` (${p.source})` : "";
        return (
          <Text key={p.providerId} color={p.configured ? colors.completed : colors.muted}>
            [{i + 1}] {p.providerId}
            {src}
          </Text>
        );
      })}
      {status ? <Text color={colors.completed}>{status}</Text> : null}
      {error ? <Text color={colors.failure}>{error}</Text> : null}
      <Box>
        <Text color={colors.muted}>{promptLabel}: </Text>
        <TextInput
          value={value}
          onChange={setValue}
          onSubmit={(v) => void onSubmit(v)}
          mask={step.name === "menu" ? undefined : "*"}
          focus
        />
      </Box>
      <Text color={colors.muted}>
        {step.name === "menu" ? MENU_HINT : "enter save · b back · esc cancel"}
      </Text>
    </Box>
  );
}

function lowerIsBack(line: string): boolean {
  const lower = line.trim().toLowerCase();
  return lower === "b" || lower === "back";
}
