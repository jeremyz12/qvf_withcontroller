// 运行:cd <含 node_modules/pptxgenjs 的目录> && node D:/ZZL_cluade/scripts/make_weekly_deck_20260904.js D:/ZZL_cluade/results/weekly_report_20260904.pptx
// Weekly progress deck: WikiState v2.5 & QVF (Aug 28 – Sep 4, 2026). English slides.
// Numbers: results/opt_batch33_A (v2.4 corpus, single store v45, reader haiku-4.5) rescored on the v2.5
// question set (560 q); batch 34/35 docs. Prices: haiku 4.5 list $1/M in, $5/M out.
const pptxgen = require("pptxgenjs");
const fs = require("fs");

const NAVY = "1E2761", INK = "1F2937", MUTED = "6B7280", LINE = "D1D5DB", ICE = "EAF0FB", WHITE = "FFFFFF";
const GRAY = "9AA3AE", ACCENT = "B85042", GOOD = "2C5F2D";
const HFONT = "Cambria", BFONT = "Calibri";

// ---------- numbers (v2.5 question set, 560 q) ----------
const ARMS = [
  // name, label, acc560, acc576, inTok, outTok, medLat, group
  ["direct", "Direct read (top-10 retrieval)", 47.32, 47.57, 878, 86, 1.55, "base"],
  ["filter", "1 Select (slot-relevant cards)", 66.25, 65.62, 2169, 108, 5.50, "qvf"],
  ["usability", "2 Certify (dated, locatable)", 66.79, 66.32, 2346, 112, 5.46, "qvf"],
  ["compile", "3 Compile (sort, merge, count)", 79.46, 79.69, 2268, 98, 5.28, "qvf"],
  ["smoc", "4 Ledger + protocol (QVF)", 89.29, 89.06, 2937, 476, 4.84, "qvf"],
  ["smoc_g", "QVF, owner-gate store", 86.25, 85.59, 2106, 464, 4.77, "abl"],
  ["smw", "Full text + protocol", 86.61, 85.59, 13921, 454, 7.84, "abl"],
  ["smwplain", "Full text, plain", 54.46, 53.47, 13672, 136, 5.46, "abl"],
  ["summary", "Unstructured summary", 57.68, 57.12, 2451, 91, 4.88, "abl"],
];
const DIRECT = ARMS[0];
const cost = a => (a[4] * 1.0 + a[5] * 5.0) / 1e6;
const fmt$ = a => "$" + cost(a).toFixed(5);
const delta = a => (a[2] - DIRECT[2]);
const sgn = x => (x >= 0 ? "+" : "") + x.toFixed(1);

const QTYPE = [ // arm, change_count, count_before, longest_tenure, first_vs_last (560 q)
  ["Direct", 35.4, 42.4, 29.7, 79.9],
  ["1 Select", 59.0, 75.0, 38.3, 89.6],
  ["2 Certify", 61.8, 72.9, 40.6, 88.9],
  ["3 Compile", 65.3, 79.2, 81.2, 92.4],
  ["4 QVF ledger", 85.4, 86.8, 90.6, 94.4],
  ["Full text + protocol", 64.6, 91.0, 92.2, 99.3],
];

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.33 x 7.5
pres.author = "Jeremy Zhong";
pres.title = "WikiState v2.5 & QVF — weekly progress";

// ---------- helpers ----------
function title(slide, text, sub) {
  slide.addText(text, { x: 0.6, y: 0.35, w: 12.1, h: 0.7, fontFace: HFONT, fontSize: 30, bold: true, color: NAVY, margin: 0 });
  if (sub) slide.addText(sub, { x: 0.6, y: 1.02, w: 12.1, h: 0.4, fontFace: BFONT, fontSize: 14, color: MUTED, margin: 0 });
}
function footer(slide, n) {
  slide.addText(`WikiState v2.5 & QVF · Sep 4, 2026`, { x: 0.6, y: 7.05, w: 8, h: 0.3, fontFace: BFONT, fontSize: 9, color: MUTED, margin: 0 });
  slide.addText(String(n), { x: 12.2, y: 7.05, w: 0.5, h: 0.3, fontFace: BFONT, fontSize: 9, color: MUTED, align: "right", margin: 0 });
}
function bullets(slide, items, o) {
  const arr = items.map((t, i) => {
    const isObj = typeof t === "object";
    const txt = isObj ? t.text : t;
    const opt = { bullet: isObj && t.sub ? { indent: 14 } : true, breakLine: i < items.length - 1, paraSpaceAfter: 6, indentLevel: isObj && t.sub ? 1 : 0 };
    if (isObj && t.bold) opt.bold = true;
    return { text: txt, options: opt };
  });
  slide.addText(arr, Object.assign({ fontFace: BFONT, fontSize: 14, color: INK, valign: "top", margin: 0 }, o));
}
function tile(slide, x, y, w, h, big, small, col) {
  slide.addShape(pres.ShapeType.roundRect, { x, y, w, h, fill: { color: ICE }, line: { color: ICE }, rectRadius: 0.08 });
  slide.addText(big, { x: x + 0.2, y: y + 0.15, w: w - 0.4, h: h * 0.5, fontFace: HFONT, fontSize: 30, bold: true, color: col || NAVY, margin: 0, valign: "middle" });
  slide.addText(small, { x: x + 0.2, y: y + h * 0.5, w: w - 0.4, h: h * 0.48, fontFace: BFONT, fontSize: 11, color: INK, margin: 0, valign: "top" });
}
function table(slide, rows, o) {
  const head = rows[0].map(c => ({ text: c, options: { bold: true, color: WHITE, fill: { color: NAVY }, fontFace: BFONT, fontSize: o.fontSize || 11, align: "center", valign: "middle" } }));
  const body = rows.slice(1).map((r, ri) => r.map((c, ci) => {
    const cell = typeof c === "object" ? c : { text: c };
    const opts = Object.assign({ fontFace: BFONT, fontSize: o.fontSize || 11, color: INK, align: ci === 0 ? "left" : "center", valign: "middle", fill: { color: ri % 2 ? "F5F7FA" : WHITE } }, cell.options || {});
    return { text: cell.text, options: opts };
  }));
  slide.addTable([head, ...body], Object.assign({ border: { type: "solid", color: LINE, pt: 0.5 }, margin: 0.04 }, o));
}
let n = 0;

// ---------- 1 title ----------
{
  const s = pres.addSlide(); n++;
  s.background = { color: NAVY };
  s.addText("WikiState v2.5 & QVF", { x: 0.8, y: 2.2, w: 11.5, h: 1.1, fontFace: HFONT, fontSize: 44, bold: true, color: WHITE, margin: 0 });
  s.addText("Weekly progress report · Aug 28 – Sep 4, 2026", { x: 0.8, y: 3.35, w: 11.5, h: 0.6, fontFace: BFONT, fontSize: 22, color: "CADCFC", margin: 0 });
  s.addText("Dataset cleaning v2.4 → v2.5  ·  why each QVF step helps  ·  full results on the latest question set", { x: 0.8, y: 4.05, w: 11.5, h: 0.5, fontFace: BFONT, fontSize: 15, color: "CADCFC", margin: 0 });
  s.addText("Jeremy Zhong", { x: 0.8, y: 6.3, w: 6, h: 0.4, fontFace: BFONT, fontSize: 14, color: WHITE, margin: 0 });
}
// ---------- 2 agenda ----------
{
  const s = pres.addSlide(); n++;
  title(s, "Agenda");
  const items = [
    ["1", "What changed this week", "corpus v2.4 → v2.5, review infrastructure, conventions & errata"],
    ["2", "QVF: why each step helps", "the four read-time steps, what each one removes, exclusion tests"],
    ["3", "Full results on the latest question set", "accuracy · tokens · cost · latency, per question type, robustness"],
    ["4", "Cross-tests", "QVF on other benchmarks; other systems on WikiState"],
    ["5", "Honest boundaries & next steps", ""],
  ];
  items.forEach((it, i) => {
    const y = 1.7 + i * 1.0;
    s.addShape(pres.ShapeType.ellipse, { x: 0.8, y: y, w: 0.6, h: 0.6, fill: { color: NAVY }, line: { color: NAVY } });
    s.addText(it[0], { x: 0.8, y: y, w: 0.6, h: 0.6, fontFace: HFONT, fontSize: 18, bold: true, color: WHITE, align: "center", valign: "middle", margin: 0 });
    s.addText(it[1], { x: 1.7, y: y - 0.02, w: 10, h: 0.38, fontFace: HFONT, fontSize: 20, bold: true, color: INK, margin: 0 });
    if (it[2]) s.addText(it[2], { x: 1.7, y: y + 0.34, w: 10.5, h: 0.32, fontFace: BFONT, fontSize: 13, color: MUTED, margin: 0 });
  });
  footer(s, n);
}
// ---------- 3 week at a glance ----------
{
  const s = pres.addSlide(); n++;
  title(s, "This week at a glance", "One corpus release, two machine reviews, one convention made explicit, one erratum");
  tile(s, 0.6, 1.7, 2.9, 1.95, "v2.4 → v2.5", "47 contaminating sentences removed, 7 duplicate filler sessions merged; −0.31% chars; 542/542 anchors intact");
  tile(s, 3.7, 1.7, 2.9, 1.95, "2 × 149", "machine reviews (v2.4, v2.5): 5/5 planted errors caught, 0/144 real chains flagged");
  tile(s, 6.8, 1.7, 2.9, 1.95, "576 → 560", "questions: 16 near-tie longest-tenure items removed (margin ≤ 1%)");
  tile(s, 9.9, 1.7, 2.9, 1.95, "+21 / −6", "QVF ledger vs the whole memory in the prompt, same reader: +21.4 (haiku, p = 5e-6) / −6.4 (Sonnet 5, p = 0.035); +42 vs top-10 retrieval on 560 q", ACCENT);
  bullets(s, [
    "Batch 34: full-read scan of all 144 chains by one model, independent per-chain adjudication by another, surgical deletion under two gates (anchors verbatim, zero residue).",
    "Review pipeline: fresh Opus 5 agents drive the actual review page item by item; two leaks in the planted-error items fixed before v2.5.",
    "Tenure convention (chains record declared starts only) found to be systemic, quantified, and written into the datasheet and the review page instead of patching one chain.",
    "Partial rerun on the v2.5 corpus with a new store (batch 35: 36 chains / 140 q): QVF 90.7 vs direct 49.3 (+41.4); paired against the v2.4 store on the same questions the differences are within noise — cleaning does not move the headline. Human review link for v2.5 is ready.",
  ], { x: 0.6, y: 4.0, w: 12.1, h: 2.9 });
  footer(s, n);
}
// ---------- 4 change 1: corpus ----------
{
  const s = pres.addSlide(); n++;
  title(s, "Change 1 · Dataset cleaning v2.4 → v2.5 (batch 34)", "Same 144 chains, same 542 gold anchors; only filler text removed");
  bullets(s, [
    { text: "Scan: every chain read in full (all sessions) under five strict rules → 1,390 verbatim flags (anachronism 1,014 · other 212 · slot-relevant 164).", bold: false },
    "Adjudicate: 217 flags that could touch a gold chain, judged per chain by an independent model → 49 CONFIRMED · 2 GOLD_ISSUE · 166 BENIGN.",
    "Delete: 47 sentences (22 whole turns); one deletion skipped because it contained a gold anchor; 7 byte-identical filler sessions merged; 1 emptied session dropped.",
    "Gates: 542/542 anchor sentences still verbatim in their sessions; 0 confirmed sentences remain; corpus −0.31% characters.",
    "Why it matters: contamination taxes the structured arms, not the retrieval arm — cleaning enlarges the structural premium (v2.0 +34.0 → v2.4 +41.5).",
  ], { x: 0.6, y: 1.6, w: 7.2, h: 5.2, fontSize: 13 });
  table(s, [
    ["Version", "Removed", "Chains", "Chars"],
    ["v2.1", "84 asserted sentences", "61", "−0.20%"],
    ["v2.2", "70 same-session echoes", "34", "−0.09%"],
    ["v2.3", "73 rule-matched sentences", "38", "−0.09%"],
    ["v2.4", "20 (pool audit)", "15", "−0.04%"],
    ["v2.5", "47 sentences + 7 dup sessions", "33", "−0.31%"],
    [{ text: "Total", options: { bold: true } }, { text: "v2.0 → v2.5", options: { bold: true } }, { text: "144 chains kept", options: { bold: true } }, { text: "−0.72%", options: { bold: true } }],
  ], { x: 8.1, y: 1.7, w: 4.6, colW: [0.8, 2.0, 0.9, 0.9], fontSize: 10.5, rowH: 0.36 });
  s.addText("Scores for v2.2 / v2.3 / v2.4 are statistically indistinguishable (saturation); v2.5 rerun pending.", { x: 8.1, y: 4.5, w: 4.6, h: 0.7, fontFace: BFONT, fontSize: 10.5, color: MUTED, margin: 0 });
  footer(s, n);
}

// ---------- 4a WikiState at a glance ----------
{
  const s = pres.addSlide(); n++;
  title(s, "WikiState v2.5 at a glance \u2014 and what only it tests", "Scale on the left; the distinctiveness matrix on the right (attributes verified from full-text reads of each benchmark)");
  table(s, [
    ["Scale (v2.5)", ""],
    ["State chains (persona \u00d7 slot)", "144: employer 51 \u00b7 position 44 \u00b7 team 38 \u00b7 residence 11"],
    ["Gold state rows", "542 (3\u20138 per chain, median 3; 25 chains with \u2265 5 states)"],
    ["Sessions / turns", "4,854 sessions (542 chain + 4,312 filler), 23,696 turns; \u2248 14K tokens per store"],
    ["Time span", "chains span 1\u201390 years (median 10.2); dates 1423\u20132024"],
    ["Questions", "560 aggregation (change_count 144 \u00b7 count_before 144 \u00b7 first_vs_last 144 \u00b7 longest_tenure 128) + 576 validity probes (current / false premise / point-in-time / trajectory)"],
    ["Holdout", "80 chains / 320 q, zero QID overlap (two independent draws)"],
    ["Scale track", "30 stores of \u2248 104K tokens, 120 q"],
    ["Verification", "542/542 anchors verbatim (machine); 2 \u00d7 149-item machine reviews 0/144 flags; human \u03b1 0.45 (0.30 excl. planted)"],
  ], { x: 0.6, y: 1.55, w: 5.3, colW: [1.6, 3.7], fontSize: 9.5, rowH: 0.5 });
  table(s, [
    ["Benchmark", "Real KB chain", "Dates", "\u2265 3 states / slot", "Point-in-time Q", "Chain aggregation Q", "Superseded value = gold"],
    [{ text: "WikiState v2.5", options: { bold: true } }, "\u2713", "\u2713", "\u2713", "\u2713", "\u2713", "\u2713"],
    ["StateMemBench 2608.19652", "\u2717 (program)", "\u2717", "partial", "\u2717", "\u2717", "\u2717 (drift = error)"],
    ["MemTrace 2606.17328", "\u2717", "\u2717", "partial", "\u2717", "\u2717", "\u2713 (historical Q)"],
    ["Ground Truth First 2607.21962", "\u2717 (script)", "\u2713", "partial", "partial", "\u2717", "partial"],
    ["MemOps 2607.12893", "\u2717", "\u2717", "partial", "\u2717", "\u2717", "partial"],
    ["Memora / HorizonBench / DynamicMem", "\u2717", "\u2713", "\u2713 / \u2717 / partial", "\u2717", "\u2717", "\u2717 (old = error)"],
    ["TimelineQA 2023", "\u2717 (templates)", "\u2713", "partial", "partial", "\u2713", "\u2717 (no supersession)"],
    ["STALE / MemConflict", "\u2717", "partial", "\u2717", "\u2717 / partial", "\u2717", "\u2717 / partial"],
    ["LongMemEval / LoCoMo", "\u2717", "\u2713", "\u2717", "\u2717", "\u2717", "\u2717"],
    ["Temporal Wiki / ChronoScope", "snapshots / parametric", "\u2713", "partial / \u2717", "\u2713", "\u2717", "partial / \u2717"],
  ], { x: 6.1, y: 1.55, w: 6.6, colW: [2.2, 0.85, 0.55, 0.8, 0.7, 0.75, 0.75], fontSize: 8.5, rowH: 0.42 });
  s.addText("Only WikiState has all three of point-in-time questions, chain-aggregation questions, and a superseded value as the gold answer \u2014 together these define query-conditioned validity: the same memory is wrong for \u201cnow\u201d and right for \u201c2009\u201d or \u201chow many times\u201d. Boundaries stated with it: LLM-rendered dialogue, assistant turns stored truncated, filler anachronisms (1,014, not touching gold), residence under-represented (11 chains), main field reused during development (holdout matches within 0.07 pp).", { x: 0.6, y: 6.15, w: 12.1, h: 0.85, fontFace: BFONT, fontSize: 10, color: INK, margin: 0 });
  footer(s, n);
}
// ---------- 5 change 2: review infrastructure ----------
{
  const s = pres.addSlide(); n++;
  title(s, "Change 2 · Review infrastructure and machine review", "149 items per review = 144 real chains + 5 planted errors (value swap, date shift, deleted row, fabricated anchor, added row)");
  table(s, [
    ["Review", "Items", "Planted errors caught", "Real chains flagged", "Median time"],
    ["Opus 5 agents on v2.4 (Sep 3)", "149/149", "5/5", "0/144", "19 s"],
    ["Opus 5 agents on v2.5 (Sep 3)", "149/149", "5/5, each with the exact defect named", "0/144 (Wilson 95% upper 2.6%)", "18 s"],
    ["Human reviewer-v25", "149", "—", "not started; link ready", "—"],
  ], { x: 0.6, y: 1.65, w: 12.1, colW: [3.2, 1.3, 3.0, 3.1, 1.5], fontSize: 11, rowH: 0.42 });
  bullets(s, [
    "Agents are fresh per batch of 12 items, see only the page, and must check five error classes explicitly; verdicts written to a slot named as a machine reviewer, never into a human slot.",
    "Two leaks in the planted items fixed: highlights now follow the injected chain; planted ids share the shape of real ids.",
    "Reviewer agreement on the v2.0 display set (senior2 human · simulated senior1 · Opus-as-author): pairwise agreement 87.4%, all three agree on 13/20 overlap items, Krippendorff α 0.45 (0.30 excluding planted items); dataset error rate estimated 6–7% (upper 17%).",
    "Rule adopted: machine review must pass with zero real-chain flags before a human link is handed out; a failed review triggers a fix and a new version.",
  ], { x: 0.6, y: 3.6, w: 12.1, h: 3.2, fontSize: 13 });
  footer(s, n);
}
// ---------- 6 change 3: conventions & errata ----------
{
  const s = pres.addSlide(); n++;
  title(s, "Change 3 · Conventions made explicit, and one erratum");
  s.addText("Tenure convention", { x: 0.6, y: 1.5, w: 6, h: 0.4, fontFace: HFONT, fontSize: 18, bold: true, color: NAVY, margin: 0 });
  bullets(s, [
    "Chains record declared starts only; a row stays current until the next declaration. Tenure ends are never stated in the log, so they are not modeled (pre-registered Aug 20).",
    "Adjudication flagged one chain for a missing end row. Checked corpus-wide: 105 of 367 transitions (80 chains) have a Wikidata end date more than a year before the next start; 53 of 136 longest-tenure golds would change under real ends.",
    "No arm is favored: on the 57 convention-sensitive questions QVF 87.7 / direct 38.6 vs 90.8 / 28.7 elsewhere. At most 3 of 63 QVF errors could be blamed on it.",
    "Decision: keep the convention; write it into the datasheet, the generator, and the review page (\"a chain is not wrong for lacking an end row\").",
  ], { x: 0.6, y: 1.95, w: 6.1, h: 4.9, fontSize: 12.5 });
  s.addText("Near-tie erratum (question set)", { x: 7.0, y: 1.5, w: 5.7, h: 0.4, fontFace: HFONT, fontSize: 18, bold: true, color: NAVY, margin: 0 });
  bullets(s, [
    "Longest-tenure uniqueness only holds at day granularity: 16 of 144 questions have top-two tenures within 1%.",
    "First v2.5 pass used a wrong \"today\" (last date + 400 days): dropped 8, of which 2 were not ties, and missed 10.",
    "Corrected to the question's own date: exactly 16 removed → 560 questions. Corpus bytes unchanged.",
    "Direction is stated: near-ties are coin flips for the direct reader (55.6% vs 29.4% on clear items), so removal slightly favors the structured arms.",
  ], { x: 7.0, y: 1.95, w: 5.7, h: 3.0, fontSize: 12.5 });
  s.addText("Gold rulings", { x: 7.0, y: 5.05, w: 5.7, h: 0.4, fontFace: HFONT, fontSize: 18, bold: true, color: NAVY, margin: 0 });
  bullets(s, [
    "Weill Cornell Medical Center → Weill Cornell Medicine kept as an employer change (two Wikidata entities).",
    "Filler anachronisms (1,014 flags) documented as known blemish; they do not touch gold chains.",
  ], { x: 7.0, y: 5.5, w: 5.7, h: 1.4, fontSize: 12.5 });
  footer(s, n);
}
// ---------- 7 QVF in one picture ----------
{
  const s = pres.addSlide(); n++;
  title(s, "QVF in one picture", "Write-time state cards, read-time dated ledger; validity is a function of (memory × query), re-derived per question");
  // write box
  s.addShape(pres.ShapeType.roundRect, { x: 0.6, y: 1.7, w: 3.4, h: 4.9, fill: { color: ICE }, line: { color: ICE }, rectRadius: 0.08 });
  s.addText("WRITE TIME (once per session)", { x: 0.8, y: 1.85, w: 3.0, h: 0.4, fontFace: HFONT, fontSize: 14, bold: true, color: NAVY, margin: 0 });
  bullets(s, [
    "Extract state cards from each session, in date order",
    "Card = slot · value · stated date · verbatim source span · owner",
    "No adjudication, no merging — record only",
    "Coverage is complete by construction (every session is read once)",
  ], { x: 0.8, y: 2.35, w: 3.0, h: 4.0, fontSize: 12.5 });
  // arrow
  s.addShape(pres.ShapeType.rightArrow, { x: 4.15, y: 3.8, w: 0.6, h: 0.6, fill: { color: GRAY }, line: { color: GRAY } });
  // read steps
  const steps = [
    ["1 Select", "keep cards of the queried slot that belong to the persona"],
    ["2 Certify", "keep cards that carry a date and can be located in a source sentence"],
    ["3 Compile", "sort by date, merge adjacent equal values, count transitions with an executor"],
    ["4 Ledger + protocol", "render the dated ledger; reader first lists the state trajectory, then answers"],
  ];
  steps.forEach((st, i) => {
    const y = 1.7 + i * 1.25;
    s.addShape(pres.ShapeType.roundRect, { x: 4.95, y: y, w: 4.2, h: 1.1, fill: { color: WHITE }, line: { color: NAVY, pt: 1 }, rectRadius: 0.06 });
    s.addText(st[0], { x: 5.1, y: y + 0.08, w: 3.9, h: 0.35, fontFace: HFONT, fontSize: 14, bold: true, color: NAVY, margin: 0 });
    s.addText(st[1], { x: 5.1, y: y + 0.42, w: 3.9, h: 0.62, fontFace: BFONT, fontSize: 11.5, color: INK, margin: 0, valign: "top" });
  });
  s.addText("READ TIME (per question)", { x: 4.95, y: 6.75, w: 4.2, h: 0.3, fontFace: BFONT, fontSize: 10, color: MUTED, margin: 0 });
  // pseudocode
  s.addText([
    { text: "WRITE(sessions):", options: { bold: true, breakLine: true } },
    { text: "  for s in sessions by date:", options: { breakLine: true } },
    { text: "    cards += extract(s)", options: { breakLine: true } },
    { text: "    # slot, value, date, span, owner", options: { breakLine: true } },
    { text: "", options: { breakLine: true } },
    { text: "READ(q, cards):", options: { bold: true, breakLine: true } },
    { text: "  pool   = select(cards, slot(q),", options: { breakLine: true } },
    { text: "                  owner=self)", options: { breakLine: true } },
    { text: "  pool   = certify(pool)", options: { breakLine: true } },
    { text: "  # dated & locatable", options: { breakLine: true } },
    { text: "  ledger = compile(sort_by_date(pool))", options: { breakLine: true } },
    { text: "  return reader(PROTOCOL,", options: { breakLine: true } },
    { text: "                render(ledger), q)", options: {} },
  ], { x: 9.4, y: 1.7, w: 3.35, h: 4.9, fontFace: "Courier New", fontSize: 9.5, color: INK, fill: { color: "F5F7FA" }, valign: "top", margin: 0.1 });
  footer(s, n);
}
// ---------- 8 ladder chart ----------
{
  const s = pres.addSlide(); n++;
  title(s, "Why each step helps — the ladder", "Same corpus, same store, same reader (haiku-4.5), same judge; paired McNemar per rung; 560 questions");
  const lad = ARMS.slice(0, 5);
  s.addChart(pres.ChartType.bar, [{ name: "Accuracy (%)", labels: lad.map(a => a[1]), values: lad.map(a => a[2]) }], {
    x: 0.6, y: 1.55, w: 7.2, h: 5.2, barDir: "col", chartColors: [NAVY],
    showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 12, dataLabelFontFace: BFONT, dataLabelColor: INK, dataLabelFormatCode: "0.0",
    valAxisMinVal: 0, valAxisMaxVal: 100, valAxisMajorUnit: 20, valAxisLabelFontSize: 10, valAxisLabelColor: MUTED, valGridLine: { color: "E5E7EB", size: 0.5 },
    catAxisLabelFontSize: 10, catAxisLabelColor: INK, catGridLine: { style: "none" }, showLegend: false, showTitle: false, barGapWidthPct: 60,
  });
  const why = [
    ["Direct 47.3", "evidence arrives unordered, undated, mixed with other people's states; a weak reader cannot compute on it (perfect gold sentences fed to direct: only 76.7)"],
    ["Select +18.9", "removes other people's and off-slot states from the counting pool — 44% of the structural premium is distractor resistance"],
    ["Certify +0.5", "small on its own here (+2.9 on v2.0, +5.7 on the clean subset); it feeds step 3 — without dates nothing can be sorted"],
    ["Compile +12.7", "counting questions are the weak reader's blind spot (full text: change_count 29.9); the ledger turns 'count transitions' into reading a table — the other 56%"],
    ["Ledger + protocol +9.8", "trajectory-first protocol; helps mid-tier readers (haiku +10.9), not stronger ones (gpt-5-mini −3.5, Gemini +0.35 n.s.)"],
  ];
  why.forEach((w, i) => {
    const y = 1.55 + i * 1.05;
    s.addText(w[0], { x: 8.1, y: y, w: 4.6, h: 0.3, fontFace: HFONT, fontSize: 13, bold: true, color: i === 0 ? GRAY : NAVY, margin: 0 });
    s.addText(w[1], { x: 8.1, y: y + 0.3, w: 4.6, h: 0.72, fontFace: BFONT, fontSize: 10.5, color: INK, margin: 0, valign: "top" });
  });
  footer(s, n);
}

// ---------- 8a what the reader is up against ----------
{
  const s = pres.addSlide(); n++;
  title(s, "What the reader is up against — one real chain", "wikiP39042: 34 dated sessions, ~170 user turns; 4 of them carry the persona's own position history");
  s.addShape(pres.ShapeType.roundRect, { x: 0.6, y: 1.6, w: 6.0, h: 3.0, fill: { color: ICE }, line: { color: ICE }, rectRadius: 0.08 });
  s.addText("The four sentences that matter (verbatim anchors)", { x: 0.8, y: 1.7, w: 5.6, h: 0.35, fontFace: HFONT, fontSize: 13, bold: true, color: NAVY, margin: 0 });
  s.addText([
    { text: "1974-02-28  ", options: { bold: true, color: NAVY } }, { text: "\u201cI'm now a member of the 46th Parliament of the United Kingdom\u201d", options: { breakLine: true } },
    { text: "1974-10-10  ", options: { bold: true, color: NAVY } }, { text: "\u201cI'm now a member of the 47th Parliament \u2026\u201d", options: { breakLine: true } },
    { text: "1992-04-09  ", options: { bold: true, color: NAVY } }, { text: "\u201cI'll be taking my seat as a member of the 51st Parliament \u2026\u201d", options: { breakLine: true } },
    { text: "1997-10-03  ", options: { bold: true, color: NAVY } }, { text: "\u201cas of today I'm officially a member of the House of Lords\u201d", options: {} },
  ], { x: 0.8, y: 2.1, w: 5.6, h: 1.6, fontFace: BFONT, fontSize: 11.5, color: INK, margin: 0, valign: "top", paraSpaceAfter: 4 });
  s.addText("Question: \u201c(Today is 1998-04-01.) How many times did I change my position?\u201d  \u2192  gold 3", { x: 0.8, y: 3.8, w: 5.6, h: 0.6, fontFace: BFONT, fontSize: 12, bold: true, color: ACCENT, margin: 0 });
  s.addText("The other ~166 turns", { x: 6.9, y: 1.6, w: 5.8, h: 0.35, fontFace: HFONT, fontSize: 13, bold: true, color: NAVY, margin: 0 });
  bullets(s, [
    "Small talk: sneakers, a festival, a flat search, tea \u2014 plus states of OTHER people in the same slot (\u201cour team lead Emily was promoted\u201d).",
    "Dates live on session headers, not in the sentences (\u201cas of today\u201d, \u201cthe count went our way\u201d).",
    "Nothing says \u201cthis supersedes that\u201d; the reader must infer succession from dates.",
  ], { x: 6.9, y: 2.0, w: 5.8, h: 2.6, fontSize: 12 });
  s.addText("To answer correctly the reader must do four things at once", { x: 0.6, y: 4.8, w: 12.1, h: 0.35, fontFace: HFONT, fontSize: 13, bold: true, color: NAVY, margin: 0 });
  table(s, [
    ["Sub-task", "What goes wrong for a small reader", "Which arm still fails it"],
    ["Find all four sentences", "top-10 retrieval covers 86.7% of anchors on 14K stores, 38.8% on 104K stores", "direct; every RAG variant at scale"],
    ["Exclude other people's states", "same-slot distractors get counted", "direct, full text (no-filler: direct +22.5, ledger +1.7)"],
    ["Order by date", "dates are on headers; narrative order \u2260 time order", "full text (order shuffle \u221211.7 on n=60, pending)"],
    ["Count transitions (merge equal neighbours)", "weak readers cannot count over a timeline (full text change_count 29.9)", "everything except compile / ledger"],
  ], { x: 0.6, y: 5.2, w: 12.1, colW: [3.0, 5.4, 3.7], fontSize: 10.5, rowH: 0.34 });
  footer(s, n);
}
// ---------- 8b each step removes one failure source ----------
{
  const s = pres.addSlide(); n++;
  title(s, "Each step removes one failure source", "Mechanism \u2192 our exclusion evidence \u2192 literature that predicts it");
  table(s, [
    ["Step", "Failure source removed", "Our evidence (same reader, same judge)", "Literature anchor"],
    ["Write-time cards", "Coverage: every session is read once, so no evidence is left to retrieval luck", "Ledger built at read time from top-10: 60.2 (85.3 with full coverage, 15.9 with one session missing). Top-50 retrieval covers 99.8% of anchors and still fails 37% \u2192 finding is necessary, not sufficient", "MemTrace 2606.17328: bottleneck is evidence use, not retrieval \u00b7 Zep 2501.13956: write-time dated facts"],
    ["1 Select", "Distractors: other people's and off-slot states enter the count", "Remove all filler sessions: direct +22.5, full text +20.0, ledger +1.7 \u2192 44% of the structural premium", "Shi et al., ICML 2023 (2302.00093): irrelevant but similar context degrades accuracy"],
    ["2 Certify", "Unverifiable / undated cards", "Remove verbatim anchors: \u22125.4 (p = 1e-4); rung alone +0.5 here, +5.7 on the clean subset \u2014 it feeds step 3", "\u2014"],
    ["3 Compile", "Aggregation: sort, merge, count are done by code, not by the LM", "Full text change_count 29.9 vs ledger 85.4; compile rung +12.7 \u2192 the other 56%", "PAL, ICML 2023 (2211.10435): let a program do the arithmetic \u00b7 Faith & Fate, NeurIPS 2023 (2305.18654): chained aggregation fails \u00b7 Test of Time, ICLR 2025 (2406.09170): ordering/counting over timelines is weak"],
    ["4 Ledger + protocol", "Skipping: answering from intuition instead of the whole trajectory", "Protocol: haiku +10.9 (p < 1e-6), gpt-5-mini \u22123.5, Gemini +0.35 n.s.; compression alone gives nothing (summary 52.8 = full text 52.3)", "Sprague et al. 2024 (2409.12183): CoT helps mainly symbolic tasks \u00b7 Lost in the Middle, TACL 2024 (2307.03172): buried evidence is missed"],
  ], { x: 0.6, y: 1.55, w: 12.1, colW: [1.5, 2.9, 4.4, 3.3], fontSize: 9.5, rowH: 0.8 });
  s.addText("One sentence: QVF turns \u201cread 14K tokens of chatter and rebuild a timeline in your head\u201d into \u201cread a 4-row dated table\u201d. The reader keeps only the step it is good at. Caveat to run next: a render-matched control (same layout, mechanism off) \u2014 Presentation, Not Mechanism (2607.16019) shows layout alone can explain most of a ledger-style gain.", { x: 0.6, y: 6.25, w: 12.1, h: 0.75, fontFace: BFONT, fontSize: 10.5, color: INK, margin: 0 });
  footer(s, n);
}
// ---------- 8c when it does not help ----------
{
  const s = pres.addSlide(); n++;
  title(s, "When it does not help \u2014 and why that is the same mechanism", "Same 140 questions / 36 chains unless noted; \u2018full context\u2019 = the whole raw memory in the prompt, plain system prompt");
  table(s, [
    ["Setting", "Full context", "Best retrieval", "QVF ledger", "Reading"],
    ["14K store \u00b7 weak reader (haiku-4.5)", "70.0 (13.6K tok)", "62.9 (top-50)", "91.4 (2.8K tok)", "+21.4 vs full context, p = 5e-6; 1/2.8 the cost"],
    ["14K store \u00b7 strong reader (Sonnet 5)", "97.1 (18.5K tok)", "70.7 (top-10)", "90.7 (3.7K tok)", "\u22126.4, p = 0.035: the reader does the four sub-tasks itself; only the 2.8\u00d7 cost edge remains"],
    ["104K store \u00b7 weak reader (30 stores / 120 q)", "7.5 (103.8K tok)", "38.3 (top-100, 8.9K tok)", "61.7 projection (8.8K) \u00b7 54.2 full ledger", "+23.3 vs budget-matched top-100, p = 2e-4; retrieval collapses first (top-10 reaches 38.8% of anchors)"],
    ["104K store · strong reader (Sonnet 5, batch 40)", "54.9 (142K tok; n = 82, 18% capped)", "67.5 (top-100, 11.6K tok)", "74.2 projection (11.5K) · 73.3 full ledger", "+17.1 vs full context on the same 82 q, p = 0.024 (store CI crosses zero, 9 stores unfinished); projection costs 1/9"],
  ], { x: 0.6, y: 1.55, w: 12.1, colW: [3.0, 1.9, 2.0, 2.4, 2.8], fontSize: 9.5, rowH: 0.56 });
  bullets(s, [
    "The ledger is reader-insensitive (haiku 91.4 \u2192 Sonnet 90.7, p = 1.0) while every other arm gains 18\u201327 pp from the stronger reader: its ceiling is set by card content, not by reading.",
    "Write-side fixes, step by step: Sonnet-built cards 133/133 gold rows but 92.9 / 92.1 (haiku / Sonnet); slot canonicalisation alone 88.6 / 91.4; adding a rule-based assertion-type filter (drop plans, nominations, one-off tasks, restatements; 203 of 1,639 cards, zero gold rows lost) gives 93.6 / 95.0 — gap to full context now −2.1 (p = 0.51). The last 3 questions are one chain whose extraction missed 28 cards. StateMemBench (2608.19652, §3.2) reports the same pattern: 44.4% of failures under oracle retrieval are stale-state answers.",
    "Claim, restated: the ledger is necessary when the reader is not frontier-class, or the store exceeds the context window, or cost is bound \u2014 any one of the three. Otherwise it is a cheaper, auditable layer, not a more accurate one.",
  ], { x: 0.6, y: 5.0, w: 12.1, h: 2.0, fontSize: 10.5 });
  footer(s, n);
}
// ---------- 9 exclusion tests ----------
{
  const s = pres.addSlide(); n++;
  title(s, "Mechanism evidence: it is the structure, not a coincidence", "Exclusion tests on the v2.0 archive unless noted; all with the same reader and judge");
  table(s, [
    ["Test", "Result", "Reading"],
    ["Perfect gold-sentence evidence fed to the direct reader", "76.7 vs ledger 82.6 (p = 8e-11)", "failure is not a retrieval gap"],
    ["Remove all filler sessions", "direct +22.5, full text +20.0, ledger +1.7", "44% of the premium is distractor resistance"],
    ["Counting question types on full text", "change_count 29.9", "the remaining 56% is aggregation resistance"],
    ["Unstructured summary at equal token budget", "52.8 = full text 52.3 (p = 0.89); summary → bare ledger +22.6 (p = 2e-21)", "compression itself contributes nothing; the structure does"],
    ["Remove verbatim anchors", "77.3 vs 82.6, −5.4 (p = 1e-4)", "anchors are load-bearing"],
    ["Build the ledger at read time from the top-10 sessions", "60.2; 85.3 when retrieval covers all sessions, 15.9 when one is missing", "'write-time' = coverage"],
    ["Oracle cards / oracle evidence", "94.97 / 76.74", "write-side headroom +4.5; residual 55 errors = write 38 · read 13 · gold+judge 4"],
    ["Protocol by reader", "haiku +10.9 (p < 1e-6) · gpt-5-mini −3.5 · Gemini 3.6 Flash +0.35 n.s.", "scaffold for mid-tier readers only"],
  ], { x: 0.6, y: 1.6, w: 12.1, colW: [3.9, 4.4, 3.8], fontSize: 11, rowH: 0.5 });
  footer(s, n);
}
// ---------- 10 results table ----------
{
  const s = pres.addSlide(); n++;
  title(s, "Results on the latest question set (v2.5, 560 q)", "Corpus v2.4, single store v45 (derived store v45k for the middle rungs), reader haiku-4.5, judge Opus 5; $ at haiku list price $1/M in, $5/M out");
  const rows = [["Arm", "Accuracy", "Δ vs direct", "In tok / q", "Out tok / q", "$ / q", "Median latency"]];
  ARMS.forEach(a => {
    const bold = a[0] === "smoc";
    const o = bold ? { bold: true, fill: { color: "FDF1EE" } } : {};
    rows.push([
      { text: a[1], options: o }, { text: a[2].toFixed(2), options: o }, { text: a[0] === "direct" ? "—" : sgn(delta(a)), options: o },
      { text: a[4].toLocaleString(), options: o }, { text: String(a[5]), options: o }, { text: fmt$(a), options: o }, { text: a[6].toFixed(2) + " s", options: o },
    ]);
  });
  table(s, rows, { x: 0.6, y: 1.65, w: 12.1, colW: [3.3, 1.3, 1.4, 1.5, 1.5, 1.4, 1.7], fontSize: 11.5, rowH: 0.42 });
  s.addText("QVF ledger vs direct: +42.0 pp, chain-cluster bootstrap 95% CI [37.0, 46.9]. Full-text + protocol reaches 86.6 at 4.7× the input tokens and 1.6× the latency; the plain full-text reader stays at 54.5. Owner-gate store −3.0 (p = 0.04 on 576) → gate stays off by default. On the original 576 questions the headline is 89.06 vs 47.57 (+41.5). Partial rerun on the v2.5 corpus with a new store (batch 35, 36 chains / 140 q): direct 49.3 · compile 70.7 · QVF 90.7 (+41.4, CI [30.9, 51.4]); paired vs the v2.4 store on the same 140 questions: −1.4 / −5.0 / −0.7, all n.s.", { x: 0.6, y: 6.0, w: 12.1, h: 0.9, fontFace: BFONT, fontSize: 11.5, color: INK, margin: 0 });
  footer(s, n);
}
// ---------- 11 cost & latency charts ----------
{
  const s = pres.addSlide(); n++;
  title(s, "Cost and latency vs direct read", "One axis per chart; same 560 questions");
  const sel = ARMS.filter(a => ["direct", "compile", "smoc", "smw", "smwplain"].includes(a[0]));
  const lab = a => ({ direct: "Direct", compile: "3 Compile", smoc: "4 QVF ledger", smw: "Full text + protocol", smwplain: "Full text plain" }[a[0]]);
  s.addChart(pres.ChartType.bar, [{ name: "Input tokens per question", labels: sel.map(lab), values: sel.map(a => a[4]) }], {
    x: 0.6, y: 1.55, w: 6.0, h: 4.6, barDir: "col", chartColors: [NAVY], showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 11, dataLabelFormatCode: "#,##0",
    valAxisMinVal: 0, valAxisMaxVal: 16000, valAxisMajorUnit: 4000, valAxisLabelFontSize: 10, valAxisLabelColor: MUTED, valGridLine: { color: "E5E7EB", size: 0.5 }, catAxisLabelFontSize: 10, catGridLine: { style: "none" }, showLegend: false, showTitle: true, title: "Input tokens per question", titleFontSize: 13, titleColor: INK, barGapWidthPct: 60,
  });
  s.addChart(pres.ChartType.bar, [{ name: "Median latency (s)", labels: sel.map(lab), values: sel.map(a => a[6]) }], {
    x: 6.9, y: 1.55, w: 5.8, h: 4.6, barDir: "col", chartColors: [GOOD], showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 11, dataLabelFormatCode: "0.0",
    valAxisMinVal: 0, valAxisMaxVal: 10, valAxisMajorUnit: 2, valAxisLabelFontSize: 10, valAxisLabelColor: MUTED, valGridLine: { color: "E5E7EB", size: 0.5 }, catAxisLabelFontSize: 10, catGridLine: { style: "none" }, showLegend: false, showTitle: true, title: "Median latency per question (s)", titleFontSize: 13, titleColor: INK, barGapWidthPct: 60,
  });
  s.addText("Ledger reads 2.9K tokens where the protocol on full text reads 13.9K (1/4.7) at similar accuracy; on a 104K-session store the ledger degrades slowly (54.2 at 20.9K tokens; slot projection 61.7 at 8.8K) while haiku on full text collapses to 7.5 at 103.8K. Against a cheap reasoning reader (gpt-5-mini full text 65.0) the cost edge shrinks to 1.4–2.6×; the earlier '5×' claim is withdrawn.", { x: 0.6, y: 6.2, w: 12.1, h: 0.75, fontFace: BFONT, fontSize: 11, color: INK, margin: 0 });
  footer(s, n);
}
// ---------- 12 per question type ----------
{
  const s = pres.addSlide(); n++;
  title(s, "Per question type (560 q)", "Counting types are where the direct reader fails and where the ledger pays off");
  const rows = [["Arm", "change_count", "count_before", "longest_tenure", "first_vs_last"]];
  QTYPE.forEach(r => rows.push(r.map((c, i) => i === 0 ? c : c.toFixed(1))));
  table(s, rows, { x: 0.6, y: 1.65, w: 12.1, colW: [3.7, 2.1, 2.1, 2.1, 2.1], fontSize: 12.5, rowH: 0.48 });
  bullets(s, [
    "first_vs_last is answerable by retrieval alone (direct 79.9); the three counting types need every transition in date order.",
    "Select and certify lift count_before most (+30); compile is what lifts longest_tenure (+40.6); the protocol adds the last +20 on change_count.",
    "Full text + protocol wins count_before and first_vs_last (91.0 / 99.3) but loses change_count (64.6) at 4.7× tokens: reading everything is not the same as counting correctly.",
    "Three validity types on the v2.0 archive: current value +8.3, point-in-time +59.0, historical aggregation +34.0 (v2.4 single store +41.5).",
  ], { x: 0.6, y: 5.2, w: 12.1, h: 1.7, fontSize: 12 });
  footer(s, n);
}
// ---------- 13 robustness ----------
{
  const s = pres.addSlide(); n++;
  title(s, "Robustness checks", "Does the gain survive new chains, other readers, and larger stores?");
  table(s, [
    ["Check", "Result", "Reading"],
    ["Holdout set: 80 chains / 320 q, zero QID overlap (40 added this week, chain-length matched, new seed)", "new 40: QVF 90.6 vs direct 50.6 (+40.0, cluster CI [31.3, 48.1]); pooled 80: +41.56 vs main field +41.49", "no overfitting to the development chains; full-context haiku 72.5 sits between"],
    ["Owner gate at write time (cards only for the persona's own states)", "clean corpus −3.0 to −3.5 (p = 0.04); recovers 92% of an −18.4 third-person attack", "hardening flag, default off"],
    ["Stronger baselines for the direct arm", "bge-reranker 35.1, TempRALM 23.4 (both below direct 47.6)", "the gap is not a weak-retriever artifact"],
    ["Stronger reader: Gemini 3.6 Flash, 14K store", "full text 95.5 > ledger 92.5; protocol +0.35 n.s.; direct 63.4", "structure wins for weak / mid readers and large stores"],
    ["Store scale: 104K-session store, 30 stores", "ledger 54.2 @ 20.9K tok · projection 61.7 @ 8.8K · haiku full text 7.5 @ 103.8K", "ledger degrades slowly with size"],
    ["Corpus versions v2.2 → v2.5", "v2.2–v2.4 indistinguishable; v2.5 partial rerun (36 chains, new store) paired vs v2.4 store: direct −1.4 · compile −5.0 · QVF −0.7, all n.s.; the 24 untouched chains drift by the same −2 to −5 (rebuild noise)", "cleaning has saturated; no v2.5 penalty"],
    ["Machine review of gold chains (v2.4 and v2.5)", "5/5 planted errors caught, 0/144 real chains flagged, each time", "chain error rate upper bound 2.6% per review"],
  ], { x: 0.6, y: 1.6, w: 12.1, colW: [4.0, 4.4, 3.7], fontSize: 11, rowH: 0.55 });
  footer(s, n);
}

// ---------- 13a realistic baselines ----------
{
  const s = pres.addSlide(); n++;
  title(s, "Realistic baseline: whole memory in the prompt (36 / 36b)", "140 questions / 36 chains, corpus v2.4; plain system prompt; judge Opus 5; $ at list prices (haiku $1/$5, Sonnet 5 $2/$10 per M)");
  table(s, [
    ["Arm", "haiku-4.5", "Sonnet 5", "In tok / q (haiku / Sonnet)", "$ / q (Sonnet)"],
    ["Whole memory in prompt, plain call", "70.0", "97.1 (max_tokens 4000; 87.9 at 800 because thinking shares the cap)", "13.6K / 18.5K", "$0.042"],
    ["Archived plain full text (other user-prompt wording, same bytes)", "58.6", "84.8", "13.6K / 18.6K", "$0.039"],
    ["Full text + trajectory protocol", "92.9", "\u2014", "13.8K", "\u2014"],
    ["Top-10 retrieval (direct)", "50.7", "70.7", "0.9K / 1.1K", "$0.005"],
    [{ text: "QVF ledger (store v45)", options: { bold: true } }, { text: "91.4", options: { bold: true } }, { text: "90.7", options: { bold: true } }, "2.8K / 3.7K", "$0.015"],
    ["QVF ledger, Sonnet-built cards (v47s)", "92.9", "92.1", "2.6K / 3.5K", "$0.015"],
    [{ text: "QVF ledger, Sonnet-built + assertion-type filter (v47skf)", options: { bold: true } }, { text: "93.6", options: { bold: true } }, { text: "95.0", options: { bold: true } }, "2.5K / 3.4K", "$0.014"],
    ["QVF ledger, + second extraction pass, union (v47skf2; ledger = gold 140/140)", "97.1", "93.6", "2.6K / 3.5K", "$0.014"],
  ], { x: 0.6, y: 1.6, w: 12.1, colW: [4.3, 1.2, 3.6, 1.9, 1.1], fontSize: 9.5, rowH: 0.38 });
  bullets(s, [
    "Prompt wording alone moves a full-context baseline by +11\u201312 pp on identical bytes: the archived \u2018plain full text\u2019 number understated the realistic baseline. The main table's first row must be the plainest full-context call.",
    "Same weak reader: ledger +21.4 over full context (p = 5e-6) at 1/2.8 the input tokens. Same strong reader: the v45 ledger is −6.4 (p = 0.035); with Sonnet-built cards and the assertion-type filter the gap is −2.1 (p = 0.51) at 1/5.4 the input tokens.",
    "Using top-10 retrieval as the only baseline inflates any memory mechanism by 19\u201337 pp. The +42 headline is therefore reported next to +21 (weak reader) and \u22126 / \u22122 (strong reader), never alone. With the ledger at 140/140 gold rows, reader scores still move 3\u20134 pp between runs (97.1 / 93.6): single 140-q runs cannot separate 93 from 97 \u2014 repeat runs or the full set are needed for such claims.",
  ], { x: 0.6, y: 5.05, w: 12.1, h: 1.9, fontSize: 11.5 });
  footer(s, n);
}
// ---------- 13b other RAG, scale, competitors ----------
{
  const s = pres.addSlide(); n++;
  title(s, "Other retrieval strategies, scale, and 15 competing systems", "haiku-4.5 reader, same judge; batches 37 (140 q), 39 (104K-token stores, 120 q), 35c (v2.5 sample, 15 chains / 58 q)");
  table(s, [
    ["14K store: retrieval variant", "acc", "anchor cov."],
    ["QVF ledger", "91.4", "\u2014"],
    ["dense top-50", "62.9", "99.8%"],
    ["LLM rerank 30\u219210", "60.7", "96.9%"],
    ["dense top-30", "57.9", "98.1%"],
    ["top-10 / as-of filter", "50.7", "86.7%"],
    ["session top-5 / hybrid RRF / MMR", "47.1 / 41.4 / 40.7", "85 / 78 / 78%"],
    ["query rewrite / recency prior", "36.4 / 10.7", "64 / 53%"],
  ], { x: 0.6, y: 1.55, w: 4.1, colW: [2.4, 0.9, 0.8], fontSize: 9.5, rowH: 0.34 });
  table(s, [
    ["104K store: arm", "acc haiku / Sonnet 5", "in tok"],
    ["QVF slot projection", "61.7 / 74.2", "8.8K / 11.5K"],
    ["QVF full ledger", "54.2 / 73.3", "20.9K / 27.2K"],
    ["dense top-100", "38.3 / 67.5", "8.9K / 11.6K"],
    ["dense top-50 / rerank", "29.2 / 26.7", "4.5K / 1K+2.9K"],
    ["top-10 direct", "16.7", "1.0K"],
    ["full text (plain)", "7.5 / 54.9*", "103.8K / 142K"],
  ], { x: 4.9, y: 1.55, w: 3.6, colW: [1.7, 1.1, 0.8], fontSize: 9.5, rowH: 0.34 });
  table(s, [
    ["v2.5 sample: system", "acc"],
    ["QVF ledger (v2.5 store / v2.4 store)", "98.3 / 89.7"],
    ["QVF compile arm", "75.9"],
    ["Whole memory in prompt (haiku)", "63.8"],
    ["timeline baseline", "56.9"],
    ["lgstore / HippoRAG 2 / txtai / cognee", "46.6 / 46.5 / 44.8 / 44.8"],
    ["Letta-FS agent (30K tok/q) / A-MEM", "43.1 / 39.7"],
    ["top-10 direct / summary RAG", "37.9 / 36.2"],
    ["LangMem / TRACE / MemOS", "32.8 / 31.0 / 31.0"],
    ["stamped ledger / obs-RAG / BM25 / Mem0", "13.8 / 13.8 / 12.1 / 10.3"],
  ], { x: 8.7, y: 1.55, w: 4.0, colW: [2.9, 1.1], fontSize: 9.5, rowH: 0.34 });
  bullets(s, [
    "14K: recall is not the bottleneck \u2014 top-50 reaches 99.8% of gold anchors and still fails 37%; the best variant is 28.6 pp below the ledger (p = 5e-10). LLM rerank costs more per question than the ledger and is 30.7 pp worse.",
    "104K: retrieval collapses first (top-10 sees 38.8% of anchors); at equal token budget the projection beats top-100 by 23.3 pp with haiku (p = 2e-4) and by 6.7 pp with Sonnet 5 (n.s.); full text is unusable for haiku and reaches only 54.9 for Sonnet 5 (*n = 82, budget stop; 18% of calls truncated at the output cap).",
    "Competitors (each independently re-scored and diffed for protocol parity): every system scores below the plain full-context call on the same 58 questions; middle-of-table CIs overlap, no ranking claimed there.",
  ], { x: 0.6, y: 5.2, w: 12.1, h: 1.8, fontSize: 11 });
  footer(s, n);
}
// ---------- 14 cross-tests: QVF elsewhere ----------
{
  const s = pres.addSlide(); n++;
  title(s, "Cross-test 1 · QVF on other benchmarks", "Same reader haiku-4.5; direct = OpenAI embedding top-10; ledger arm vs direct");
  table(s, [
    ["Benchmark", "Type", "Ledger vs direct", "Verdict"],
    ["STALE (120, fresh)", "state supersession", "61.7 vs 46.7, +15.0 (p = 0.008, 3 judges agree)", "positive"],
    ["LongMemEval temporal reasoning (133)", "temporal reasoning", "60.2 vs 47.4, +12.8", "positive"],
    ["LongMemEval knowledge update (78)", "knowledge update", "80.8 vs 78.2, +2.6", "tie"],
    ["LongMemEval multi-session (132)", "cross-session", "59.1 vs 61.4, −2.3", "tie (powered null)"],
    ["LongMemEval single-user (68) / single-assistant (45)", "verbatim facts / assistant content", "72.1 vs 97.1, −25.0 · 0 vs 100", "negative (card schema extracts user entities only)"],
    ["LongMemEval preference (28)", "preferences", "42.9 vs 71.4, −28.6", "negative"],
    ["Temporal Wiki (300)", "yearly snapshots", "82.3 vs 86.7, −4.3", "negative (card builder dates by narrated year)"],
    ["AMemGym (600) / PersonaMem v2 (600)", "wording options / retractions", "−3.3 to −4.7 · −7.2 (who = others +14.0)", "negative"],
    ["MemConflict / MemOps / ElephantBench-OB", "conflict / ops / multi-ledger retention", "tie · +4.2 n.s. · 98.3 (= full text 100)", "tie"],
  ], { x: 0.6, y: 1.6, w: 12.1, colW: [3.6, 2.4, 3.6, 2.5], fontSize: 10.5, rowH: 0.45 });
  s.addText("Reading of 16 arenas: the ledger wins where the question needs cross-date state-transition reasoning and memories are dated statements (STALE, LME temporal, WikiState's three validity types); it loses on verbatim facts, preferences and wording, assistant-side content, and snapshot corpora. This is the claim's scope, stated in §1 and limitations.", { x: 0.6, y: 6.1, w: 12.1, h: 0.85, fontFace: BFONT, fontSize: 11, color: INK, margin: 0 });
  footer(s, n);
}
// ---------- 15 cross-tests: competitors on WikiState ----------
{
  const s = pres.addSlide(); n++;
  title(s, "Cross-test 2 · Other memory systems on WikiState", "60-question v1 calibration set, same reader and judge; official packages where available (18 run, 2 blocked by Docker)");
  table(s, [
    ["System", "Acc", "Note"],
    [{ text: "QVF ledger / compile / select", options: { bold: true } }, { text: "86.7 / 83.3 / 70.0", options: { bold: true } }, "three tiers of this method"],
    ["timeline (self-built timeline baseline)", "63.3", "strongest non-QVF"],
    ["Letta-style file-system agent", "56.7", "$0.021 per question, 21× cost"],
    ["HippoRAG 2 (ICML 2025, official)", "55.0", "chain-state recall@10 0.915 — retrieval wins, adjudication loses"],
    ["lgstore / txtai / direct read", "55.0 / 53.3 / 51.7", ""],
    ["Summary RAG / cognee / MemOS", "46.7 / 46.7 / 45.0", "MemOS expands 4.1 nodes per session instead of consolidating"],
    ["A-MEM / LangMem", "43.3 / 40.0", ""],
    ["TRACE (LoCoMo config / factory)", "30.0 / 16.7", "0 supersession edges by default; full 576 q: 16.0"],
    ["Mem0 / BM25 / Graphiti / LightRAG", "26.7 / 13.3 / 3.3 / 1.7", "Mem0 131 s per question to build"],
  ], { x: 0.6, y: 1.6, w: 12.1, colW: [4.2, 2.4, 5.5], fontSize: 11, rowH: 0.42 });
  s.addText("Shared failure mode: retrieval wins, adjudication loses. Competitors treat validity as a one-time scalar fixed at write time (Zep / TRACE / MemStrata); QVF treats validity as a function of memory × query and re-derives it at read time. Middle of the table: confidence intervals overlap, no ranking claimed; head and tail are separated.", { x: 0.6, y: 6.05, w: 12.1, h: 0.9, fontFace: BFONT, fontSize: 11, color: INK, margin: 0 });
  footer(s, n);
}
// ---------- 16 boundaries & next ----------
{
  const s = pres.addSlide(); n++;
  title(s, "Honest boundaries and next steps");
  s.addText("Boundaries (said up front)", { x: 0.6, y: 1.5, w: 6, h: 0.4, fontFace: HFONT, fontSize: 18, bold: true, color: NAVY, margin: 0 });
  bullets(s, [
    "Scope is three conditions (non-frontier reader, or store beyond the context window, or cost-bound). With a strong reader on a 14K store the whole memory in the prompt beats the v45 ledger (97.1 vs 90.7, p = 0.035); Sonnet-built cards plus an assertion-type filter reach 95.0 (−2.1 vs full context, n.s.); the residual is one chain's extraction gap.",
    "External arenas: 2 positive, several ties, several negative; the scope is three conditions, not a universal win.",
    "Owner gate costs accuracy on clean text; the '5× cost' and 'ledger constant' claims are withdrawn.",
    "Human agreement is fair (\u03b1 \u2248 0.3\u20130.45); the v2.5 human review has not started; the 560-q table uses the v2.4-corpus store; the partial v2.5-corpus rerun (36 chains) agrees with it within noise; write-side extraction is nondeterministic (two passes overlap 2\u201333% of cards) and 140-q reader runs jitter 3\u20134 pp.",
    "Card builder regression (slot_class / owner fields) still patched via a derived store; fix pending.",
  ], { x: 0.6, y: 1.95, w: 6.0, h: 4.9, fontSize: 12.5 });
  s.addText("Next steps", { x: 7.0, y: 1.5, w: 5.7, h: 0.4, fontFace: HFONT, fontSize: 18, bold: true, color: NAVY, margin: 0 });
  bullets(s, [
    "Author review of v2.5 on the author-v25 link (149 items, ~1.5–2 min each); compute agreement against the machine review.",
    "Running now: render-matched control (layout kept, compile off) and a second-family judge re-judging the main table; finish the 104K full-context arm (38 questions) so the store-level CI closes; then a full v2.5-corpus rerun once the human review settles the corpus.",
    "Fix the card builder schema regression and retire the derived store.",
    "Paper: §2 ancestors (temporal databases, TAC-KBP), §8 limitations as a three-condition scope, datasheet v2.5 with the tenure convention and errata.",
  ], { x: 7.0, y: 1.95, w: 5.7, h: 4.9, fontSize: 12.5 });
  footer(s, n);
}

const out = process.argv[2] || "D:/ZZL_cluade/results/weekly_report_20260904.pptx";
pres.writeFile({ fileName: out }).then(f => console.log("written", f, "slides", n));
