"""Regenerate the score section of EVAL_REPORT.md from saved results, so no number in
the report is typed by hand. Everything between the AUTO markers is replaced; the
hand-written failure-and-fix writeup outside them is kept.

  python -m eval.report
"""
import json
from pathlib import Path

from agent.config import ROOT
from eval.metrics import SUM_KEYS

START, END = "<!-- AUTO:START (python -m eval.report) -->", "<!-- AUTO:END -->"


def load():
    out = {}
    for f in sorted((ROOT / "results").glob("*/summary.json")):
        if f.parent.name != "scratch":
            out[f.parent.name] = json.loads(f.read_text(encoding="utf-8"))
    return out


def build(versions: dict) -> str:
    if not versions:
        return "No eval runs saved yet. Run `python -m eval.run_eval`."
    names = list(versions)
    first = versions[names[0]]["runs"][0]["conversations"]
    lines = ["| Conv | Name | " + " | ".join(f"{v} (checks per run)" for v in names) + " | " +
             " | ".join(f"{v} passed runs" for v in names) + f" | Critical failures ({names[-1]}) |",
             "|---|---|" + "---|" * (2 * len(names) + 1)]
    for c in first:
        cells, passes = [], []
        for v in names:
            runs = versions[v]["runs"]
            rows = [next((x for x in r["conversations"] if x["id"] == c["id"]), None) for r in runs]
            cells.append(" · ".join("—" if x is None else ("crash" if x.get("crashed") else
                                                           f"{x['n_passed']}/{x['n_scored']}") for x in rows))
            passes.append(f"{sum(1 for x in rows if x and x['passed'])}/{len(rows)}")
        last = [next((x for x in r["conversations"] if x["id"] == c["id"]), None) for r in versions[names[-1]]["runs"]]
        crit = sorted({f for x in last if x for f in (x.get("critical_failures") or [])})
        lines.append(f"| {c['id']} | {c['name']} | " + " | ".join(cells) + " | " + " | ".join(passes) +
                     f" | {', '.join(crit) or '—'} |")
    for v in names:
        lines += ["", f"### Prompt {v}", ""]
        meta = versions[v]["runs"][0]["meta"]
        lines += [f"Model `{meta['model']}`, effort `{meta['effort']}`, judge {'on' if meta['judge'] else 'off'}, "
                  f"today {meta['today']}. Transcripts in `transcripts/{v}/`, raw results in `results/{v}/`.", "",
                  "| Run | Checks | Conversations passing | " + " | ".join(SUM_KEYS) + " |",
                  "|---|---|---|" + "---|" * len(SUM_KEYS)]
        for k, r in enumerate(versions[v]["runs"], 1):
            t = r["totals"]
            lines.append(f"| {k} ({r['meta']['timestamp']}) | {t['checks_passed']}/{t['checks_scored']} "
                         f"({t['pct']:.1f}%) | {t['conversations_passed']}/{t['conversations']} | " +
                         " | ".join(str(t["metrics"][key]) for key in SUM_KEYS) + " |")
    return "\n".join(lines)


def main():
    path = ROOT / "EVAL_REPORT.md"
    text = path.read_text(encoding="utf-8") if path.exists() else f"# Eval report\n\n{START}\n{END}\n"
    if START not in text:
        text += f"\n{START}\n{END}\n"
    head, rest = text.split(START, 1)
    _, tail = rest.split(END, 1)
    path.write_text(f"{head}{START}\n{build(load())}\n{END}{tail}", encoding="utf-8")
    print("updated EVAL_REPORT.md")


if __name__ == "__main__":
    main()
