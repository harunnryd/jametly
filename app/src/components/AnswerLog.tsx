type AnswerLogProps = {
  answer: string;
  busy: boolean;
};

export function AnswerLog({ answer, busy }: AnswerLogProps) {
  return (
    <section
      aria-busy={busy}
      aria-label="Answer"
      aria-relevant="additions text"
      className="overlay__answer"
      data-empty={answer.length === 0}
      role="log"
    >
      {answer}
    </section>
  );
}
