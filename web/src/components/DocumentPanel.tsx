import { useEffect, useRef, useState } from "react";
import { api } from "../api";

interface Props {
  documentId: string;
  start: number;
  end: number;
  label?: string;
  onClose: () => void;
}

interface DocumentData {
  id: string;
  title: string;
  source: string;
  text: string;
}

const cache = new Map<string, DocumentData>();
const CONTEXT = 2400;

/** The source document around a passage, with the passage highlighted and scrolled into view. */
export function DocumentPanel({ documentId, start, end, label, onClose }: Props) {
  const [doc, setDoc] = useState<DocumentData | null>(cache.get(documentId) ?? null);
  const [error, setError] = useState("");
  const [full, setFull] = useState(false);
  const markRef = useRef<HTMLElement>(null);

  useEffect(() => {
    setFull(false);
    if (cache.has(documentId)) {
      setDoc(cache.get(documentId)!);
      return;
    }
    setDoc(null);
    api<DocumentData>(`/api/documents/${encodeURI(documentId)}`)
      .then((data) => {
        cache.set(documentId, data);
        setDoc(data);
      })
      .catch((e: Error) => setError(e.message));
  }, [documentId]);

  useEffect(() => {
    const mark = markRef.current;
    const body = mark?.closest(".doc-body");
    if (mark && body) {
      const offset = mark.getBoundingClientRect().top - body.getBoundingClientRect().top;
      body.scrollTo({ top: Math.max(0, body.scrollTop + offset - 80), behavior: "smooth" });
    }
  }, [doc, start, end, full]);

  const from = full ? 0 : Math.max(0, start - CONTEXT);
  const to = full || !doc ? doc?.text.length ?? 0 : Math.min(doc.text.length, end + CONTEXT);

  return (
    <aside className="document-panel" aria-label="Source document">
      <header className="spread">
        <div className="grow">
          {label && <span className="tag pen">{label}</span>}
          <h2 className="doc-title">{doc?.title ?? documentId}</h2>
          <p className="faint">{documentId}</p>
        </div>
        <button className="quiet" onClick={onClose} aria-label="Close the document">
          Close
        </button>
      </header>
      {error && <p className="notice error">{error}</p>}
      {!doc && !error && (
        <p className="row muted">
          <span className="spinner" /> Opening the document
        </p>
      )}
      {doc && (
        <div className="doc-body passage-text">
          {from > 0 && <p className="faint doc-cut">Beginning of the document not shown.</p>}
          {doc.text.slice(from, start)}
          <mark ref={markRef}>{doc.text.slice(start, end)}</mark>
          {doc.text.slice(end, to)}
          {(from > 0 || to < doc.text.length) && (
            <p className="doc-cut">
              <button className="small" onClick={() => setFull(true)}>
                Show the whole document
              </button>
            </p>
          )}
        </div>
      )}
    </aside>
  );
}
