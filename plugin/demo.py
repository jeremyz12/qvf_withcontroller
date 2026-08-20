# -*- coding: utf-8 -*-
"""qvf_plugin demo: 6 sessions in (4 state declarations + 2 distractors),
4 questions out. Data = one real WikiState entity (employment history of a
real person via Wikidata CC0; dialogue carrier is synthetic).

Run:  python demo.py        (needs ANTHROPIC_API_KEY in env or ../.env)
"""
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
try:                                     # optional .env convenience
    from dotenv import load_dotenv
    load_dotenv(HERE.parent / ".env")
except ImportError:
    pass

from qvf_plugin import QVFMemory

SESSIONS = json.loads((HERE / "demo_sessions.json").read_text(encoding="utf-8"))["sessions"]

QUESTIONS = [
    ("(Today is 1998-09-01.) What's my current employer these days?", "1998-09-01"),
    ("What employer did I have on 1987-08-16?", "1998-09-01"),
    ("(Today is 1998-09-01.) How many times did I change my employer?", "1998-09-01"),
    ("(Today is 1998-09-01.) Which employer did I hold the longest?", "1998-09-01"),
]

def main():
    mem = QVFMemory()
    for d, text in SESSIONS:
        n = mem.ingest(text, date=d)
        print(f"[ingest {d}] +{n} card(s)")
    print(f"\ntotal cards: {len(mem.cards)}\n" + "=" * 60)
    for q, today in QUESTIONS:
        out = mem.ask(q, today=today)
        print(f"\nQ: {q}\n  route  : {out['route']}")
        if out.get("derived"):
            print(f"  derived: {out['derived'][0][:90]}")
        print(f"  answer : {out['answer'][:200]}")

if __name__ == "__main__":
    main()
