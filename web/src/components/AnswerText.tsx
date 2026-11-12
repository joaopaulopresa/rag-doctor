import { splitCitations } from "./citations";

interface Props {
  text: string;
  passages: number;
  active?: number | null;
  onCite: (number: number) => void;
}

/** An answer whose [n] markers open the passage they cite. Markers that match no passage stay plain. */
export function AnswerText({ text, passages, active, onCite }: Props) {
  return (
    <p className="answer-text">
      {splitCitations(text).map((segment, index) =>
        segment.kind === "text" ? (
          <span key={index}>{segment.text}</span>
        ) : (
          <span key={index} className="cites">
            {segment.numbers.map((number) =>
              number >= 1 && number <= passages ? (
                <button
                  key={number}
                  type="button"
                  className={`cite${active === number ? " on" : ""}`}
                  onClick={() => onCite(number)}
                  aria-label={`Open source ${number}`}
                >
                  {number}
                </button>
              ) : (
                <span key={number} className="cite invalid" title="This citation matches no passage">
                  {number}
                </span>
              ),
            )}
          </span>
        ),
      )}
    </p>
  );
}
