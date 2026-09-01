# -*- coding: utf-8 -*-
"""填充会话池审计:对 1,100 个去重会话逐个判断是否含用户自身的状态断言。

为什么审池子:4,320 个填充实例由 1,100 个不同会话复用而成(中位 3 次,最多
17 次),审池子一次 = 覆盖全部实例,且每个会话只有 1-2K 字符,成本低两个数量级。
判据:是否出现【用户第一人称】或【助手复述】的、关于用户本人的
employer / position / residence / team 状态断言(不必具名机构)。
排除:他人、疑问/计划/愿望/在读学位、纯隐含在职或居住而无值无转移。
产物 results/filler_pool_audit.jsonl(逐会话一行,含逐字引文)
"""
import json, re, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")
import anthropic

SYS = ("You screen filler chit-chat sessions for a benchmark. The benchmark "
       "measures how a user's employer / job position / place of residence / "
       "team changes over time; filler sessions must NOT assert any such state "
       "about the user, or they corrupt the gold answers. Output JSON only.")
TMPL = """SESSION TEXT (a whole filler conversation; 'user:' and 'assistant:' turns):
{text}

Does this session contain any assertion — by the user in the first person, or \
echoed back by the assistant — about the USER'S OWN employer, job position/ \
title, place of residence, or team membership?

Count as an assertion: stating or presupposing a concrete job/employer/place/ \
team ("my students at the language school in Roppongi", "I'm a data analyst at \
a mid-sized company", "I live in Tokyo", "my team at work"), or a transition \
("I got promoted", "I started my new job", "I moved to X"), or the assistant \
echoing one ("Congratulations on your new job").
Do NOT count: other people's jobs or homes; questions, plans, wishes; degrees \
in progress; travel; merely implying employment ("before work", "my commute") \
with no value and no transition.

Return JSON: {{"has_state": true|false, "kinds": ["employer"|"position"| \
"residence"|"team"], "quotes": ["<verbatim sentence>", ...]}}"""


def main():
    pool = json.loads((ROOT / "data/filler_pool_v23.json").read_text(encoding="utf-8"))
    out = ROOT / "results/filler_pool_audit.jsonl"
    done = {json.loads(l)["h"] for l in open(out, encoding="utf-8")} if out.exists() else set()
    fh = open(out, "a", encoding="utf-8")
    cli = anthropic.Anthropic()
    n = flagged = 0
    for h, v in pool.items():
        if h in done: continue
        res = {"has_state": False, "kinds": [], "quotes": []}
        for attempt in range(3):
            try:
                r = cli.messages.create(model="claude-haiku-4-5", max_tokens=800,
                                        temperature=0.0, system=SYS,
                                        messages=[{"role": "user",
                                                   "content": TMPL.format(text=v["text"][:12000])}])
                t = "".join(b.text for b in r.content if b.type == "text")
                m = re.search(r"\{.*\}", t, re.S)
                if m: res = json.loads(m.group(0)); break
            except Exception as ex:
                print(f"retry {attempt}: {str(ex)[:60]}", flush=True); time.sleep(4)
        norm = lambda s: re.sub(r"\s+", " ", s or "").strip().lower()
        body = norm(v["text"])
        qs = [q for q in (res.get("quotes") or []) if norm(q)[:50] in body]
        fh.write(json.dumps({"h": h, "n_uses": v["n"], "slots": v["slots"],
                             "has_state": bool(res.get("has_state")) and bool(qs),
                             "kinds": res.get("kinds") or [], "quotes": qs},
                            ensure_ascii=False) + "\n")
        fh.flush(); n += 1; flagged += bool(qs)
        if n % 50 == 0: print(f"[{n}/{len(pool)}] flagged={flagged}", flush=True)
    print(f"POOL AUDIT DONE n={n} flagged={flagged}")


if __name__ == "__main__":
    main()
