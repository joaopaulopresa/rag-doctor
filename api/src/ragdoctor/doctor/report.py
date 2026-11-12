"""The before/after report as one self-contained HTML page (no scripts, no external files)."""

from __future__ import annotations

from datetime import UTC, datetime
from html import escape
from typing import Any

from ragdoctor.doctor.compare import Comparison
from ragdoctor.doctor.diagnosis import LABELS

CHANGE_LABELS = {
    "fixed": "Fixed",
    "broken": "Newly broken",
    "still_wrong": "Still wrong",
    "still_correct": "Still correct",
}

_STYLE = """
:root{--bg:#f7f7f4;--card:#fff;--ink:#1c2321;--muted:#5d6763;--line:#dfe3df;--accent:#0f766e;
--good:#15803d;--bad:#b42318;--warn:#a15c07}
@media (prefers-color-scheme:dark){:root{--bg:#121614;--card:#1a201d;--ink:#e7ece9;
--muted:#9aa5a0;--line:#2b3430;--accent:#2dd4bf;--good:#4ade80;--bad:#f87171;--warn:#fbbf24}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.5 "Inter",system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1080px;margin:0 auto;padding:32px 20px 64px}
h1{font-size:26px;margin:0 0 4px}h2{font-size:18px;margin:32px 0 12px}
.muted{color:var(--muted)}.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));
gap:12px;margin-top:20px}.tile{background:var(--card);border:1px solid var(--line);border-radius:10px;
padding:14px 16px}.tile b{display:block;font-size:26px;font-variant-numeric:tabular-nums}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);
border-radius:10px;overflow:hidden}th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);
vertical-align:top}th{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
td.num{font-variant-numeric:tabular-nums;white-space:nowrap}
.tag{display:inline-block;padding:1px 8px;border-radius:99px;font-size:12px;border:1px solid var(--line)}
.fixed{color:var(--good)}.broken{color:var(--bad)}.still_wrong{color:var(--warn)}
.note{background:var(--card);border-left:3px solid var(--accent);padding:10px 14px;margin-top:16px}
"""


def _pct(value: float) -> str:
    return f"{100 * value:.1f}%"


def _target(examination: dict[str, Any]) -> str:
    target = examination.get("target") or {}
    return escape(str(target.get("display") or target.get("name") or "?"))


def render_comparison(
    before: dict[str, Any],
    after: dict[str, Any],
    comparison: Comparison,
    questions: dict[str, str],
) -> str:
    """Return the report page.

    Args:
        before: ``{"id", "label", "target"}`` of the first examination.
        after: The same for the second.
        comparison: The result of `compare`.
        questions: Question text by id.
    """
    diff = comparison.difference
    verdict = (
        "The change is significant at the 95% level: the interval of the difference excludes zero."
        if diff.excludes_zero
        else "The interval of the difference includes zero: this change is not significant on "
        "these questions."
    )
    tiles = [
        (
            "Correct before",
            _pct(comparison.before.mean),
            f"{_pct(comparison.before.low)} to {_pct(comparison.before.high)}",
        ),
        (
            "Correct after",
            _pct(comparison.after.mean),
            f"{_pct(comparison.after.low)} to {_pct(comparison.after.high)}",
        ),
        (
            "Difference",
            f"{100 * diff.mean:+.1f} pts",
            f"{100 * diff.low:+.1f} to {100 * diff.high:+.1f} pts",
        ),
        (
            "Questions compared",
            str(comparison.questions),
            f"{comparison.excluded} left out (wrong gold, failed or not in both)",
        ),
    ]
    tile_html = "".join(
        f'<div class="tile"><span class="muted">{escape(t)}</span><b>{escape(v)}</b>'
        f'<span class="muted">{escape(s)}</span></div>'
        for t, v, s in tiles
    )
    counts = "".join(
        f'<div class="tile"><span class="muted">{CHANGE_LABELS[k]}</span><b class="{k}">'
        f"{comparison.counts[k]}</b></div>"
        for k in ("fixed", "broken", "still_wrong", "still_correct")
    )
    order = {"fixed": 0, "broken": 1, "still_wrong": 2, "still_correct": 3}
    rows = "".join(
        f"<tr><td>{escape(m.question_id)}</td><td>{escape(questions.get(m.question_id, ''))}</td>"
        f"<td>{escape(LABELS[m.before])}</td><td>{escape(LABELS[m.after])}</td>"
        f'<td><span class="tag {m.change}">{CHANGE_LABELS[m.change]}</span></td></tr>'
        for m in sorted(comparison.movements, key=lambda m: (order[m.change], m.question_id))
    )
    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Before and after - RAG Doctor</title><style>{_STYLE}</style></head>
<body><main>
<p class="muted">RAG Doctor - before/after report - {generated}</p>
<h1>{escape(str(before.get("label")))} &rarr; {escape(str(after.get("label")))}</h1>
<p class="muted">Before: {_target(before)}<br>After: {_target(after)}</p>
<div class="tiles">{tile_html}</div>
<div class="note">{verdict} Intervals are 95% bootstrap intervals over questions; the difference
uses a paired bootstrap. "Correct" means the judge gave full correctness and the main claim is
supported by the passages. These are judge scores ({escape(str(after.get("judge", "LLM judge")))}),
not yet validated against human labels.</div>
<h2>Movement per question</h2>
<div class="tiles">{counts}</div>
<h2>Every question</h2>
<table><thead><tr><th>Id</th><th>Question</th><th>Before</th><th>After</th><th>Change</th></tr>
</thead><tbody>{rows}</tbody></table>
</main></body></html>
"""
