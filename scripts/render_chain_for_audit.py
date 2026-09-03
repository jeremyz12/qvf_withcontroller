# -*- coding: utf-8 -*-
"""审计渲染器:把一条链(uid)的槽位、金标链、全部会话(含填充)按可读文本打出,供逐链审计代理阅读。
用法:python scripts/render_chain_for_audit.py <uid> [--data data/wikistate_full_ALL_v24.json]
标记:[CHAIN] = 金标链所在会话(chain_index 非空);[FILLER] = 填充会话。每轮 user:/assistant:。
"""
import argparse, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from build_corpus_v21 import unwrap  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("uid")
    ap.add_argument("--data", default="data/wikistate_full_ALL_v24.json")
    a = ap.parse_args()
    data = {e["uid"]: e for e in json.loads((ROOT / a.data).read_text(encoding="utf-8"))}
    e = data[a.uid]
    print(f"UID {e['uid']}  SLOT {e['slot']}  SESSIONS {len(e['sessions'])}")
    print("GOLD CHAIN (date | value | anchor):")
    for i, r in enumerate(e["chain"], 1):
        print(f"  #{i} {r['date']} | {r['value']} | \"{r.get('state_span','')}\"")
    print()
    for si, s in enumerate(e["sessions"], 1):
        tag = "CHAIN" if s.get("chain_index") is not None else "FILLER"
        print(f"=== Session {si} [{tag}] date={s.get('date')} ===")
        for t in s.get("turns", []):
            role, body, _ = unwrap(t)
            if isinstance(body, str) and body.strip():
                print(f"{role}: {body.strip()}")
        print()


if __name__ == "__main__":
    main()
