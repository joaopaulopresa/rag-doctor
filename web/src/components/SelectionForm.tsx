import type { Catalog, Selection } from "../types";

interface Props {
  catalog: Catalog;
  value: Selection;
  onChange: (value: Selection) => void;
  idPrefix?: string;
}

/** Pick one option per pipeline part from the catalogue. */
export function SelectionForm({ catalog, value, onChange, idPrefix = "sel" }: Props) {
  const set = (patch: Partial<Selection>) => onChange({ ...value, ...patch });
  return (
    <div className="selection-form">
      <label className="field" htmlFor={`${idPrefix}-chunker`}>
        Chunking
        <select id={`${idPrefix}-chunker`} value={value.chunker} onChange={(e) => set({ chunker: e.target.value })}>
          {catalog.chunkers.map((o) => (
            <option key={o.id} value={o.id}>
              {o.label}
            </option>
          ))}
        </select>
      </label>
      <label className="field" htmlFor={`${idPrefix}-mode`}>
        Search
        <select id={`${idPrefix}-mode`} value={value.search_mode} onChange={(e) => set({ search_mode: e.target.value })}>
          {catalog.search_modes.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
      </label>
      <label className="field" htmlFor={`${idPrefix}-embedder`}>
        Embedding model
        <select
          id={`${idPrefix}-embedder`}
          value={value.embedder ?? ""}
          disabled={value.search_mode === "lexical"}
          onChange={(e) => set({ embedder: e.target.value || null })}
        >
          {catalog.embedders.map((o) => (
            <option key={o.id} value={o.id}>
              {o.label}
            </option>
          ))}
        </select>
      </label>
      <label className="field" htmlFor={`${idPrefix}-reranker`}>
        Reranker
        <select id={`${idPrefix}-reranker`} value={value.reranker ?? ""} onChange={(e) => set({ reranker: e.target.value || null })}>
          <option value="">None</option>
          {catalog.rerankers.map((o) => (
            <option key={o.id} value={o.id}>
              {o.label}
              {o.expensive ? " (about 10x the cost)" : ""}
            </option>
          ))}
        </select>
      </label>
      <label className="field" htmlFor={`${idPrefix}-generator`}>
        Generator
        <select id={`${idPrefix}-generator`} value={value.generator ?? ""} onChange={(e) => set({ generator: e.target.value || null })}>
          {catalog.generators.map((o) => (
            <option key={o.id} value={o.id}>
              {o.label}
            </option>
          ))}
        </select>
      </label>
      <label className="field" htmlFor={`${idPrefix}-k`}>
        Passages in context
        <input
          id={`${idPrefix}-k`}
          type="number"
          min={1}
          max={10}
          value={value.top_k}
          onChange={(e) => set({ top_k: Math.max(1, Math.min(10, Number(e.target.value) || 1)) })}
        />
      </label>
    </div>
  );
}
