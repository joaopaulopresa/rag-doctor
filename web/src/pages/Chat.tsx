import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api, postStream } from "../api";
import { useAuth } from "../auth";
import { AnswerText } from "../components/AnswerText";
import { Brand } from "../components/Brand";
import { ConfigLine } from "../components/ConfigLine";
import { DocumentPanel } from "../components/DocumentPanel";
import type { ConfigurationDescription, Passage } from "../types";

interface Status {
  ready: boolean;
  documents: number;
  questions: number;
  configuration: (ConfigurationDescription & { name: string }) | null;
}

interface Turn {
  id: string;
  question: string;
  step: "searching" | "writing" | "done" | "error";
  passages: Passage[];
  answer: string;
  invalid: number[];
  messageId?: number;
  seconds?: number;
  cached?: boolean;
  feedback?: 1 | -1;
  error?: string;
}

const SUGGESTIONS = [
  'Consider "Viber Messenger"\'s privacy policy; do you sell any of our data?',
  "Consider the Promotion Agreement between Depomed, Inc. and King Pharmaceuticals, Inc. for Glumetza; Is there a cap on liability under this contract?",
  "Consider VELCO's Non-Disclosure Agreement; Does the document allow the Receiving Party to share some Confidential Information with their employees?",
];

export default function Chat() {
  const { user } = useAuth();
  const [status, setStatus] = useState<Status | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState<{ turn: string; passage: Passage } | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let timer: number | undefined;
    const load = () =>
      api<Status>("/api/status")
        .then((s) => {
          setStatus(s);
          if (!s.ready) timer = window.setTimeout(load, 4000);
        })
        .catch(() => (timer = window.setTimeout(load, 4000)));
    load();
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [turns]);

  const update = (id: string, patch: Partial<Turn>) => setTurns((all) => all.map((t) => (t.id === id ? { ...t, ...patch } : t)));

  const ask = async (question: string) => {
    const text = question.trim();
    if (text.length < 3 || busy) return;
    const id = crypto.randomUUID();
    const started = performance.now();
    setTurns((all) => [...all, { id, question: text, step: "searching", passages: [], answer: "", invalid: [] }]);
    setDraft("");
    setBusy(true);
    try {
      await postStream("/api/chat", { question: text }, (event) => {
        if (event.type === "passages") update(id, { passages: event.passages as Passage[] });
        else if (event.type === "status" && event.step === "writing") update(id, { step: "writing" });
        else if (event.type === "answer")
          update(id, {
            answer: String(event.text),
            passages: event.passages as Passage[],
            invalid: event.invalid_citations as number[],
          });
        else if (event.type === "done") {
          const usage = event.usage as { paid_usd: number; cost_usd: number };
          update(id, {
            step: "done",
            messageId: Number(event.message_id),
            seconds: (performance.now() - started) / 1000,
            cached: usage.paid_usd === 0 && usage.cost_usd > 0,
          });
        }
        else if (event.type === "error") update(id, { step: "error", error: String(event.message) });
      });
    } catch (error) {
      update(id, { step: "error", error: (error as Error).message });
    } finally {
      setBusy(false);
    }
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    void ask(draft);
  };

  const rate = async (turn: Turn, value: 1 | -1) => {
    if (!turn.messageId) return;
    update(turn.id, { feedback: value });
    await api(`/api/chat/${turn.messageId}/feedback`, { method: "POST", json: { value } }).catch(() => undefined);
  };

  return (
    <div className={`chat-layout${open ? " with-doc" : ""}`}>
      <div className="chat-column">
        <header className="topbar">
          <Brand />
          <nav className="row">
            {user?.role === "admin" ? <Link to="/admin/doctor">Admin</Link> : <Link to="/login">Sign in</Link>}
          </nav>
        </header>

        <main className="chat-main">
          {turns.length === 0 && (
            <section className="intro">
              <h1>Ask the document library</h1>
              <p className="muted lead">
                {status
                  ? `${status.documents} contracts, NDAs and privacy policies from the LegalBench-RAG benchmark. `
                  : "Contracts, NDAs and privacy policies from the LegalBench-RAG benchmark. "}
                Every answer cites the passages it used; open a citation to read it in its document.
              </p>
              <div className="suggestions">
                {SUGGESTIONS.map((s) => (
                  <button key={s} type="button" className="suggestion" onClick={() => void ask(s)} disabled={busy || !status?.ready}>
                    {s}
                  </button>
                ))}
              </div>
            </section>
          )}

          {turns.map((turn) => (
            <article key={turn.id} className="turn">
              <p className="question">{turn.question}</p>
              {turn.step === "error" ? (
                <p className="notice error">{turn.error}</p>
              ) : (
                <>
                  {turn.answer ? (
                    <AnswerText
                      text={turn.answer}
                      passages={turn.passages.length}
                      active={open?.turn === turn.id ? open.passage.number : null}
                      onCite={(n) => setOpen({ turn: turn.id, passage: turn.passages[n - 1] })}
                    />
                  ) : (
                    <p className="row muted">
                      <span className="spinner" />
                      {turn.step === "searching" ? "Searching the documents" : `Writing the answer from ${turn.passages.length} passages`}
                    </p>
                  )}
                  {turn.passages.length > 0 && (
                    <ol className="sources" aria-label="Passages given to the model">
                      {turn.passages.map((p) => (
                        <li key={p.number}>
                          <button
                            type="button"
                            className={`source${open?.turn === turn.id && open.passage.number === p.number ? " on" : ""}`}
                            onClick={() => setOpen({ turn: turn.id, passage: p })}
                          >
                            <span className="source-number">{p.number}</span>
                            <span className="grow source-title">{p.title}</span>
                          </button>
                        </li>
                      ))}
                    </ol>
                  )}
                  {turn.step === "done" && (
                    <div className="turn-foot row">
                      <span className="faint">
                        {turn.cached ? "Answered from the cache, " : ""}
                        {turn.seconds?.toFixed(1)} s
                      </span>
                      <span className="grow" />
                      {turn.feedback ? (
                        <span className="faint">
                          {turn.feedback === 1 ? "Thanks for the feedback." : "Thanks. The question was sent to the review queue."}
                        </span>
                      ) : (
                        <>
                          <button className="quiet small" onClick={() => void rate(turn, 1)}>
                            Helpful
                          </button>
                          <button className="quiet small" onClick={() => void rate(turn, -1)}>
                            Not helpful
                          </button>
                        </>
                      )}
                    </div>
                  )}
                </>
              )}
            </article>
          ))}
          <div ref={endRef} />
        </main>

        <footer className="composer">
          <form onSubmit={submit} className="composer-form">
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void ask(draft);
                }
              }}
              placeholder={status?.ready === false ? "The library is being indexed. One moment." : "Ask about a contract or a privacy policy"}
              rows={2}
              aria-label="Your question"
              disabled={status?.ready === false}
            />
            <button className="primary" type="submit" disabled={busy || draft.trim().length < 3 || !status?.ready}>
              Ask
            </button>
          </form>
          {status?.configuration && (
            <div className="faint config-note">
              Answering with <ConfigLine config={status.configuration} compact />
            </div>
          )}
        </footer>
      </div>

      {open && (
        <DocumentPanel
          documentId={open.passage.document_id}
          start={open.passage.start}
          end={open.passage.end}
          label={`Source ${open.passage.number}`}
          onClose={() => setOpen(null)}
        />
      )}
    </div>
  );
}
