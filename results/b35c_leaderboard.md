# 竞品同题榜单(批 35c,2026-09-04):WikiState v2.5 抽样 15 链 / 58 题

- 语料 data/wikistate_full_ALL_v25.json;链 results/b35c_sample_uids.txt(employer 4 / position 4 / residence 4 / team 3,取自批 35 的 36 链分层样本);题 results/b35c_questions.jsonl(58)。
- 协议沿用 60 题标定场:读者 claude-haiku-4-5、temperature 0、max_tokens 300、READER_SYS;判官 qvf.judge.ClaudeJudge(claude-opus-5);k=10;各系统自带建库,每链新建;只加命令行参数不改机制。每个系统由独立代理复算并核对 `git diff -- scripts` 未触协议常量(parity)。
- 成本按 haiku $1/$5 每百万;建库费用按各自 verdict(部分为估算,见各文件)。QVF 各臂与全上下文行取自其他批次在同 58 题上的逐题行(v2.5 店 = 批 35;v2.4 店 = 批 33-A;全上下文 = 批 36),同读者同判官。

## 一、榜单(按准确率)

| 系统 | n | 准确率 | Wilson 95% | 每题输入 tok | 每题输出 tok | 中位延迟 s | 建库 s/店 | 本批花费 $ | 复核 | 备注 |
|---|---|---|---|---|---|---|---|---|---|---|
| QVF 账目(v2.5 店 v46,批 35) | 58 | 98.3 | [90.9, 99.7] | 2713.3 | 470.2 | 5.5 | — | — | (同题行) | 写时卡 + 读时账目;店建于 v2.5 |
| QVF 账目(v2.4 店 v45,批 33-A) | 58 | 89.7 | [79.2, 95.2] | 2809.4 | 479.0 | 4.8 | — | — | (同题行) | 同题另一店;两店差为抽样噪声 |
| QVF 计算臂(v2.5 派生店) | 58 | 75.9 | [63.5, 85.0] | 2269.0 | 95.1 | 5.2 | — | — | (同题行) | 无协议 |
| 全上下文裸调用(批 36,haiku) | 58 | 63.8 | [50.9, 74.9] | 13649.6 | 211.2 | 3.0 | — | — | (同题行) | 完整记录进 prompt,"日常情况"基线;v2.4 语料 |
| timeline | 58 | 56.9 | [44.1, 68.8] | 1853.8 | 95.3 | 4.6 | 44.8 | 0.7 | 通过 | Zero protocol deviations from the 60-question calibration run: reader claude-haiku-4-5 / t |
| lgstore | 58 | 46.6 | [34.3, 59.2] | 1195 | 84.3 | 5.0 | 3.9 | 0.1 | 通过 | RESUME: results/b35c_lgstore.jsonl already held 51 judged rows (13 full uids + 1 question  |
| hipporag2 | 58 | 46.5 | [34.3, 59.2] | 1194.9 | 82.3 | 6.0 | 31.1 | 0.5 | 通过 | RESUME: file was already COMPLETE on arrival - 58 rows / 58 unique question_ids, exactly e |
| txtai | 58 | 44.8 | [32.7, 57.5] | 1205.2 | 81.9 | 4.6 | 6.2 | 0.3 | 通过 | acc is reported in percent (26/58 correct). Per question type: change_count 20.00 (3/15),  |
| cognee | 58 | 44.8 | [32.7, 57.5] | 1198.1 | 84.1 | 6.3 | 33.3 | 1.1 | 通过 | acc is reported in PERCENT (26/58 = 44.83%); per type: change_count 5/15=33.33, count_befo |
| letta_fs | 58 | 43.1 | [31.2, 55.9] | 30190.5 | 674.6 | 12.6 | 0.0 | 2.1 | 通过 | RESUME: results/b35c_letta_fs.jsonl already held 58 judged rows covering ALL 58 qids (0 mi |
| amem | 58 | 39.7 | [28.1, 52.5] | 1211.8 | 84.6 | 4.9 | 120 | 0.6 | 通过 | acc reported as a fraction: 0.3966 = 39.66% (23/58). RESUME: results/b35c_amem.jsonl alrea |
| top-10 直读(v2.5,批 35) | 58 | 37.9 | [26.6, 50.8] | 861.9 | 85.3 | 1.6 | — | — | (同题行) | OpenAI 嵌入 top-10 |
| sumrag | 58 | 36.2 | [25.1, 49.1] | 918.9 | 85.9 | 4.9 | 57.1 | 0.8 | 通过 | acc is reported as a PERCENT (21/58 correct). Per question type: change_count 3/15 = 20.00 |
| langmem | 58 | 32.8 | [22.1, 45.6] | 835 | 100.1 | 5.1 | 288.8 | 3.4 | 通过 | No protocol deviation from the 60-question calibration run: reader / judge / k=10 / 300-ch |
| memos | 58 | 31.0 | [20.6, 43.8] | 613 | 92.4 | 5.0 | 207.8 | 2.9 | 通过 | RESUME OUTCOME: nothing was left to run. results/b35c_memos.jsonl already held 58 rows / 5 |
| mstrata | 58 | 13.8 | [7.2, 24.9] | 319.8 | 75.6 | 4.6 | 67.8 | 1.0 | 通过 | No protocol deviation. Reader/judge/k=10/300-char truncation/sess_text/date-ordered ingest |
| obsrag | 58 | 13.8 | [7.2, 24.9] | 210.1 | 74.9 | 4.8 | 75.2 | 0.9 | 通过 | acc is reported as a percentage (13.79% = 8/58), matching the README/leaderboard conventio |
| bm25 | 58 | 12.1 | [6.0, 22.9] | 1213.4 | 86.1 | 4.6 | 0.0 | 0.5 | 通过 | RESUME: 54 of the 58 rows were already in results/b35c_bm25.jsonl from an earlier interrup |
| mem0 | 58 | 10.3 | [4.8, 20.8] | 786.4 | 101 | 5.0 | 81 | 0.8 | 通过 | 1) Corpus/questions/uids swapped to b35c per task (v2.5, 58 q, 15 uids); reader/judge/k/tr |

- TRACE 在本批因 API 529 两次中断,单独补跑中(结果出来后追加一行)。Graphiti / LightRAG 沿用批 33 判定为构造性失败,未列;Letta 服务端 / Memobase 需 Docker,阻塞。
- 中段(lgstore / HippoRAG 2 / txtai / cognee / Letta-FS / A-MEM)区间互相覆盖,不排名;首尾分离。
- 全上下文裸调用(haiku)63.8 高于全部竞品:这些系统在 14K 小库上的取证策略不如"什么都不做、全放进去";只有 QVF 账目显著高于它。

## 二、60 题 v1 标定场存档(仅参考,不同语料不同题,不可与上表相减)

| 系统 | acc |
|---|---|
| QVF 账目 / 编译 / 选择 | 86.7 / 83.3 / 70.0 |
| timeline | 63.3 |
| Letta-FS | 56.7 |
| HippoRAG 2 | 55.0 |
| lgstore / txtai / 直读 | 55.0 / 53.3 / 51.7 |
| 摘要 RAG / cognee / MemOS | 46.7 / 46.7 / 45.0 |
| A-MEM / LangMem | 43.3 / 40.0 |
| TRACE(LoCoMo 配置 / 出厂) | 30.0 / 16.7 |
| Mem0 / BM25 / obs-RAG / 盖章台账 | 26.7 / 13.3 / 13.3 / 11.7 |
| Graphiti / LightRAG | 3.3 / 1.7 |

## 三、各系统偏离与复核摘录

### amem
- 状态 done;脚本改动:scripts/repro_batch4.py only (CLI plumbing + metering; no protocol constants touched). amem-relevant changes: (1) new --amem-repo PATH -> sets env AMEM_REPO; AmemSystem.__init__ now does repo = os.environ.get("AMEM_REPO") or <old hardcoded Temp path>, then sys.path.insert(0, repo); it also runs `git
- 偏离:acc reported as a fraction: 0.3966 = 39.66% (23/58). RESUME: results/b35c_amem.jsonl already held a COMPLETE judged run - 58 rows, 58 unique question_ids, exactly equal to the 58 qids in b35c_questions.jsonl (no missing, no extra, no duplicates; gold_answer and question_type verified row-by-row against the question file), all 15 uids of b35c_sample_uids.txt present (13 uids x 4 q + wikiP551000/wikiP551008 x 3 q). Nothing was missing, so NO new answering was run and no judged row was touched or discarded; I verified the harness appends and skips done question_ids before deciding. An earlier att
- 复核:parity=True matches=True;Recomputed from D:\ZZL_cluade\results\b35c_amem.jsonl: n=58, 23 judge_correct = 0.39655 (39.66%), mean input tokens 1211.8, mean output 84.6, median latency 4.88 s. Per-type: change_count 2/15, count_before 6/15, first_vs_last 12/15, longest_tenure 3/13. All identical to the report (0.0 pp / 0% delta).  Integrity: 58 unique question_ids, zero duplicates; every question_id present in results/b35c_q

### bm25
- 状态 done;脚本改动:No new edits this run. scripts/repro_batch4.py already carried the b35c wiring in the working tree (git diff: +98/-8), and I ran it unchanged. Relevant additions (loading section only): --vols (comma-separated corpus json, default VOLS), --uids-file (uid list, keeps file order, replaces sample_store
- 偏离:RESUME: 54 of the 58 rows were already in results/b35c_bm25.jsonl from an earlier interrupted run of the same command; the harness appends and skips done question_ids (done set + `qs = [q for q in by_uid[uid] if q["qid"] not in done]`), so I ran it once and it built only the missing store and answered only the missing 4 questions of wikiP54001-Q16225986 (log: results/b35c_bm25_run.log). No judged row was discarded; a 54-row backup was made in the scratchpad first. The _part1/merge path was not needed. Verified: question_id set == the 58 qids in b35c_questions.jsonl exactly, no dups/extras, uid
- 复核:parity=True matches=True;Recomputed from D:\ZZL_cluade\results\b35c_bm25.jsonl: n=58, judge_correct=7 -> acc 12.069% (reported 12.07); mean usage_input_tokens 1213.38 (reported 1213.4), mean usage_output_tokens 86.12 (reported 86.1), median latency_s 4.635 s (reported 4.63). Per-type accuracy reproduces exactly: change_count 1/15, count_before 5/15, first_vs_last 0/15, longest_tenure 1/13. Integrity: 0 duplicate question_

### cognee
- 状态 done;脚本改动:ZERO new code written this session. The b35c CLI plumbing already existed in the working tree (uncommitted, from the interrupted earlier attempt); I verified it against the protocol and used it as-is. Verified diff of scripts/repro_batch4.py (98 insertions / 8 deletions, only main()'s loading block 
- 偏离:acc is reported in PERCENT (26/58 = 44.83%); per type: change_count 5/15=33.33, count_before 5/15=33.33, longest_tenure 5/13=38.46, first_vs_last 11/15=73.33. All 58 qids present exactly once (no missing/extra/dupes); memories_n = 10.00 on every row (zero empty retrievals). Command run: python scripts/repro_batch4.py --system cognee --vols data/wikistate_full_ALL_v25.json --uids-file results/b35c_sample_uids.txt --questions-file results/b35c_questions.jsonl --out results/b35c_cognee.jsonl --store-root results/b35c_cognee_stores2 (main env, PYTHONUTF8=1). Wall clock ~14.4 min this run (+~1.4 mi
- 复核:parity=True matches=True;RECOMPUTED from results/b35c_cognee.jsonl (58 rows): judge_correct 26/58 = 44.83% (report 44.83, exact). mean input tokens 1198.07 (report 1198.1), mean output 84.09 (report 84.1), median latency 6.33 s (report 6.33). Per-type: change_count 5/15=33.33, count_before 5/15=33.33, longest_tenure 5/13=38.46, first_vs_last 11/15=73.33 — all match. memories_n = 10 on every row.  INTEGRITY: all 58 questio

### hipporag2
- 状态 done;脚本改动:scripts/hipporag2_baseline.py, +21/-2 lines, confined to main()'s loader block plus one output field. (a) Four new CLI args per README section 2, copied from trace_contestant.py: --vols (comma-separated corpus json, default VOLS), --uids-file (uid list, file order preserved, replaces sample_stores()
- 偏离:RESUME: file was already COMPLETE on arrival - 58 rows / 58 unique question_ids, exactly equal to the 58 qids in b35c_questions.jsonl (0 missing, 0 extra, 0 duplicate; uid/question/gold/qtype verified row-by-row, 0 mismatches). No questions needed rerunning; b35c_hipporag2.jsonl received ZERO writes this session and no judged row was moved or discarded. Ran as 3 segments (logs _b35c_hipporag2_run.log/_run2.log/_run3.log): seg1 completed 6 stores/24 q then was killed mid-index on store 7; seg2 +5 stores/18 q; seg3 +4 stores/16 q.  PROTOCOL: no deviation from the 60-q calibration on reader (mode
- 复核:parity=True matches=True;Recomputed from D:\ZZL_cluade\results\b35c_hipporag2.jsonl: n=58, 58 unique question_ids, acc 46.55 (27/58); mean input 1194.9 / output 82.3 tok; median latency 6.04 s. By type: first_vs_last 14/15, count_before 7/15, change_count 4/15, longest_tenure 2/13 — identical to report. Coverage: every uid is in results/b35c_sample_uids.txt (15 distinct stores), every question_id is in results/b35c_questi

### langmem
- 状态 done;脚本改动:scripts/langmem_s5_agg.py: +29/-12 lines, confined to the loading section of main(), copied from b35c_README §2 skeleton. Added --vols (comma-separated corpus json; default still the original 4-volume VOLS), --uids-file (replaces the equidistant sampling formula, keeps file order), --questions-file 
- 偏离:No protocol deviation from the 60-question calibration run: reader / judge / k=10 / 300-char memory line / 400-char per turn / first 6 turns / date prefix / one fresh store per uid are all byte-identical to the run that produced results/wsc_s5_langmem.jsonl; only the three loading-section CLI args were added. Corpus and question set changed by design (b35c scope), so per README §5 the archived 60-q acc 40.00 must NOT be compared directly with this 32.76 — comparison is only within b35c, paired by question_id.  RESUME handling: when I took over, results/b35c_langmem.jsonl held 29 rows AND the p
- 复核:parity=True matches=True;Recompute from D:\ZZL_cluade\results\b35c_langmem.jsonl: n=58, acc=32.7586% (19/58), mean input tokens 835.03, mean output 100.09, median latency 5.14 s, mean per-store ingest 288.8 s. All match the report exactly (well within 0.1 pp / 5%).  Integrity: 58 rows, 58 unique question_ids, zero duplicates; the qid set is exactly equal to the 58 qids in results/b35c_questions.jsonl; all 15 uids present 

### letta_fs
- 状态 done;脚本改动:Only CLI plumbing in scripts/letta_fs_agent_baseline.py (+20/-1 lines, all inside main()'s loading block; git diff confirms nothing else changed): added --vols (comma-separated corpus json, default repro_batch2.VOLS), --uids-file (replaces sample_stores() picked, file order preserved), --questions-f
- 偏离:RESUME: results/b35c_letta_fs.jsonl already held 58 judged rows covering ALL 58 qids (0 missing), so nothing needed re-running; no judged row was discarded, overwritten or moved aside. The harness appends (open(out_p,"a")) and skips done question_ids, so a re-run would have been a no-op anyway. I verified rather than re-ran, and recomputed every number from the jsonl: acc 43.10% (25/58); by type change_count 6/15=40.00%, count_before 4/15=26.67%, first_vs_last 8/15=53.33%, longest_tenure 7/13=53.85%; mean in 30190.5 / out 674.6 tok (totals 1,751,049 / 39,124); median latency 12.57 s (mean 15.7
- 复核:parity=True matches=True;No blocking issues. Recomputed from D:\ZZL_cluade\results\b35c_letta_fs.jsonl: n=58, acc 43.10% (25/58); by type change_count 6/15, count_before 4/15, first_vs_last 8/15, longest_tenure 7/13; mean input 30190.5 / output 674.6 tokens; median latency 12.57 s; build 0.0069 s/store (15 stores, deduped by uid via ingest_seconds). All match the reported numbers exactly (0.0 pp / 0% delta). Integrity: 0 

### lgstore
- 状态 done;脚本改动:None. The b35c wiring already existed in scripts/repro_batch4.py when I took over (git diff: 98 insertions / 8 deletions vs HEAD, made by the earlier interrupted attempt). Relevant to lgstore: new CLI flags --vols (comma-separated corpus json, default VOLS), --uids-file (replaces sample_stores() pic
- 偏离:RESUME: results/b35c_lgstore.jsonl already held 51 judged rows (13 full uids + 1 question of wikiP54003). Verified in code that the harness appends and skips done question_ids (fh=open(out_p,"a"); done={...question_id...}; qs filtered by qid not in done), so I re-ran the same command and it answered ONLY the 7 missing questions (wikiP54001-Q16225986 x4 and wikiP54003-Q26001185 v2cb/v2fl/v2lt). No judged row was discarded or overwritten; a read-only backup of the 51 rows is in the scratchpad. Final file has exactly the 58 qids of b35c_questions.jsonl, no missing/extra/duplicate. Command: PYTHON
- 复核:parity=True matches=True;Recomputed from D:\ZZL_cluade\results\b35c_lgstore.jsonl: n=58, judge_correct 27/58 = 0.4655 (46.55%), mean input 1194.97 tok, mean output 84.26 tok, median latency 4.97 s. Per-type: first_vs_last 15/15, count_before 8/15, change_count 3/15, longest_tenure 1/13 — all identical to the report. All 58 rows have memories_n=10 and a non-empty answer.  Integrity: 0 duplicate question_ids; the 58 qids ar

### mem0
- 状态 done;脚本改动:scripts/repro_batch2.py (+42/-6): added optional --vols / --uids-file / --questions-file / --out / --store-root to main(), replacing only the loader block (entries source, picked, by_uid, out_p) per b35c_README §二 skeleton — loop body, reader call, judge call and row writing untouched; Mem0System.__
- 偏离:1) Corpus/questions/uids swapped to b35c per task (v2.5, 58 q, 15 uids); reader/judge/k/truncation/prompts/sess_text unchanged from the 60-q calibration run. 2) Store moved off mem0's factory paths (D:\tmp\qdrant, ~/.mem0) to results/b35c_mem0_stores with collection b35c_mem0 (store-freeze rule); LLM+embedder config untouched — legacy dirs still stamped Aug 21, zero writes this round. 3) MEM0_TELEMETRY=False and a read-only openai class-level usage meter (counts only). 4) delete_all(user_id=uid) before each ingest as resume safety; no-op on this run's fresh collection. 5) memories_n=20 despite
- 复核:parity=True matches=True;Recomputed from D:\ZZL_cluade\results\b35c_mem0.jsonl: n=58, acc=10.3448% (6/58), mean input tok 786.40, mean output tok 100.98, median latency 5.05 s, mean ingest_seconds per store 81.0 (15 distinct stores). All match the report within tolerance (acc exact, tokens exact/<0.1%, latency exact, build_s 81).  Integrity: 0 duplicate question_ids; all 58 question_ids present in results/b35c_questions.j

### memos
- 状态 done;脚本改动:No script edit was made in this session. scripts/repro_batch33h_memos.py already carried the b35c wiring in the working tree (uncommitted, git diff = +27/-3 lines); I read it line by line and used it as is. The diff adds only 5 loading-stage CLI args (--vols / --uids-file / --questions-file / --out 
- 偏离:RESUME OUTCOME: nothing was left to run. results/b35c_memos.jsonl already held 58 rows / 58 unique question_ids, exactly matching the 58 qids in results/b35c_questions.jsonl (no missing, no extra, no duplicates), every row judged. Harness code confirms the append+skip branch of the resume rule (out_p opened "a"; done = existing question_ids; qs = [q for q in by_uid[uid] if q["qid"] not in done]), so re-invoking it would have answered 0 questions; no judged row was discarded and no file was moved aside. I re-verified instead of re-running, and recomputed every number below from the jsonl itself
- 复核:parity=True matches=True;Recomputed from D:\ZZL_cluade\results\b35c_memos.jsonl (no rerun): n=58, judge_correct 18/58 = 0.3103; mean usage_input_tokens 613.0, mean output 92.4; latency_s median 5.02 (mean 5.25, max 9.50). Per type: change_count 4/15, count_before 3/15, first_vs_last 6/15, longest_tenure 5/13. build_s deduped by uid: 15 stores, mean 207.8, median 206.0, total 3116.8 s. All match the report exactly (0.0 pp 

### mstrata
- 状态 done;脚本改动:No new script changes this round. scripts/repro_batch4.py already carried the b35c CLI plumbing from the interrupted attempt (uncommitted working-tree diff, verified line by line): five new args --vols/--uids-file/--out/--store-root/--amem-repo; loading section uses `vols = a.vols.split(",") if a.vo
- 偏离:No protocol deviation. Reader/judge/k=10/300-char truncation/sess_text/date-ordered ingest all identical to the calibration run; corpus, uid list and question file were swapped per b35c design. RESUME: results/b35c_mstrata.jsonl already held 8 judged rows (2 uids, no partial rows). Verified repro_batch4.main() opens the output with "a" and skips question_ids already present (`qs = [q for q in by_uid[uid] if q["qid"] not in done]`, empty -> continue, store not rebuilt), so I resumed in place; nothing moved aside, zero judged rows discarded. 50 new questions / 13 new stores answered; merged file
- 复核:parity=True matches=True;Recomputed from D:\ZZL_cluade\results\b35c_mstrata.jsonl: n=58, judge_correct 8/58 = 13.793% (report 13.79, exact); mean usage_input_tokens 319.83 (report 319.8), mean usage_output_tokens 75.55 (report 75.6), median latency_s 4.63 (report 4.63, mean 4.89); per-store ingest_seconds over 15 distinct uids mean 67.79 / median 66.8 / total 1016.9 (report 67.8 / 66.8 / 1016.9). Per-type: change_count 4/

### obsrag
- 状态 done;脚本改动:Zero lines changed in any repo script this round. scripts/repro_batch2.py already carried the b35c plumbing from before this attempt (git diff 42+/6-, uncommitted): main()'s loading block only — --vols replaces hardcoded VOLS, --questions-file rebuilds by_uid, --uids-file replaces sample_stores() pi
- 偏离:acc is reported as a percentage (13.79% = 8/58), matching the README/leaderboard convention. RESUME: results/b35c_obsrag.jsonl already held 8 judged rows (uids wikiP108035-Q39407125, wikiP108021-Q37837264) from the interrupted 19:58 run of the same command. repro_batch2.py::main natively appends and skips done question_ids (done set from out_p; `qs = [q for q in by_uid[uid] if q["qid"] not in done]`; `if not qs: continue` skips that store's build too), so I did NOT move the file aside — I verified the 8 rows were unique, non-null judge_correct, non-empty answer, no FALLBACK judge, then ran onl
- 复核:parity=True matches=True;Recompute from D:\ZZL_cluade\results\b35c_obsrag.jsonl: n=58, correct=8, acc=13.7931% (reported 13.79), mean input 210.07 tok (reported 210.1), mean output 74.93 (reported 74.9), median latency 4.75 s (reported 4.75), per-uid build mean 75.25 s / median 74.2 s (reported 75.25 / 74.23 — median differs by 0.03 s, rounding of the per-row stored value). All within 0.1 pp / 5%.  Integrity: 0 duplicate 

### sumrag
- 状态 done;脚本改动:NONE — I changed no script. The b35c CLI plumbing was already present in the working tree as an uncommitted edit to scripts/repro_batch2.py (git diff HEAD: +42/-6): --vols / --uids-file / --questions-file / --out in the loader section of main(), plus --store-root used only by Mem0System (not reached
- 偏离:acc is reported as a PERCENT (21/58 correct). Per question type: change_count 3/15 = 20.00%, count_before 3/15 = 20.00%, first_vs_last 10/15 = 66.67%, longest_tenure 5/13 = 38.46%. All 58 question_ids match results/b35c_questions.jsonl exactly (no dupes, none missing); 15/15 stores built; zero reader-failure rows; every question retrieved memories_n=10.  DEVIATIONS / CAVEATS: 1. RESUME: 4 rows (uid wikiP108035-Q39407125, ingest_seconds 56.0) came from the earlier interrupted attempt — same script, corpus, question file and protocol. The harness appends and skips done question_ids (main(): done
- 复核:parity=True matches=True;Recomputed from D:\ZZL_cluade\results\b35c_sumrag.jsonl: n=58, judge_correct 21/58 = 36.207% (reported 36.21, delta 0.00 pp); mean input 918.88 tok (reported 918.9), mean output 85.879 (reported 85.9), median latency 4.86 s (reported 4.86); mean per-store ingest_seconds 57.05 (reported build_s_per_store 57.1, 0.1% delta). All within tolerance -> matches_report true.  Per-type recompute agrees exac

### timeline
- 状态 done;脚本改动:scripts/repro_batch2.py: only the loader block of main() was touched, per b35c_README §二 skeleton. Added argparse options --vols / --uids-file / --questions-file / --out (plus --store-root, which is mem0-only and unused by timeline). out_p = ROOT/a.out if a.out else the original hardcoded path; vols
- 偏离:Zero protocol deviations from the 60-question calibration run: reader claude-haiku-4-5 / temperature 0 / max_tokens 300 / verbatim READER_SYS, judge qvf.judge.ClaudeJudge() default (claude-opus-5, confirmed at runtime), 300-char memory-line truncation (timeline's frozen value), date-prefixed session paragraphs at 400 chars x 6 turns, no retrieval (timeline hands the full timeline to the reader, so k does not apply), fresh store per uid, sessions ingested date-ascending. Only the four CLI loader arguments were added. RESUME: results/b35c_timeline.jsonl did not exist when the run started; the si
- 复核:parity=True matches=True;Recomputed from D:\ZZL_cluade\results\b35c_timeline.jsonl: n=58, judge_correct 33/58 = 0.5690 (reported 0.569), mean input 1853.8 / output 95.3 (exact), median latency 4.605 s (reported 4.61), store-deduped ingest mean 44.82 s/store (exact). Per-type matches: first_vs_last 15/15, count_before 7/15, change_count 6/15, longest_tenure 5/13. Integrity: 0 duplicate question_ids; all 58 qids present in 

### txtai
- 状态 done;脚本改动:No script edited this session. scripts/repro_batch4.py already carried the b35c plumbing from the interrupted attempt (uncommitted vs HEAD); I verified it and re-used it. txtai-relevant parts of that diff, all inside main()'s loading block: (1) --vols -> vols = a.vols.split(",") if a.vols else VOLS;
- 偏离:acc is reported in percent (26/58 correct). Per question type: change_count 20.00 (3/15), count_before 46.67 (7/15), first_vs_last 86.67 (13/15), longest_tenure 23.08 (3/13). All 58 question_ids exactly equal the b35c_questions.jsonl qid set (no missing, no duplicates); memories_n = 10 for every row; 0 empty retrievals, 0 empty answers. RESUME: the file already held 49 judged rows. repro_batch4.py appends and skips done question_ids (done set + `qs = [q for q in by_uid[uid] if q["qid"] not in done]`), so I ran it in place and it answered ONLY the 9 missing questions (wikiP54031-Q16198306_v2fl;
- 复核:parity=True matches=True;Recomputed from results/b35c_txtai.jsonl: n=58, 26 correct -> 44.83% (report 44.83, exact). Mean input tok 1205.16 (report 1205.2), mean output 81.86 (report 81.9), median latency 4.565 s (report 4.56). Per-type accuracy reproduces exactly: change_count 20.00 (3/15), count_before 46.67 (7/15), first_vs_last 86.67 (13/15), longest_tenure 23.08 (3/13). 15 distinct uids, mean build 6.147 s (report 6.
