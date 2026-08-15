# -*- coding: utf-8 -*-
"""Blind question writer for the new-domain zero-modification test (P26/P69/P1303).

Written by the independent blind writer. Constraints honored:
- NEVER opened scripts/complex_query_arm.py nor COMPILE_PROMPT / its few-shots.
- Inputs seen: the three newdom chain JSONs, old-domain probing_queries surface
  text (data/wikistate_full*.json) + old S5 question surfaces
  (results/wsc_s5_all.jsonl) strictly for (a) loader-format compatibility and
  (b) the 20% bridge (old-template isomorphic) questions, per the audit design.
- Gold answers are derived 100% mechanically from the chains by the rules below
  (denotational semantics from study_logs/QVF_methods_formalization_20260814.md §4).

Gold rules (zero human discretion):
  S1 dim1_current      : gold = chain[-1].value ; Today = chain[-1].date verbatim.
  S2 dim4_point_in_time: pick a consecutive pair of DISTINCT chain dates (Da,Db);
                         query date d strictly inside under BOTH partial-date
                         conventions (floor -00->01 / ceil -00->12-31), with a
                         1-day margin for full dates (gap>=3d) or a strictly
                         intermediate year for partial dates (year gap>=2);
                         gold = value of last chain item with date <= d.
  S3 dim5_trajectory   : gold = " -> ".join(values)  (old-domain gold format).
  S4 dim2_premise_mid  : presupposed v = seeded pick among chain[i], i<m-1, with
                         date(i+1) != date(i); gold = fixed mechanical template
                         naming current value, Today, and the end date of v's
                         period (old-domain gold style).
  S5 change_count      : gold = len(chain) - 1                      (m-1).
  S5 first_vs_last     : gold = "first: {v1}; most recent: {vm}"    (old format).
  S5 longest_tenure    : closed intervals only (last open segment excluded; with
                         Today = last chain date it has length 0), same-value
                         segments accumulated; entry emitted ONLY if the argmax
                         is identical and separated by >=1 day under both
                         partial-date conventions; ties skipped.
  Today prefix "(Today is {t_m}.)" on dim1, dim2 and all S5 (old convention:
  Today = last chain date verbatim, incl. partial dates); none on dim4/dim5.

fame_risk (mechanical): subject sitelinks >= 10, OR any entity (subject or
chain value, via data/newdom_fame_sitelinks.json) with sitelinks >= 15 whose
label appears in question text or gold text. fame_max_sitelinks recorded so a
different threshold can be re-applied downstream without regeneration.
"""
import json, random, re, calendar
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = 20260815
N_PER_TYPE = 25
BRIDGE_FRAC = 0.2
FAME_SUBJ = 10
FAME_ENT = 15

DOMAINS = [
    dict(prop="P26",   slotword="spouse",     cand="data/newdom_P26.json",   full="data/newdom_P26_full.json",   s5="data/newdom_s5_P26.jsonl"),
    dict(prop="P69",   slotword="school",     cand="data/newdom_P69.json",   full="data/newdom_P69_full.json",   s5="data/newdom_s5_P69.jsonl"),
    dict(prop="P1303", slotword="instrument", cand="data/newdom_P1303.json", full="data/newdom_P1303_full.json", s5="data/newdom_s5_P1303.jsonl"),
]

# ---------------------------------------------------------------- date utils
def parse_parts(s):
    y, m, d = s.split("-")
    return int(y), int(m), int(d)

def to_ord(s, mode):
    """Ordinal day for possibly-partial ISO date. mode='floor' or 'ceil'."""
    import datetime as dt
    y, m, d = parse_parts(s)
    if mode == "floor":
        m = m or 1
        d = d or 1
    else:
        m = m or 12
        d = d or calendar.monthrange(y, m)[1]
    return dt.date(y, m, d).toordinal()

def is_partial(s):
    y, m, d = parse_parts(s)
    return m == 0 or d == 0

def iso(o):
    import datetime as dt
    return dt.date.fromordinal(o).isoformat()

# ------------------------------------------------- handwritten surface pools
# 6 handwritten variants per type per domain, covering >=5 styles:
# direct / imperative / indirect / colloquial / formal (+ one extra).
POOLS = {
 "P26": {
  "dim1_current": [
    ("direct",     "Who is my spouse right now?"),
    ("imperative", "Tell me who I'm married to as of today."),
    ("indirect",   "I'm updating my emergency-contact form and it wants my spouse's name — what should I write?"),
    ("colloquial", "Quick check — who's my other half these days?"),
    ("formal",     "Please state the name of my present spouse."),
    ("indirect",   "If someone asked you who my husband or wife is at the moment, what would you tell them?"),
  ],
  "dim4_point_in_time": [
    ("direct",     "Who was I married to on {d}?"),
    ("imperative", "Look back and tell me who my spouse was on {d}."),
    ("indirect",   "I found an old photo dated {d} — who would my husband or wife have been back then?"),
    ("colloquial", "Back on {d}, who was I hitched to?"),
    ("formal",     "Kindly identify the person to whom I was married as of {d}."),
    ("direct",     "On {d}, specifically, who was my spouse?"),
  ],
  "dim5_trajectory": [
    ("direct",     "Who have I been married to over the years, in order?"),
    ("imperative", "Walk me through all my marriages from the first to the latest."),
    ("indirect",   "I'm writing my memoir — could you lay out how my married life has unfolded, spouse by spouse?"),
    ("colloquial", "So how did my love life go — who came after whom?"),
    ("formal",     "Please enumerate my spouses in chronological order of marriage."),
    ("imperative", "Give me the full timeline of my marriages, earliest first."),
  ],
  "dim2_premise_mid": [
    ("direct",     "My spouse {v} and I are planning a getaway — where should we go?"),
    ("colloquial", "Since I'm married to {v}, what anniversary gift would suit the two of us?"),
    ("indirect",   "A friend wants to send a card addressed to me and my spouse {v} — how should it read?"),
    ("formal",     "Given that my spouse is {v}, what should I keep in mind when filing a joint declaration?"),
    ("imperative", "Help me draft a dinner invitation coming from me and my spouse {v}."),
    ("indirect",   "As {v} is my spouse, what would be a thoughtful way to celebrate us?"),
  ],
  "change_count": [
    ("direct",     "How many times has my spouse changed?"),
    ("colloquial", "Count it up — how many times did I go from one spouse to the next?"),
    ("imperative", "Give me the number of times my marriage partner changed."),
    ("indirect",   "If you tallied every time I moved on to a new spouse, what number would you get?"),
    ("formal",     "State the total number of spousal transitions in my history."),
    ("direct",     "Across my whole life, how many spouse-to-spouse changes were there?"),
  ],
  "first_vs_last": [
    ("direct",     "Who was my first spouse, and who is my most recent one?"),
    ("colloquial", "Who did I marry first, and who's the latest?"),
    ("imperative", "Name both my first spouse and my most recent spouse."),
    ("indirect",   "For the opening and closing chapters of the memoir: who started my married life, and who is at the end of it so far?"),
    ("formal",     "Please identify my earliest spouse as well as my most recent spouse."),
    ("direct",     "Two names, please: my very first spouse and my newest one."),
  ],
  "longest_tenure": [
    ("direct",     "Which spouse was I married to for the longest time?"),
    ("colloquial", "Which marriage of mine lasted the longest — who was it with?"),
    ("imperative", "Tell me which spouse I stayed with longest."),
    ("indirect",   "Of all my marriages, which partner did I spend the most years with?"),
    ("formal",     "Please determine the spouse with whom my marriage endured the longest."),
    ("direct",     "Looking at durations only, which spouse tops the list?"),
  ],
 },
 "P69": {
  "dim1_current": [
    ("direct",     "Which institution am I enrolled at right now?"),
    ("imperative", "Tell me which school I'm currently enrolled in."),
    ("indirect",   "If my CV needs a 'current institution' line, what should it say?"),
    ("colloquial", "Where am I at, school-wise, at the moment?"),
    ("formal",     "Please state the educational institution in which I am presently enrolled."),
    ("direct",     "What's the name of the place I'm studying at now?"),
  ],
  "dim4_point_in_time": [
    ("direct",     "Which school was I enrolled at on {d}?"),
    ("imperative", "Tell me where I was studying as of {d}."),
    ("indirect",   "There's a certificate dated {d} in my files — which institution would I have been at then?"),
    ("colloquial", "Back on {d}, where was I studying?"),
    ("formal",     "Kindly state my institution of enrollment as of {d}."),
    ("direct",     "On {d}, which institution was I attending?"),
  ],
  "dim5_trajectory": [
    ("direct",     "Which schools have I attended over the years, in order?"),
    ("imperative", "List every institution I've studied at, from the first to the latest."),
    ("indirect",   "For my alumni profile, could you lay out my educational path institution by institution?"),
    ("colloquial", "How did my studies hop from place to place — what's the sequence?"),
    ("formal",     "Please provide a chronological account of the institutions I have attended."),
    ("imperative", "Trace my education timeline for me, earliest school first."),
  ],
  "dim2_premise_mid": [
    ("direct",     "Since I'm enrolled at {v}, what's the best way to get to campus?"),
    ("colloquial", "As a current student of {v}, what scholarships could I look into?"),
    ("indirect",   "My cousin wants to visit me at {v} — what should I tell her about coming by?"),
    ("formal",     "Given that my institution is {v}, which library services would typically be available to me?"),
    ("imperative", "Help me write an email signature that mentions I study at {v}."),
    ("direct",     "Because I'm still at {v}, what campus events should I look out for?"),
  ],
  "change_count": [
    ("direct",     "How many times have I switched institutions?"),
    ("imperative", "Count the times I moved from one school to the next."),
    ("indirect",   "If you added up every school-to-school move I made, what's the total?"),
    ("colloquial", "How many times did I jump from one school to another?"),
    ("formal",     "State the number of institution changes in my educational history."),
    ("direct",     "In total, how many school switches have I made?"),
  ],
  "first_vs_last": [
    ("direct",     "What was my first school, and which one am I at most recently?"),
    ("imperative", "Name the first institution I attended and the latest one."),
    ("colloquial", "Where did my education start, and where has it landed most recently?"),
    ("indirect",   "For the form: earliest institution attended, and the most recent institution?"),
    ("formal",     "Please identify both the first and the most recent institution I attended."),
    ("direct",     "Two answers: my first school ever, and my newest one."),
  ],
  "longest_tenure": [
    ("direct",     "Which school did I spend the longest time at?"),
    ("colloquial", "Which institution kept me around the longest?"),
    ("imperative", "Tell me the school where I stayed longest."),
    ("indirect",   "Of all the places I studied, where did I put in the most years?"),
    ("formal",     "Please determine the institution at which my enrollment lasted the longest."),
    ("direct",     "Duration-wise, which school tops my list?"),
  ],
 },
 "P1303": {
  "dim1_current": [
    ("direct",     "What instrument am I playing at the moment?"),
    ("imperative", "Tell me which instrument I currently play."),
    ("indirect",   "If a bandmate asked what I'm on right now, instrument-wise, what's the answer?"),
    ("colloquial", "What am I gigging on nowadays?"),
    ("formal",     "Please state the instrument I am presently playing."),
    ("direct",     "Which instrument is my current one?"),
  ],
  "dim4_point_in_time": [
    ("direct",     "Which instrument was I playing on {d}?"),
    ("imperative", "Tell me what instrument I was on as of {d}."),
    ("indirect",   "There's a concert flyer from {d} with my name on it — what instrument would I have been playing?"),
    ("colloquial", "Back on {d}, what was I playing?"),
    ("formal",     "Kindly identify the instrument I played as of {d}."),
    ("direct",     "On {d}, which instrument was mine?"),
  ],
  "dim5_trajectory": [
    ("direct",     "Which instruments have I played over the years, in order?"),
    ("imperative", "List every instrument I've taken up, from the first to the latest."),
    ("indirect",   "For the band bio, could you lay out my musical journey instrument by instrument?"),
    ("colloquial", "How did I bounce between instruments — what's the sequence?"),
    ("formal",     "Please provide a chronological account of the instruments I have played."),
    ("imperative", "Trace my instrument history for me, earliest first."),
  ],
  "dim2_premise_mid": [
    ("direct",     "Since I play the {v}, what maintenance routine should I follow for it?"),
    ("colloquial", "As a {v} player, which warm-up exercises would you recommend for me?"),
    ("indirect",   "My niece wants to hear me play the {v} at her party — what pieces would work?"),
    ("formal",     "Given that my instrument is the {v}, what would be a sensible practice schedule?"),
    ("imperative", "Help me shop for accessories for my {v}."),
    ("direct",     "Because the {v} is my instrument, which well-known pieces should I learn next?"),
  ],
  "change_count": [
    ("direct",     "How many times have I switched instruments?"),
    ("imperative", "Count the times I moved from one instrument to the next."),
    ("indirect",   "If you tallied each instrument-to-instrument switch of mine, what number comes out?"),
    ("colloquial", "How many times did I go from playing one thing to another?"),
    ("formal",     "State the number of instrument changes in my musical history."),
    ("direct",     "In total, how many instrument switches have I made?"),
  ],
  "first_vs_last": [
    ("direct",     "What was my first instrument, and what's my most recent one?"),
    ("imperative", "Name the instrument I started on and the one I've taken up most recently."),
    ("colloquial", "What did I start out playing, and what am I on most recently?"),
    ("indirect",   "For the bio: first instrument ever, and the newest one?"),
    ("formal",     "Please identify both the first and the most recent instrument I have played."),
    ("direct",     "Two answers: my first instrument, and my latest."),
  ],
  "longest_tenure": [
    ("direct",     "Which instrument did I play for the longest time?"),
    ("colloquial", "Which instrument kept me hooked the longest?"),
    ("imperative", "Tell me the instrument I stuck with longest."),
    ("indirect",   "Of everything I've played, which one got the most years?"),
    ("formal",     "Please determine the instrument I played for the greatest duration."),
    ("direct",     "Duration-wise, which instrument tops my list?"),
  ],
 },
}

# Old-domain isomorphic templates for the 20% bridge (verbatim from old
# probing_queries / wsc_s5_all surfaces, slot word substituted).
BRIDGE = {
  "dim1_current":       "What's my current {slot} these days?",
  "dim4_point_in_time": "What {slot} did I have on {d}?",
  "dim5_trajectory":    "How has my {slot} changed over time — which values, in order?",
  "dim2_premise_mid":   "Since my {slot} is {v}, what would typically be relevant to know about it?",
  "change_count":       "How many times did I change my {slot}?",
  "first_vs_last":      "What was my first {slot}, and what is my most recent one?",
  "longest_tenure":     "Which {slot} did I hold the longest?",
}

TYPES = ["dim1_current", "dim4_point_in_time", "dim5_trajectory", "dim2_premise_mid",
         "change_count", "first_vs_last", "longest_tenure"]
S5_SUFFIX = {"longest_tenure": "s5a", "change_count": "s5b", "first_vs_last": "s5d"}


def load(p):
    return json.loads((ROOT / p).read_text(encoding="utf-8"))


def main():
    fame = load("data/newdom_fame_sitelinks.json")
    meta_all = {"seed": SEED, "n_per_type": N_PER_TYPE, "bridge_frac": BRIDGE_FRAC,
                "fame_rule": f"subject>={FAME_SUBJ} or mentioned-entity>={FAME_ENT} sitelinks",
                "domains": {}}
    total = 0
    for dom in DOMAINS:
        prop, slotword = dom["prop"], dom["slotword"]
        cands = {c["qid"]: c for c in load(dom["cand"])}
        entries = load(dom["full"])
        pools = POOLS[prop]

        # per-entry precomputation
        info = {}
        for e in entries:
            uid = e["uid"]
            qid = uid.split("-", 1)[1]
            cand = cands.get(qid)
            chain = e["chain"]
            m = len(chain)
            values = [c["value"] for c in chain]
            dates = [c["date"] for c in chain]
            label = cand["label"] if cand else uid
            # value qid per index (for fame): align candidate chain to rendered
            # chain by start date, consuming candidate items in order (render
            # may drop/merge items, e.g. one P26 entry is 9 -> 8)
            vqids = [None] * m
            if cand:
                ci = 0
                cchain = cand["chain"]
                for i in range(m):
                    while ci < len(cchain) and cchain[ci]["start"] != dates[i]:
                        ci += 1
                    if ci < len(cchain):
                        vqids[i] = cchain[ci].get("position")
                        ci += 1
            subj_sl = fame.get(qid, cand["sitelinks"] if cand else 0)
            val_sl = {values[i]: fame.get(vqids[i], 0) for i in range(m)}
            # S2 eligible interval picks: consecutive DISTINCT-date pairs whose
            # left date is UNIQUE in the chain (otherwise "value at d" is
            # ill-defined among same-date states)
            pairs = []
            for i in range(m - 1):
                if dates[i] == dates[i + 1]:
                    continue
                if dates.count(dates[i]) != 1:
                    continue
                Da, Db = dates[i], dates[i + 1]
                if is_partial(Da) or is_partial(Db):
                    ya, yb = parse_parts(Da)[0], parse_parts(Db)[0]
                    if yb - ya >= 2:
                        pairs.append(("partial", i, Da, Db))
                else:
                    if to_ord(Db, "floor") - to_ord(Da, "floor") >= 3:
                        pairs.append(("full", i, Da, Db))
            # longest: closed segments, both conventions must agree with margin
            long_gold = None
            if m >= 2:
                agree = []
                for mode in ("floor", "ceil"):
                    dur = {}
                    for i in range(m - 1):
                        dur[values[i]] = dur.get(values[i], 0) + (to_ord(dates[i + 1], mode) - to_ord(dates[i], mode))
                    rank = sorted(dur.items(), key=lambda kv: -kv[1])
                    if rank[0][1] >= 1 and (len(rank) == 1 or rank[0][1] - rank[1][1] >= 1):
                        agree.append(rank[0][0])
                    else:
                        agree.append(None)
                if agree[0] is not None and agree[0] == agree[1]:
                    long_gold = agree[0]
            # S4 presupposed candidates: i < m-1 with next date differing
            s4_idx = [i for i in range(m - 1) if dates[i + 1] != dates[i]]
            uniq_last = dates.count(dates[-1]) == 1   # "current" well-defined
            uniq_first = dates.count(dates[0]) == 1   # "first" well-defined
            all_distinct = len(set(dates)) == m       # order well-defined
            info[uid] = dict(chain=chain, m=m, values=values, dates=dates, label=label,
                             subj_sl=subj_sl, val_sl=val_sl, pairs=pairs,
                             long_gold=long_gold, s4_idx=s4_idx, today=dates[-1],
                             uniq_last=uniq_last, uniq_first=uniq_first,
                             all_distinct=all_distinct)

        def fame_flag(uid, texts):
            inf = info[uid]
            mx = inf["subj_sl"]
            hit = inf["subj_sl"] >= FAME_SUBJ
            blob = " ".join(str(t) for t in texts)
            for v, sl in inf["val_sl"].items():
                if v in blob:
                    mx = max(mx, sl)
                    if sl >= FAME_ENT:
                        hit = True
            return hit, mx

        uids = [e["uid"] for e in entries]
        rng = random.Random(f"{SEED}-{prop}")
        picks = {}
        for t in TYPES:
            if t == "dim4_point_in_time":
                elig = [u for u in uids if info[u]["pairs"]]
            elif t == "dim2_premise_mid":
                elig = [u for u in uids if info[u]["s4_idx"] and info[u]["uniq_last"]]
            elif t == "longest_tenure":
                elig = [u for u in uids if info[u]["long_gold"] is not None]
            elif t == "dim1_current":
                elig = [u for u in uids if info[u]["uniq_last"]]
            elif t == "first_vs_last":
                elig = [u for u in uids if info[u]["uniq_first"] and info[u]["uniq_last"]]
            elif t == "dim5_trajectory":
                elig = [u for u in uids if info[u]["all_distinct"]]
            else:  # change_count: gold = m-1 is date-convention-free
                elig = list(uids)
            sel = [(u, 0) for u in rng.sample(elig, min(N_PER_TYPE, len(elig)))]
            # S5-only top-up: when eligible entries fall short, allow a second
            # differently-phrased question per entry (same mechanical gold),
            # distinct qid suffix; dims cannot double (dict key = identity).
            if t in S5_SUFFIX and len(sel) < N_PER_TYPE and elig:
                extra = [u for u in rng.sample(elig, len(elig))][: N_PER_TYPE - len(sel)]
                sel += [(u, 1) for u in extra]
            n_bridge = round(BRIDGE_FRAC * len(sel))
            bridge_set = set(rng.sample(range(len(sel)), n_bridge))
            order = list(range(len(pools[t])))
            rng.shuffle(order)
            picks[t] = (sel, bridge_set, order)

        # build questions
        by_uid_pq = {}
        s5_rows = []
        counts = {}
        prev_surface = {}
        for t in TYPES:
            sel, bridge_set, order = picks[t]
            for j, (uid, occ) in enumerate(sel):
                inf = info[uid]
                rng_q = random.Random(f"{SEED}-{prop}-{t}-{uid}-{occ}")
                is_bridge = j in bridge_set
                if is_bridge:
                    style, tmpl = "bridge", BRIDGE[t]
                else:
                    style, tmpl = pools[t][order[j % len(pools[t])]]
                # doubled S5 question must not repeat the first surface verbatim
                # (S5 templates carry no per-question placeholders, so template
                # identity == surface identity)
                if occ == 1 and tmpl == prev_surface.get((uid, t)):
                    for shift in range(1, len(pools[t]) + 1):
                        cand_style, cand_tmpl = pools[t][order[(j + shift) % len(pools[t])]]
                        if cand_tmpl != prev_surface.get((uid, t)):
                            style, tmpl, is_bridge = cand_style, cand_tmpl, False
                            break
                prev_surface[(uid, t)] = tmpl
                today = inf["today"]
                prefix = f"(Today is {today}.) "
                row = None
                if t == "dim1_current":
                    gold = inf["values"][-1]
                    q = prefix + tmpl.format(slot=slotword)
                    basis = "gold = chain[-1].value; Today = chain[-1].date"
                    row = dict(q=q, gold=gold)
                elif t == "dim4_point_in_time":
                    kind, i, Da, Db = rng_q.choice(inf["pairs"])
                    if kind == "full":
                        lo, hi = to_ord(Da, "floor") + 1, to_ord(Db, "floor") - 1
                        d = iso(rng_q.randint(lo, hi))
                    else:
                        ya, yb = parse_parts(Da)[0], parse_parts(Db)[0]
                        y = rng_q.randint(ya + 1, yb - 1)
                        d = f"{y:04d}-{rng_q.randint(3,10):02d}-{rng_q.randint(5,25):02d}"
                    # gold = last chain item with date <= d (floor convention;
                    # d is strictly interior under both conventions by construction)
                    gi = max(i2 for i2 in range(inf["m"]) if to_ord(inf["dates"][i2], "floor") <= to_ord(d, "floor"))
                    gold = inf["values"][gi]
                    q = tmpl.format(slot=slotword, d=d)
                    basis = f"d={d} strictly inside ({Da},{Db}) under floor and ceil partial-date conventions; gold = value of last chain item with date <= d"
                    row = dict(q=q, gold=gold, date=d)
                elif t == "dim5_trajectory":
                    gold = " -> ".join(inf["values"])
                    q = tmpl.format(slot=slotword)
                    basis = "gold = ' -> '.join(chain values), chronological"
                    row = dict(q=q, gold=gold)
                elif t == "dim2_premise_mid":
                    i = rng_q.choice(inf["s4_idx"])
                    v = inf["values"][i]
                    ended = inf["dates"][i + 1]
                    cur = inf["values"][-1]
                    gold = (f"The premise is outdated: as of {today} {inf['label']}'s current {slotword} is {cur} "
                            f"(the {v} period ended {ended}). A correct answer must correct the premise; "
                            f"it must not answer as if {v} were current.")
                    q = prefix + tmpl.format(slot=slotword, v=v)
                    basis = f"presupposed = chain[{i}].value (non-current, next date differs); ended = chain[{i+1}].date; current = chain[-1].value"
                    row = dict(q=q, gold=gold, presupposed=v)
                elif t == "change_count":
                    gold = inf["m"] - 1
                    q = prefix + tmpl.format(slot=slotword)
                    basis = f"one change per chain transition: gold = len(chain)-1 = {gold}"
                elif t == "first_vs_last":
                    gold = f"first: {inf['values'][0]}; most recent: {inf['values'][-1]}"
                    q = prefix + tmpl.format(slot=slotword)
                    basis = "gold = (chain[0].value, chain[-1].value), old-domain gold format"
                elif t == "longest_tenure":
                    gold = inf["long_gold"]
                    q = prefix + tmpl.format(slot=slotword)
                    basis = ("CLOSED intervals only (last open segment has length 0 as of Today = last chain date); "
                             "same-value segments accumulated; argmax identical with >=1 day margin under floor and ceil partial-date conventions")
                fr, mx = fame_flag(uid, [q, gold])
                if t.startswith("dim"):
                    rowd = dict(row)
                    rowd.update(gold=row["gold"], style=style, bridge=is_bridge,
                                fame_risk=fr, fame_max_sitelinks=mx, basis=basis)
                    by_uid_pq.setdefault(uid, {})[t] = rowd
                else:
                    suff = S5_SUFFIX[t] + ("" if occ == 0 else "2")
                    s5_rows.append(dict(uid=uid, qid=f"{uid}_{suff}", qtype=t,
                                        slot=e_slot(entries, uid), question=q, gold=gold,
                                        basis=basis, style=style, bridge=is_bridge,
                                        fame_risk=fr, fame_max_sitelinks=mx))
                counts[t] = counts.get(t, 0) + 1
                total += 1

        # write back probing_queries
        for e in entries:
            e["probing_queries"] = by_uid_pq.get(e["uid"], {})
        with open(ROOT / dom["full"], "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=1)
        with open(ROOT / dom["s5"], "w", encoding="utf-8", newline="") as f:
            for r in s5_rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        meta_all["domains"][prop] = dict(counts=counts,
                                         n_s1_s4=sum(v for k, v in counts.items() if k.startswith("dim")),
                                         n_s5=len(s5_rows))
        print(prop, counts)
    meta_all["total"] = total
    with open(ROOT / "data/newdom_probes.meta.json", "w", encoding="utf-8") as f:
        json.dump(meta_all, f, ensure_ascii=False, indent=1)
    print("TOTAL", total)


def e_slot(entries, uid):
    for e in entries:
        if e["uid"] == uid:
            return e["slot"]
    return None


if __name__ == "__main__":
    main()
