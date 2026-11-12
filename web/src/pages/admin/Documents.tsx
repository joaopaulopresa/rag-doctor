import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../api";
import { JobProgress } from "../../components/JobProgress";
import type { Job } from "../../types";

interface Row {
  id: string;
  title: string;
  source: string;
  origin: string;
  status: string;
  error: string;
  characters: number;
  questions: number;
}

export default function Documents() {
  const [rows, setRows] = useState<Row[] | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [errors, setErrors] = useState<{ file: string; error: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  const load = useCallback(() => {
    api<{ documents: Row[] }>("/api/admin/documents").then((d) => setRows(d.documents));
  }, []);
  useEffect(load, [load]);

  const upload = async (files: FileList | null) => {
    if (!files?.length) return;
    setBusy(true);
    const body = new FormData();
    for (const file of Array.from(files)) body.append("files", file);
    try {
      const result = await api<{ job: Job | null; errors: { file: string; error: string }[] }>("/api/admin/documents", { method: "POST", body });
      setErrors(result.errors);
      setJob(result.job);
      load();
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  };

  const bySource = rows?.reduce<Record<string, number>>((acc, r) => ({ ...acc, [r.source]: (acc[r.source] ?? 0) + 1 }), {});

  return (
    <div className="page">
      <header className="page-head spread">
        <div>
          <h1>Documents</h1>
          <p className="muted">
            {rows ? `${rows.length} documents: ${Object.entries(bySource ?? {}).map(([s, n]) => `${n} ${s}`).join(", ")}.` : ""} Added files are
            chunked and embedded with the active configuration.
          </p>
        </div>
        <div>
          <input ref={input} type="file" multiple accept=".pdf,.txt,.md" hidden onChange={(e) => void upload(e.target.files)} />
          <button className="primary" onClick={() => input.current?.click()} disabled={busy}>
            Add documents
          </button>
        </div>
      </header>
      {job && <section className="panel pad"><JobProgress job={job} onFinish={load} /></section>}
      {errors.map((e) => (
        <p key={e.file} className="notice error">
          {e.file}: {e.error}
        </p>
      ))}
      <div className="panel">
        <table>
          <thead>
            <tr>
              <th>Document</th>
              <th>Collection</th>
              <th className="num">Characters</th>
              <th className="num">Gold questions</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {rows?.map((r) => (
              <tr key={r.id}>
                <td>
                  {r.title}
                  <div className="faint">{r.id}</div>
                </td>
                <td>{r.source}</td>
                <td className="num">{r.characters.toLocaleString()}</td>
                <td className="num">{r.questions}</td>
                <td>
                  <span className={`tag${r.status === "ready" ? " pen" : ""}`}>{r.status === "ready" ? "Indexed" : r.status === "pending" ? "Waiting for indexing" : "Failed"}</span>
                  {r.error && <div className="faint">{r.error}</div>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
