import type { ConfigurationDescription } from "../types";

const MODES: Record<string, string> = { dense: "dense search", hybrid: "hybrid search", lexical: "lexical search" };

/** A configuration as its five parts, read left to right in pipeline order. */
export function ConfigLine({ config, compact }: { config: ConfigurationDescription; compact?: boolean }) {
  const parts: [string, string][] = [
    ["Chunks", config.chunker.display],
    ["Embedding", config.embedder?.display ?? "none"],
    ["Search", MODES[config.search_mode] ?? config.search_mode],
    ["Reranker", config.reranker?.display ?? "none"],
    ["Generator", config.generator?.display ?? "none"],
  ];
  if (compact) {
    const words = [
      `${config.chunker.display} chunks`,
      config.embedder?.display,
      MODES[config.search_mode] ?? config.search_mode,
      config.reranker ? `${config.reranker.display} reranker` : "no reranker",
      config.generator?.display,
    ].filter(Boolean);
    return <span className="config-compact">{words.join(", ")}</span>;
  }
  return (
    <dl className="config-line">
      {parts.map(([k, v]) => (
        <div key={k}>
          <dt>{k}</dt>
          <dd>{v}</dd>
        </div>
      ))}
      <div>
        <dt>Context</dt>
        <dd>{config.top_k} passages</dd>
      </div>
    </dl>
  );
}
