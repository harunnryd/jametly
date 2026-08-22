import { useCallback, useEffect, useRef, useState } from "react";
import {
  cancelChat,
  restartEngine,
  startChat,
  subscribeStream,
  type BridgeFailure,
  type StreamEvent,
} from "@/lib/bridge";

export type StreamStatus = "idle" | "streaming" | "complete" | "cancelled" | "error";

export type ChatStream = {
  status: StreamStatus;
  answer: string;
  failure: BridgeFailure | null;
  submit: (prompt: string) => void;
  cancel: () => void;
  restart: () => void;
};

type Active = { correlationId: string; threadId: string };

export function useChatStream(): ChatStream {
  const [status, setStatus] = useState<StreamStatus>("idle");
  const [answer, setAnswer] = useState("");
  const [failure, setFailure] = useState<BridgeFailure | null>(null);
  const active = useRef<Active | null>(null);

  const handleEvent = useCallback((event: StreamEvent) => {
    if (event.correlationId !== active.current?.correlationId) {
      return;
    }

    switch (event.kind) {
      case "token":
        setAnswer((previous) => previous + event.text);
        return;
      case "done":
        setStatus((previous) => (previous === "streaming" ? "complete" : previous));
        return;
      case "error":
        setFailure({ code: event.code, message: event.message, retryable: false });
        setStatus("error");
        return;
      case "cancelled":
        setStatus("cancelled");
        return;
      default:
        return;
    }
  }, []);

  useEffect(() => {
    let disposed = false;
    let unsubscribe: (() => void) | undefined;

    void subscribeStream(handleEvent).then((stop) => {
      if (disposed) {
        stop();
        return;
      }
      unsubscribe = stop;
    });

    return () => {
      disposed = true;
      unsubscribe?.();
    };
  }, [handleEvent]);

  const submit = useCallback((prompt: string) => {
    const trimmed = prompt.trim();
    if (trimmed.length === 0) {
      return;
    }

    const started = startChat({ messages: [{ role: "user", content: trimmed }] });
    active.current = { correlationId: started.correlationId, threadId: started.threadId };
    setAnswer("");
    setFailure(null);
    setStatus("streaming");

    void started.reply.then((reply) => {
      if (active.current?.correlationId !== started.correlationId) {
        return;
      }
      if (!reply.ok) {
        setFailure(reply.error);
        setStatus("error");
        return;
      }
      setStatus((previous) => (previous === "streaming" ? "complete" : previous));
    });
  }, []);

  const cancel = useCallback(() => {
    const current = active.current;
    if (!current) {
      return;
    }
    void cancelChat(current.threadId);
    setStatus("cancelled");
  }, []);

  const restart = useCallback(() => {
    void restartEngine().then((reply) => {
      if (reply.ok) {
        setFailure(null);
        setStatus("idle");
      } else {
        setFailure(reply.error);
      }
    });
  }, []);

  return { status, answer, failure, submit, cancel, restart };
}
