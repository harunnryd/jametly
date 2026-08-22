import { useEffect, useRef, useState } from "react";

type AskInputProps = {
  busy: boolean;
  onSubmit: (prompt: string) => void;
};

export function AskInput({ busy, onSubmit }: AskInputProps) {
  const [value, setValue] = useState("");
  const field = useRef<HTMLInputElement>(null);

  useEffect(() => {
    field.current?.focus();
  }, []);

  return (
    <div className="overlay__row">
      <label className="overlay__label" htmlFor="ask-prompt">
        Ask jametly about this meeting
      </label>
      <input
        ref={field}
        id="ask-prompt"
        className="overlay__input"
        type="text"
        autoComplete="off"
        spellCheck={false}
        placeholder="Ask jametly…"
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={(event) => {
          if (event.key !== "Enter" || event.nativeEvent.isComposing) {
            return;
          }
          event.preventDefault();
          onSubmit(value);
          setValue("");
        }}
      />
      {busy ? (
        <span aria-hidden="true" className="overlay__pulse" />
      ) : null}
    </div>
  );
}
