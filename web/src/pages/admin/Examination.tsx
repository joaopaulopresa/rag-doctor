import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, pct, usd } from "../../api";
import { ConfigLine } from "../../components/ConfigLine";
import { JobProgress } from "../../components/JobProgress";
import { OUTCOME_LABELS, OutcomeTag, OutcomeStrip } from "../../components/OutcomeStrip";
import type { CaseBrief, ConfigurationDescription, Examination as ExaminationType, Experiment, ExaminationSummary, PrescriptionItem } from "../../types";

interface Detail {
  examination: ExaminationType;
  experiments: Pick<Experiment, "id" | "name" | "purpose" | "job" | "summary">[];
  followups: ExaminationType[];
}

const STAGE_TEXT: Record<string, string> = {
  retrieval: "Retrieval",
  ranking: "Ranking",
  generation: "Generation",
  unknown: "Cannot be located",
};

function Recommendation({ experiment, onApplied }: { experiment: Detail["experiments"][number]; onApplied: () => void }) {
  const [busy, setBusy] = useState(false);
  const [applied, setApplied] = useState("");
  const rec = experiment.summary.recommendation;
  const rows = experiment.summary.answers ?? [];
  if (!rec) return null;
  const apply = async () => {
    setBusy(true);
    try {
      await api("/api/admin/configurations/apply", {
        method: "POST",
        json: { spec: rec.spec, name: rec.display.split(" -> ")[0], note: `Recommended by experiment #${experiment.id}`, origin: `experiment #${experiment.id}` },
      });
      setApplied(rec.display);
      onApplied();
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="stack">
      <table className="compact-table">
        <thead>
          <tr>
            <th>Configuration measured on these questions</th>
            <th className="num">Judge correctness</th>
            <th className="num">95% interval</th>
            <th className="num">Per 1,000 answers</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.config_key} className={row.config_key === rec.config_key ? "chosen" : ""}>
              <td>{row.configuration}</td>
              <td className="num">{pct(row.correctness, 1)}</td>
              <td className="num faint">
                {pct(row.correctness_low)} to {pct(row.correctness_high)}
              </td>
              <td className="num">{usd(row.cost_per_1k_answers_usd, 2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="spread">
        <p className="muted grow">
          <b>Measured winner:</b> {rec.display}. {rec.reason}
        </p>
        {applied ? (
          <span className="tag pen">Applied to the chat</span>
        ) : (
          <button className="primary" onClick={() => void apply()} disabled={busy}>
            Apply to the chat
          </button>
        )}
      </div>
      <p className="faint">
        Judge correctness is the mean of the judge's 0 to 2 score, scaled to 0 to 100%. <Link to={`/admin/experiments/${experiment.id}`}>Full experiment</Link>
      </p>
    </div>
  );
}

function PrescriptionRow({
  item,
  summary,
  experiment,
  onStart,
  onChange,
}: {
  item: PrescriptionItem;
  summary: ExaminationSummary;
  experiment?: Detail["experiments"][number];
  onStart: (outcome: string) => void;
  onChange: () => void;
}) {
  return (
    <li className="rx">
      <div className="rx-head spread">
        <div className="row">
          <OutcomeTag outcome={item.outcome} />
          <span className="muted">
            {item.count} of {summary.evaluated} questions ({pct(item.share)})
          </span>
        </div>
        <span className="faint">Failing stage: {STAGE_TEXT[item.stage] ?? item.stage}</span>
      </div>
      <p>
        Candidate fixes to measure: {item.candidates.join(", ")}.
      </p>
      {item.plan && (
        <div className="rx-plan">
          <p className="muted">{item.plan.description}</p>
          {experiment ? (
            experiment.job && experiment.job.status !== "done" ? (
              <JobProgress job={experiment.job} onFinish={onChange} />
            ) : (
              <Recommendation experiment={experiment} onApplied={onChange} />
            )
          ) : (
            <div>
              <button className="primary" onClick={() => onStart(item.outcome)}>
                Run this experiment
              </button>
            </div>
          )}
        </div>
      )}
      {item.same_plan_as && <p className="faint">Measured by the same experiment as “{OUTCOME_LABELS[item.same_plan_as]}”.</p>}
    </li>
  );
}

export default function Examination() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [detail, setDetail] = useState<Detail | null>(null);
  const [cases, setCases] = useState<CaseBrief[]>([]);
  const [filter, setFilter] = useState<string | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api<Detail>(`/api/admin/examinations/${id}`)
      .then(setDetail)
      .catch((e: Error) => setError(e.message));
    api<{ cases: CaseBrief[] }>(`/api/admin/examinations/${id}/cases`).then((d) => setCases(d.cases));
  }, [id]);
  useEffect(load, [load]);

  if (error) return <p className="notice error">{error}</p>;
  if (!detail) return <p className="row muted page"><span className="spinner" /> Loading</p>;

  const { examination, experiments, followups } = detail;
  const running = examination.job && examination.job.status !== "done";
  const summary = "counts" in examination.summary ? (examination.summary as ExaminationSummary) : null;
  const shown = filter ? cases.filter((c) => c.outcome === filter) : cases;
  const experimentFor = (item: PrescriptionItem) =>
    experiments.find((e) => item.plan && e.purpose === item.plan.description);

  const startExperiment = async (outcome: string) => {
    await api(`/api/admin/examinations/${examination.id}/experiments`, { method: "POST", json: { outcome } });
    load();
  };

  const reexamine = async () => {
    const data = await api<{ examination: ExaminationType }>("/api/admin/examinations", {
      method: "POST",
      json: { target: examination.target_kind, external_system_id: examination.external_system_id, same_questions_as: examination.id },
    });
    navigate(`/admin/doctor/${data.examination.id}`);
  };

  return (
    <div className="page">
      <header className="page-head">
        <p className="faint">
          <Link to="/admin/doctor">Doctor</Link> / Examination #{examination.id}
        </p>
        <div className="spread">
          <h1>{examination.label}</h1>
          {examination.baseline_id && summary && (
            <Link className="button" to={`/admin/compare?before=${examination.baseline_id}&after=${examination.id}`}>
              Compare with #{examination.baseline_id}
            </Link>
          )}
        </div>
        {examination.target_kind === "own" ? (
          <ConfigLine config={examination.target as unknown as ConfigurationDescription} />
        ) : (
          <p className="muted">
            External system at <code>{examination.target.url}</code>. Diagnosis is limited to what it returns.
          </p>
        )}
      </header>

      {running && examination.job && (
        <section className="panel pad">
          <JobProgress job={examination.job} onFinish={load} />
        </section>
      )}

      {summary && (
        <>
          <section className="panel pad findings">
            <div className="findings-head">
              <div>
                <span className="faint">Correct</span>
                <b className="big-number">{pct(summary.correct_rate)}</b>
                <span className="faint">
                  95% interval {pct(summary.correct_low)} to {pct(summary.correct_high)}
                </span>
              </div>
              <div>
                <span className="faint">Questions</span>
                <b className="big-number">{summary.evaluated}</b>
                <span className="faint">
                  {summary.total - summary.evaluated - summary.errors > 0 ? `${summary.total - summary.evaluated - summary.errors} marked wrong gold` : "none marked wrong gold"}
                  {summary.errors ? `, ${summary.errors} could not be examined` : ""}
                </span>
              </div>
              <div>
                <span className="faint">Paid for this run</span>
                <b className="big-number">{usd(summary.paid_usd, 3)}</b>
                <span className="faint">judge included; cached calls are free</span>
              </div>
            </div>
            <OutcomeStrip counts={summary.counts} errors={summary.errors} selected={filter} onSelect={setFilter} />
            <p className="faint">
              Correct means the judge gave full correctness and the main claim is supported by the passages. Scores come from an LLM judge and
              have not been validated against human labels yet.
            </p>
          </section>

          <section className="section">
            <div className="spread">
              <h2>Prescription</h2>
              {examination.target_kind === "own" && (
                <button onClick={() => void reexamine()}>Re-examine the active configuration on these questions</button>
              )}
            </div>
            {summary.prescription.length === 0 ? (
              <div className="panel empty">
                <p>Every examined answer is correct. Nothing to prescribe.</p>
              </div>
            ) : (
              <ol className="rx-list">
                {summary.prescription.map((item) => (
                  <PrescriptionRow key={item.outcome} item={item} summary={summary} experiment={experimentFor(item)} onStart={(o) => void startExperiment(o)} onChange={load} />
                ))}
              </ol>
            )}
            {examination.target_kind === "external" && (
              <p className="faint">
                For an external system the doctor names the failing stage but cannot run experiments on it: its code and settings are not
                reachable from here.
              </p>
            )}
            {followups.length > 0 && (
              <div className="panel pad stack">
                <h3>Re-examinations on the same questions</h3>
                {followups.map((f) => (
                  <div key={f.id} className="spread">
                    <span>
                      #{f.id} {f.label}
                    </span>
                    {f.job?.status === "done" ? (
                      <Link className="button primary" to={`/admin/compare?before=${examination.id}&after=${f.id}`}>
                        Open the before/after report
                      </Link>
                    ) : (
                      f.job && <JobProgress job={f.job} onFinish={load} />
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="section">
            <div className="spread">
              <h2>Cases{filter ? `: ${OUTCOME_LABELS[filter]}` : ""}</h2>
              {filter && (
                <button className="quiet" onClick={() => setFilter(null)}>
                  Show all {cases.length}
                </button>
              )}
            </div>
            <div className="panel">
              <table>
                <thead>
                  <tr>
                    <th>Question</th>
                    <th>Outcome</th>
                    <th className="num">Gold in candidates</th>
                    <th className="num">Gold in context</th>
                  </tr>
                </thead>
                <tbody>
                  {shown.map((c) => (
                    <tr key={c.id} className="clickable" onClick={() => navigate(`/admin/cases/${c.id}`)}>
                      <td>
                        <Link to={`/admin/cases/${c.id}`}>{c.question}</Link>
                        <div className="faint">{c.question_id}</div>
                      </td>
                      <td>
                        <OutcomeTag outcome={c.outcome} />
                      </td>
                      <td className="num">{c.candidate_gold_rank ? `rank ${c.candidate_gold_rank}` : "–"}</td>
                      <td className="num">{c.context_gold_rank ? `passage ${c.context_gold_rank}` : "–"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
