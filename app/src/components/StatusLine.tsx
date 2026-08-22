import type { StreamStatus } from "@/hooks/useChatStream";

const MESSAGES: Record<StreamStatus, string> = {
  idle: "",
  streaming: "Thinking…",
  complete: "Answer complete",
  cancelled: "Cancelled",
  error: "",
};

export function StatusLine({ status }: { status: StreamStatus }) {
  return (
    <p className="overlay__status" role="status">
      {MESSAGES[status]}
    </p>
  );
}
