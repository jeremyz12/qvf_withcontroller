# -*- coding: utf-8 -*-
"""批 33-E 共享嵌入缓存:把 v2.4 全库记忆流用 text-embedding-3-small 嵌一次,
落盘 npz(uid -> [n,1536] float32,**未归一化**,与 OpenAIDenseRetriever._embed
返回值逐位同源),供 E1(交叉编码重排)与 E2(时间融合)两臂共用。

动机:两臂 + 网格共需 ~2000 次检索,逐进程重嵌 23,754 条既慢又多花 6x 嵌入费;
一次缓存保证 E1/E2/参照 direct 三者用**完全相同**的稠密底座,消除嵌入器自由度。

记忆装配逐字复用 scripts/ext_direct_arm._memories(不复制)。

用法:
  QVF_EMBED_BACKEND=openai PYTHONUTF8=1 python scripts/b33e_embed_cache.py \
      --data data/wikistate_full_ALL_v24.json --out <path>.npz
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dotenv import load_dotenv  # noqa: E402
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import numpy as np  # noqa: E402
from openai import OpenAI  # noqa: E402

from ext_direct_arm import _memories  # noqa: E402

MODEL = "text-embedding-3-small"


def embed_batch(client: OpenAI, texts):
    batch = [t if t.strip() else " " for t in texts]
    r = client.embeddings.create(model=MODEL, input=batch)
    return [d.embedding for d in r.data], r.usage.total_tokens


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/wikistate_full_ALL_v24.json")
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()

    entries = json.loads(Path(a.data).read_text(encoding="utf-8"))
    client = OpenAI()
    # 全库拉平成一份 (uid, 序号, 文本) 表,按 256 切批(与
    # OpenAIDenseRetriever._embed 同批量),4 线程并发。
    flat, spans = [], {}
    for e in entries:
        mems = _memories(e)
        spans[e["uid"]] = (len(flat), len(flat) + len(mems))
        flat.extend(m.content for m in mems)
    print(f"entries={len(entries)} memories={len(flat)}", flush=True)

    chunks = [(i, flat[i:i + 256]) for i in range(0, len(flat), 256)]
    out = [None] * len(chunks)
    tok = [0] * len(chunks)
    t0 = time.time()

    def work(k):
        i, texts = chunks[k]
        for attempt in range(4):
            try:
                v, u = embed_batch(client, texts)
                return k, v, u
            except Exception as exc:  # noqa: BLE001
                print(f"retry {attempt} chunk {k}: {type(exc).__name__}",
                      flush=True)
                time.sleep(3 * (attempt + 1))
        raise RuntimeError(f"chunk {k} failed")

    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        for k, v, u in ex.map(work, range(len(chunks))):
            out[k], tok[k] = v, u
            if k % 20 == 0:
                print(f"chunk {k}/{len(chunks)} ({time.time() - t0:.0f}s)",
                      flush=True)

    mat = np.asarray([v for c in out for v in c], dtype="float32")
    assert mat.shape[0] == len(flat), (mat.shape, len(flat))
    store = {uid: mat[s:e] for uid, (s, e) in spans.items()}
    outp = Path(a.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    np.savez(outp, **store)
    total_tok = sum(tok)
    print(f"WROTE {outp} uids={len(store)} rows={mat.shape} "
          f"embed_tokens={total_tok} cost=${total_tok / 1e6 * 0.02:.4f} "
          f"({time.time() - t0:.0f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
