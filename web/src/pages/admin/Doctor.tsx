import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, pct } from "../../api";
import { JobProgress } from "../../components/JobProgress";
import { OutcomeStrip } from "../../components/OutcomeStrip";
import type { Examination } from "../../types";

interface ExternalSystem {
  id: number;
  name: string;
}

export default function Doctor() {
  const navigate = useNavigate();
  const [rows, setRows] = useState<Examination[] | null>(null);
  const [systems, setSystems] = useState<ExternalSystem[]>([]);
  const [target, setTarget] = useState("own");
  const [questions, setQuestions] = useState(60);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api<{ examinations: Examination[] }>("/api/admin/examinations").then((d) => setRows(d.examinations));
    api<{ systems: ExternalSystem[] }>("/api/admin/external-systems").then((d) => setSystems(d.systems));
  }, []);
  useEffect(load, [load]);

  const start = async () => {
    setBusy(true);
    setError("");
    try {
      const body = target === "own" ? { target: "own", questions } : { target: "external", external_system_id: Number(target), questions };
      const data = await api<{ examination: Examination }>("/api/admin/examinations", { method: "POST", json: body });
      navigate(`/admin/doctor/${data.examination.id}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  };

  return (
    <div className="page">
      <header className="page-head">
        <h1>Doctor</h1>
        <p className="muted">
          Asks every question of a sample of the question set, has the judge score each answer and locates where each wrong answer went
          wrong.
        </p>
      </header>

      <section className="panel pad new-exam">
        <h2>Examine a system</h2>
        <div className="row exam-form">
          <label className="field grow">
            System
            <select value={target} onChange={(e) => setTarget(e.target.value)}>
              <option value="own">This app, active configuration</option>
              {systems.map((s) => (
                <option key={s.id} value={s.id}>
                  External: {s.name}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            Questions
            <input type="number" min={5} max={582} value={questions} onChange={(e) => setQuestions(Number(e.target.value))} />
          </label>
          <button className="primary" onClick={() => void start()} disabled={busy}>
            Start the examination
          </button>
        </div>
        <p className="faint">
          Questions are drawn in proportion from each source collection. About $0.0005 per question on this app (generation plus judge),
          less for answers already in the cache.
        </p>
        {error && <p className="notice error">{error}</p>}
      </section>

      <section className="section">
        <h2>Examinations</h2>
        {rows === null ? (
          <p className="row muted">
            <span className="spinner" /> Loading
          </p>
        ) : rows.length === 0 ? (
          <div className="panel empty">
            <p>No examination yet. Start one above to see where the answers go wrong.</p>
          </div>
        ) : (
          <div className="panel">
            <table>
              <thead>
                <tr>
                  <th>Examination</th>
                  <th>Breakdown</th>
                  <th className="num">Correct</th>
                  <th className="num">Questions</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const s = row.summary;
                  const done = row.job?.status === "done" && "counts" in s;
                  return (
                    <tr key={row.id} className="clickable" onClick={() => navigate(`/admin/doctor/${row.id}`)}>
                      <td>
                        <Link to={`/admin/doctor/${row.id}`}>{row.label}</Link>
                        <div className="faint">
                          #{row.id}, {row.target_kind === "own" ? row.target.display : row.target.url}
                          {row.baseline_id ? `, repeats #${row.baseline_id}` : ""}
                        </div>
                      </td>
                      <td style={{ minWidth: 220 }}>
                        {done ? <OutcomeStrip counts={s.counts} errors={s.errors} legend={false} /> : row.job && <JobProgress job={row.job} onFinish={load} />}
                      </td>
                      <td className="num">{done ? pct(s.correct_rate) : "–"}</td>
                      <td className="num">{row.questions}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
