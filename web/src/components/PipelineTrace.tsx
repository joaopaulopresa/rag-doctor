interface Props {
  outcome: string;
  candidates: number | null;
  candidateRank: number | null;
  hasContext: boolean;
  contextSize: number;
  contextRank: number | null;
  scores: { correctness: number; faithfulness: number; citation: number } | null;
}

type State = "pass" | "fail" | "unknown";

/** Where the gold passage was lost: candidates, then context, then the answer. */
export function PipelineTrace({ outcome, candidates, candidateRank, hasContext, contextSize, contextRank, scores }: Props) {
  const color = `var(--o-${outcome})`;
  const stages: { title: string; state: State; headline: string; detail: string }[] = [];

  if (candidates === null) {
    stages.push({
      title: "Search",
      state: "unknown",
      headline: "Not exposed",
      detail: "The system does not return its candidate passages.",
    });
  } else {
    stages.push({
      title: "Search",
      state: candidateRank ? "pass" : "fail",
      headline: candidateRank ? `Gold at rank ${candidateRank}` : "Gold not found",
      detail: candidateRank ? `of ${candidates} candidate passages` : `in any of the ${candidates} candidate passages`,
    });
  }

  if (!hasContext) {
    stages.push({ title: "Context", state: "unknown", headline: "No passages", detail: "The system returned no passages with its answer." });
  } else {
    stages.push({
      title: "Context",
      state: contextRank ? "pass" : "fail",
      headline: contextRank ? `Gold is passage ${contextRank}` : "Gold left out",
      detail: contextRank ? `of the ${contextSize} given to the generator` : `of the ${contextSize} passages given to the generator`,
    });
  }

  const right = scores?.correctness === 2;
  stages.push({
    title: "Answer",
    state: outcome === "correct" ? "pass" : outcome === "wrong_gold" ? "unknown" : right && outcome !== "unsupported" ? "pass" : "fail",
    headline: scores ? `Correctness ${scores.correctness} of 2` : "Not judged",
    detail: scores ? `Faithfulness ${scores.faithfulness} of 2, citations ${scores.citation} of 2 (judge scores)` : "",
  });

  // The doctor blames the first failing stage; later stages are shown but not blamed.
  const blamed = stages.findIndex((s) => s.state === "fail");

  return (
    <ol className="trace" aria-label="Where the answer went wrong">
      {stages.map((stage, index) => {
        const isBlamed = index === blamed && outcome !== "correct";
        return (
          <li key={stage.title} className={`trace-stage ${stage.state}${isBlamed ? " blamed" : ""}`} style={isBlamed ? { borderColor: color } : undefined}>
            <span className="trace-title">{stage.title}</span>
            <span className="trace-mark" style={isBlamed ? { background: color } : undefined} aria-hidden>
              {stage.state === "pass" ? "✓" : stage.state === "fail" ? "✕" : "?"}
            </span>
            <b>{stage.headline}</b>
            <span className="faint">{stage.detail}</span>
            {isBlamed && (
              <span className="trace-blame" style={{ color }}>
                The answer went wrong here
              </span>
            )}
          </li>
        );
      })}
    </ol>
  );
}
