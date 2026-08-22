import { useCallback, useEffect, useRef, useState } from "react";
import {
  cancelChat,
  restartEngine,
  startChat,
  subscribeStream,
  type BridgeFailure,
  type ErrorCode,
  type StreamEvent,
} from "@/lib/bridge";

export type StreamStatus = "idle" | "streaming" | "complete" | "cancelled" | "error";

type Terminal = Exclude<StreamStatus, "idle" | "streaming">;

type Flight = {
  generation: number;
  correlationId: string;
  threadId: string;
  terminal: Terminal | null;
};

export type ChatStream = {
  status: StreamStatus;
  answer: string;
  failure: BridgeFailure | null;
  submit: (prompt: string) => void;
  cancel: () => void;
  restart: () => void;
};

const RETRYABLE_CODES: ReadonlySet<ErrorCode> = new Set<ErrorCode>([
  "PROVIDER_RATE_LIMIT",
  "PROVIDER_UNAVAILABLE",
  "PYTHON_TIMEOUT",
  "AUDIO_DEVICE_LOST",
]);

const TIMEOUT_FAILURE: BridgeFailure = {
  code: "PYTHON_TIMEOUT",
  message: "the engine took too long to answer",
  retryable: true,
};

export function useChatStream(): ChatStream {
  const [status, setStatus] = useState<StreamStatus>("idle");
  const [answer, setAnswer] = useState("");
  const [failure, setFailure] = useState<BridgeFailure | null>(null);
  const flight = useRef<Flight | null>(null);
  const generation = useRef(0);

  const settle = useCallback((target: Flight, next: Terminal, reason: BridgeFailure | null) => {
    target.terminal = next;
    if (reason) {
      setFailure(reason);
    }
    setStatus(next);
  }, []);

  const ownedBy = useCallback((correlationId: string): Flight | null => {
    const current = flight.current;
    if (!current || current.generation !== generation.current) {
      return null;
    }
    if (current.correlationId !== correlationId || current.terminal !== null) {
      return null;
    }
    return current;
  }, []);

  const handleEvent = useCallback(
    (event: StreamEvent) => {
      const current = ownedBy(event.correlationId);
      if (!current) {
        return;
      }

      switch (event.kind) {
        case "token":
          setAnswer((previous) => previous + event.text);
          return;
        case "state":
          if (event.state === "timeout") {
            settle(current, "error", TIMEOUT_FAILURE);
          }
          return;
        case "done":
          settle(current, "complete", null);
          return;
        case "error":
          settle(current, "error", {
            code: event.code,
            message: event.message,
            retryable: RETRYABLE_CODES.has(event.code),
          });
          return;
        case "cancelled":
          settle(current, "cancelled", null);
          return;
        default:
          return;
      }
    },
    [ownedBy, settle],
  );

  useEffect(() => {
    let disposed = false;
    let unsubscribe: (() => void) | undefined;

    void subscribeStream(handleEvent)
      .then((stop) => {
        if (disposed) {
          stop();
          return;
        }
        unsubscribe = stop;
      })
      .catch((reason: unknown) => {
        if (disposed) {
          return;
        }
        setFailure({
          code: "TRANSPORT",
          message: reason instanceof Error ? reason.message : String(reason),
          retryable: true,
        });
      });

    return () => {
      disposed = true;
      unsubscribe?.();
    };
  }, [handleEvent]);

  const abandon = useCallback((target: Flight | null) => {
    if (!target || target.terminal !== null) {
      return;
    }
    target.terminal = "cancelled";
    void cancelChat(target.threadId);
  }, []);

  const submit = useCallback(
    (prompt: string) => {
      const trimmed = prompt.trim();
      if (trimmed.length === 0) {
        return;
      }

      abandon(flight.current);

      const started = startChat({ messages: [{ role: "user", content: trimmed }] });
      generation.current += 1;
      const mine: Flight = {
        generation: generation.current,
        correlationId: started.correlationId,
        threadId: started.threadId,
        terminal: null,
      };
      flight.current = mine;

      setAnswer("");
      setFailure(null);
      setStatus("streaming");

      void started.reply.then((reply) => {
        if (flight.current !== mine || mine.generation !== generation.current) {
          return;
        }
        if (mine.terminal === "cancelled") {
          return;
        }
        if (!reply.ok) {
          settle(mine, "error", reply.error);
          return;
        }
        if (mine.terminal === null) {
          settle(mine, "complete", null);
        }
      });
    },
    [abandon, settle],
  );

  const cancel = useCallback(() => {
    const current = flight.current;
    if (!current || current.terminal !== null) {
      return;
    }
    void cancelChat(current.threadId);
    settle(current, "cancelled", null);
  }, [settle]);

  const restart = useCallback(() => {
    abandon(flight.current);
    generation.current += 1;
    flight.current = null;
    setAnswer("");
    setFailure(null);
    setStatus("idle");

    void restartEngine().then((reply) => {
      if (!reply.ok) {
        setFailure(reply.error);
      }
    });
  }, [abandon]);

  return { status, answer, failure, submit, cancel, restart };
}
