import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, usd } from "../../api";
import { AnswerText } from "../../components/AnswerText";
import { DocumentPanel } from "../../components/DocumentPanel";
import { OutcomeTag } from "../../components/OutcomeStrip";
import { PipelineTrace } from "../../components/PipelineTrace";
import type { CaseBrief, Examination } from "../../types";

interface ContextPassage {
  number: number;
  text: string;
  document_id: string | null;
  span: [number, number] | null;
  holds_gold: boolean;
  title: string | null;
}

interface CaseData {
  question: string;
  gold: { document_id: string; spans: [number, number][]; texts: string[]; title: string };
  answer: string;
  context: ContextPassage[];
  has_context: boolean;
  context_gold_rank: number | null;
  candidates: number | null;
  candidate_gold_rank: number | null;
  scores: { correctness: number; faithfulness: number; citation: number };
  rationale: string;
  cost_usd: number;
  latency_s: number;
  diagnosed?: string;
  error?: string;
}

interface Detail {
  case: CaseBrief & { data: CaseData };
  examination: Examination;
  meaning: string | null;
}

type Open = { documentId: string; start: number; end: number; label: string };

export default function Case() {
  const { id } = useParams();
  const [detail, setDetail] = useState<Detail | null>(null);
  const [open, setOpen] = useState<Open | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api<Detail>(`/api/admin/cases/${id}`).then(setDetail);
  }, [id]);
  useEffect(load, [load]);

  if (!detail) return <p className="row muted page"><span className="spinner" /> Loading</p>;
  const { case: item, examination, meaning } = detail;
  const data = item.data;

  const toggleWrongGold = async () => {
    setBusy(true);
    try {
      await api(`/api/admin/cases/${item.id}/wrong-gold`, { method: "POST", json: { wrong: !item.wrong_gold } });
      load();
    } finally {
      setBusy(false);
    }
  };

  const openPassage = (p: ContextPassage) => {
    if (p.document_id && p.span) setOpen({ documentId: p.document_id, start: p.span[0], end: p.span[1], label: `Passage ${p.number}` });
    else setExpanded(expanded === p.number ? null : p.number);
  };

  return (
    <div className={`case-layout${open ? " with-doc" : ""}`}>
      <div className="page">
        <header className="page-head">
          <p className="faint">
            <Link to="/admin/doctor">Doctor</Link> / <Link to={`/admin/doctor/${examination.id}`}>{examination.label}</Link> / {item.question_id}
          </p>
          <h1 className="case-question">{data.question}</h1>
          <div className="row">
            <OutcomeTag outcome={item.outcome} />
            {meaning && <span className="muted">{meaning}</span>}
          </div>
        </header>

        {data.error ? (
          <p className="notice error">{data.error}</p>
        ) : (
          <>
            <PipelineTrace
              outcome={item.wrong_gold ? data.diagnosed ?? item.outcome : item.outcome}
              candidates={data.candidates}
              candidateRank={data.candidate_gold_rank}
              hasContext={data.has_context}
              contextSize={data.context.length}
              contextRank={data.context_gold_rank}
              scores={data.scores}
            />

            <div className="case-grid">
              <section className="panel pad stack">
                <div className="spread">
                  <h2>Gold evidence</h2>
                  <button
                    className="small"
                    onClick={() =>
                      setOpen({ documentId: data.gold.document_id, start: data.gold.spans[0][0], end: data.gold.spans[data.gold.spans.length - 1][1], label: "Gold evidence" })
                    }
                  >
                    Open in the document
                  </button>
                </div>
                <p className="faint">{data.gold.title}</p>
                {data.gold.texts.map((t, i) => (
                  <blockquote key={i} className="passage-text gold-quote">
                    {t}
                  </blockquote>
                ))}
              </section>

              <section className="panel pad stack">
                <h2>Answer</h2>
                <AnswerText
                  text={data.answer}
                  passages={data.context.length}
                  onCite={(n) => openPassage(data.context[n - 1])}
                />
                <div className="judge">
                  <p className="faint">Judge rationale</p>
                  <p>{data.rationale}</p>
                </div>
                <p className="faint">
                  Cost of this case {usd(data.cost_usd)}, answer in {data.latency_s.toFixed(1)} s
                </p>
              </section>
            </div>

            <section className="section">
              <h2>Passages given to the generator</h2>
              {!data.has_context ? (
                <div className="panel empty">
                  <p>The system returned no passages, so retrieval cannot be checked.</p>
                </div>
              ) : (
                <ol className="context-list">
                  {data.context.map((p) => (
                    <li key={p.number} className={`panel context-item${p.holds_gold ? " gold" : ""}`}>
                      <button type="button" className="context-head" onClick={() => openPassage(p)}>
                        <span className="source-number">{p.number}</span>
                        <span className="grow">{p.title ?? "Passage returned by the system"}</span>
                        {p.holds_gold && <span className="tag pen">Holds the gold evidence</span>}
                      </button>
                      {expanded === p.number || !p.span ? (
                        <p className="passage-text context-text">{p.text}</p>
                      ) : (
                        <p className="passage-text context-text clamp">{p.text}</p>
                      )}
                    </li>
                  ))}
                </ol>
              )}
            </section>
          </>
        )}

        <section className="panel pad spread">
          <div className="grow">
            <h3>Is the question itself wrong?</h3>
            <p className="muted">
              If the gold evidence does not answer the question, mark it. The question leaves the question set and stops counting in
              examinations.
            </p>
          </div>
          <button className={item.wrong_gold ? "" : "danger"} onClick={() => void toggleWrongGold()} disabled={busy}>
            {item.wrong_gold ? "Restore the question" : "Mark the question as wrong gold"}
          </button>
        </section>
      </div>
      {open && <DocumentPanel documentId={open.documentId} start={open.start} end={open.end} label={open.label} onClose={() => setOpen(null)} />}
    </div>
  );
}
