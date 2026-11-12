import { useEffect, useState, type FormEvent } from "react";
import { ApiError, api, usd } from "../../api";
import { AnswerText } from "../../components/AnswerText";
import { DocumentPanel } from "../../components/DocumentPanel";
import { JobProgress } from "../../components/JobProgress";
import { SelectionForm } from "../../components/SelectionForm";
import type { Job, Passage, Selection } from "../../types";
import { useCatalog } from "../../useCatalog";

interface Usage {
  cost_usd: number;
  paid_usd: number;
  latency_s: number;
}

interface Result {
  answer: string;
  passages: Passage[];
  usage: { retrieval: Usage; rerank: Usage; generation: Usage; total: Usage };
}

type SideState = { result?: Result; error?: string; missing?: boolean; job?: Job; busy?: boolean };

export default function Playground() {
  const catalog = useCatalog();
  const [left, setLeft] = useState<Selection | null>(null);
  const [right, setRight] = useState<Selection | null>(null);
  const [question, setQuestion] = useState("Consider \"Viber Messenger\"'s privacy policy; do you sell any of our data?");
  const [state, setState] = useState<[SideState, SideState]>([{}, {}]);
  const [open, setOpen] = useState<Passage | null>(null);

  useEffect(() => {
    if (catalog && !left) {
      setLeft(catalog.initial);
      setRight({ ...catalog.initial, reranker: null, generator: "mistral-small-2603" });
    }
  }, [catalog, left]);

  const patch = (side: 0 | 1, value: SideState) => setState((s) => (side === 0 ? [value, s[1]] : [s[0], value]));

  const runSide = async (side: 0 | 1, selection: Selection) => {
    patch(side, { busy: true });
    try {
      const result = await api<Result>("/api/admin/playground", { method: "POST", json: { selection, question } });
      patch(side, { result });
    } catch (e) {
      const missing = e instanceof ApiError && e.status === 409;
      patch(side, { error: (e as Error).message, missing });
    }
  };

  const run = (event: FormEvent) => {
    event.preventDefault();
    if (left) void runSide(0, left);
    if (right) void runSide(1, right);
  };

  const buildIndex = async (side: 0 | 1, selection: Selection) => {
    const data = await api<{ job: Job }>("/api/admin/playground/index", { method: "POST", json: selection });
    patch(side, { job: data.job, missing: true, error: "Building the index for this configuration." });
  };

  if (!catalog || !left || !right) return <p className="row muted page"><span className="spinner" /> Loading</p>;

  return (
    <div className={`case-layout${open ? " with-doc" : ""}`}>
      <div className="page">
        <header className="page-head">
          <h1>Playground</h1>
          <p className="muted">Ask one question of two configurations and compare their answers, passages, cost and time.</p>
        </header>
        <form className="row" onSubmit={run}>
          <input className="grow" value={question} onChange={(e) => setQuestion(e.target.value)} aria-label="Question" />
          <button className="primary" type="submit" disabled={question.trim().length < 3}>
            Ask both
          </button>
        </form>
        <div className="versus">
          {([0, 1] as const).map((side) => {
            const selection = side === 0 ? left : right;
            const s = state[side];
            return (
              <section key={side} className="panel pad stack">
                <h2>{side === 0 ? "Configuration A" : "Configuration B"}</h2>
                <SelectionForm catalog={catalog} value={selection} onChange={side === 0 ? setLeft : setRight} idPrefix={`side${side}`} />
                {s.busy && (
                  <p className="row muted">
                    <span className="spinner" /> Answering
                  </p>
                )}
                {s.error && <p className="notice">{s.error}</p>}
                {s.missing && !s.job && (
                  <button onClick={() => void buildIndex(side, selection)}>Build its index</button>
                )}
                {s.job && <JobProgress job={s.job} onFinish={() => void runSide(side, selection)} />}
                {s.result && (
                  <div className="stack">
                    <AnswerText text={s.result.answer} passages={s.result.passages.length} onCite={(n) => setOpen(s.result!.passages[n - 1])} />
                    <ol className="sources">
                      {s.result.passages.map((p) => (
                        <li key={p.number}>
                          <button type="button" className="source" onClick={() => setOpen(p)}>
                            <span className="source-number">{p.number}</span>
                            <span className="grow source-title">{p.title}</span>
                          </button>
                        </li>
                      ))}
                    </ol>
                    <table className="compact-table">
                      <tbody>
                        {(["retrieval", "rerank", "generation", "total"] as const).map((k) => (
                          <tr key={k}>
                            <td>{k === "total" ? <b>Total</b> : k[0].toUpperCase() + k.slice(1)}</td>
                            <td className="num">{usd(s.result!.usage[k].cost_usd, 5)}</td>
                            <td className="num">{s.result!.usage[k].latency_s.toFixed(2)} s</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    <p className="faint">Cost and time of the original calls; a repeated question is served from the cache for free.</p>
                  </div>
                )}
              </section>
            );
          })}
        </div>
      </div>
      {open && <DocumentPanel documentId={open.document_id} start={open.start} end={open.end} label={`Passage ${open.number}`} onClose={() => setOpen(null)} />}
    </div>
  );
}
