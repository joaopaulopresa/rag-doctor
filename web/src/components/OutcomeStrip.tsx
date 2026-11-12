export const OUTCOME_ORDER = ["correct", "not_retrieved", "ranked_low", "ignored", "unsupported", "wrong_answer", "wrong_gold", "error"];

export const OUTCOME_LABELS: Record<string, string> = {
  correct: "Correct",
  not_retrieved: "Not retrieved",
  ranked_low: "Retrieved, ranked low",
  ignored: "In context, ignored",
  unsupported: "Unsupported",
  wrong_answer: "Wrong answer",
  wrong_gold: "Wrong gold",
  error: "Could not examine",
};

export function OutcomeDot({ outcome }: { outcome: string }) {
  return <span className="dot" style={{ background: `var(--o-${outcome})` }} aria-hidden />;
}

export function OutcomeTag({ outcome }: { outcome: string }) {
  return (
    <span className="tag outcome-tag" style={{ color: `var(--o-${outcome})` }}>
      <OutcomeDot outcome={outcome} />
      <span style={{ color: "var(--ink)" }}>{OUTCOME_LABELS[outcome] ?? outcome}</span>
    </span>
  );
}

interface Props {
  counts: Record<string, number>;
  errors?: number;
  selected?: string | null;
  onSelect?: (outcome: string | null) => void;
  legend?: boolean;
}

/** The breakdown of an examination: one segment per outcome, sized by its count. */
export function OutcomeStrip({ counts, errors = 0, selected, onSelect, legend = true }: Props) {
  const entries = OUTCOME_ORDER.map((o) => [o, o === "error" ? errors : counts[o] ?? 0] as const).filter(([, n]) => n > 0);
  const total = entries.reduce((sum, [, n]) => sum + n, 0);
  if (!total) return null;
  return (
    <div className="strip">
      <div className="strip-bar" role="img" aria-label={entries.map(([o, n]) => `${OUTCOME_LABELS[o]}: ${n}`).join(", ")}>
        {entries.map(([outcome, n]) => (
          <span
            key={outcome}
            style={{ flexGrow: n, background: `var(--o-${outcome})`, opacity: selected && selected !== outcome ? 0.28 : 1 }}
            title={`${OUTCOME_LABELS[outcome]}: ${n}`}
          />
        ))}
      </div>
      {legend && <div className="strip-legend">
        {entries.map(([outcome, n]) => (
          <button
            key={outcome}
            type="button"
            className={`legend-item${selected === outcome ? " on" : ""}`}
            aria-label={`${OUTCOME_LABELS[outcome]}: ${n} (${Math.round((100 * n) / total)}%)`}
            aria-pressed={onSelect ? selected === outcome : undefined}
            onClick={() => onSelect?.(selected === outcome ? null : outcome)}
            disabled={!onSelect}
          >
            <OutcomeDot outcome={outcome} />
            <span>{OUTCOME_LABELS[outcome]}</span>
            <b>{n}</b>
            <span className="faint">{Math.round((100 * n) / total)}%</span>
          </button>
        ))}
      </div>}
    </div>
  );
}
