# -*- coding: utf-8 -*-
"""单遍 Opus-5 机器复核(2026-09-03,用户令):与 scripts/machine_review.py 同一提示词、
同一界面版链(data/app_displayed_chains.json)、同一 v2.0 日志,只换读者模型为 claude-opus-5。
产物 results/machine_review_149_opus5.jsonl(可分片 --shard i --nshard n,输出按片文件)。
本产物是机器审计,不写入任何人类评审身份。
"""
import argparse, json, re, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")
import anthropic
from machine_review import SYS, TMPL, log_of  # 逐字复用提示词与日志渲染

MODEL = None  # 由 --model 指定;默认 claude-opus-5


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--nshard", type=int, default=1)
    ap.add_argument("--model", default="claude-opus-5")
    ap.add_argument("--tag", default="opus5")
    a = ap.parse_args()
    global MODEL
    MODEL = a.model
    items = json.loads((ROOT / "data/app_displayed_chains.json").read_text(encoding="utf-8"))
    cmap = json.loads((ROOT / "data/labelstudio_chainproj_map.json").read_text(encoding="utf-8"))
    data = {e["uid"]: e for e in json.loads((ROOT / "data/wikistate_full_ALL.json").read_text(encoding="utf-8"))}
    out = ROOT / f"results/machine_review_149_{a.tag}_s{a.shard}.jsonl"
    import glob as _g  # 全局续跑:任一分片已出的题都跳过(分片数可变)
    done = {json.loads(l)["item"] for f in _g.glob(str(ROOT / f"results/machine_review_149_{a.tag}_s*.jsonl"))
            for l in open(f, encoding="utf-8")}
    fh = open(out, "a", encoding="utf-8")
    cli = anthropic.Anthropic()
    keys = sorted(items)[a.shard::a.nshard]
    n = 0
    for item in keys:
        info = items[item]
        if item in done: continue
        uid = cmap.get(item, {}).get("uid")
        if uid not in data: continue
        chain = "\n".join(" | ".join(r) for r in info["rows"])
        prompt = TMPL.format(slot=info["slot"], chain=chain, log=log_of(data[uid]))
        res = {"verdict": "unsure", "classes": [], "note": "", "evidence_quote": ""}
        ti = to = 0
        for attempt in range(3):
            try:
                # opus-5 拒绝 temperature 参数("deprecated for this model"),按默认采样;
                # 回复含 ThinkingBlock,只取 text 块。
                r = cli.messages.create(model=MODEL, max_tokens=4000, system=SYS,
                                        messages=[{"role": "user", "content": prompt}])
                ti, to = r.usage.input_tokens, r.usage.output_tokens
                txt = "".join(b.text for b in r.content if b.type == "text")
                m = re.search(r"\{.*\}", txt, re.S)
                if m: res = json.loads(m.group(0)); break
            except Exception as ex:
                print(f"retry {attempt}: {str(ex)[:60]}", flush=True); time.sleep(4)
        q = re.sub(r"\s+", " ", str(res.get("evidence_quote", ""))).strip().lower()
        blob = re.sub(r"\s+", " ", log_of(data[uid])).lower()
        res["quote_verified"] = bool(q) and q in blob
        fh.write(json.dumps({"item": item, "uid": uid, "slot": info["slot"], "model": MODEL,
                             "catch": bool(cmap.get(item, {}).get("catch")),
                             "usage_input_tokens": ti, "usage_output_tokens": to,
                             **res}, ensure_ascii=False) + "\n")
        fh.flush(); n += 1
        print(f"[{a.shard}:{n}] {item} {res['verdict']} {res.get('classes')}", flush=True)
    print(f"MACHINE REVIEW {a.tag} DONE shard {a.shard}: n={n}")


if __name__ == "__main__":
    main()
