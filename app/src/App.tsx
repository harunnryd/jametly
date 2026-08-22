import { getCurrentWindow } from "@tauri-apps/api/window";
import { useCallback, useEffect } from "react";
import { AnswerLog } from "@/components/AnswerLog";
import { AskInput } from "@/components/AskInput";
import { FailureNotice } from "@/components/FailureNotice";
import { StatusLine } from "@/components/StatusLine";
import { useChatStream } from "@/hooks/useChatStream";
import "@/styles/overlay.css";

export function App() {
  const { status, answer, failure, submit, cancel, restart } = useChatStream();
  const streaming = status === "streaming";

  const dismiss = useCallback(() => {
    if (streaming) {
      cancel();
      return;
    }
    void getCurrentWindow().hide();
  }, [cancel, streaming]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") {
        return;
      }
      event.preventDefault();
      dismiss();
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [dismiss]);

  return (
    <main className="overlay" data-status={status}>
      <AskInput busy={streaming} onSubmit={submit} />
      <StatusLine status={status} />
      <AnswerLog answer={answer} busy={streaming} />
      {failure ? <FailureNotice failure={failure} onRestart={restart} /> : null}
    </main>
  );
}
