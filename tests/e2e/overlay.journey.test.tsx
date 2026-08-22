import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { act } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const invoke = vi.fn();
const listen = vi.fn();
const hide = vi.fn();

vi.mock("@tauri-apps/api/core", () => ({ invoke: (...args: unknown[]) => invoke(...args) }));
vi.mock("@tauri-apps/api/event", () => ({ listen: (...args: unknown[]) => listen(...args) }));
vi.mock("@tauri-apps/api/window", () => ({ getCurrentWindow: () => ({ hide }) }));

const { App } = await import("@/App");

type Sidecar = {
  emit: (payload: Record<string, unknown>) => Promise<void>;
  replies: Map<string, (value: unknown) => void>;
  lastCorrelationId: () => string;
  lastThreadId: () => string;
};

let sidecar: Sidecar;

beforeEach(() => {
  invoke.mockReset();
  listen.mockReset();
  hide.mockReset();

  const replies = new Map<string, (value: unknown) => void>();
  let deliver: (payload: Record<string, unknown>) => void = () => {};
  let lastCorrelationId = "";
  let lastThreadId = "";

  listen.mockImplementation((_name: string, handler: (e: { payload: unknown }) => void) => {
    deliver = (payload) => handler({ payload });
    return Promise.resolve(() => {});
  });

  invoke.mockImplementation((command: string, args?: Record<string, unknown>) => {
    if (command === "jamly_restart_engine") {
      return Promise.resolve(null);
    }

    const { id, method, params } = args as {
      id: string;
      method: string;
      params: Record<string, unknown>;
    };

    if (method === "chat.stream") {
      lastCorrelationId = id;
      lastThreadId = params.thread_id as string;
      return new Promise((resolve) => replies.set(id, resolve));
    }

    if (method === "chat.cancel") {
      const pending = replies.get(lastCorrelationId);
      pending?.({ id: lastCorrelationId, result: { cancelled: true } });
      return Promise.resolve({
        id,
        result: { thread_id: params.thread_id, cancelled: 1 },
      });
    }

    return Promise.resolve({ id, result: {} });
  });

  sidecar = {
    emit: async (payload) => {
      await act(async () => {
        deliver(payload);
      });
    },
    replies,
    lastCorrelationId: () => lastCorrelationId,
    lastThreadId: () => lastThreadId,
  };
});

async function streamAnswer(tokens: string[]) {
  const correlationId = sidecar.lastCorrelationId();
  const threadId = sidecar.lastThreadId();

  await sidecar.emit({
    correlation_id: correlationId,
    kind: "chat.state",
    thread_id: threadId,
    state: "started",
  });
  for (const data of tokens) {
    await sidecar.emit({
      correlation_id: correlationId,
      kind: "chat.token",
      thread_id: threadId,
      data,
    });
  }
  await sidecar.emit({
    correlation_id: correlationId,
    kind: "chat.done",
    thread_id: threadId,
    tokens: tokens.length,
  });
  await act(async () => {
    sidecar.replies.get(correlationId)?.({
      id: correlationId,
      result: { thread_id: threadId, model: "llama3", tokens: tokens.length },
    });
  });
}

describe("asking the overlay a question", () => {
  it("carries a question through to a streamed answer the user can read", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.type(
      screen.getByRole("textbox", { name: /ask/i }),
      "what did they decide about pricing?{Enter}",
    );

    await waitFor(() => expect(invoke).toHaveBeenCalled());
    expect(screen.getByRole("status")).toHaveTextContent(/thinking/i);

    await streamAnswer(["They ", "deferred ", "the ", "pricing ", "call."]);

    expect(screen.getByRole("log", { name: /answer/i })).toHaveTextContent(
      "They deferred the pricing call.",
    );
    expect(screen.getByRole("status")).toHaveTextContent(/complete/i);
  });

  it("replaces the previous answer when the user asks again", async () => {
    const user = userEvent.setup();
    render(<App />);
    const input = screen.getByRole("textbox", { name: /ask/i });

    await user.type(input, "first question{Enter}");
    await waitFor(() => expect(invoke).toHaveBeenCalled());
    await streamAnswer(["first answer"]);

    await user.type(input, "second question{Enter}");
    await waitFor(() => expect(invoke).toHaveBeenCalledTimes(2));
    await streamAnswer(["second answer"]);

    const log = screen.getByRole("log", { name: /answer/i });
    expect(log).toHaveTextContent("second answer");
    expect(log).not.toHaveTextContent("first answer");
  });

  it("lets the user abandon a slow answer and then dismiss the overlay", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.type(screen.getByRole("textbox", { name: /ask/i }), "summarise everything{Enter}");
    await waitFor(() => expect(invoke).toHaveBeenCalled());
    await sidecar.emit({
      correlation_id: sidecar.lastCorrelationId(),
      kind: "chat.token",
      thread_id: sidecar.lastThreadId(),
      data: "Well,",
    });

    await user.keyboard("{Escape}");

    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(/cancelled/i));
    expect(hide).not.toHaveBeenCalled();

    await user.keyboard("{Escape}");

    await waitFor(() => expect(hide).toHaveBeenCalledOnce());
  });

  it("tells the user when the engine has given up and lets them restart it", async () => {
    invoke.mockImplementationOnce(() =>
      Promise.reject("sidecar is stopped after repeated crashes; restart the engine to retry"),
    );
    const user = userEvent.setup();
    render(<App />);

    await user.type(screen.getByRole("textbox", { name: /ask/i }), "anything{Enter}");

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/restart the engine/i);

    await user.click(screen.getByRole("button", { name: /restart/i }));

    await waitFor(() => expect(invoke).toHaveBeenCalledWith("jamly_restart_engine"));
    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
  });
});
