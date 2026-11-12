import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../api";
import { JobProgress } from "../../components/JobProgress";
import type { Job } from "../../types";

interface Question {
  id: string;
  text: string;
  document_id: string | null;
  document_title: string | null;
  evidence: string[];
  source: string;
  status: "draft" | "accepted" | "rejected";
  origin: string;
  note: string;
}

const TABS: [string, string][] = [
  ["draft", "To review"],
  ["accepted", "Accepted"],
  ["rejected", "Rejected"],
];

function Editor({ question, documents, onSaved }: { question: Question; documents: { id: string; title: string }[]; onSaved: () => void }) {
  const [text, setText] = useState(question.text);
  const [documentId, setDocumentId] = useState(question.document_id ?? "");
  const [evidence, setEvidence] = useState(question.evidence.join("\n"));
  const [error, setError] = useState("");

  const save = async (status?: string) => {
    setError("");
    try {
      const body: Record<string, unknown> = { text };
      if (documentId !== (question.document_id ?? "")) body.document_id = documentId;
      if (evidence.trim() && evidence !== question.evidence.join("\n")) body.evidence = evidence;
      if (status) body.status = status;
      await api(`/api/admin/questions/${question.id}`, { method: "PATCH", json: body });
      onSaved();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <div className="stack editor">
      <label className="field">
        Question
        <textarea value={text} onChange={(e) => setText(e.target.value)} rows={2} />
      </label>
      <label className="field">
        Document
        <select value={documentId} onChange={(e) => setDocumentId(e.target.value)}>
          <option value="">Choose the document that answers it</option>
          {documents.map((d) => (
            <option key={d.id} value={d.id}>
              {d.title}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        Gold evidence, copied word for word from the document
        <textarea className="serif" value={evidence} onChange={(e) => setEvidence(e.target.value)} rows={4} />
      </label>
      {question.note && <p className="faint">{question.note}</p>}
      {error && <p className="notice error">{error}</p>}
      <div className="row">
        <button className="primary" onClick={() => void save("accepted")}>
          Accept
        </button>
        <button onClick={() => void save()}>Save</button>
        <button className="danger" onClick={() => void save("rejected")}>
          Reject
        </button>
      </div>
    </div>
  );
}

export default function Questions() {
  const [tab, setTab] = useState("draft");
  const [search, setSearch] = useState("");
  const [data, setData] = useState<{ total: number; counts: Record<string, number>; questions: Question[] } | null>(null);
  const [documents, setDocuments] = useState<{ id: string; title: string }[]>([]);
  const [openId, setOpenId] = useState<string | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [message, setMessage] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);

  const load = useCallback(() => {
    const query = new URLSearchParams({ status_filter: tab, limit: "100" });
    if (search) query.set("q", search);
    api<typeof data & object>(`/api/admin/questions?${query}`).then(setData);
  }, [tab, search]);
  useEffect(load, [load]);
  useEffect(() => {
    api<{ documents: { id: string; title: string }[] }>("/api/admin/documents").then((d) => setDocuments(d.documents));
  }, []);

  const draft = async () => {
    const result = await api<{ job: Job }>("/api/admin/questions/draft", { method: "POST", json: { count: 10, seed: Date.now() % 1000 } });
    setJob(result.job);
  };

  const importFile = async (files: FileList | null) => {
    if (!files?.length) return;
    const body = new FormData();
    body.append("file", files[0]);
    try {
      const r = await api<{ added: number; updated: number; skipped: number }>("/api/admin/questions/import", { method: "POST", body });
      setMessage(`Imported: ${r.added} added, ${r.updated} updated, ${r.skipped} skipped because their evidence does not match a document.`);
      load();
    } catch (e) {
      setMessage((e as Error).message);
    }
  };

  return (
    <div className="page">
      <header className="page-head spread">
        <div>
          <h1>Question set</h1>
          <p className="muted">Gold questions with the evidence that answers them. Only accepted questions are used by experiments and examinations.</p>
        </div>
        <div className="row">
          <a className="button" href="/api/admin/questions/export">
            Export
          </a>
          <input ref={fileInput} type="file" accept=".json" hidden onChange={(e) => void importFile(e.target.files)} />
          <button onClick={() => fileInput.current?.click()}>Import</button>
          <button className="primary" onClick={() => void draft()}>
            Draft 10 questions
          </button>
        </div>
      </header>
      {job && (
        <section className="panel pad stack">
          <JobProgress job={job} onFinish={() => { setTab("draft"); load(); }} />
          {job.status === "done" && <p className="faint">Drafts are written by {String("meta-llama/llama-3.1-8b-instruct")}; review each before accepting it.</p>}
        </section>
      )}
      {message && <p className="notice">{message}</p>}

      <div className="spread">
        <div className="tabs" role="tablist">
          {TABS.map(([key, label]) => (
            <button key={key} role="tab" aria-selected={tab === key} className={`tab${tab === key ? " on" : ""}`} onClick={() => setTab(key)}>
              {label} <b>{data?.counts[key] ?? 0}</b>
            </button>
          ))}
        </div>
        <input placeholder="Search questions" value={search} onChange={(e) => setSearch(e.target.value)} style={{ maxWidth: 280 }} aria-label="Search questions" />
      </div>

      <div className="panel">
        {data && data.questions.length === 0 ? (
          <div className="empty">
            <p>{tab === "draft" ? "Nothing to review. Draft questions from the documents, or wait for feedback from the chat." : "No question here."}</p>
          </div>
        ) : (
          <ul className="question-list">
            {data?.questions.map((q) => (
              <li key={q.id}>
                <button type="button" className="question-row" onClick={() => setOpenId(openId === q.id ? null : q.id)} aria-expanded={openId === q.id}>
                  <span className="grow">
                    {q.text}
                    <span className="faint block">
                      {q.id}, {q.document_title ?? "no document yet"}, {q.origin}
                    </span>
                  </span>
                </button>
                {openId === q.id ? (
                  <Editor question={q} documents={documents} onSaved={() => { setOpenId(null); load(); }} />
                ) : (
                  q.evidence[0] && <p className="passage-text evidence-preview">{q.evidence[0].slice(0, 260)}{q.evidence[0].length > 260 ? "…" : ""}</p>
                )}
              </li>
            ))}
          </ul>
        )}
        {data && data.total > data.questions.length && <p className="faint pad-s">Showing {data.questions.length} of {data.total}. Search to narrow down.</p>}
      </div>
    </div>
  );
}
