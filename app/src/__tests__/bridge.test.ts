import { beforeEach, describe, expect, it, vi } from "vitest";

const invoke = vi.fn();
const listen = vi.fn();

vi.mock("@tauri-apps/api/core", () => ({ invoke: (...args: unknown[]) => invoke(...args) }));
vi.mock("@tauri-apps/api/event", () => ({ listen: (...args: unknown[]) => listen(...args) }));

const {
  STREAM_EVENT,
  call,
  cancelChat,
  newThreadId,
  parseStreamEvent,
  restartEngine,
  startChat,
  subscribeStream,
} = await import("@/lib/bridge");

beforeEach(() => {
  invoke.mockReset();
  listen.mockReset();
  listen.mockResolvedValue(() => {});
});

describe("parseStreamEvent", () => {
  it("maps chat token events onto the unified model", () => {
    expect(
      parseStreamEvent({
        correlation_id: "req-1",
        kind: "chat.token",
        thread_id: "th-1",
        data: "hello",
      }),
    ).toEqual({
      family: "chat",
      kind: "token",
      correlationId: "req-1",
      threadId: "th-1",
      text: "hello",
    });
  });

  it("maps ask tokens and bare debug tokens onto the same kind", () => {
    const ask = parseStreamEvent({
      correlation_id: "req-2",
      kind: "ask.token",
      thread_id: "th-2",
      data: "a",
    });
    const debug = parseStreamEvent({ correlation_id: "req-3", kind: "token", data: "b" });

    expect(ask).toMatchObject({ family: "ask", kind: "token", text: "a" });
    expect(debug).toMatchObject({ family: "stream", kind: "token", text: "b" });
  });

  it("maps state, done, error, and cancelled terminals", () => {
    expect(
      parseStreamEvent({
        correlation_id: "r",
        kind: "chat.state",
        thread_id: "t",
        state: "completed",
      }),
    ).toMatchObject({ kind: "state", state: "completed" });

    expect(
      parseStreamEvent({ correlation_id: "r", kind: "chat.done", thread_id: "t", tokens: 7 }),
    ).toMatchObject({ kind: "done", tokens: 7 });

    expect(
      parseStreamEvent({
        correlation_id: "r",
        kind: "chat.error",
        thread_id: "t",
        code: "PROVIDER_UNAVAILABLE",
        message: "no ollama",
      }),
    ).toMatchObject({ kind: "error", code: "PROVIDER_UNAVAILABLE", message: "no ollama" });

    expect(parseStreamEvent({ correlation_id: "r", kind: "cancelled" })).toMatchObject({
      kind: "cancelled",
      correlationId: "r",
      threadId: null,
    });
  });

  it("rejects malformed events instead of surfacing partial state", () => {
    expect(parseStreamEvent(null)).toBeNull();
    expect(parseStreamEvent("token")).toBeNull();
    expect(parseStreamEvent({ kind: "chat.token", data: "x" })).toBeNull();
    expect(parseStreamEvent({ correlation_id: "r", kind: "chat.token" })).toBeNull();
    expect(parseStreamEvent({ correlation_id: "r", kind: "chat.done", tokens: "seven" })).toBeNull();
    expect(parseStreamEvent({ correlation_id: "r", kind: "unheard.of" })).toBeNull();
    expect(
      parseStreamEvent({ correlation_id: "r", kind: "chat.error", code: "NOPE", message: "m" }),
    ).toBeNull();
  });
});

describe("call", () => {
  it("narrows an untagged ok reply", async () => {
    invoke.mockResolvedValue({ id: "req-1", result: { thread_id: "th-1", tokens: 3 } });

    const reply = await call("chat.stream", { messages: [] }, { id: "req-1" });

    expect(invoke).toHaveBeenCalledWith("jamly_invoke", {
      id: "req-1",
      method: "chat.stream",
      params: { messages: [] },
    });
    expect(reply).toEqual({ ok: true, value: { thread_id: "th-1", tokens: 3 } });
  });

  it("narrows an untagged error reply into the typed failure", async () => {
    invoke.mockResolvedValue({
      id: "req-1",
      error: { code: "PROVIDER_AUTH", message: "bad key", retryable: false },
    });

    const reply = await call("chat.stream", {});

    expect(reply).toEqual({
      ok: false,
      error: { code: "PROVIDER_AUTH", message: "bad key", retryable: false },
    });
  });

  it("classifies the stopped engine so the UI can offer a restart", async () => {
    invoke.mockRejectedValue(
      "sidecar is stopped after repeated crashes; restart the engine to retry",
    );

    const reply = await call("chat.stream", {});

    expect(reply.ok).toBe(false);
    if (reply.ok) return;
    expect(reply.error.code).toBe("ENGINE_STOPPED");
    expect(reply.error.retryable).toBe(true);
  });

  it("classifies any other rejection as a transport failure", async () => {
    invoke.mockRejectedValue("sidecar stdin write failed: broken pipe");

    const reply = await call("chat.stream", {});

    expect(reply).toMatchObject({ ok: false, error: { code: "TRANSPORT", retryable: false } });
  });

  it("rejects a reply that is neither ok nor error", async () => {
    invoke.mockResolvedValue({ id: "req-1" });

    const reply = await call("chat.stream", {});

    expect(reply).toMatchObject({ ok: false, error: { code: "TRANSPORT" } });
  });
});

describe("subscribeStream", () => {
  it("listens on the sidecar event name and forwards only well-formed events", async () => {
    let emit: (event: { payload: unknown }) => void = () => {};
    listen.mockImplementation((_name: string, handler: (e: { payload: unknown }) => void) => {
      emit = handler;
      return Promise.resolve(() => {});
    });

    const seen: string[] = [];
    await subscribeStream((event) => {
      seen.push(event.kind);
    });

    expect(listen).toHaveBeenCalledWith(STREAM_EVENT, expect.any(Function));

    emit({ payload: { correlation_id: "r", kind: "chat.token", thread_id: "t", data: "a" } });
    emit({ payload: { kind: "garbage" } });
    emit({ payload: { correlation_id: "r", kind: "chat.done", thread_id: "t", tokens: 1 } });

    expect(seen).toEqual(["token", "done"]);
  });

  it("filters to one correlation id when asked", async () => {
    let emit: (event: { payload: unknown }) => void = () => {};
    listen.mockImplementation((_name: string, handler: (e: { payload: unknown }) => void) => {
      emit = handler;
      return Promise.resolve(() => {});
    });

    const seen: string[] = [];
    await subscribeStream(
      (event) => {
        seen.push(event.correlationId);
      },
      { correlationId: "mine" },
    );

    emit({ payload: { correlation_id: "mine", kind: "chat.token", thread_id: "t", data: "a" } });
    emit({ payload: { correlation_id: "other", kind: "chat.token", thread_id: "t", data: "b" } });

    expect(seen).toEqual(["mine"]);
  });

  it("returns the unlisten handle so callers can clean up", async () => {
    const unlisten = vi.fn();
    listen.mockResolvedValue(unlisten);

    const stop = await subscribeStream(() => {});
    stop();

    expect(unlisten).toHaveBeenCalledOnce();
  });
});

describe("startChat", () => {
  it("always sends an explicit thread id so cancel has a target", async () => {
    invoke.mockResolvedValue({ id: "req-1", result: { thread_id: "th-mine", tokens: 1 } });

    await startChat({ messages: [{ role: "user", content: "hi" }], threadId: "th-mine" });

    const params = invoke.mock.calls[0]?.[1] as { params: Record<string, unknown> };
    expect(params.params.thread_id).toBe("th-mine");
    expect(params.params.messages).toEqual([{ role: "user", content: "hi" }]);
  });

  it("generates a thread id when the caller omits one", async () => {
    invoke.mockResolvedValue({ id: "req-1", result: { thread_id: "th-x", tokens: 1 } });

    await startChat({ messages: [{ role: "user", content: "hi" }] });

    const params = invoke.mock.calls[0]?.[1] as { params: Record<string, unknown> };
    expect(params.params.thread_id).toMatch(/^th-/);
  });

  it("returns the correlation id it used so the caller can filter events", async () => {
    invoke.mockResolvedValue({ id: "req-1", result: { thread_id: "th-x", tokens: 1 } });

    const started = startChat({ messages: [{ role: "user", content: "hi" }] });
    const { correlationId } = started;
    const params = invoke.mock.calls[0]?.[1] as { id: string };

    expect(correlationId).toBe(params.id);
    await started.reply;
  });
});

describe("cancelChat and restartEngine", () => {
  it("cancels by thread id", async () => {
    invoke.mockResolvedValue({ id: "req-2", result: { thread_id: "th-1", cancelled: 1 } });

    const reply = await cancelChat("th-1");

    expect(invoke).toHaveBeenCalledWith("jamly_invoke", {
      id: expect.any(String),
      method: "chat.cancel",
      params: { thread_id: "th-1" },
    });
    expect(reply).toMatchObject({ ok: true });
  });

  it("restarts the engine through its own command", async () => {
    invoke.mockResolvedValue(null);

    await restartEngine();

    expect(invoke).toHaveBeenCalledWith("jamly_restart_engine");
  });
});

describe("newThreadId", () => {
  it("mints distinct prefixed ids", () => {
    expect(newThreadId()).not.toBe(newThreadId());
    expect(newThreadId()).toMatch(/^th-/);
  });
});
