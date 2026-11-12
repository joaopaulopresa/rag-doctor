import { useCallback, useEffect, useState } from "react";
import { api } from "../../api";
import { ConfigLine } from "../../components/ConfigLine";
import { JobProgress } from "../../components/JobProgress";
import { SelectionForm } from "../../components/SelectionForm";
import type { ConfigurationDescription, Job, Selection } from "../../types";
import { useCatalog } from "../../useCatalog";

type Config = ConfigurationDescription & { id: number; name: string; origin: string; selection: Selection | null };

interface Data {
  active: (Config & { activated_at: string; index_ready: boolean }) | null;
  history: { activation_id: number; note: string; activated_by: string; activated_at: string; active: boolean; configuration: Config }[];
}

export default function Configurations() {
  const catalog = useCatalog();
  const [data, setData] = useState<Data | null>(null);
  const [draft, setDraft] = useState<Selection | null>(null);
  const [name, setName] = useState("");
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api<Data>("/api/admin/configurations").then((d) => {
      setData(d);
      setDraft((current) => current ?? d.active?.selection ?? null);
    });
  }, []);
  useEffect(load, [load]);

  const apply = async (body: Record<string, unknown>) => {
    setError("");
    try {
      const result = await api<{ job: Job | null }>("/api/admin/configurations/apply", { method: "POST", json: body });
      setJob(result.job);
      load();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <div className="page">
      <header className="page-head">
        <h1>Configurations</h1>
        <p className="muted">The chat answers with the active configuration. Every change is kept in the history and can be restored.</p>
      </header>

      {data?.active && (
        <section className="panel pad stack">
          <div className="spread">
            <div>
              <span className="faint">Active since {new Date(data.active.activated_at).toLocaleString()}</span>
              <h2>{data.active.name}</h2>
            </div>
            <span className={`tag${data.active.index_ready ? " pen" : ""}`}>{data.active.index_ready ? "Index ready" : "Index being built"}</span>
          </div>
          <ConfigLine config={data.active} />
          {job && <JobProgress job={job} onFinish={load} />}
        </section>
      )}

      {catalog && draft && (
        <section className="panel pad stack">
          <h2>Make a configuration active</h2>
          <SelectionForm catalog={catalog} value={draft} onChange={setDraft} />
          <div className="row">
            <input placeholder="Name, for the history" value={name} onChange={(e) => setName(e.target.value)} style={{ maxWidth: 320 }} />
            <button className="primary" onClick={() => void apply({ selection: draft, name: name || undefined, note: "Set by hand" })}>
              Apply to the chat
            </button>
          </div>
          <p className="faint">If this configuration has no index yet, the documents are chunked and embedded first; the chat waits for it.</p>
          {error && <p className="notice error">{error}</p>}
        </section>
      )}

      <section className="section">
        <h2>History</h2>
        <div className="panel">
          <table>
            <thead>
              <tr>
                <th>When</th>
                <th>Configuration</th>
                <th>Note</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {data?.history.map((h) => (
                <tr key={h.activation_id}>
                  <td className="nowrap">{new Date(h.activated_at).toLocaleString()}</td>
                  <td>
                    <b>{h.configuration.name}</b>
                    <div className="faint">
                      <ConfigLine config={h.configuration} compact />
                    </div>
                  </td>
                  <td className="muted">
                    {h.note}
                    <div className="faint">{h.activated_by}</div>
                  </td>
                  <td className="num">
                    {h.active ? (
                      <span className="tag pen">Active</span>
                    ) : (
                      <button className="small" onClick={() => void apply({ configuration_id: h.configuration.id, note: `Restored from ${new Date(h.activated_at).toLocaleDateString()}` })}>
                        Restore
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
