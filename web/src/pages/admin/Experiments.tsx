import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, pct, usd } from "../../api";
import { JobProgress } from "../../components/JobProgress";
import type { CatalogOption, Experiment } from "../../types";
import { useCatalog } from "../../useCatalog";

function Choices({ title, options, value, onChange }: { title: string; options: CatalogOption[] | string[]; value: string[]; onChange: (v: string[]) => void }) {
  return (
    <fieldset className="choices">
      <legend>{title}</legend>
      {options.map((option) => {
        const id = typeof option === "string" ? option : option.id;
        const label = typeof option === "string" ? option : option.label;
        const expensive = typeof option !== "string" && option.expensive;
        return (
          <label key={id} className="check">
            <input type="checkbox" checked={value.includes(id)} onChange={(e) => onChange(e.target.checked ? [...value, id] : value.filter((v) => v !== id))} />
            {label}
            {expensive && <span className="tag">about 10x the cost</span>}
          </label>
        );
      })}
    </fieldset>
  );
}

export default function Experiments() {
  const catalog = useCatalog();
  const navigate = useNavigate();
  const [rows, setRows] = useState<Experiment[] | null>(null);
  const [form, setForm] = useState({
    name: "Lab experiment",
    chunkers: ["context-header"],
    embedders: ["text-embedding-3-large"],
    search_modes: ["dense"],
    rerankers: ["cohere-rerank-5-fast"],
    generators: ["granite-4.2-8b", "mistral-small-2603"],
    questions: 40,
    context_k: 5,
  });
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api<{ experiments: Experiment[] }>("/api/admin/experiments").then((d) => setRows(d.experiments));
  }, []);
  useEffect(load, [load]);

  const start = async () => {
    setError("");
    try {
      const data = await api<{ experiment: Experiment }>("/api/admin/experiments", { method: "POST", json: form });
      navigate(`/admin/experiments/${data.experiment.id}`);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const retrievalConfigs =
    form.chunkers.length * (form.search_modes.filter((m) => m !== "lexical").length * form.embedders.length + (form.search_modes.includes("lexical") ? 1 : 0));

  return (
    <div className="page">
      <header className="page-head">
        <h1>Experiments</h1>
        <p className="muted">
          Compare chunkers, embedding models, search modes, rerankers and generators on the question set. Retrieval is measured on every
          combination; the best three go on to reranking and to answers scored by the judge.
        </p>
      </header>

      {catalog && (
        <section className="panel pad stack">
          <h2>New experiment</h2>
          <label className="field">
            Name
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </label>
          <div className="choices-grid">
            <Choices title="Chunking" options={catalog.chunkers} value={form.chunkers} onChange={(v) => setForm({ ...form, chunkers: v })} />
            <Choices title="Embedding model" options={catalog.embedders} value={form.embedders} onChange={(v) => setForm({ ...form, embedders: v })} />
            <Choices title="Search" options={catalog.search_modes} value={form.search_modes} onChange={(v) => setForm({ ...form, search_modes: v })} />
            <Choices title="Rerankers" options={catalog.rerankers} value={form.rerankers} onChange={(v) => setForm({ ...form, rerankers: v })} />
            <Choices title="Generators" options={catalog.generators} value={form.generators} onChange={(v) => setForm({ ...form, generators: v })} />
          </div>
          <div className="row">
            <label className="field">
              Questions
              <input type="number" min={5} max={582} value={form.questions} onChange={(e) => setForm({ ...form, questions: Number(e.target.value) })} />
            </label>
            <label className="field">
              Passages in context
              <input type="number" min={1} max={10} value={form.context_k} onChange={(e) => setForm({ ...form, context_k: Number(e.target.value) })} />
            </label>
          </div>
          <div className="spread">
            <p className="faint">
              {retrievalConfigs} retrieval configurations, then up to {3 * form.generators.length} answer configurations on {form.questions} questions.
              Every model call is cached, so repeating an experiment costs nothing.
            </p>
            <button className="primary" onClick={() => void start()} disabled={!form.chunkers.length || !form.embedders.length || !form.search_modes.length || !form.generators.length}>
              Run the experiment
            </button>
          </div>
          {error && <p className="notice error">{error}</p>}
        </section>
      )}

      <section className="section">
        <h2>Past experiments</h2>
        {rows && rows.length === 0 && (
          <div className="panel empty">
            <p>No experiment yet.</p>
          </div>
        )}
        {rows && rows.length > 0 && (
          <div className="panel">
            <table>
              <thead>
                <tr>
                  <th>Experiment</th>
                  <th>Measured winner</th>
                  <th className="num">Judge correctness</th>
                  <th className="num">Paid</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const best = row.summary.answers?.find((a) => a.config_key === row.summary.recommendation?.config_key);
                  return (
                    <tr key={row.id} className="clickable" onClick={() => navigate(`/admin/experiments/${row.id}`)}>
                      <td>
                        <Link to={`/admin/experiments/${row.id}`}>{row.name}</Link>
                        <div className="faint">
                          #{row.id}
                          {row.examination_id ? `, prescribed by examination #${row.examination_id}` : ""}
                        </div>
                      </td>
                      <td>{row.job?.status === "done" ? row.summary.recommendation?.display ?? "–" : row.job && <JobProgress job={row.job} onFinish={load} />}</td>
                      <td className="num">{best ? pct(best.correctness, 1) : "–"}</td>
                      <td className="num">{usd(row.summary.paid_usd, 3)}</td>
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
