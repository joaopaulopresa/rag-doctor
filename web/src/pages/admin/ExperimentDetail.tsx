import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, pct, usd } from "../../api";
import { JobProgress } from "../../components/JobProgress";
import type { Experiment, ExperimentRow } from "../../types";

/** Judge correctness against cost per 1,000 answers: one point per answer configuration. */
function QualityCost({ rows, chosen }: { rows: ExperimentRow[]; chosen?: string }) {
  if (rows.length < 2) return null;
  const w = 560, h = 260, pad = { l: 52, r: 16, t: 14, b: 40 };
  const costs = rows.map((r) => r.cost_per_1k_answers_usd);
  const scores = rows.flatMap((r) => [r.correctness_low, r.correctness_high]);
  const maxCost = Math.max(...costs) * 1.1 || 1;
  const lo = Math.max(0, Math.min(...scores) - 0.05), hi = Math.min(1, Math.max(...scores) + 0.05);
  const x = (c: number) => pad.l + (c / maxCost) * (w - pad.l - pad.r);
  const y = (s: number) => pad.t + (1 - (s - lo) / (hi - lo || 1)) * (h - pad.t - pad.b);
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((t) => lo + t * (hi - lo));
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="chart" role="img" aria-label="Judge correctness against cost per 1,000 answers">
      {ticks.map((t) => (
        <g key={t}>
          <line x1={pad.l} x2={w - pad.r} y1={y(t)} y2={y(t)} stroke="var(--rule)" />
          <text x={pad.l - 8} y={y(t) + 4} textAnchor="end" className="chart-label">
            {Math.round(t * 100)}%
          </text>
        </g>
      ))}
      <text x={(w + pad.l) / 2} y={h - 8} textAnchor="middle" className="chart-label">
        Cost per 1,000 answers (USD)
      </text>
      {[0, 0.5, 1].map((t) => (
        <text key={t} x={x(t * maxCost)} y={h - pad.b + 16} textAnchor="middle" className="chart-label">
          {(t * maxCost).toFixed(2)}
        </text>
      ))}
      {rows.map((r) => (
        <g key={r.config_key}>
          <line x1={x(r.cost_per_1k_answers_usd)} x2={x(r.cost_per_1k_answers_usd)} y1={y(r.correctness_low)} y2={y(r.correctness_high)} stroke={r.config_key === chosen ? "var(--pen)" : "var(--ink-faint)"} strokeWidth={1.5} />
          <circle cx={x(r.cost_per_1k_answers_usd)} cy={y(r.correctness)} r={r.config_key === chosen ? 6 : 4.5} fill={r.config_key === chosen ? "var(--pen)" : "var(--panel)"} stroke={r.config_key === chosen ? "var(--pen)" : "var(--ink-soft)"} strokeWidth={1.5}>
            <title>{`${r.configuration}: ${pct(r.correctness, 1)}, $${r.cost_per_1k_answers_usd.toFixed(3)} per 1,000`}</title>
          </circle>
        </g>
      ))}
    </svg>
  );
}

export default function ExperimentDetail() {
  const { id } = useParams();
  const [row, setRow] = useState<Experiment | null>(null);
  const [applied, setApplied] = useState<string | null>(null);

  const load = useCallback(() => {
    api<{ experiment: Experiment }>(`/api/admin/experiments/${id}`).then((d) => setRow(d.experiment));
  }, [id]);
  useEffect(load, [load]);

  if (!row) return <p className="row muted page"><span className="spinner" /> Loading</p>;
  const s = row.summary;
  const rec = s.recommendation;

  const apply = async (spec: Record<string, unknown> | null, display: string, key: string) => {
    if (!spec) return;
    await api("/api/admin/configurations/apply", {
      method: "POST",
      json: { spec, name: display.split(" -> ")[0], note: `From experiment #${row.id}`, origin: `experiment #${row.id}` },
    });
    setApplied(key);
  };

  return (
    <div className="page">
      <header className="page-head">
        <p className="faint">
          <Link to="/admin/experiments">Experiments</Link> / #{row.id}
          {row.examination_id && (
            <>
              {" "}
              (prescribed by <Link to={`/admin/doctor/${row.examination_id}`}>examination #{row.examination_id}</Link>)
            </>
          )}
        </p>
        <h1>{row.name}</h1>
        {row.purpose && <p className="muted">{row.purpose}</p>}
      </header>

      {row.job && row.job.status !== "done" && (
        <section className="panel pad">
          <JobProgress job={row.job} onFinish={load} />
        </section>
      )}

      {s.answers && (
        <>
          {rec && (
            <section className="panel pad stack">
              <div className="spread">
                <div className="grow">
                  <span className="faint">Measured winner on {s.questions} questions</span>
                  <h2>{rec.display}</h2>
                  <p className="muted">{rec.reason}</p>
                </div>
                {applied === rec.config_key ? (
                  <span className="tag pen">Applied to the chat</span>
                ) : (
                  <button className="primary" onClick={() => void apply(rec.spec, rec.display, rec.config_key)}>
                    Apply to the chat
                  </button>
                )}
              </div>
            </section>
          )}

          <section className="section">
            <div className="spread">
              <h2>Answers, scored by the judge</h2>
              <a href={`/api/admin/experiments/${row.id}/report`} target="_blank" rel="noreferrer">
                Open the full engine report
              </a>
            </div>
            <div className="panel">
              <table>
                <thead>
                  <tr>
                    <th>Configuration</th>
                    <th className="num">Judge correctness</th>
                    <th className="num">95% interval</th>
                    <th className="num">Gold in context</th>
                    <th className="num">Per 1,000 answers</th>
                    <th className="num">Median latency</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {s.answers.map((a) => (
                    <tr key={a.config_key} className={a.config_key === rec?.config_key ? "chosen" : ""}>
                      <td>
                        {a.configuration}
                        {a.tied_with_best && <div className="faint">statistically tied with the best</div>}
                      </td>
                      <td className="num">{pct(a.correctness, 1)}</td>
                      <td className="num faint">
                        {pct(a.correctness_low)} to {pct(a.correctness_high)}
                      </td>
                      <td className="num">{pct(a.gold_in_context)}</td>
                      <td className="num">{usd(a.cost_per_1k_answers_usd, 3)}</td>
                      <td className="num">{a.latency_p50_s.toFixed(1)} s</td>
                      <td className="num">
                        {applied === a.config_key ? (
                          <span className="tag pen">Applied</span>
                        ) : (
                          <button className="small" onClick={() => void apply(a.spec, a.configuration, a.config_key)}>
                            Apply
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="panel pad">
              <h3>Quality against cost</h3>
              <QualityCost rows={s.answers} chosen={rec?.config_key} />
            </div>
          </section>

          {s.retrieval && s.retrieval.length > 0 && (
            <section className="section">
              <h2>Retrieval, best configurations</h2>
              <div className="panel">
                <table>
                  <thead>
                    <tr>
                      <th>Configuration</th>
                      <th className="num">{s.primary_metric}</th>
                      <th className="num">recall@5</th>
                      <th className="num">recall@10</th>
                    </tr>
                  </thead>
                  <tbody>
                    {s.retrieval.map((r) => (
                      <tr key={String(r.config_key)}>
                        <td>{String(r.configuration)}</td>
                        <td className="num">{pct(r[s.primary_metric!] as number, 1)}</td>
                        <td className="num">{pct(r["recall@5"] as number, 1)}</td>
                        <td className="num">{pct(r["recall@10"] as number, 1)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="faint">
                {s.primary_metric} is the share of the gold evidence's characters found in the top 5 passages. Paid for this experiment:{" "}
                {usd(s.paid_usd, 3)}.
              </p>
            </section>
          )}
        </>
      )}
    </div>
  );
}
