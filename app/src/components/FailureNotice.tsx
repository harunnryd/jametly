import type { BridgeFailure } from "@/lib/bridge";

type FailureNoticeProps = {
  failure: BridgeFailure;
  onRestart: () => void;
};

export function FailureNotice({ failure, onRestart }: FailureNoticeProps) {
  return (
    <div className="overlay__failure" data-retryable={failure.retryable} role="alert">
      <span className="overlay__failure-code">{failure.code}</span>
      <span className="overlay__failure-message">{failure.message}</span>
      {failure.code === "ENGINE_STOPPED" ? (
        <button className="overlay__restart" onClick={onRestart} type="button">
          Restart engine
        </button>
      ) : null}
    </div>
  );
}
