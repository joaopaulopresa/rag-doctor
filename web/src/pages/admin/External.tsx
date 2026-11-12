import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../../api";
import type { Examination } from "../../types";

interface Spec {
  url: string;
  method: "POST" | "GET";
  body: unknown;
  answer_path: string;
  passages_path: string | null;
  passage_text: string;
}

interface System {
  id: number;
  name: string;
  spec: Spec;
}

const blank = (url: string): Spec => ({
  url,
  method: "POST",
  body: { query: "{{question}}" },
  answer_path: "answer",
  passages_path: "sources",
  passage_text: "content",
});

export default function External() {
  const navigate = useNavigate();
  const [systems, setSystems] = useState<System[]>([]);
  const [mockUrl, setMockUrl] = useState("");
  const [name, setName] = useState("Support bot (demo mock)");
  const [spec, setSpec] = useState<Spec>(blank(""));
  const [body, setBody] = useState(JSON.stringify(blank("").body, null, 2));
  const [question, setQuestion] = useState('Consider "Viber Messenger"\'s privacy policy; do you sell any of our data?');
  const [test, setTest] = useState<{ ok: boolean; answer?: string; passages?: { text: string }[] | null; error?: string; latency_s?: number } | null>(null);
  const [error, setError] = useState("");
  const [questions, setQuestions] = useState(30);

  const load = useCallback(() => {
    api<{ systems: System[]; mock_url: string }>("/api/admin/external-systems").then((d) => {
      setSystems(d.systems);
      setMockUrl(d.mock_url);
      setSpec((s) => (s.url ? s : blank(`${d.mock_url}/ask`)));
    });
  }, []);
  useEffect(load, [load]);

  const current = (): Spec | null => {
    try {
      return { ...spec, body: JSON.parse(body), passages_path: spec.passages_path || null };
    } catch {
      setError("The request body is not valid JSON.");
      return null;
    }
  };

  const runTest = async () => {
    setError("");
    const s = current();
    if (!s) return;
    setTest(null);
    try {
      setTest(await api("/api/admin/external-systems/test", { method: "POST", json: { spec: s, question } }));
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const save = async () => {
    setError("");
    const s = current();
    if (!s) return;
    try {
      await api("/api/admin/external-systems", { method: "POST", json: { name, spec: s } });
      load();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const examine = async (system: System) => {
    const data = await api<{ examination: Examination }>("/api/admin/examinations", {
      method: "POST",
      json: { target: "external", external_system_id: system.id, questions },
    });
    navigate(`/admin/doctor/${data.examination.id}`);
  };

  const field = (key: keyof Spec, label: string, hint: string) => (
    <label className="field">
      {label}
      <input value={String(spec[key] ?? "")} onChange={(e) => setSpec({ ...spec, [key]: e.target.value })} />
      <span className="faint">{hint}</span>
    </label>
  );

  return (
    <div className="page">
      <header className="page-head">
        <h1>External systems</h1>
        <p className="muted">
          Point the doctor at another RAG system over HTTP. No access to its code is needed: say where the question goes and where the answer
          and the passages come back. The same question set and judge are used.
        </p>
      </header>

      {systems.length > 0 && (
        <section className="section">
          <h2>Connected</h2>
          <div className="panel">
            <table>
              <tbody>
                {systems.map((s) => (
                  <tr key={s.id}>
                    <td>
                      <b>{s.name}</b>
                      <div className="faint">
                        {s.spec.method} {s.spec.url}
                      </div>
                    </td>
                    <td className="num">
                      <div className="row" style={{ justifyContent: "flex-end" }}>
                        <input type="number" min={5} max={582} value={questions} onChange={(e) => setQuestions(Number(e.target.value))} style={{ width: 90 }} aria-label="Questions" />
                        <button className="primary" onClick={() => void examine(s)}>
                          Examine {questions} questions
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section className="panel pad stack">
        <h2>Connect a system</h2>
        {mockUrl && (
          <p className="faint">
            This demo ships a deliberately weak RAG service at {mockUrl}/ask: keyword search over the same documents, two passages, answers by a
            small 8B model. The form is filled in for it.
          </p>
        )}
        <div className="form-grid">
          <label className="field">
            Name
            <input value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <label className="field">
            Endpoint
            <input value={spec.url} onChange={(e) => setSpec({ ...spec, url: e.target.value })} />
          </label>
          <label className="field">
            Method
            <select value={spec.method} onChange={(e) => setSpec({ ...spec, method: e.target.value as Spec["method"] })}>
              <option>POST</option>
              <option>GET</option>
            </select>
          </label>
          {field("answer_path", "Answer in the reply", "Dotted path, for example data.answer")}
          {field("passages_path", "Passages in the reply", "Leave empty if the system returns none")}
          {field("passage_text", "Text of each passage", "Field inside each passage; empty if passages are strings")}
        </div>
        <label className="field">
          Request body, with {"{{question}}"} where the question goes
          <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={4} spellCheck={false} />
        </label>
        <div className="row">
          <input className="grow" value={question} onChange={(e) => setQuestion(e.target.value)} aria-label="Test question" />
          <button onClick={() => void runTest()}>Test the connection</button>
          <button className="primary" onClick={() => void save()}>
            Save
          </button>
        </div>
        {error && <p className="notice error">{error}</p>}
        {test && (
          <div className="panel pad stack">
            {test.ok ? (
              <>
                <p>
                  <b>Answer:</b> {test.answer}
                </p>
                <p className="faint">
                  {test.passages ? `${test.passages.length} passages read from the reply` : "No passages: only answer-level diagnosis is possible"}, in{" "}
                  {test.latency_s?.toFixed(1)} s.
                </p>
              </>
            ) : (
              <p className="notice error">{test.error}</p>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
