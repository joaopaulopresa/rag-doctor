/** Splits an answer into text and citation markers such as [2] or [1, 3]. */
export type Segment = { kind: "text"; text: string } | { kind: "cite"; numbers: number[] };

const CITATION = /\[(\d+(?:\s*,\s*\d+)*)\]/g;

export function splitCitations(answer: string): Segment[] {
  const segments: Segment[] = [];
  let last = 0;
  for (const match of answer.matchAll(CITATION)) {
    const index = match.index ?? 0;
    if (index > last) segments.push({ kind: "text", text: answer.slice(last, index) });
    segments.push({ kind: "cite", numbers: match[1].split(",").map((n) => Number(n.trim())) });
    last = index + match[0].length;
  }
  if (last < answer.length) segments.push({ kind: "text", text: answer.slice(last) });
  return segments;
}
