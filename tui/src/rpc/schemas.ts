import { z } from "zod";

export const uiEventSchema = z.object({
  type: z.string(),
  payload: z.record(z.unknown()).default({}),
});

export const sessionHelloResultSchema = z.object({
  protocolVersion: z.string(),
  projectName: z.string(),
  model: z.string(),
  providerId: z.string().optional(),
  baseUrl: z.string().nullable().optional(),
  branch: z.string(),
  capabilities: z.array(z.string()),
});
