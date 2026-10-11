"""Run every conversation against the real model, score it from the event log, and
write transcripts + results. Nothing in the report is typed in by hand.

  python -m eval.run_eval                     # all 21 (12 core + extra edges), 1 run, prompt v1
  python -m eval.run_eval --runs 3 --judge    # 3 runs per conversation, LLM judge on
  python -m eval.run_eval --only c04,c10      # quick look; written to results/scratch/

Full runs refuse to overwrite an earlier run of the same prompt version (so v1 stays
untouched once v2 exists) unless --overwrite is passed.
"""
import argparse
import glob
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import yaml

from agent import config
from agent.llm import make_llm
from agent.prompt import system_prompt
from agent.runner import Conversation
from eval import checks as C
from eval.judge import PROMISE_RUBRIC, make_judge, transcript_for_judge
from eval.metrics import SUM_KEYS, conversation_metrics, total
from paylane.api import MockPaylane
from paylane.redact import redact, redact_text
from paylane.session import Session

ROOT = config.ROOT


# ---------------------------------------------------------------- running

def load_conversations(only=None, suite="all"):
    convs = []
    for f in sorted(glob.glob(str(ROOT / "conversations" / "*.yaml"))):
        c = yaml.safe_load(Path(f).read_text(encoding="utf-8"))
        c["file"] = Path(f).name
        if only and c["id"] not in only:
            continue
        if suite == "core" and not c["id"].startswith("c"):
            continue
        if suite == "extra" and not c["id"].startswith("e"):
            continue
        convs.append(c)
    return convs


def run_conversation(conv, llm, system, today) -> dict:
    setup = conv.get("setup") or {}
    api = MockPaylane(fail_escalation=setup.get("fail_escalation", False),
                      fail_refund=setup.get("fail_refund", ()))
    s = Session()
    convo = Conversation(llm, system, api, s, today)
    turns = []
    for i, text in enumerate(conv["turns"], 1):
        r = convo.send(text)
        turns.append({"turn": i, "customer": text, "reply": r.reply, "draft": r.draft, "fallback": r.fallback})
    return {"id": conv["id"], "name": conv["name"], "turns": turns, "events": s.events,
            "tickets": list(s.tickets), "final_status": {k: t["status"] for k, t in api.txns.items()}}


def score(rec, conv, judge) -> list[dict]:
    out = []
    redacted_turns = [{**t, "customer": redact_text(t["customer"])} for t in rec["turns"]]
    for entry in conv["checks"]:
        name, param = C.parse_check(entry)
        if name == "judge":
            if judge:
                passed, detail = judge.grade(param, transcript_for_judge(redacted_turns))
            else:
                passed, detail = None, "skipped: judge off (use --judge, or hand review)"
        elif name == "no_unpromised_commitments":
            passed, detail = C.no_unpromised_commitments_regex(rec)
            if judge and passed:
                jp, jd = judge.grade(PROMISE_RUBRIC, transcript_for_judge(redacted_turns))
                passed, detail = (jp if jp is not None else passed), f"regex ok; judge: {jd}"
            elif not judge:
                detail += " (regex only; judge off)"
        else:
            fn = C.CHECKS.get(name)
            if fn is None:
                raise SystemExit(f"{conv['file']}: unknown check {name!r}")
            passed, detail = fn(rec, param)
        out.append({"check": C.label(name, param), "name": name, "critical": name not in C.NON_CRITICAL,
                    "passed": passed, "detail": detail})
    return out


def actual_decision(rec) -> dict:
    refunds = sorted({(e["args"] or {}).get("txn_id", "").upper() for e in C.ok_refunds(rec)})
    return {"refunds": refunds, "escalate": bool(C.escalations(rec))}


def evaluate(conv, llm, system, today, judge) -> dict:
    try:
        rec = run_conversation(conv, llm, system, today)
    except Exception as e:  # a crash is a failure of the run, recorded, never hidden
        return {"id": conv["id"], "name": conv["name"], "crashed": f"{type(e).__name__}: {e}",
                "checks": [], "passed": False}
    results = score(rec, conv, judge)
    scored = [r for r in results if r["passed"] is not None]
    crit_fail = [r["check"] for r in results if r["critical"] and r["passed"] is False]
    expected = conv.get("expected") or {}
    actual = actual_decision(rec)
    saved = {**rec, "turns": [{**t, "customer": redact_text(t["customer"]), "reply": redact_text(t["reply"]),
                               "draft": redact_text(t["draft"]) if t["draft"] else None} for t in rec["turns"]]}
    return {"id": conv["id"], "name": conv["name"], "type": conv.get("type"), "why": conv.get("why"),
            "checks": results, "n_scored": len(scored), "n_passed": sum(1 for r in scored if r["passed"]),
            "critical_failures": crit_fail, "passed": not crit_fail,
            "expected": expected, "actual": actual,
            "decision_match": (sorted(expected.get("refunds", [])) == actual["refunds"]
                               and bool(expected.get("escalate")) == actual["escalate"]) if expected else None,
            "metrics": conversation_metrics(rec), "record": saved}


# ---------------------------------------------------------------- writing

def fmt_args(args):
    if not isinstance(args, dict):
        return json.dumps(args)
    return ", ".join(f"{k}={json.dumps(v, ensure_ascii=False)}" for k, v in args.items())


def write_transcript(path: Path, res: dict, meta: dict):
    lines = [f"# {res['id']}: {res['name']}", "",
             f"Model `{meta['model']}` · prompt `{meta['prompt_version']}` · effort `{meta['effort']}` · "
             f"today {meta['today']} · run {meta['run']} · {meta['timestamp']}", ""]
    if res.get("crashed"):
        lines += [f"**CRASHED:** {res['crashed']}", ""]
        path.write_text("\n".join(lines), encoding="utf-8")
        return
    rec = res["record"]
    if res.get("why"):
        lines += [f"_Why this case:_ {res['why']}", ""]
    lines += [f"**Result: {'PASS' if res['passed'] else 'FAIL'}** · {res['n_passed']}/{res['n_scored']} checks · "
              f"expected {json.dumps(res['expected'])} · actual {json.dumps(res['actual'])}", ""]
    for t in rec["turns"]:
        lines += [f"## Turn {t['turn']}", "", f"**Customer:** {t['customer']}", ""]
        n_before = len(lines)
        for e in rec["events"]:
            if e["turn"] != t["turn"] or e["kind"] == "model_response":
                continue
            if e["kind"] == "tool":
                status = f" · txn now `{e['txn_status_after']}`" if e.get("txn_status_after") else ""
                lines.append(f"- `{e['tool']}({fmt_args(e['args'])})` [{e['source']}] → **{e['decision']}** → "
                             f"`{json.dumps(e['result'], ensure_ascii=False)}`{status}")
            elif e["kind"] == "escalation":
                how = "reused open ticket" if e.get("reused") else ("ticket " + e["ticket_id"] if e.get("ticket_id")
                                                                    else f"FAILED {json.dumps(e.get('result'))}")
                lines.append(f"- escalation [{e['source']}] → {how} · summary: _{e['summary']}_")
            else:
                extra = {k: v for k, v in e.items() if k not in ("turn", "kind")}
                lines.append(f"- {e['kind']} {json.dumps(extra, ensure_ascii=False)}")
        lines += ([""] if len(lines) > n_before else []) + [f"**Agent:** {t['reply']}", ""]
        if t.get("fallback"):
            lines += [f"> Runner fallback ({t['fallback']}). Model draft, not shown to the customer: "
                      f"{t['draft'] or '(none)'}", ""]
    lines += ["## Checks", "", "| Check | Critical | Result | Detail |", "|---|---|---|---|"]
    for r in res["checks"]:
        mark = {True: "PASS", False: "**FAIL**", None: "skip"}[r["passed"]]
        lines.append(f"| {r['check']} | {'yes' if r['critical'] else 'no'} | {mark} | "
                     f"{str(r['detail']).replace('|', '/')} |")
    m = res["metrics"]
    lines += ["", "## Safety metrics", "", ", ".join(f"{k}: {m[k]}" for k in SUM_KEYS)]
    if m["forbidden_detail"]:
        lines += ["", f"Forbidden attempts: `{json.dumps(m['forbidden_detail'])}`"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_summary(out_dir: Path, version: str, runs: list[dict]):
    convs = [c["id"] for c in runs[0]["conversations"]]
    by = {cid: [next(x for x in r["conversations"] if x["id"] == cid) for r in runs] for cid in convs}
    n = len(runs)
    lines = [f"# Eval summary: prompt {version}", "",
             f"{n} run(s). Provider `{runs[0]['meta']['provider']}`, model `{runs[0]['meta']['model']}`, effort `{runs[0]['meta']['effort']}`, "
             f"judge {'on' if runs[0]['meta']['judge'] else 'off'}. Generated by eval/run_eval.py.", "",
             "| Conv | Name | Checks per run | Passed (runs) | Critical failures |", "|---|---|---|---|---|"]
    for cid in convs:
        rs = by[cid]
        per = " · ".join("crash" if r.get("crashed") else f"{r['n_passed']}/{r['n_scored']}" for r in rs)
        passed = sum(1 for r in rs if r["passed"])
        crit = sorted({f for r in rs for f in r.get("critical_failures", [])} |
                      ({"crashed"} if any(r.get("crashed") for r in rs) else set()))
        lines.append(f"| {cid} | {rs[0]['name']} | {per} | {passed}/{n} | {', '.join(crit) or '—'} |")
    for k, r in enumerate(runs, 1):
        t = r["totals"]
        lines += ["", f"**Run {k}:** {t['checks_passed']}/{t['checks_scored']} checks "
                      f"({t['pct']:.1f}%), {t['conversations_passed']}/{t['conversations']} conversations pass. "
                      f"Core: {t['core_passed']}/{t['core_total']}.",
                  "", "| Metric | Value |", "|---|---|"]
        lines += [f"| {key} | {t['metrics'][key]} |" for key in SUM_KEYS]
        lines += ["", f"Transcripts: `transcripts/{version}/run{k}/`"]
    (out_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out_dir / "summary.json").write_text(json.dumps(
        {"version": version, "runs": [{"meta": r["meta"], "totals": r["totals"],
                                       "conversations": [{k: c.get(k) for k in (
                                           "id", "name", "passed", "n_passed", "n_scored", "critical_failures",
                                           "decision_match", "crashed")} for c in r["conversations"]]}
                                      for r in runs]}, indent=2), encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", default=config.PROMPT_VERSION)
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--only", default="", help="comma-separated conversation ids")
    ap.add_argument("--suite", choices=["all", "core", "extra"], default="all")
    ap.add_argument("--judge", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--overwrite", action="store_true")
    a = ap.parse_args(argv)

    only = {x.strip() for x in a.only.split(",") if x.strip()}
    convs = load_conversations(only, a.suite)
    if not convs:
        raise SystemExit("no conversations matched")
    scratch = bool(only) or a.suite != "all"
    tag = "scratch" if scratch else a.prompt
    res_dir, tr_root = ROOT / "results" / tag, ROOT / "transcripts" / tag
    if not scratch and (res_dir / "run1.json").exists() and not a.overwrite:
        raise SystemExit(f"results/{tag} already exists. Freeze it, add a new prompt version, "
                         f"or pass --overwrite if you really mean it.")
    res_dir.mkdir(parents=True, exist_ok=True)

    system = system_prompt(a.prompt, config.TODAY_DATE)
    llm = make_llm(config.PROVIDER, config.MODEL, config.EFFORT, config.FALLBACKS)
    judge = make_judge(config.PROVIDER, config.JUDGE_MODEL) if a.judge else None

    runs = []
    for k in range(1, a.runs + 1):
        meta = {**config.snapshot(), "prompt_version": a.prompt, "run": k, "judge": bool(judge),
                "judge_model": config.JUDGE_MODEL if judge else None,
                "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "conversations": [c["id"] for c in convs]}
        print(f"run {k}/{a.runs}: {len(convs)} conversations, model {meta['model']}, prompt {a.prompt}", flush=True)
        with ThreadPoolExecutor(max_workers=max(1, a.workers)) as pool:
            results = list(pool.map(lambda c: evaluate(c, llm, system, config.TODAY_DATE, judge), convs))
        tr_dir = tr_root / f"run{k}"
        tr_dir.mkdir(parents=True, exist_ok=True)
        for res in results:
            write_transcript(tr_dir / f"{res['id']}.md", res, meta)
            mark = "CRASH" if res.get("crashed") else ("PASS" if res["passed"] else "FAIL")
            print(f"  {res['id']:<5} {mark:<5} {res.get('n_passed', 0)}/{res.get('n_scored', 0)} "
                  f"{', '.join(res.get('critical_failures', [])) or res.get('crashed', '')}", flush=True)
        ok = [r for r in results if not r.get("crashed")]
        cp, cs = sum(r["n_passed"] for r in ok), sum(r["n_scored"] for r in ok)
        totals = {"checks_passed": cp, "checks_scored": cs, "pct": 100 * cp / cs if cs else 0.0,
                  "conversations": len(results), "conversations_passed": sum(1 for r in results if r["passed"]),
                  "core_passed": sum(1 for r in results if r["passed"] and r["id"].startswith("c")),
                  "core_total": sum(1 for r in results if r["id"].startswith("c")),
                  "crashes": len(results) - len(ok),
                  "metrics": total([r["metrics"] for r in ok])}
        run = {"meta": meta, "totals": totals, "conversations": results}
        (res_dir / f"run{k}.json").write_text(json.dumps(redact(run), indent=2, ensure_ascii=False), encoding="utf-8")
        runs.append(run)
        print(f"  score {cp}/{cs} ({totals['pct']:.1f}%) | conversations {totals['conversations_passed']}/"
              f"{len(results)} | policy-violating executions {totals['metrics']['policy_violating_executions']} | "
              f"forbidden attempts {totals['metrics']['forbidden_refund_attempts']}", flush=True)
    write_summary(res_dir, tag, runs)
    print(f"wrote results/{tag}/summary.md and transcripts/{tag}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
