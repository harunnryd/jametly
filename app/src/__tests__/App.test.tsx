import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { act } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const invoke = vi.fn();
const listen = vi.fn();
const hide = vi.fn();

vi.mock("@tauri-apps/api/core", () => ({ invoke: (...args: unknown[]) => invoke(...args) }));
vi.mock("@tauri-apps/api/event", () => ({ listen: (...args: unknown[]) => listen(...args) }));
vi.mock("@tauri-apps/api/window", () => ({
  getCurrentWindow: () => ({ hide }),
}));

const { App } = await import("@/App");

type Payload = Record<string, unknown>;

let emit: (payload: Payload) => void;
let unlisten: ReturnType<typeof vi.fn>;

beforeEach(() => {
  invoke.mockReset();
  listen.mockReset();
  hide.mockReset();
  unlisten = vi.fn();
  emit = () => {};
  listen.mockImplementation((_name: string, handler: (e: { payload: unknown }) => void) => {
    emit = (payload) => handler({ payload });
    return Promise.resolve(unlisten);
  });
  invoke.mockResolvedValue({ id: "x", result: { thread_id: "th", model: "m", tokens: 0 } });
});

function correlationIdOf(callIndex = 0): string {
  const args = invoke.mock.calls[callIndex]?.[1] as { id: string };
  return args.id;
}

function deferReply(): (value: unknown) => void {
  let resolve: (value: unknown) => void = () => {};
  invoke.mockImplementationOnce(
    () =>
      new Promise((inner) => {
        resolve = inner;
      }),
  );
  return (value) => resolve(value);
}

async function ask(text: string) {
  const user = userEvent.setup();
  const input = screen.getByRole("textbox", { name: /ask/i });
  await user.type(input, `${text}{Enter}`);
  await waitFor(() => expect(invoke).toHaveBeenCalled());
  return user;
}

async function emitting(payload: Payload) {
  await act(async () => {
    emit(payload);
  });
}

describe("overlay accessibility and focus", () => {
  it("labels the prompt and focuses it so the hotkey lands on the input", async () => {
    render(<App />);

    const input = screen.getByRole("textbox", { name: /ask/i });
    await waitFor(() => expect(input).toHaveFocus());
  });

  it("mounts the answer log before any token arrives so it is announced", () => {
    render(<App />);

    const log = screen.getByRole("log", { name: /answer/i });
    expect(log).toBeInTheDocument();
    expect(log).toHaveAttribute("aria-busy", "false");
  });
});

describe("streaming a chat answer", () => {
  it("sends the typed prompt to chat.stream with an explicit thread id", async () => {
    render(<App />);
    await ask("why did revenue dip?");

    expect(invoke).toHaveBeenCalledWith("jamly_invoke", {
      id: expect.any(String),
      method: "chat.stream",
      params: {
        messages: [{ role: "user", content: "why did revenue dip?" }],
        thread_id: expect.stringMatching(/^th-/),
      },
    });
  });

  it("renders tokens in arrival order and settles aria-busy on completion", async () => {
    const settleReply = deferReply();
    render(<App />);
    await ask("hi");
    const correlationId = correlationIdOf();
    const log = screen.getByRole("log", { name: /answer/i });

    await waitFor(() => expect(log).toHaveAttribute("aria-busy", "true"));

    for (const text of ["Revenue ", "dipped ", "12%."]) {
      await emitting({
        correlation_id: correlationId,
        kind: "chat.token",
        thread_id: "th",
        data: text,
      });
    }

    expect(log).toHaveTextContent("Revenue dipped 12%.");

    await emitting({
      correlation_id: correlationId,
      kind: "chat.done",
      thread_id: "th",
      tokens: 3,
    });

    expect(log).toHaveAttribute("aria-busy", "false");
    expect(screen.getByRole("status")).toHaveTextContent(/complete/i);

    await act(async () => {
      settleReply({ id: "x", result: { thread_id: "th", model: "m", tokens: 3 } });
    });
  });

  it("ignores tokens belonging to another request", async () => {
    deferReply();
    render(<App />);
    await ask("hi");
    const correlationId = correlationIdOf();

    await emitting({ correlation_id: correlationId, kind: "chat.token", data: "mine" });
    await emitting({ correlation_id: "someone-else", kind: "chat.token", data: "theirs" });

    const log = screen.getByRole("log", { name: /answer/i });
    expect(log).toHaveTextContent("mine");
    expect(log).not.toHaveTextContent("theirs");
  });

  it("ignores malformed events without breaking the stream", async () => {
    deferReply();
    render(<App />);
    await ask("hi");
    const correlationId = correlationIdOf();

    await emitting({ correlation_id: correlationId, kind: "chat.token", data: "good" });
    await emitting({ kind: "garbage" });
    await emitting({ correlation_id: correlationId, kind: "chat.token", data: 42 });
    await emitting({ correlation_id: correlationId, kind: "chat.token", data: " still good" });

    expect(screen.getByRole("log", { name: /answer/i })).toHaveTextContent("good still good");
  });

  it("treats the reply as authoritative when the done event is dropped", async () => {
    render(<App />);
    await ask("hi");

    await waitFor(() =>
      expect(screen.getByRole("log", { name: /answer/i })).toHaveAttribute("aria-busy", "false"),
    );
    expect(screen.getByRole("status")).toHaveTextContent(/complete/i);
  });
});

describe("superseding an in-flight question", () => {
  it("cancels the previous thread and keeps the new question live", async () => {
    const settleFirst = deferReply();
    render(<App />);
    const user = await ask("first");
    const firstThread = (invoke.mock.calls[0]?.[1] as { params: { thread_id: string } }).params
      .thread_id;

    deferReply();
    deferReply();
    await user.type(screen.getByRole("textbox", { name: /ask/i }), "second{Enter}");

    await waitFor(() =>
      expect(invoke).toHaveBeenCalledWith("jamly_invoke", {
        id: expect.any(String),
        method: "chat.cancel",
        params: { thread_id: firstThread },
      }),
    );
    expect(screen.getByRole("log", { name: /answer/i })).toHaveAttribute("aria-busy", "true");

    await act(async () => {
      settleFirst({ id: "x", result: { thread_id: firstThread, model: "m", tokens: 0 } });
    });
  });

  it("drops tokens from the superseded request", async () => {
    deferReply();
    render(<App />);
    const user = await ask("first");
    const stale = correlationIdOf();

    await emitting({ correlation_id: stale, kind: "chat.token", thread_id: "t", data: "stale" });
    await user.type(screen.getByRole("textbox", { name: /ask/i }), "second{Enter}");
    await emitting({ correlation_id: stale, kind: "chat.token", thread_id: "t", data: "leaked" });

    const log = screen.getByRole("log", { name: /answer/i });
    expect(log).not.toHaveTextContent("leaked");
    expect(log).not.toHaveTextContent("stale");
  });

  it("ignores a stale success reply so the live stream keeps running", async () => {
    const settleFirst = deferReply();
    render(<App />);
    const user = await ask("first");
    const firstThread = (invoke.mock.calls[0]?.[1] as { params: { thread_id: string } }).params
      .thread_id;

    deferReply();
    deferReply();
    await user.type(screen.getByRole("textbox", { name: /ask/i }), "second{Enter}");
    await waitFor(() => expect(invoke).toHaveBeenCalledTimes(3));

    await act(async () => {
      settleFirst({ id: "x", result: { thread_id: firstThread, model: "m", tokens: 1 } });
    });

    expect(screen.getByRole("log", { name: /answer/i })).toHaveAttribute("aria-busy", "true");
    expect(screen.getByRole("status")).toHaveTextContent(/thinking/i);
  });
});

describe("timeout handling", () => {
  it("terminates the stream when the sidecar reports a timeout state", async () => {
    deferReply();
    render(<App />);
    await ask("hi");

    await emitting({
      correlation_id: correlationIdOf(),
      kind: "chat.state",
      thread_id: "t",
      state: "timeout",
    });

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("PYTHON_TIMEOUT");
    expect(screen.getByRole("log", { name: /answer/i })).toHaveAttribute("aria-busy", "false");
  });

  it("reports one failure when the timeout event and the timeout reply both arrive", async () => {
    const settleReply = deferReply();
    render(<App />);
    await ask("hi");
    const correlationId = correlationIdOf();

    await emitting({
      correlation_id: correlationId,
      kind: "chat.state",
      thread_id: "t",
      state: "timeout",
    });
    await act(async () => {
      settleReply({
        id: correlationId,
        error: { code: "PYTHON_TIMEOUT", message: "deadline exceeded", retryable: true },
      });
    });

    expect(screen.getAllByRole("alert")).toHaveLength(1);
  });

  it("keeps a cancelled stream cancelled when a failing reply lands afterwards", async () => {
    const settleReply = deferReply();
    render(<App />);
    const user = await ask("hi");
    const correlationId = correlationIdOf();

    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(/cancelled/i));

    await act(async () => {
      settleReply({
        id: correlationId,
        error: { code: "PYTHON_TIMEOUT", message: "deadline exceeded", retryable: true },
      });
    });

    expect(screen.getByRole("status")).toHaveTextContent(/cancelled/i);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

describe("retryability", () => {
  it("preserves retryability for a streamed provider error", async () => {
    deferReply();
    render(<App />);
    await ask("hi");

    await emitting({
      correlation_id: correlationIdOf(),
      kind: "chat.error",
      thread_id: "t",
      code: "PROVIDER_RATE_LIMIT",
      message: "slow down",
    });

    expect(await screen.findByRole("alert")).toHaveTextContent("PROVIDER_RATE_LIMIT");
    expect(screen.getByRole("alert")).toHaveAttribute("data-retryable", "true");
  });
});

describe("failure states", () => {
  it("surfaces a streamed error with its code", async () => {
    invoke.mockResolvedValue({
      id: "x",
      error: { code: "PROVIDER_UNAVAILABLE", message: "ollama is not running", retryable: true },
    });
    render(<App />);
    await ask("hi");

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("ollama is not running");
    expect(alert).toHaveTextContent("PROVIDER_UNAVAILABLE");
  });

  it("offers an engine restart when the sidecar has stopped", async () => {
    invoke.mockRejectedValueOnce(
      "sidecar is stopped after repeated crashes; restart the engine to retry",
    );
    render(<App />);
    const user = await ask("hi");

    const restart = await screen.findByRole("button", { name: /restart/i });
    invoke.mockResolvedValueOnce(null);
    await user.click(restart);

    expect(invoke).toHaveBeenCalledWith("jamly_restart_engine");
  });
});

describe("dismissal and cancellation", () => {
  it("cancels the in-flight stream on Escape instead of hiding", async () => {
    let resolveReply: (value: unknown) => void = () => {};
    invoke.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveReply = resolve;
        }),
    );
    render(<App />);
    const user = await ask("hi");

    await user.keyboard("{Escape}");

    await waitFor(() =>
      expect(invoke).toHaveBeenCalledWith("jamly_invoke", {
        id: expect.any(String),
        method: "chat.cancel",
        params: { thread_id: expect.stringMatching(/^th-/) },
      }),
    );
    expect(hide).not.toHaveBeenCalled();

    await act(async () => {
      resolveReply({ id: "x", result: { thread_id: "th", model: "m", tokens: 0 } });
    });
  });

  it("hides the overlay on Escape when idle", async () => {
    render(<App />);
    const user = userEvent.setup();

    await user.keyboard("{Escape}");

    await waitFor(() => expect(hide).toHaveBeenCalledOnce());
  });
});

describe("listener lifecycle", () => {
  it("unsubscribes from the sidecar event stream on unmount", async () => {
    const { unmount } = render(<App />);
    await waitFor(() => expect(listen).toHaveBeenCalled());

    unmount();

    await waitFor(() => expect(unlisten).toHaveBeenCalled());
  });
});
