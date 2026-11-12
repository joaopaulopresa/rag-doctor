import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, pct } from "../../api";
import { ConfigLine } from "../../components/ConfigLine";
import { OutcomeTag } from "../../components/OutcomeStrip";
import type { ConfigurationDescription, Examination } from "../../types";

interface Interval {
  mean: number;
  low: number;
  high: number;
}

interface Comparison {
  before: Examination;
  after: Examination;
  questions: number;
  excluded: number;
  counts: Record<string, number>;
  before_rate: Interval;
  after_rate: Interval;
  difference: Interval & { significant: boolean };
  movements: { question_id: string; question: string; before: string; after: string; change: string }[];
  judge_model: string;
}

const CHANGES: [string, string][] = [
  ["fixed", "Fixed"],
  ["broken", "Newly broken"],
  ["still_wrong", "Still wrong"],
  ["still_correct", "Still correct"],
];

function points(value: number) {
  const n = 100 * value;
  return `${n >= 0 ? "+" : ""}${n.toFixed(1)}`;
}

export default function Compare() {
  const [params] = useSearchParams();
  const before = params.get("before");
  const after = params.get("after");
  const [data, setData] = useState<Comparison | null>(null);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState<string>("fixed");

  useEffect(() => {
    api<Comparison>(`/api/admin/compare?before=${before}&after=${after}`)
      .then((d) => {
        setData(d);
        if (!d.counts.fixed) setFilter(d.counts.broken ? "broken" : "still_wrong");
      })
      .catch((e: Error) => setError(e.message));
  }, [before, after]);

  if (error) return <p className="notice error page">{error}</p>;
  if (!data) return <p className="row muted page"><span className="spinner" /> Loading</p>;
  const shown = data.movements.filter((m) => m.change === filter);
  const diff = data.difference;

  return (
    <div className="page">
      <header className="page-head">
        <p className="faint">
          <Link to="/admin/doctor">Doctor</Link> / <Link to={`/admin/doctor/${data.before.id}`}>#{data.before.id}</Link> and{" "}
          <Link to={`/admin/doctor/${data.after.id}`}>#{data.after.id}</Link>
        </p>
        <div className="spread">
          <h1>Before and after</h1>
          <a className="button" href={`/api/admin/compare/report?before=${before}&after=${after}`} target="_blank" rel="noreferrer">
            Export as HTML
          </a>
        </div>
      </header>

      <section className="ba">
        <div className="panel pad ba-side">
          <span className="faint">Before, #{data.before.id}</span>
          <b className="big-number">{pct(data.before_rate.mean, 1)}</b>
          <span className="faint">
            correct, 95% interval {pct(data.before_rate.low)} to {pct(data.before_rate.high)}
          </span>
          {data.before.target_kind === "own" && <ConfigLine config={data.before.target as unknown as ConfigurationDescription} />}
        </div>
        <div className={`ba-diff${diff.significant ? " significant" : ""}`}>
          <b>{points(diff.mean)} pts</b>
          <span>
            {points(diff.low)} to {points(diff.high)}
          </span>
          <span className="faint">{diff.significant ? "significant" : "not significant"}</span>
        </div>
        <div className="panel pad ba-side">
          <span className="faint">After, #{data.after.id}</span>
          <b className="big-number">{pct(data.after_rate.mean, 1)}</b>
          <span className="faint">
            correct, 95% interval {pct(data.after_rate.low)} to {pct(data.after_rate.high)}
          </span>
          {data.after.target_kind === "own" && <ConfigLine config={data.after.target as unknown as ConfigurationDescription} />}
        </div>
      </section>

      <p className="notice">
        {data.questions} questions compared{data.excluded ? `, ${data.excluded} left out (wrong gold, failed, or not in both)` : ""}. Intervals are
        95% bootstrap intervals; the difference is paired by question. Scores come from the judge ({data.judge_model}) and are not yet validated
        against human labels.
      </p>

      <section className="section">
        <div className="tabs" role="tablist">
          {CHANGES.map(([key, label]) => (
            <button key={key} role="tab" aria-selected={filter === key} className={`tab change-${key}${filter === key ? " on" : ""}`} onClick={() => setFilter(key)}>
              {label} <b>{data.counts[key]}</b>
            </button>
          ))}
        </div>
        <div className="panel">
          {shown.length === 0 ? (
            <div className="empty">
              <p>No question in this group.</p>
            </div>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Question</th>
                  <th>Before</th>
                  <th>After</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((m) => (
                  <tr key={m.question_id}>
                    <td>
                      {m.question}
                      <div className="faint">{m.question_id}</div>
                    </td>
                    <td>
                      <OutcomeTag outcome={m.before} />
                    </td>
                    <td>
                      <OutcomeTag outcome={m.after} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>
    </div>
  );
}
