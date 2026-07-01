"""Text CLI for the oracle. Run:  PYTHONPATH=app python3 -m oracle.cli "your question"

Uses a local Ollama model if one is running; otherwise the offline template weave.
"""
import sys

from .deck import load_deck, SLOT_LABEL
from .select import select_cards
from .weave import weave
from .llm import LLM

BOLD, DIM, GOLD, RESET = "\033[1m", "\033[2m", "\033[33m", "\033[0m"


def render(question, picks, reading, sel_mode, weave_mode):
    print()
    print(f"{GOLD}{BOLD}🐢  THE TERRIBLE TURTLE ORACLE{RESET}")
    print(f"{DIM}“{question}”{RESET}")
    print(f"{DIM}(cards: {sel_mode} · weave: {weave_mode}){RESET}\n")
    for realm in ("roots", "trunk", "branches"):
        c = picks[realm]
        print(f"{GOLD}▸ {c['name'].upper()}{RESET}  {DIM}— {realm}, {SLOT_LABEL[realm]}{RESET}")
        print(f"  {c['reading']}")
        print(f"  {DIM}↳ {c['real_2026']['name']}{RESET}\n")
    print(f"{BOLD}THE READING{RESET}")
    print(reading["reading"] + "\n")
    print(f"{BOLD}YOUR ADVENTURE TONIGHT{RESET}")
    print(reading["adventure"] + "\n")


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    question = " ".join(argv).strip() or input("Ask the Turtle: ").strip()
    _, _, by_realm = load_deck()
    llm = LLM()
    picks, sel_mode = select_cards(question, by_realm, llm)
    reading, weave_mode = weave(question, picks, llm)
    render(question, picks, reading, sel_mode, weave_mode)


if __name__ == "__main__":
    main()
