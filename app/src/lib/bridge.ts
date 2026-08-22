import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { z } from "zod";

export const STREAM_EVENT = "stream.event";
export const CRASH_EVENT = "python.crash";
export const RESTARTED_EVENT = "python.restarted";

const ENGINE_STOPPED_MARKER = "sidecar is stopped after repeated crashes";

export const ERROR_CODES = [
  "PARSE_ERROR",
  "INVALID_REQUEST",
  "IPC_SCHEMA_VERSION",
  "PROVIDER_RATE_LIMIT",
  "PROVIDER_AUTH",
  "PROVIDER_UNAVAILABLE",
  "PYTHON_TIMEOUT",
  "AUDIO_DEVICE_LOST",
  "OCR_FAILED",
  "MEETING_NOT_FOUND",
  "INTERNAL",
] as const;

export type ErrorCode = (typeof ERROR_CODES)[number];
export type FailureCode = ErrorCode | "ENGINE_STOPPED" | "TRANSPORT";

export type BridgeFailure = {
  code: FailureCode;
  message: string;
  retryable: boolean;
};

export type Reply<T> = { ok: true; value: T } | { ok: false; error: BridgeFailure };

export type StreamFamily = "chat" | "ask" | "stream";
export type StreamState = "started" | "timeout" | "completed";

export type StreamEvent =
  | {
      family: StreamFamily;
      kind: "state";
      correlationId: string;
      threadId: string | null;
      state: StreamState;
    }
  | {
      family: StreamFamily;
      kind: "token";
      correlationId: string;
      threadId: string | null;
      text: string;
    }
  | {
      family: StreamFamily;
      kind: "done";
      correlationId: string;
      threadId: string | null;
      tokens: number;
    }
  | {
      family: StreamFamily;
      kind: "error";
      correlationId: string;
      threadId: string | null;
      code: ErrorCode;
      message: string;
    }
  | {
      family: StreamFamily;
      kind: "cancelled";
      correlationId: string;
      threadId: string | null;
    }
  | {
      family: "ask";
      kind: "citation" | "tool_call" | "tool_result";
      correlationId: string;
      threadId: string | null;
      data: unknown;
    };

const envelopeSchema = z
  .object({
    correlation_id: z.string(),
    kind: z.string(),
    thread_id: z.string().optional(),
  })
  .passthrough();

const errorCodeSchema = z.enum(ERROR_CODES);
const tokenSchema = z.object({ data: z.string() });
const doneSchema = z.object({ tokens: z.number().int() });
const errorSchema = z.object({ code: errorCodeSchema, message: z.string() });
const stateSchema = z.object({ state: z.enum(["started", "timeout", "completed"]) });

const errorBodySchema = z.object({
  code: errorCodeSchema,
  message: z.string(),
  retryable: z.boolean().default(false),
});

const okReplySchema = z.object({ id: z.string(), result: z.unknown() });
const errReplySchema = z.object({ id: z.string(), error: errorBodySchema });

function splitKind(kind: string): { family: StreamFamily; name: string } | null {
  const dot = kind.indexOf(".");
  if (dot < 0) {
    return { family: "stream", name: kind };
  }
  const prefix = kind.slice(0, dot);
  if (prefix !== "chat" && prefix !== "ask") {
    return null;
  }
  return { family: prefix, name: kind.slice(dot + 1) };
}

export function parseStreamEvent(raw: unknown): StreamEvent | null {
  const envelope = envelopeSchema.safeParse(raw);
  if (!envelope.success) {
    return null;
  }

  const split = splitKind(envelope.data.kind);
  if (!split) {
    return null;
  }

  const { family, name } = split;
  const correlationId = envelope.data.correlation_id;
  const threadId = envelope.data.thread_id ?? null;

  switch (name) {
    case "state": {
      const parsed = stateSchema.safeParse(raw);
      return parsed.success
        ? { family, kind: "state", correlationId, threadId, state: parsed.data.state }
        : null;
    }
    case "token": {
      const parsed = tokenSchema.safeParse(raw);
      return parsed.success
        ? { family, kind: "token", correlationId, threadId, text: parsed.data.data }
        : null;
    }
    case "done": {
      const parsed = doneSchema.safeParse(raw);
      return parsed.success
        ? { family, kind: "done", correlationId, threadId, tokens: parsed.data.tokens }
        : null;
    }
    case "error": {
      const parsed = errorSchema.safeParse(raw);
      return parsed.success
        ? {
            family,
            kind: "error",
            correlationId,
            threadId,
            code: parsed.data.code,
            message: parsed.data.message,
          }
        : null;
    }
    case "cancelled":
      return { family, kind: "cancelled", correlationId, threadId };
    case "citation":
    case "tool_call":
    case "tool_result": {
      if (family !== "ask") {
        return null;
      }
      const data = (raw as { data?: unknown }).data;
      return { family, kind: name, correlationId, threadId, data };
    }
    default:
      return null;
  }
}

function transportFailure(message: string): BridgeFailure {
  return { code: "TRANSPORT", message, retryable: false };
}

function classifyRejection(reason: unknown): BridgeFailure {
  const message = reason instanceof Error ? reason.message : String(reason);
  if (message.includes(ENGINE_STOPPED_MARKER)) {
    return { code: "ENGINE_STOPPED", message, retryable: true };
  }
  return transportFailure(message);
}

function narrowReply<T>(raw: unknown): Reply<T> {
  const failed = errReplySchema.safeParse(raw);
  if (failed.success) {
    return { ok: false, error: failed.data.error };
  }

  const succeeded = okReplySchema.safeParse(raw);
  if (succeeded.success && succeeded.data.result !== undefined) {
    return { ok: true, value: succeeded.data.result as T };
  }

  return {
    ok: false,
    error: transportFailure(`sidecar returned a reply that is neither result nor error`),
  };
}

export function newRequestId(): string {
  return `req-${crypto.randomUUID()}`;
}

export function newThreadId(): string {
  return `th-${crypto.randomUUID()}`;
}

export async function call<T>(
  method: string,
  params: Record<string, unknown>,
  options: { id?: string } = {},
): Promise<Reply<T>> {
  const id = options.id ?? newRequestId();
  try {
    const raw = await invoke("jamly_invoke", { id, method, params });
    return narrowReply<T>(raw);
  } catch (reason) {
    return { ok: false, error: classifyRejection(reason) };
  }
}

export type StreamHandler = (event: StreamEvent) => void;
export type Unsubscribe = () => void;

export async function subscribeStream(
  handler: StreamHandler,
  options: { correlationId?: string } = {},
): Promise<Unsubscribe> {
  const unlisten = await listen(STREAM_EVENT, (event: { payload: unknown }) => {
    const parsed = parseStreamEvent(event.payload);
    if (!parsed) {
      return;
    }
    if (options.correlationId && parsed.correlationId !== options.correlationId) {
      return;
    }
    handler(parsed);
  });
  return unlisten as Unsubscribe;
}

export type ChatMessage = { role: "system" | "user" | "assistant"; content: string };
export type ChatResult = { thread_id: string; model: string; tokens: number };

export type StartedChat = {
  correlationId: string;
  threadId: string;
  reply: Promise<Reply<ChatResult>>;
};

export function startChat(request: {
  messages: ChatMessage[];
  threadId?: string;
  providerId?: string;
  model?: string;
  deadlineSeconds?: number;
}): StartedChat {
  const correlationId = newRequestId();
  const threadId = request.threadId ?? newThreadId();

  const params: Record<string, unknown> = {
    messages: request.messages,
    thread_id: threadId,
  };
  if (request.providerId !== undefined) {
    params.provider_id = request.providerId;
  }
  if (request.model !== undefined) {
    params.model = request.model;
  }
  if (request.deadlineSeconds !== undefined) {
    params.deadline_s = request.deadlineSeconds;
  }

  return {
    correlationId,
    threadId,
    reply: call<ChatResult>("chat.stream", params, { id: correlationId }),
  };
}

export type CancelResult = { thread_id: string; cancelled: number };

export function cancelChat(threadId: string): Promise<Reply<CancelResult>> {
  return call<CancelResult>("chat.cancel", { thread_id: threadId });
}

export async function restartEngine(): Promise<Reply<null>> {
  try {
    await invoke("jamly_restart_engine");
    return { ok: true, value: null };
  } catch (reason) {
    return { ok: false, error: classifyRejection(reason) };
  }
}
