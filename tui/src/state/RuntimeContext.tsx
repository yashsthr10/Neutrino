import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  useRef,
} from "react";

import { JsonRpcClient } from "../rpc/client.js";
import type {
  CredentialsListResult,
  InferenceCatalogResult,
  InferenceListModelsResult,
} from "../rpc/types.js";
import {
  initialState,
  runtimeReducer,
  type RuntimeAction,
  type RuntimeViewState,
} from "./reducer.js";

type RuntimeApi = {
  state: RuntimeViewState;
  dispatch: React.Dispatch<RuntimeAction>;
  execute: (task: string) => Promise<void>;
  cancel: () => Promise<void>;
  approve: (action: string) => Promise<void>;
  selectRecovery: (optionId: string) => Promise<void>;
  undo: () => Promise<void>;
  refreshContext: () => Promise<void>;
  requestRepoTree: () => Promise<void>;
  status: () => Promise<unknown>;
  setMode: (mode: string) => Promise<void>;
  credentialsList: (profile?: string) => Promise<CredentialsListResult>;
  credentialsSet: (
    providerId: string,
    fields: Record<string, string>,
    opts?: { kind?: string; profile?: string },
  ) => Promise<void>;
  credentialsRemove: (providerId: string, profile?: string) => Promise<void>;
  inferenceCatalog: (profile?: string) => Promise<InferenceCatalogResult>;
  inferenceListModels: (
    providerId: string,
    opts?: { baseUrl?: string; profile?: string },
  ) => Promise<InferenceListModelsResult>;
  setModel: (
    providerId: string,
    model: string,
    opts?: { baseUrl?: string; profile?: string },
  ) => Promise<void>;
};

const RuntimeContext = createContext<RuntimeApi | null>(null);

export function RuntimeProvider({
  cwd,
  children,
}: {
  cwd: string;
  children: React.ReactNode;
}) {
  const [state, dispatch] = useReducer(runtimeReducer, undefined, initialState);
  const clientRef = useRef<JsonRpcClient | null>(null);

  useEffect(() => {
    const client = new JsonRpcClient(cwd, {
      onEvent: (event) => dispatch({ type: "ui_event", event }),
      onError: (message) => {
        // stderr diagnostics — keep non-fatal unless disconnect
        if (message.toLowerCase().includes("traceback")) {
          dispatch({ type: "fatal", message });
        }
      },
      onExit: (code) => {
        if (code !== 0 && code !== null) {
          dispatch({ type: "fatal", message: `Runtime exited with code ${code}` });
        }
      },
    });
    clientRef.current = client;
    let cancelled = false;
    (async () => {
      try {
        const hello = await client.start();
        if (cancelled) return;
        dispatch({
          type: "connected",
          projectName: hello.projectName,
          model: hello.model,
          providerId: hello.providerId,
          baseUrl: hello.baseUrl ?? null,
          branch: hello.branch,
        });
        await client.requestRepoTree();
      } catch (err) {
        if (!cancelled) {
          dispatch({
            type: "fatal",
            message: err instanceof Error ? err.message : String(err),
          });
        }
      }
    })();
    return () => {
      cancelled = true;
      client.stop();
    };
  }, [cwd]);

  const execute = useCallback(async (task: string) => {
    await clientRef.current?.execute(task);
  }, []);

  const cancel = useCallback(async () => {
    await clientRef.current?.cancel();
  }, []);

  const approve = useCallback(async (action: string) => {
    const id = clientRef.current && state.approval?.requestId;
    if (!id) return;
    await clientRef.current?.approve(id, action);
    dispatch({ type: "clear_approval" });
  }, [state.approval?.requestId]);

  const selectRecovery = useCallback(async (optionId: string) => {
    await clientRef.current?.selectRecovery(optionId);
    dispatch({ type: "clear_recovery" });
  }, []);

  const undo = useCallback(async () => {
    await clientRef.current?.undo();
  }, []);

  const refreshContext = useCallback(async () => {
    await clientRef.current?.refreshContext();
  }, []);

  const requestRepoTree = useCallback(async () => {
    await clientRef.current?.requestRepoTree();
  }, []);

  const status = useCallback(async () => {
    return clientRef.current?.status();
  }, []);

  const setMode = useCallback(async (mode: string) => {
    await clientRef.current?.setMode(mode);
  }, []);

  const credentialsList = useCallback(async (profile = "default") => {
    const client = clientRef.current;
    if (!client) {
      return { profile, providers: [] };
    }
    return client.credentialsList(profile);
  }, []);

  const credentialsSet = useCallback(
    async (
      providerId: string,
      fields: Record<string, string>,
      opts?: { kind?: string; profile?: string },
    ) => {
      await clientRef.current?.credentialsSet(providerId, fields, opts);
    },
    [],
  );

  const credentialsRemove = useCallback(async (providerId: string, profile = "default") => {
    await clientRef.current?.credentialsRemove(providerId, profile);
  }, []);

  const inferenceCatalog = useCallback(async (profile = "default") => {
    const client = clientRef.current;
    if (!client) {
      return {
        profile,
        active: {
          providerId: "openai-compatible",
          model: "—",
          type: "openai-compatible",
          vendor: null,
          baseUrl: null,
        },
        providers: [],
      };
    }
    return client.inferenceCatalog(profile);
  }, []);

  const inferenceListModels = useCallback(
    async (providerId: string, opts?: { baseUrl?: string; profile?: string }) => {
      const client = clientRef.current;
      if (!client) {
        return { providerId, models: [], source: "catalog", warning: "not connected" };
      }
      return client.inferenceListModels(providerId, opts);
    },
    [],
  );

  const setModel = useCallback(
    async (
      providerId: string,
      model: string,
      opts?: { baseUrl?: string; profile?: string },
    ) => {
      await clientRef.current?.setModel(providerId, model, opts);
      dispatch({
        type: "set_model",
        model,
        providerId,
        baseUrl: opts?.baseUrl ?? null,
      });
    },
    [],
  );

  const api = useMemo(
    () => ({
      state,
      dispatch,
      execute,
      cancel,
      approve,
      selectRecovery,
      undo,
      refreshContext,
      requestRepoTree,
      status,
      setMode,
      credentialsList,
      credentialsSet,
      credentialsRemove,
      inferenceCatalog,
      inferenceListModels,
      setModel,
    }),
    [
      state,
      execute,
      cancel,
      approve,
      selectRecovery,
      undo,
      refreshContext,
      requestRepoTree,
      status,
      setMode,
      credentialsList,
      credentialsSet,
      credentialsRemove,
      inferenceCatalog,
      inferenceListModels,
      setModel,
    ],
  );

  return <RuntimeContext.Provider value={api}>{children}</RuntimeContext.Provider>;
}

export function useRuntime(): RuntimeApi {
  const ctx = useContext(RuntimeContext);
  if (!ctx) {
    throw new Error("useRuntime must be used within RuntimeProvider");
  }
  return ctx;
}
