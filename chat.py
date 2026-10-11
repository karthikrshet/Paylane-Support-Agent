"""Talk to the agent yourself. Tool calls and guard decisions print as they happen.

  python chat.py                    # real model (needs ANTHROPIC_API_KEY or `ant auth login`)
  python chat.py --fail-escalation  # simulate an escalation outage
"""
import argparse
import json

from rich.console import Console

from agent import config
from agent.llm import make_llm
from agent.prompt import system_prompt
from agent.runner import Conversation
from paylane.api import MockPaylane
from paylane.session import Session


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", default=config.PROMPT_VERSION)
    ap.add_argument("--fail-escalation", action="store_true")
    ap.add_argument("--fail-refund", default="", help="comma-separated txn ids the processor rejects")
    a = ap.parse_args()

    con = Console()
    api = MockPaylane(fail_escalation=a.fail_escalation,
                      fail_refund={x.strip().upper() for x in a.fail_refund.split(",") if x.strip()})
    s = Session()
    llm = make_llm(config.PROVIDER, config.MODEL, config.EFFORT, config.FALLBACKS)
    convo = Conversation(llm, system_prompt(a.prompt, config.TODAY_DATE), api, s, config.TODAY_DATE)
    con.print(f"[dim]Paylane support · model {config.MODEL} · prompt {a.prompt} · today {config.TODAY_DATE}. "
              f"Test customers: priya@example.com/4821, marcus@example.com/1934, aisha@example.com/7710 (frozen), "
              f"tom@example.com/5502. Ctrl+C to quit.[/dim]")
    seen = 0
    while True:
        try:
            text = con.input("[bold cyan]you>[/bold cyan] ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not text:
            continue
        r = convo.send(text)
        for e in s.events[seen:]:
            if e["kind"] == "model_response":
                continue
            if e["kind"] == "tool":
                con.print(f"[dim]  {e['tool']}({json.dumps(e['args'])}) → {e['decision']} → "
                          f"{json.dumps(e['result'])}[/dim]")
            else:
                con.print(f"[dim]  {e['kind']}: {json.dumps({k: v for k, v in e.items() if k not in ('turn', 'kind')})}[/dim]")
        seen = len(s.events)
        if r.fallback:
            con.print(f"[yellow]  (runner fallback: {r.fallback}; model draft: {r.draft!r})[/yellow]")
        con.print(f"[bold green]agent>[/bold green] {r.reply}")


if __name__ == "__main__":
    main()
