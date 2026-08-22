/** Wire types mirrored from protocol/schema.ts */

export const PROTOCOL_VERSION = "1.0.0";

export type RuntimeMode = "fast" | "deep" | "auto";
export type ApprovalAction = "accept" | "edit" | "reject" | "view";
export type LogLevel = "info" | "warning" | "error" | "debug";

export type UiEventType =
  | "execution.started"
  | "state.changed"
  | "pipeline.progress"
  | "activity.delta"
  | "log.line"
  | "diff.updated"
  | "repo.tree"
  | "status.snapshot"
  | "context.summary"
  | "approval.requested"
  | "recovery.requested"
  | "tokens.updated"
  | "execution.finished"
  | "tool.called"
  | "agent.message"
  | "reasoning.block"
  | "phase.step_complete"
  | "explanation.available"
  | "model.changed"
  | "plan.tasks_updated";

export interface UiEventEnvelope {
  type: UiEventType;
  payload: Record<string, unknown>;
}

export interface SessionHelloResult {
  protocolVersion: string;
  projectName: string;
  model: string;
  providerId?: string;
  baseUrl?: string | null;
  branch: string;
  capabilities: string[];
}

/** Status only — never includes secret values. */
export interface CredentialProviderStatus {
  providerId: string;
  configured: boolean;
  source: string | null;
  kind: string | null;
}

export interface CredentialsListResult {
  profile: string;
  providers: CredentialProviderStatus[];
}

export interface InferenceCatalogProvider {
  providerId: string;
  configured: boolean;
  source: string | null;
  kind: string | null;
  type: string;
  vendor: string | null;
}

export interface InferenceCatalogResult {
  profile: string;
  active: {
    providerId: string;
    model: string;
    type: string;
    vendor: string | null;
    baseUrl: string | null;
  };
  providers: InferenceCatalogProvider[];
}

export interface InferenceListModelsResult {
  providerId: string;
  models: { id: string; name?: string | null; ownedBy?: string | null }[];
  source: string;
  warning?: string | null;
}

export interface JsonRpcRequest {
  jsonrpc: "2.0";
  id: number | string;
  method: string;
  params?: Record<string, unknown>;
}

export interface JsonRpcNotification {
  jsonrpc: "2.0";
  method: string;
  params?: Record<string, unknown>;
}

export type JsonRpcInbound =
  | { jsonrpc: "2.0"; id: number | string; result: unknown }
  | { jsonrpc: "2.0"; id: number | string | null; error: { code: number; message: string } }
  | JsonRpcNotification;
