// Talk deck (English), 15-minute version: QVF steps, this week's write-side fixes and generality check, WikiState, reviewer feedback. 2026-09-05.
// Run: NODE_PATH=<dir with node_modules/pptxgenjs> node scripts/make_talk_deck_20260905.js <out.pptx>
const pptxgen = require("pptxgenjs");

const NAVY = "1E2761", INK = "1F2937", MUTED = "6B7280", LINE = "D1D5DB", ICE = "EAF0FB", WHITE = "FFFFFF";
const GRAY = "9AA3AE", ACCENT = "B85042", GOOD = "2C5F2D", CODEBG = "F5F7FA";
const HFONT = "Cambria", BFONT = "Calibri", MONO = "Courier New";

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.author = "Jeremy Zhong";
pres.title = "QVF & WikiState";
let n = 0;

function title(slide, text, sub) {
  slide.addText(text, { x: 0.6, y: 0.35, w: 12.1, h: 0.7, fontFace: HFONT, fontSize: 28, bold: true, color: NAVY, margin: 0 });
  if (sub) slide.addText(sub, { x: 0.6, y: 1.02, w: 12.1, h: 0.4, fontFace: BFONT, fontSize: 13, color: MUTED, margin: 0 });
}
function footer(slide) {
  slide.addText("QVF & WikiState \u00b7 5 Sep 2026", { x: 0.6, y: 7.05, w: 8, h: 0.3, fontFace: BFONT, fontSize: 9, color: MUTED, margin: 0 });
  slide.addText(String(n), { x: 12.2, y: 7.05, w: 0.5, h: 0.3, fontFace: BFONT, fontSize: 9, color: MUTED, align: "right", margin: 0 });
}
function bullets(slide, items, o) {
  const arr = items.map((t, i) => ({ text: t, options: { bullet: true, breakLine: i < items.length - 1, paraSpaceAfter: 5 } }));
  slide.addText(arr, Object.assign({ fontFace: BFONT, fontSize: 12, color: INK, valign: "top", margin: 0 }, o));
}
function table(slide, rows, o) {
  const head = rows[0].map(c => ({ text: c, options: { bold: true, color: WHITE, fill: { color: NAVY }, fontFace: BFONT, fontSize: o.fontSize || 11, align: "center", valign: "middle" } }));
  const body = rows.slice(1).map((r, ri) => r.map((c, ci) => {
    const cell = typeof c === "object" ? c : { text: c };
    const opts = Object.assign({ fontFace: BFONT, fontSize: o.fontSize || 11, color: INK, align: ci === 0 ? "left" : "center", valign: "middle", fill: { color: ri % 2 ? CODEBG : WHITE } }, cell.options || {});
    return { text: cell.text, options: opts };
  }));
  slide.addTable([head, ...body], Object.assign({ border: { type: "solid", color: LINE, pt: 0.5 }, margin: 0.04 }, o));
}
function box(slide, x, y, w, h, heading, lines, opts) {
  const fill = (opts && opts.fill) || ICE;
  slide.addShape(pres.ShapeType.roundRect, { x, y, w, h, fill: { color: fill }, line: { color: fill }, rectRadius: 0.06 });
  slide.addText(heading, { x: x + 0.15, y: y + 0.08, w: w - 0.3, h: 0.32, fontFace: HFONT, fontSize: 12.5, bold: true, color: (opts && opts.color) || NAVY, margin: 0 });
  slide.addText(lines.map((t, i) => ({ text: t, options: { breakLine: i < lines.length - 1, paraSpaceAfter: 3 } })), { x: x + 0.15, y: y + 0.42, w: w - 0.3, h: h - 0.5, fontFace: (opts && opts.mono) ? MONO : BFONT, fontSize: (opts && opts.fontSize) || 10, color: INK, valign: "top", margin: 0 });
}
function code(slide, x, y, w, h, lines) {
  slide.addText(lines.map((t, i) => ({ text: t, options: { breakLine: i < lines.length - 1 } })), { x, y, w, h, fontFace: MONO, fontSize: 9.5, color: INK, fill: { color: CODEBG }, valign: "top", margin: 0.1 });
}
function stepSlide(stepTitle, sub, before, after, pseudo, evidence, lit) {
  const s = pres.addSlide(); n++;
  title(s, stepTitle, sub);
  box(s, 0.6, 1.55, 4.0, 2.75, before.h, before.lines, { fill: "F3F4F6", color: MUTED, fontSize: 9.5 });
  s.addShape(pres.ShapeType.rightArrow, { x: 4.72, y: 2.7, w: 0.45, h: 0.45, fill: { color: GRAY }, line: { color: GRAY } });
  box(s, 5.3, 1.55, 4.0, 2.75, after.h, after.lines, { fontSize: 9.5 });
  code(s, 9.5, 1.55, 3.25, 2.75, pseudo);
  s.addText("Why this step exists \u2014 our evidence", { x: 0.6, y: 4.5, w: 6.5, h: 0.3, fontFace: HFONT, fontSize: 12.5, bold: true, color: NAVY, margin: 0 });
  bullets(s, evidence, { x: 0.6, y: 4.85, w: 6.9, h: 2.1, fontSize: 10.5 });
  s.addText("Literature that predicts it", { x: 7.8, y: 4.5, w: 4.9, h: 0.3, fontFace: HFONT, fontSize: 12.5, bold: true, color: NAVY, margin: 0 });
  bullets(s, lit, { x: 7.8, y: 4.85, w: 4.9, h: 2.1, fontSize: 10.5 });
  footer(s);
}

// ---------- 1 title ----------
{
  const s = pres.addSlide(); n++;
  s.background = { color: NAVY };
  s.addText("QVF: query-conditioned validity for conversational memory", { x: 0.8, y: 2.0, w: 11.7, h: 1.4, fontFace: HFONT, fontSize: 38, bold: true, color: WHITE, margin: 0 });
  s.addText("Why each step helps, what the write side gained this week, and whether it travels beyond WikiState", { x: 0.8, y: 3.5, w: 11.5, h: 0.6, fontFace: BFONT, fontSize: 20, color: "CADCFC", margin: 0 });
  s.addText("Progress talk \u00b7 5 September 2026 \u00b7 15 minutes", { x: 0.8, y: 4.3, w: 11.5, h: 0.5, fontFace: BFONT, fontSize: 15, color: "CADCFC", margin: 0 });
  s.addText("Jeremy Zhong", { x: 0.8, y: 6.3, w: 6, h: 0.4, fontFace: BFONT, fontSize: 14, color: WHITE, margin: 0 });
}
// ---------- 2 agenda ----------
{
  const s = pres.addSlide(); n++;
  title(s, "Agenda (15 minutes)");
  const items = [
    ["1", "QVF step by step \u2014 why each step removes one failure source", "one real chain, before \u2192 after, evidence  (7 min)"],
    ["2", "This week: four write-side fixes from a senior labmate’s code review, and a generality check", "WikiState 90 \u2192 95; two third-party arenas; what is general and what was tuned  (4 min)"],
    ["3", "WikiState: scale, what only it tests, review status", "(2 min)"],
    ["4", "Feedback received, what changed, boundaries, next steps", "(2 min)"],
  ];
  items.forEach((it, i) => {
    const y = 1.8 + i * 1.15;
    s.addShape(pres.ShapeType.ellipse, { x: 0.8, y: y, w: 0.6, h: 0.6, fill: { color: NAVY }, line: { color: NAVY } });
    s.addText(it[0], { x: 0.8, y: y, w: 0.6, h: 0.6, fontFace: HFONT, fontSize: 18, bold: true, color: WHITE, align: "center", valign: "middle", margin: 0 });
    s.addText(it[1], { x: 1.7, y: y - 0.02, w: 10.8, h: 0.4, fontFace: HFONT, fontSize: 19, bold: true, color: INK, margin: 0 });
    if (it[2]) s.addText(it[2], { x: 1.7, y: y + 0.38, w: 10.8, h: 0.32, fontFace: BFONT, fontSize: 13, color: MUTED, margin: 0 });
  });
  footer(s);
}
// ---------- 3 the problem ----------
{
  const s = pres.addSlide(); n++;
  title(s, "The problem: what the reader is up against \u2014 one real chain", "wikiP39042: 34 dated sessions, ~170 user turns; four of them carry the persona's own position history");
  s.addShape(pres.ShapeType.roundRect, { x: 0.6, y: 1.55, w: 6.0, h: 2.95, fill: { color: ICE }, line: { color: ICE }, rectRadius: 0.08 });
  s.addText("The four sentences that matter (verbatim anchors)", { x: 0.8, y: 1.65, w: 5.6, h: 0.35, fontFace: HFONT, fontSize: 13, bold: true, color: NAVY, margin: 0 });
  s.addText([
    { text: "1974-02-28  ", options: { bold: true, color: NAVY } }, { text: "\u201cI'm now a member of the 46th Parliament of the United Kingdom\u201d", options: { breakLine: true } },
    { text: "1974-10-10  ", options: { bold: true, color: NAVY } }, { text: "\u201cI'm now a member of the 47th Parliament \u2026\u201d", options: { breakLine: true } },
    { text: "1992-04-09  ", options: { bold: true, color: NAVY } }, { text: "\u201cI'll be taking my seat as a member of the 51st Parliament \u2026\u201d", options: { breakLine: true } },
    { text: "1997-10-03  ", options: { bold: true, color: NAVY } }, { text: "\u201cas of today I'm officially a member of the House of Lords\u201d", options: {} },
  ], { x: 0.8, y: 2.05, w: 5.6, h: 1.55, fontFace: BFONT, fontSize: 11.5, color: INK, margin: 0, valign: "top", paraSpaceAfter: 4 });
  s.addText("Q: \u201c(Today is 1998-04-01.) How many times did I change my position?\u201d  \u2192  gold 3", { x: 0.8, y: 3.7, w: 5.6, h: 0.6, fontFace: BFONT, fontSize: 12, bold: true, color: ACCENT, margin: 0 });
  s.addText("The other ~166 turns", { x: 6.9, y: 1.55, w: 5.8, h: 0.35, fontFace: HFONT, fontSize: 13, bold: true, color: NAVY, margin: 0 });
  bullets(s, [
    "Small talk: sneakers, a festival, a flat search, tea \u2014 plus states of OTHER people in the same slot.",
    "Dates live on session headers, not in the sentences (\u201cas of today\u201d, \u201cthe count went our way\u201d).",
    "Nothing says \u201cthis supersedes that\u201d; succession must be inferred from dates.",
    "Existing memory systems and benchmarks fix validity at write time: the latest value wins and older values count as errors \u2014 but \u201cwhere was I in 2009?\u201d and \u201chow many times?\u201d need the superseded values.",
  ], { x: 6.9, y: 1.95, w: 5.8, h: 2.6, fontSize: 11.5 });
  s.addText("To answer correctly the reader must do four things at once", { x: 0.6, y: 4.7, w: 12.1, h: 0.35, fontFace: HFONT, fontSize: 13, bold: true, color: NAVY, margin: 0 });
  table(s, [
    ["Sub-task", "What goes wrong for a small reader", "Which arm still fails it"],
    ["Find all four sentences", "top-10 retrieval covers 86.7% of anchors on 14K stores, 38.8% on 104K stores", "retrieval; every RAG variant at scale"],
    ["Exclude other people's states", "same-slot distractors get counted", "retrieval and full text (no-filler: direct +22.5, ledger +1.7)"],
    ["Order by date", "dates are on headers; narrative order \u2260 time order", "full text"],
    ["Count transitions (merge equal neighbours)", "weak readers cannot count over a timeline (full text change_count 29.9)", "everything except compile / ledger"],
  ], { x: 0.6, y: 5.1, w: 12.1, colW: [3.0, 5.4, 3.7], fontSize: 10, rowH: 0.33 });
  footer(s);
}
// ---------- 4 QVF in one picture ----------
{
  const s = pres.addSlide(); n++;
  title(s, "QVF in one picture", "Write-time state cards, read-time dated ledger; validity is a function of (memory \u00d7 query), re-derived per question");
  s.addShape(pres.ShapeType.roundRect, { x: 0.6, y: 1.6, w: 3.4, h: 4.9, fill: { color: ICE }, line: { color: ICE }, rectRadius: 0.08 });
  s.addText("WRITE TIME (once per session)", { x: 0.8, y: 1.75, w: 3.0, h: 0.4, fontFace: HFONT, fontSize: 14, bold: true, color: NAVY, margin: 0 });
  bullets(s, ["Extract state cards from each session, in date order", "Card = slot \u00b7 value \u00b7 stated date \u00b7 verbatim source span \u00b7 entity", "No adjudication, no merging \u2014 record only", "Coverage is complete by construction (every session is read once)"], { x: 0.8, y: 2.25, w: 3.0, h: 4.0, fontSize: 12 });
  s.addShape(pres.ShapeType.rightArrow, { x: 4.15, y: 3.8, w: 0.6, h: 0.6, fill: { color: GRAY }, line: { color: GRAY } });
  const steps = [["1 Select", "keep cards of the queried slot that belong to the persona"], ["2 Certify", "keep cards that carry a date, can be located in a source sentence, and declare a held state"], ["3 Compile", "sort by date, merge adjacent equal values, count transitions with an executor"], ["4 Ledger + protocol", "render the dated ledger; reader first lists the state trajectory, then answers"]];
  steps.forEach((st, i) => {
    const y = 1.6 + i * 1.25;
    s.addShape(pres.ShapeType.roundRect, { x: 4.95, y: y, w: 4.2, h: 1.1, fill: { color: WHITE }, line: { color: NAVY, pt: 1 }, rectRadius: 0.06 });
    s.addText(st[0], { x: 5.1, y: y + 0.08, w: 3.9, h: 0.35, fontFace: HFONT, fontSize: 14, bold: true, color: NAVY, margin: 0 });
    s.addText(st[1], { x: 5.1, y: y + 0.42, w: 3.9, h: 0.62, fontFace: BFONT, fontSize: 11, color: INK, margin: 0, valign: "top" });
  });
  s.addText("READ TIME (per question)", { x: 4.95, y: 6.65, w: 4.2, h: 0.3, fontFace: BFONT, fontSize: 10, color: MUTED, margin: 0 });
  code(s, 9.4, 1.6, 3.35, 4.9, ["WRITE(sessions):", "  for s in sessions by date:", "    cards += extract(s)", "    # slot, value, date,", "    # span, entity", "", "READ(q, cards):", "  pool = select(cards,", "                slot(q), self)", "  pool = certify(pool)", "  ledger = compile(", "           sort_by_date(pool))", "  return reader(PROTOCOL,", "         render(ledger), q)"]);
  footer(s);
}
// ---------- 5..9 the five steps ----------
stepSlide("Step 0 \u00b7 Write time: state cards, no adjudication", "Failure source removed: coverage \u2014 every session is read once, so no evidence is left to retrieval luck",
  { h: "Before: a raw session (1992-04-09, user turns)", lines: [
    "\u201cRight, polling day at last \u2014 I've been up since half five, out at the school gate in Royton with a flask of tea and a rosette\u2026 Remind me to buy new laces for the brown shoes\u2026\u201d",
    "\u201cWell \u2014 the count went our way. I'll be taking my seat as a member of the 51st Parliament of the United Kingdom, so put that in your notes\u2026 My voice has completely gone.\u201d",
    "\u201cBefore I collapse: set something for later in the week about digs in London\u2026 And tea. Lots of tea.\u201d" ] },
  { h: "After: cards extracted from that session (real store v45)", lines: [
    "r41  slot political_activity \u00b7 value \u201ccampaigning for Parliament in Royton\u201d \u00b7 date 1992-04-09 \u00b7 span \u201cI've been up since half five, out at the school gate in Royton\u2026\u201d",
    "r42  slot political_office \u00b7 value \u201cmember of 51st Parliament of the United Kingdom\u201d \u00b7 date 1992-04-09 \u00b7 span \u201cI'll be taking my seat as a member of the 51st Parliament\u2026\u201d \u00b7 entity user",
    "Nothing is merged, ranked or judged; the shoe laces and the London digs are simply not states." ] },
  ["WRITE(sessions):", "  for s in sorted(sessions, by=date):", "    for c in LLM_extract(s):", "      cards.append({", "        slot: c.slot,", "        value: c.value,", "        stated_date: c.date or s.date,", "        span: verbatim(c.span, s),", "        entity: c.entity })", "  # no supersession decision here"],
  ["Ledger built at read time from the 10 retrieved turns: 60.2; 85.3 when retrieval happens to cover every session, 15.9 when one session is missing \u2192 write-time = coverage.",
   "Top-50 retrieval reaches 99.8% of gold anchors and still fails 37%: finding is necessary, not sufficient \u2014 the next steps do the rest.",
   "Perfect gold sentences fed to the direct reader: 76.7 < ledger 82.6 (p = 8e-11)."],
  ["MemTrace (2606.17328): across 13 configurations the dominant bottleneck is evidence use, not retrieval.", "Zep / Graphiti (2501.13956): write-time extraction into dated facts as a memory design."]);

stepSlide("Step 1 \u00b7 Select: the queried slot, the persona's own states", "Failure source removed: distractors \u2014 other people's and off-slot states entering the count",
  { h: "Before: all 56 cards of this persona (store v45)", lines: [
    "travel_history 8 \u00b7 political_office 4 \u00b7 event_attendance 3 \u00b7 political_activity 2 \u00b7 shopping_habits 2 \u00b7 family_relationships 2 \u00b7 podcast_app 2 \u00b7 morning_exercise_routine 1 \u00b7 \u2026",
    "A weak reader given all of this counts \u201ccampaigning in Royton\u201d as a position change and, in other chains, \u201cour team lead Emily was promoted\u201d as the persona's own state." ] },
  { h: "After: the pool for slot = position, entity = user", lines: [
    "1974-02-28  member of 46th Parliament of the UK",
    "1974-10-10  member of 47th Parliament of the UK",
    "1992-04-09  member of 51st Parliament of the UK",
    "1997-10-03  member of House of Lords",
    "4 cards remain; 52 are out of the counting pool before the reader sees anything." ] },
  ["SELECT(cards, q):", "  slot = slot_class(q)   # employer |", "         # position | team | residence", "  return [c for c in cards", "          if slot_class(c.slot) == slot", "          and c.entity == 'user']"],
  ["Remove all filler sessions from the corpus: direct +22.5, full text +20.0, ledger +1.7 \u2192 the ledger had already removed the harm; 44% of the structural premium is distractor resistance.",
   "Owner gate at write time (cards only for the persona) recovers 92% of an \u221218.4 third-person attack but costs \u22123 on clean text \u2192 kept as a hardening flag, default off."],
  ["Shi et al., ICML 2023 (2302.00093): topically similar but irrelevant context sharply lowers LLM accuracy."]);

stepSlide("Step 2 \u00b7 Certify: dated, locatable, and a held state", "Failure source removed: unverifiable cards \u2014 no date, no verbatim source, or not a state at all (plans, nominations, one-off tasks)",
  { h: "Before: the pool can contain cards that are\u2026", lines: [
    "\u2026 without a stated date (\u201cI do a 30-minute yoga session every morning\u201d \u2014 a routine, no date);",
    "\u2026 whose span cannot be located verbatim in the source session (paraphrased by the extractor);",
    "\u2026 plans / nominations / candidacies (\u201cteaching assistant nominee\u201d), incoming / admitted (\u201cadmitted to UC Berkeley\u201d), one-off tasks (\u201cworking on a big campaign at job\u201d), restatements." ] },
  { h: "After: only cards that pass three checks", lines: [
    "stated_date present (day precision when the source has one);",
    "span found verbatim in its session (the anchor a human reviewer can check);",
    "assertion_type = start (a first-person declaration of holding the state).",
    "In the example chain all four position cards pass; in the 36-chain sample the filter drops 203 of 1,639 cards and loses zero gold rows." ] },
  ["CERTIFY(pool):", "  out = []", "  for c in pool:", "    if not c.stated_date: continue", "    if c.span not in text(session(c)):", "      continue", "    if assertion_type(c) != 'start':", "      continue   # plan, task, restate,", "                  # other_person", "    out.append(c)", "  return out"],
  ["Remove verbatim anchors from the ledger: \u22125.4 (p = 1e-4) \u2014 readers start trusting unsupported cards.",
   "Assertion-type filter (rules, zero cost): compiled ledger = gold 131 \u2192 137 of 140 questions; reader accuracy 88.6 / 91.4 \u2192 93.6 / 95.0 (haiku / Sonnet 5); the residual errors were plans and nominations misread as roles.",
   "The rung alone is small (+0.5 here, +5.7 on the clean subset): it feeds step 3 \u2014 without dates nothing can be sorted."],
  ["TAC-KBP temporal slot filling (2011/2013) and Garrido et al., ACL 2012: employer / position / membership / residence as slots whose values are valid only over an interval and must be anchored to dated evidence."]);

stepSlide("Step 3 \u00b7 Compile: sort, merge, count \u2014 by code, not by the LM", "Failure source removed: aggregation \u2014 ordering and counting over a timeline is the weak reader's blind spot",
  { h: "Before: certified cards in extraction order", lines: [
    "\u201cmember of 51st Parliament\u201d (1992-04-09), \u201cmember of 46th Parliament\u201d (1974-02-28), \u201cmember of House of Lords\u201d (1997-10-03), \u201cmember of 47th Parliament\u201d (1974-10-10), plus any restated value from a later session\u2026",
    "A reader asked \u201chow many times\u201d must order, deduplicate and count in its head." ] },
  { h: "After: the ledger, computed", lines: [
    "#1  1974-02-28  46th Parliament          tenure 224 d",
    "#2  1974-10-10  47th Parliament          tenure 6,391 d",
    "#3  1992-04-09  51st Parliament          tenure 2,003 d",
    "#4  1997-10-03  House of Lords           current (to Today)",
    "transitions = 3 \u00b7 values before 1998-04-01 = 4 \u00b7 first = 46th, latest = House of Lords",
    "Equal adjacent values are merged so a restatement never counts as a change." ] },
  ["COMPILE(cards, today):", "  rows = sort(cards, key=stated_date)", "  rows = merge_adjacent_equal(rows)", "  n_changes = len(rows) - 1", "  for i, r in enumerate(rows):", "    end = rows[i+1].date if i+1 < len(rows)", "          else today", "    r.tenure = end - r.date", "  return rows, n_changes"],
  ["Full text, same reader: change_count 29.9; ledger 85.4. The compile rung is the largest single step (+12.7 on 560 q) \u2014 the other 56% of the structural premium.",
   "Deeper retrieval does not substitute: top-50 lifts count_before but change_count drops (47.2 \u2192 33.3) and longest_tenure stays at 34 (ledger 94).",
   "With a strong reader the compile step matters less (Sonnet 5 on full context 97.1) \u2014 the reader can count itself; with a 104K store it cannot (54.9 vs projection 74.2)."],
  ["PAL, ICML 2023 (2211.10435): let a program execute the arithmetic step.", "Faith and Fate, NeurIPS 2023 (2305.18654): transformers fail on chained multi-step aggregation.", "Test of Time, ICLR 2025 (2406.09170): ordering and counting over timelines is weak even when facts are given."]);

stepSlide("Step 4 \u00b7 Ledger + protocol: list the trajectory, then answer", "Failure source removed: skipping \u2014 answering from intuition instead of the whole trajectory",
  { h: "Before: what the reader used to see", lines: [
    "Either 14K tokens of chat in narrative order (full text), or 10 retrieved turns with session dates (top-10), and a question.",
    "Weak readers jump to a plausible number (\u201c2\u201d or \u201c4\u201d) without enumerating the states." ] },
  { h: "After: the rendered ledger + the trajectory-first protocol", lines: [
    "DATE | VALUE | SOURCE SENTENCE (verbatim)  \u2014 4 rows, ~2.9K tokens including the protocol",
    "Protocol: \u201cFirst list the trajectory of the queried slot with dates; then answer the question from that list.\u201d",
    "Reader output: \u201cTrajectory: 1974-02-28 46th; 1974-10-10 47th; 1992-04-09 51st; 1997-10-03 House of Lords. Changes: 3.\u201d",
    "Every row carries its anchor sentence, so the answer is auditable." ] },
  ["ANSWER(q, rows):", "  prompt = PROTOCOL", "         + render_table(rows)", "         + q", "  # PROTOCOL: list the dated", "  # trajectory first, then answer", "  return reader(prompt)"],
  ["Protocol effect by reader: haiku +10.9 (p < 1e-6), gpt-5-mini \u22123.5, Gemini 3.6 Flash +0.35 n.s. \u2014 a scaffold for weak and mid-tier readers.",
   "Compression alone gives nothing: an unstructured summary at equal token budget scores 52.8 = full text 52.3; summary \u2192 bare ledger +22.6 (p = 2e-21).",
   "Five readers on the same 140 q: the ledger beats top-10 retrieval by \u2265 15 pp for all; against the whole memory in the prompt it wins for haiku (+23.6) and a local 14B model (+17.9), ties for Gemini (\u22120.7) and roughly ties for gpt-5-mini (−4.3, n.s., after fixing its output cap)."],
  ["Sprague et al. 2024 (2409.12183): chain-of-thought helps mainly on symbolic / counting tasks.", "Lost in the Middle, TACL 2024 (2307.03172): evidence buried in long context is missed.", "Render-matched control (batches 44 / 46b): same layout + protocol with compile off scores 85.0 (14K) / 70.0 (104K); keyword-matched raw quotes in the same layout 85.4 / 55.8; ledger 89.3 / projection 61.7. About 88% of the ledger’s gain over plain full text is layout + protocol; write-time cards add coverage, de-duplication (raw quotes double-count repeated mentions at 104K) and auditability, not most of the accuracy."]);

// ---------- 10 ladder ----------
const ARMS = [["Direct read (top-10 retrieval)", 47.32], ["1 Select", 66.25], ["2 Certify", 66.79], ["3 Compile", 79.46], ["4 Ledger + protocol (QVF)", 89.29]];
{
  const s = pres.addSlide(); n++;
  title(s, "Putting the steps back together: the ladder", "560 questions, corpus v2.4, one store, reader haiku-4.5, judge Opus 5; paired McNemar per rung");
  s.addChart(pres.ChartType.bar, [{ name: "Accuracy (%)", labels: ARMS.map(a => a[0]), values: ARMS.map(a => a[1]) }], {
    x: 0.6, y: 1.55, w: 7.2, h: 5.2, barDir: "col", chartColors: [NAVY], showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 12, dataLabelFontFace: BFONT, dataLabelColor: INK, dataLabelFormatCode: "0.0",
    valAxisMinVal: 0, valAxisMaxVal: 100, valAxisMajorUnit: 20, valAxisLabelFontSize: 10, valAxisLabelColor: MUTED, valGridLine: { color: "E5E7EB", size: 0.5 }, catAxisLabelFontSize: 10, catAxisLabelColor: INK, catGridLine: { style: "none" }, showLegend: false, showTitle: false, barGapWidthPct: 60,
  });
  const why = [["Direct 47.3", "top-10 retrieval, raw text"], ["Select +18.9", "distractors out of the counting pool (44% of the premium)"], ["Certify +0.5", "small alone; feeds the compile step"], ["Compile +12.7", "counting by code (the other 56%)"], ["Ledger + protocol +9.8", "trajectory-first reading; helps weak / mid readers"]];
  why.forEach((w, i) => {
    const y = 1.55 + i * 1.0;
    s.addText(w[0], { x: 8.1, y: y, w: 4.6, h: 0.3, fontFace: HFONT, fontSize: 13, bold: true, color: i === 0 ? GRAY : NAVY, margin: 0 });
    s.addText(w[1], { x: 8.1, y: y + 0.3, w: 4.6, h: 0.6, fontFace: BFONT, fontSize: 10.5, color: INK, margin: 0, valign: "top" });
  });
  s.addText("Whole gain: +42.0 pp vs top-10 retrieval, chain-cluster 95% CI [37.0, 46.9]; +21.4 vs the whole memory in the prompt on the same weak reader.", { x: 8.1, y: 6.55, w: 4.6, h: 0.5, fontFace: BFONT, fontSize: 10, color: ACCENT, margin: 0 });
  footer(s);
}
// ---------- 11 this week: write-side fixes ----------
{
  const s = pres.addSlide(); n++;
  title(s, "This week: four write-side fixes from a senior labmate’s code review", "Batches 47–50. Each fix is a default-off builder flag; stores are never overwritten; every number is a paired comparison on the same questions");
  table(s, [
    ["Fix", "What it does", "Evidence", "Verdict"],
    ["Slim card contract", "Stop extracting claim, value_tags, implies_stale_slots, relation fields (42% of card characters; the ledger path never reads them)", "36 chains, Sonnet: gold rows 133/133, extra rows 4 \u2192 2, output tokens \u221233%", "confirmed, lossless"],
    ["Closed-set slot rule + value normalisation", "slot_class from a closed set so \u2018postdoc at X\u2019 becomes position + employer, two cards; strip parentheticals and corporate suffixes from values", "without it a strong reader falls 95.0 \u2192 88.6 (count_before 89 \u2192 69); with it 92.9", "confirmed, required"],
    ["Semantic entailment filter", "A cheap model labels each card\u2019s assertion type (start / plan / task / other person / restate / hypothetical / ended); drop non-start types, keep ended", "144 chains: extra rows 40 \u2192 28, compiled ceiling 91.4 \u2192 93.8, zero gold rows lost; keyword rules 92.7", "confirmed on state-chain slots"],
    ["Two-stage extraction (embedding localiser \u2192 extractor)", "Stage 1 picks candidate turns by similarity to \u2018state start\u2019 queries; Stage 2 extracts only those", "WikiState: lossless, build tokens \u221290%, 104K weak reader 54.2 \u2192 70.0. STALE 61.7 \u2192 43.3, MemOps 52.5 \u2192 25.8", "works only with domain slot queries: tuned, default off"],
  ], { x: 0.6, y: 1.55, w: 12.1, colW: [2.2, 3.9, 3.9, 2.1], fontSize: 9.5, rowH: 0.62 });
  table(s, [
    ["144 chains, 560 questions, haiku reader", "Accuracy (two runs)", "In tok / q", "$ / q", "Missing gold rows", "Compiled ceiling"],
    ["Old store v48f (batch 46d)", "89.82 / 90.18", "2,753", "$0.0052", "14 / 542", "92.5"],
    [{ text: "All four fixes (v52f)", options: { bold: true } }, { text: "95.36 / 94.82", options: { bold: true } }, "968", "$0.0033", "6 (wording variants)", "97.5"],
    ["Paired vs v48f", "+5.5 / +4.6 pp, McNemar p = 1e-4 / 1e-3, cluster 95% CI [+2.2, +8.9]", "\u221265%", "\u221237%", "", ""],
  ], { x: 0.6, y: 4.95, w: 12.1, colW: [3.0, 3.6, 1.2, 1.1, 1.6, 1.6], fontSize: 10, rowH: 0.36 });
  s.addText("First time a write-side change moved the reader significantly. Without the tuned Stage 1, the three general fixes alone reach 95.7 on the 36-chain subset (v48f 90.0 on the same questions). Sonnet 5 reader: 92.9 vs 95.0 before (n.s.).", { x: 0.6, y: 6.45, w: 12.1, h: 0.5, fontFace: BFONT, fontSize: 10.5, color: INK, margin: 0 });
  footer(s);
}
// ---------- 12 generality check ----------
{
  const s = pres.addSlide(); n++;
  title(s, "Is the new configuration tuned to WikiState?", "Same configuration on two third-party arenas: batch 19 fresh samples (40 stores / 120 q each), haiku reader and the arena\u2019s own judge, paired with the old cards built by the same extractor family");
  table(s, [
    ["Configuration", "WikiState (36 chains, 140 q, haiku)", "MemOps (120 q)", "STALE (120 q)", "Reading"],
    ["Direct read (top-10)", "\u2014", "48.3", "46.7", "baseline"],
    ["Old cards, full extraction", "90.0 (v48f)", "52.5", "61.7", "batch 19 / 46d"],
    ["Three general fixes, no Stage 1", "95.7", "50.0 (20 stores, same-store old 48.3; p = 1.0)", "58.3 (20 stores, same-store old 66.7; p = 0.36)", "MemOps equal; STALE \u22128 n.s., dim3 loses the ended / condition information the slim contract dropped"],
    ["+ Stage 1 with four WikiState slot queries", "95.7 / 94.3", "25.8 (p = 1e-6)", "43.3 (p = 0.004)", "tuned: below direct read on both arenas"],
    ["+ Stage 1 with 15 general queries", "\u2014", "42.5", "50.0", "recovers half; still below full extraction"],
    ["General contract (+ended, +condition) with a store-wide entailment filter", "91.4 (\u22124.3, p = 0.15)", "23.3", "47.5", "filter drops 76\u201378% of cards on generic memories: the \u2018held state\u2019 semantics are WikiState\u2019s"],
    ["General contract, no filter", "91.4", "50.0 (−2.5, p = 0.69)", "48.3 (−13.3, p = 0.007)", "the slim contract itself costs 13 pp on STALE; restoring ended / condition did not recover it"],
    ["General contract, filter on state-chain slot classes only", "91.4", "47.5 (−5.0, p = 0.38)", "47.5 (−14.2, p = 0.014)", "this filter scope is harmless (−0.8 / −2.5 vs no filter)"],
  ], { x: 0.6, y: 1.55, w: 12.1, colW: [3.0, 2.4, 2.0, 2.0, 2.7], fontSize: 9, rowH: 0.42 });
  bullets(s, [
    "What travels: the closed-set slot rule with value normalisation, and the entailment filter restricted to state-chain slot classes (harmless on all three arenas).",
    "What does not: the slim contract (−13 pp on STALE, p = 0.007, even with ended / condition restored), any Stage 1 whose queries name the benchmark’s slots, and a store-wide filter. All three are default-off and reported as WikiState-specific ablations.",
    "The senior labmate\u2019s Stage 1 (\u2018cheap model / embedding / rule\u2019 event localisation, slot-agnostic) has not been tested yet; the four-query version was my shortcut, not his suggestion.",
  ], { x: 0.6, y: 5.55, w: 12.1, h: 1.4, fontSize: 10 });
  footer(s);
}
// ---------- 15 main table ----------
{
  const s = pres.addSlide(); n++;
  title(s, "Main table: 560 questions, all arms", "Corpus v2.4, store v45 (derived store v45k for the middle rungs) unless noted; reader haiku-4.5, judge Opus 5; $ at haiku list price $1/M in, $5/M out; the v52f row uses the tuned Stage 1 and is reported as an ablation");
  const rows = [["Arm", "Accuracy", "\u0394 vs direct", "In tok / q", "Out tok / q", "$ / q", "Median latency"],
    ["Direct read (top-10 retrieval)", "47.32", "\u2014", "878", "86", "$0.00131", "1.55 s"], ["1 Select", "66.25", "+18.9", "2,169", "108", "$0.00271", "5.50 s"], ["2 Certify", "66.79", "+19.5", "2,346", "112", "$0.00291", "5.46 s"], ["3 Compile", "79.46", "+32.1", "2,268", "98", "$0.00276", "5.28 s"],
    [{ text: "4 Ledger + protocol (QVF)", options: { bold: true } }, { text: "89.29", options: { bold: true } }, { text: "+42.0", options: { bold: true } }, "2,937", "476", "$0.00532", "4.84 s"],
    ["4 QVF, frozen Sonnet-built store v48f (batch 46d, mean of 2 runs)", "90.00", "+42.7", "2,753", "485", "$0.00518", "5.77 s"],
    ["4 QVF, all four fixes incl. tuned Stage 1 (v52f, batch 49, mean of 2 runs)", "95.09", "+47.8", "968", "462", "$0.00328", "5.01 s"],
    ["QVF, owner-gate store", "86.25", "+38.9", "2,106", "464", "$0.00443", "4.77 s"], ["Full text + protocol", "86.61", "+39.3", "13,921", "454", "$0.01619", "7.84 s"], ["Full text, plain (archived wording)", "54.46", "+7.1", "13,672", "136", "$0.01435", "5.46 s"], ["Unstructured summary", "57.68", "+10.4", "2,451", "91", "$0.00291", "4.88 s"]];
  table(s, rows, { x: 0.6, y: 1.6, w: 12.1, colW: [3.3, 1.3, 1.4, 1.5, 1.5, 1.4, 1.7], fontSize: 10, rowH: 0.34 });
  s.addText("Per question type (direct \u2192 QVF): change_count 35.4 \u2192 85.4, count_before 42.4 \u2192 86.8, longest_tenure 29.7 \u2192 90.6, first_vs_last 79.9 \u2192 94.4. Counting types are where the direct reader fails and where the ledger pays; first_vs_last is answerable by retrieval alone. Three validity types (v2.0 archive): current value +8.3, point-in-time +59.0, historical aggregation +34.0.", { x: 0.6, y: 5.85, w: 12.1, h: 1.1, fontFace: BFONT, fontSize: 10.5, color: INK, margin: 0 });
  footer(s);
}
// ---------- 19 WikiState at a glance ----------
{
  const s = pres.addSlide(); n++;
  title(s, "WikiState v2.5 at a glance \u2014 and what only it tests", "Scale on the left; the distinctiveness matrix on the right (attributes verified from full-text reads of each benchmark)");
  table(s, [["Scale (v2.5)", ""], ["State chains (persona \u00d7 slot)", "144: employer 51 \u00b7 position 44 \u00b7 team 38 \u00b7 residence 11"], ["Gold state rows", "542 (3\u20138 per chain, median 3; 25 chains with \u2265 5 states)"], ["Sessions / turns", "4,854 sessions (542 chain + 4,312 filler), 23,696 turns; \u2248 14K tokens per store"], ["Time span", "chains span 1\u201390 years (median 10.2); dates 1423\u20132024"], ["Questions", "560 aggregation (change_count 144 \u00b7 count_before 144 \u00b7 first_vs_last 144 \u00b7 longest_tenure 128) + 576 validity probes"], ["Holdout", "80 chains / 320 q, zero QID overlap (two independent draws)"], ["Scale track", "30 stores of \u2248 104K tokens, 120 q"], ["Verification", "542/542 anchors verbatim (machine); 2 \u00d7 149-item machine reviews 0/144 flags; human \u03b1 0.45 (0.30 excl. planted)"]], { x: 0.6, y: 1.55, w: 5.3, colW: [1.6, 3.7], fontSize: 9.5, rowH: 0.5 });
  table(s, [["Benchmark", "Real KB chain", "Dates", "\u2265 3 states / slot", "Point-in-time Q", "Chain aggregation Q", "Superseded value = gold"], [{ text: "WikiState v2.5", options: { bold: true } }, "\u2713", "\u2713", "\u2713", "\u2713", "\u2713", "\u2713"], ["StateMemBench 2608.19652", "\u2717 (program)", "\u2717", "partial", "\u2717", "\u2717", "\u2717 (drift = error)"], ["MemTrace 2606.17328", "\u2717", "\u2717", "partial", "\u2717", "\u2717", "\u2713 (historical Q)"], ["Ground Truth First 2607.21962", "\u2717 (script)", "\u2713", "partial", "partial", "\u2717", "partial"], ["MemOps 2607.12893", "\u2717", "\u2717", "partial", "\u2717", "\u2717", "partial"], ["Memora / HorizonBench / DynamicMem", "\u2717", "\u2713", "\u2713 / \u2717 / partial", "\u2717", "\u2717", "\u2717 (old = error)"], ["TimelineQA 2023", "\u2717 (templates)", "\u2713", "partial", "partial", "\u2713", "\u2717 (no supersession)"], ["STALE / MemConflict", "\u2717", "partial", "\u2717", "\u2717 / partial", "\u2717", "\u2717 / partial"], ["LongMemEval / LoCoMo", "\u2717", "\u2713", "\u2717", "\u2717", "\u2717", "\u2717"], ["Temporal Wiki / ChronoScope", "snapshots / parametric", "\u2713", "partial / \u2717", "\u2713", "\u2717", "partial / \u2717"]], { x: 6.1, y: 1.55, w: 6.6, colW: [2.2, 0.85, 0.55, 0.8, 0.7, 0.75, 0.75], fontSize: 8.5, rowH: 0.42 });
  s.addText("Only WikiState has all three of point-in-time questions, chain-aggregation questions, and a superseded value as the gold answer \u2014 together these define query-conditioned validity. Boundaries stated with it: LLM-rendered dialogue, assistant turns stored truncated, filler anachronisms (1,014, not touching gold), residence under-represented (11 chains), main field reused during development (holdout matches within 0.07 pp).", { x: 0.6, y: 6.15, w: 12.1, h: 0.85, fontFace: BFONT, fontSize: 10, color: INK, margin: 0 });
  footer(s);
}
// ---------- 20 WikiState: reviewers, fixes, human evaluation ----------
{
  const s = pres.addSlide(); n++;
  title(s, "WikiState: reviewer findings, fixes, and evaluation status", "Human review rounds on the display version; machine review of every release; latest version now under human evaluation");
  table(s, [
    ["Round", "Who", "Coverage", "Found", "What changed"],
    ["Round 1 (v2.0 display)", "author (all 149) \u00b7 senior1 (a reviewer I recruited, 85) \u00b7 senior2 (a reviewer recruited by my lab senior, 84)", "149 items = 144 chains + 5 planted errors", "senior2 7 errors / 1 unsure; senior1 5 errors; agreement \u03b1 0.45 (0.30 excl. planted); error rate est. 6\u20137%", "v2.1\u2013v2.4: four cleaning passes (247 contaminating sentences, \u22120.42%), gold-contamination erratum, 16 near-tie questions removed"],
    ["Machine review (v2.4, v2.5)", "fresh Opus 5 agents driving the review page", "149 each", "5/5 planted errors caught, 0/144 real chains flagged (Wilson upper 2.6%)", "v2.5: full-read scan of 144 chains (1,390 flags), independent adjudication (49 confirmed), surgical deletion under two gates; tenure convention written into datasheet and review page"],
    ["Now", "author on v2.5; senior reviewers next", "149", "in progress", "v2.5 numbers replace the main table once agreement is computed"],
  ], { x: 0.6, y: 1.6, w: 12.1, colW: [1.8, 3.0, 1.8, 2.7, 2.8], fontSize: 10, rowH: 0.75 });
  bullets(s, [
    "Cleaning taxes the retrieval arm less than the structured arms, so every pass widened the gap (v2.0 +34.0 \u2192 v2.4 +41.5); v2.2 / v2.3 / v2.4 / v2.5 scores are statistically indistinguishable \u2014 cleaning has saturated.",
    "Rule adopted: a release is handed to human reviewers only after machine review passes with zero real-chain flags; a failed review triggers a fix and a new version.",
    "The full dataset browser (chains, questions, raw sessions with highlighted anchors) is in the talk folder.",
  ], { x: 0.6, y: 5.0, w: 12.1, h: 1.9, fontSize: 11 });
  footer(s);
}
// ---------- 15 feedback received ----------
{
  const s = pres.addSlide(); n++;
  title(s, "Feedback received (a senior labmate’s code review, Notion) and what changed", "He read the 27 Aug main branch; verified against current code and results; four items changed, two intentionally not");
  table(s, [
    ["His point", "Verdict after checking", "What changed"],
    ["claim, value_tags, implies_stale_slots, validity species are unused or guesses", "correct for the ledger path (never read; 42% of card characters); the species prompt belongs to the engine path, not the card builder", "slim contract flag; lossless on WikiState but −13 pp on STALE even with cessation / condition restored → WikiState-specific option, not the default"],
    ["owner \u2248 entity, meaningless", "based on old code: main stores had no owner field; it matters only under third-person injection (recovers 92% of an 18.4 pp drop)", "kept as a default-off flag"],
    ["One LLM call decides six things; long context misses states; propose two-stage extraction", "misses measured (haiku 71/542 rows, Sonnet 21 \u2192 14); 14K stores are single-batch, so length is not the cause; regex localiser recalls 12.5\u201365%", "embedding Stage 1 built; lossless on WikiState, tuned elsewhere \u2192 default off"],
    ["Verifier checks substring, not entailment (\u2018considered joining Google\u2019)", "correct; it is exactly the batch 38c finding; keyword rules had two false drops", "entailment verifier with his {entailed, type} output; beats keyword rules with zero gold loss"],
    ["Slot canonicalisation only in the prompt; value normalisation too weak", "post-processing alias table already existed; prompt-side canonicalisation did not raise scores; value variants inflate change counts in 6\u201316% of transitions", "closed-set rule + value normaliser; harmless at reader level"],
    ["Relation edges dangle across batches \u2192 updates lost", "misread: the ledger path computes transitions from dates, not relation labels; 14K stores are single-batch", "relation fields dropped with the slim contract"],
  ], { x: 0.6, y: 1.55, w: 12.1, colW: [3.4, 4.6, 4.1], fontSize: 9.5, rowH: 0.7 });
  s.addText("Net effect of the review: +5 pp for the weak reader on 144 chains, \u221263% read tokens, \u221290% build tokens where Stage 1 applies, and a sharper statement of what is general.", { x: 0.6, y: 6.5, w: 12.1, h: 0.45, fontFace: BFONT, fontSize: 10.5, color: INK, margin: 0 });
  footer(s);
}
// ---------- 16 boundaries & next steps ----------
{
  const s = pres.addSlide(); n++;
  title(s, "Honest boundaries and next steps");
  s.addText("Boundaries (said up front)", { x: 0.6, y: 1.5, w: 6, h: 0.4, fontFace: HFONT, fontSize: 18, bold: true, color: NAVY, margin: 0 });
  bullets(s, [
    "Scope is three conditions: non-frontier reader, or store beyond the context window, or cost-bound. A strong reader on a 14K store reads the whole memory as well or better (97.1); the ledger is then the cheaper, auditable layer.",
    "About 88% of the ledger\u2019s gain over plain full text is layout + trajectory protocol; write-time cards earn their place through coverage, de-duplication, auditability and cost.",
    "The slim contract, the tuned Stage 1 and the store-wide entailment filter are reported only as WikiState-specific ablations; the method section gets the closed-set slot rule, value normalisation and the chain-slot entailment filter, which held on all three arenas.",
    "Synthetic dialogue; assistant turns stored truncated; human agreement fair (\u03b1 0.45 / 0.30); v2.5 human review in progress; extraction is nondeterministic; reader run-to-run sd \u2264 1.6 pp.",
  ], { x: 0.6, y: 1.95, w: 6.0, h: 4.9, fontSize: 11.5 });
  s.addText("Next steps", { x: 7.0, y: 1.5, w: 5.7, h: 0.4, fontFace: HFONT, fontSize: 18, bold: true, color: NAVY, margin: 0 });
  bullets(s, [
    "Ablate why the slim contract loses 13 pp on STALE (claim, relation fields, closed-set slots: ~$11 each); rebuild the 144-chain main store with the configuration that held on all three arenas and re-run the main table.",
    "Test the senior labmate\u2019s slot-agnostic Stage 1 (cheap model judging \u2018is this turn a state declaration?\u2019) on WikiState and STALE (~$4).",
    "Finish the v2.5 human evaluation (author, then the two senior reviewers) and report agreement against the machine review.",
    "Paper: \u00a71 claim restated as \u2018validity = f(memory \u00d7 query)\u2019; \u00a72 ancestors (TAC-KBP temporal slot filling) and the 22 newly read neighbours; method section = general configuration; \u00a78 limitations = three conditions + what was tuned.",
  ], { x: 7.0, y: 1.95, w: 5.7, h: 4.9, fontSize: 11.5 });
  footer(s);
}
// ---------- backup divider ----------
{
  const s = pres.addSlide(); n++;
  s.background = { color: NAVY };
  s.addText("Backup", { x: 0.8, y: 2.6, w: 11.7, h: 1.0, fontFace: HFONT, fontSize: 40, bold: true, color: WHITE, margin: 0 });
  s.addText("Ladder \u00b7 exclusion tests \u00b7 when it does not help \u00b7 realistic baseline \u00b7 other retrieval, scale, competitors \u00b7 cost \u00b7 cross-tests", { x: 0.8, y: 3.7, w: 11.5, h: 0.6, fontFace: BFONT, fontSize: 16, color: "CADCFC", margin: 0 });
}
// ---------- 11 exclusion tests ----------
{
  const s = pres.addSlide(); n++;
  title(s, "Mechanism evidence: exclusion tests", "Same reader and judge; v2.0 archive unless noted \u2014 each row rules out one alternative explanation");
  table(s, [
    ["Test", "Result", "Rules out"],
    ["Perfect gold-sentence evidence fed to the direct reader", "76.7 vs ledger 82.6 (p = 8e-11)", "\u201cit is just a retrieval gap\u201d"],
    ["Remove all filler sessions", "direct +22.5, full text +20.0, ledger +1.7", "\u2014 (quantifies the distractor share: 44%)"],
    ["Unstructured summary at equal token budget", "52.8 = full text 52.3 (p = 0.89); summary \u2192 bare ledger +22.6 (p = 2e-21)", "\u201cit is just shorter\u201d"],
    ["Remove verbatim anchors", "77.3 vs 82.6, \u22125.4 (p = 1e-4)", "\u201canchors are decoration\u201d"],
    ["Build the ledger at read time from the top-10 turns", "60.2; 85.3 with full coverage, 15.9 with one session missing", "\u201cwrite time does not matter\u201d"],
    ["Oracle cards / oracle evidence", "94.97 / 76.74", "\u2014 (write-side headroom +4.5; residual 55 errors = write 38 \u00b7 read 13 \u00b7 gold+judge 4)"],
    ["Second-family judge (gpt-5-mini) re-judges 2,304 rows", "agreement 89\u201397%, \u03ba 0.78\u20130.91; ledger \u2212 direct widens to +48.6", "\u201cthe judge favours QVF\u201d"],
    ["80 holdout chains, zero QID overlap (two independent draws)", "+40.0 and +43.1 on the two halves; pooled +41.56 vs main field +41.49", "\u201cover-fitted to the development chains\u201d"],
    ["Nine retrieval variants incl. top-50 (99.8% anchor coverage) and LLM rerank", "best 62.9 vs ledger 91.4 (p = 5e-10)", "\u201ca better retriever would do it\u201d"],
    ["Render-matched controls (same layout + protocol, mechanism off)", "14K: cards-only 85.0, raw quotes 85.4, ledger 89.3; 104K: cards-only 70.0, raw quotes 55.8, projection 61.7", "\u2014 (limits the claim: ~88% of the gain is layout + protocol; cards add coverage, de-dup, auditability)"],
  ], { x: 0.6, y: 1.55, w: 12.1, colW: [3.9, 4.4, 3.8], fontSize: 10, rowH: 0.46 });
  footer(s);
}
// ---------- 12 when it does not help ----------
{
  const s = pres.addSlide(); n++;
  title(s, "When it does not help \u2014 the same mechanism, read the other way", "140 questions / 36 chains unless noted; \u2018full context\u2019 = the whole raw memory in the prompt, plain system prompt");
  table(s, [
    ["Setting", "Full context", "Best retrieval", "QVF ledger", "Reading"],
    ["14K store \u00b7 weak reader (haiku-4.5)", "70.0 (13.6K tok)", "62.9 (top-50)", "91.4 (2.8K tok)", "+21.4 vs full context, p = 5e-6; 1/2.8 the cost"],
    ["14K store \u00b7 strong reader (Sonnet 5)", "97.1 (18.5K tok)", "70.7 (top-10)", "95.0 (3.4K tok, filtered Sonnet-built store)", "\u22122.1, p = 0.51: the reader does the four sub-tasks itself; 1/5.4 the tokens remain the edge"],
    ["104K store \u00b7 weak reader (30 stores / 120 q)", "7.5 (103.8K tok)", "38.3 (top-100, 8.9K tok)", "61.7 projection (8.8K)", "+23.3 vs budget-matched top-100, p = 2e-4; retrieval collapses first (top-10 reaches 38.8% of anchors)"],
    ["104K store \u00b7 strong reader (Sonnet 5)", "65.8 (142K tok; 120 q, capped rows rerun at 8000)", "67.5 (top-100, 11.6K tok)", "74.2 projection (11.5K)", "+8.4 vs full context, per-question p = 0.02\u20130.19, store-level CI crosses zero; projection costs 1/9"],
  ], { x: 0.6, y: 1.55, w: 12.1, colW: [3.0, 1.9, 2.0, 2.4, 2.8], fontSize: 9.5, rowH: 0.56 });
  bullets(s, [
    "Five readers on the same 140 questions: the ledger beats top-10 retrieval by \u2265 15 pp for every reader; against full context it wins for haiku (+23.6) and a local qwen3:14b (+17.9), ties for Gemini 3.6 Flash (\u22120.7) and for gpt-5-mini after fixing its output cap (\u22124.3, n.s.). The stronger the reader on full context, the smaller the ledger's edge. Full text + protocol on Sonnet 5: 96.4 = plain full text 97.1 = ledger 95.0.",
    "Write side: Sonnet-built cards give 133/133 gold rows but 92.9 / 92.1; the assertion-type filter lifts to 93.6 / 95.0; a second extraction pass reaches 140/140 gold rows. Scaled to all 144 chains (batch 46d) the frozen configuration cuts missing gold rows 71 → 14 and lifts the compiled ceiling 85.9 → 92.5, yet the haiku reader scores 89.8 / 90.2 vs 89.3 on the haiku-built store (p = 0.80): ledger content is not this reader's bottleneck. Extraction is nondeterministic (two passes overlap 2\u201333% of cards) and repeat runs of six arms show run-to-run sd \u2264 1.6 pp (batch 46c).",
    "Claim, restated: the ledger is necessary when the reader is not frontier-class, or the store exceeds the context window, or cost is bound \u2014 any one of the three. Otherwise it is a cheaper, auditable layer, not a more accurate one.",
  ], { x: 0.6, y: 5.0, w: 12.1, h: 2.0, fontSize: 10.5 });
  footer(s);
}
// ---------- 13 realistic baseline ----------
{
  const s = pres.addSlide(); n++;
  title(s, "Realistic baseline: whole memory in the prompt", "140 questions / 36 chains, corpus v2.4; plain system prompt; judge Opus 5; $ at list prices (haiku $1/$5, Sonnet 5 $2/$10 per M)");
  table(s, [
    ["Arm", "haiku-4.5", "Sonnet 5", "In tok / q (haiku / Sonnet)", "$ / q (Sonnet)"],
    ["Whole memory in prompt, plain call", "70.0", "97.1 (max_tokens 4000; 87.9 at 800 because thinking shares the cap)", "13.6K / 18.5K", "$0.042"],
    ["Archived plain full text (other user-prompt wording, same bytes)", "58.6", "84.8", "13.6K / 18.6K", "$0.039"],
    ["Full text + trajectory protocol", "92.9", "96.4", "13.8K / 18.6K", "$0.041"],
    ["Top-10 retrieval (direct)", "50.7", "70.7", "0.9K / 1.1K", "$0.005"],
    [{ text: "QVF ledger (store v45)", options: { bold: true } }, { text: "91.4", options: { bold: true } }, { text: "90.7", options: { bold: true } }, "2.8K / 3.7K", "$0.015"],
    ["QVF ledger, Sonnet-built cards (v47s)", "92.9", "92.1", "2.6K / 3.5K", "$0.015"],
    [{ text: "QVF ledger, Sonnet-built + assertion-type filter (v47skf)", options: { bold: true } }, { text: "93.6", options: { bold: true } }, { text: "95.0", options: { bold: true } }, "2.5K / 3.4K", "$0.014"],
    ["QVF ledger, + second extraction pass, union (v47skf2; ledger = gold 140/140)", "97.1", "93.6", "2.6K / 3.5K", "$0.014"],
  ], { x: 0.6, y: 1.6, w: 12.1, colW: [4.3, 1.2, 3.6, 1.9, 1.1], fontSize: 9.5, rowH: 0.38 });
  bullets(s, [
    "Prompt wording alone moves a full-context baseline by +11\u201312 pp on identical bytes; the main table's first row must be the plainest full-context call.",
    "Same weak reader: ledger +21.4 over full context (p = 5e-6) at 1/2.8 the input tokens. Same strong reader: with Sonnet-built cards and the assertion-type filter the gap is \u22122.1 (p = 0.51) at 1/5.4 the input tokens.",
    "Using top-10 retrieval as the only baseline inflates any memory mechanism by 19\u201337 pp; the +42 headline is reported next to +21 (weak reader) and \u22122 (strong reader), never alone. Run-to-run sd across six arms is \u2264 1.6 pp (batch 46c), so differences under ~3 pp are not claimed.",
  ], { x: 0.6, y: 5.1, w: 12.1, h: 1.85, fontSize: 10.5 });
  footer(s);
}
// ---------- 14 other RAG, scale, competitors ----------
{
  const s = pres.addSlide(); n++;
  title(s, "Other retrieval strategies, scale, and 15 competing systems", "haiku-4.5 reader, same judge; 14K stores (140 q), 104K-token stores (120 q), v2.5 sample (15 chains / 58 q)");
  table(s, [["14K store: retrieval variant", "acc", "anchor cov."], ["QVF ledger", "91.4", "\u2014"], ["dense top-50", "62.9", "99.8%"], ["LLM rerank 30\u219210", "60.7", "96.9%"], ["dense top-30", "57.9", "98.1%"], ["top-10 / as-of filter", "50.7", "86.7%"], ["session top-5 / hybrid RRF / MMR", "47.1 / 41.4 / 40.7", "85 / 78 / 78%"], ["query rewrite / recency prior", "36.4 / 10.7", "64 / 53%"]], { x: 0.6, y: 1.55, w: 4.1, colW: [2.4, 0.9, 0.8], fontSize: 9.5, rowH: 0.34 });
  table(s, [["104K store: arm", "acc haiku / Sonnet 5", "in tok"], ["QVF slot projection", "61.7 / 74.2", "8.8K / 11.5K"], ["QVF full ledger", "54.2 / 73.3", "20.9K / 27.2K"], ["dense top-100", "38.3 / 67.5", "8.9K / 11.6K"], ["dense top-50 / rerank", "29.2 / 26.7", "4.5K / 1K+2.9K"], ["top-10 direct", "16.7", "1.0K"], ["full text (plain)", "7.5 / 54.9*", "103.8K / 142K"]], { x: 4.9, y: 1.55, w: 3.6, colW: [1.7, 1.1, 0.8], fontSize: 9.5, rowH: 0.34 });
  table(s, [["v2.5 sample: system", "acc"], ["QVF ledger (v2.5 store / v2.4 store)", "98.3 / 89.7"], ["QVF compile arm", "75.9"], ["Whole memory in prompt (haiku)", "63.8"], ["timeline baseline", "56.9"], ["lgstore / HippoRAG 2 / txtai / cognee", "46.6 / 46.5 / 44.8 / 44.8"], ["Letta-FS agent (30K tok/q) / A-MEM", "43.1 / 39.7"], ["top-10 direct / summary RAG", "37.9 / 36.2"], ["LangMem / TRACE / MemOS", "32.8 / 31.0 / 31.0"], ["stamped ledger / obs-RAG / BM25 / Mem0", "13.8 / 13.8 / 12.1 / 10.3"]], { x: 8.7, y: 1.55, w: 4.0, colW: [2.9, 1.1], fontSize: 9.5, rowH: 0.34 });
  bullets(s, [
    "14K: recall is not the bottleneck \u2014 top-50 reaches 99.8% of gold anchors and still fails 37%; the best variant is 28.6 pp below the ledger (p = 5e-10). LLM rerank costs more per question than the ledger and is 30.7 pp worse.",
    "104K: retrieval collapses first (top-10 sees 38.8% of anchors); at equal token budget the projection beats top-100 by 23.3 pp with haiku (p = 2e-4) and by 6.7 pp with Sonnet 5 (n.s.); full text is unusable for haiku and reaches only 54.9 for Sonnet 5 (*n = 82).",
    "Competitors (each independently re-scored and diffed for protocol parity): every system scores below the plain full-context call on the same 58 questions; middle-of-table CIs overlap, no ranking claimed there.",
  ], { x: 0.6, y: 5.2, w: 12.1, h: 1.8, fontSize: 10.5 });
  footer(s);
}
// ---------- 16 cost & latency ----------
{
  const s = pres.addSlide(); n++;
  title(s, "Cost and latency", "One axis per chart; 560 questions, haiku-4.5");
  const lab = ["Direct", "3 Compile", "4 QVF ledger", "Full text + protocol", "Full text plain"];
  s.addChart(pres.ChartType.bar, [{ name: "Input tokens per question", labels: lab, values: [878, 2268, 2937, 13921, 13672] }], { x: 0.6, y: 1.55, w: 6.0, h: 4.6, barDir: "col", chartColors: [NAVY], showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 11, dataLabelFormatCode: "#,##0", valAxisMinVal: 0, valAxisMaxVal: 16000, valAxisMajorUnit: 4000, valAxisLabelFontSize: 10, valAxisLabelColor: MUTED, valGridLine: { color: "E5E7EB", size: 0.5 }, catAxisLabelFontSize: 10, catGridLine: { style: "none" }, showLegend: false, showTitle: true, title: "Input tokens per question", titleFontSize: 13, titleColor: INK, barGapWidthPct: 60 });
  s.addChart(pres.ChartType.bar, [{ name: "Median latency (s)", labels: lab, values: [1.55, 5.28, 4.84, 7.84, 5.46] }], { x: 6.9, y: 1.55, w: 5.8, h: 4.6, barDir: "col", chartColors: [GOOD], showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 11, dataLabelFormatCode: "0.0", valAxisMinVal: 0, valAxisMaxVal: 10, valAxisMajorUnit: 2, valAxisLabelFontSize: 10, valAxisLabelColor: MUTED, valGridLine: { color: "E5E7EB", size: 0.5 }, catAxisLabelFontSize: 10, catGridLine: { style: "none" }, showLegend: false, showTitle: true, title: "Median latency per question (s)", titleFontSize: 13, titleColor: INK, barGapWidthPct: 60 });
  s.addText("The ledger reads 2.9K tokens where the protocol on full text reads 13.9K (1/4.7) at similar accuracy; on a 104K store the projection reads 8.8K vs 103.8K (1/12) and full text collapses. Against cheaper reasoning readers the cost edge is 1.4\u20132.6\u00d7; the earlier \u20185\u00d7\u2019 claim is withdrawn.", { x: 0.6, y: 6.2, w: 12.1, h: 0.75, fontFace: BFONT, fontSize: 10.5, color: INK, margin: 0 });
  footer(s);
}
// ---------- 17 cross-test 1 ----------
{
  const s = pres.addSlide(); n++;
  title(s, "Cross-test 1 \u00b7 QVF on other benchmarks", "Same reader haiku-4.5; direct = OpenAI embedding top-10; ledger arm vs direct");
  table(s, [["Benchmark", "Type", "Ledger vs direct", "Verdict"], ["STALE (120, fresh)", "state supersession", "61.7 vs 46.7, +15.0 (p = 0.008, 3 judges agree)", "positive"], ["LongMemEval temporal reasoning (133)", "temporal reasoning", "60.2 vs 47.4, +12.8", "positive"], ["LongMemEval knowledge update (78)", "knowledge update", "80.8 vs 78.2, +2.6", "tie"], ["LongMemEval multi-session (132)", "cross-session", "59.1 vs 61.4, \u22122.3", "tie (powered null)"], ["LongMemEval single-user (68) / single-assistant (45)", "verbatim facts / assistant content", "72.1 vs 97.1, \u221225.0 \u00b7 0 vs 100", "negative (card schema extracts user entities only)"], ["LongMemEval preference (28)", "preferences", "42.9 vs 71.4, \u221228.6", "negative"], ["Temporal Wiki (300)", "yearly snapshots", "82.3 vs 86.7, \u22124.3", "negative (card builder dates by narrated year)"], ["AMemGym (600) / PersonaMem v2 (600)", "wording options / retractions", "\u22123.3 to \u22124.7 \u00b7 \u22127.2 (who = others +14.0)", "negative"], ["MemConflict / MemOps / ElephantBench-OB", "conflict / ops / multi-ledger retention", "tie \u00b7 +4.2 n.s. \u00b7 98.3 (= full text 100)", "tie"]], { x: 0.6, y: 1.6, w: 12.1, colW: [3.6, 2.4, 3.6, 2.5], fontSize: 10.5, rowH: 0.45 });
  s.addText("The ledger wins where the question needs cross-date state-transition reasoning and memories are dated statements; it loses on verbatim facts, preferences and wording, assistant-side content, and snapshot corpora. This is the claim's scope, stated in \u00a71 and limitations.", { x: 0.6, y: 6.1, w: 12.1, h: 0.85, fontFace: BFONT, fontSize: 10.5, color: INK, margin: 0 });
  footer(s);
}
// ---------- 18 cross-test 2 ----------
{
  const s = pres.addSlide(); n++;
  title(s, "Cross-test 2 \u00b7 Other memory systems on WikiState", "60-question v1 calibration set; same reader and judge; official packages where available (18 run, 2 blocked by Docker)");
  table(s, [["System", "Acc", "Note"], [{ text: "QVF ledger / compile / select", options: { bold: true } }, { text: "86.7 / 83.3 / 70.0", options: { bold: true } }, "three tiers of this method"], ["timeline (self-built timeline baseline)", "63.3", "strongest non-QVF"], ["Letta-style file-system agent", "56.7", "$0.021 per question, 21\u00d7 cost"], ["HippoRAG 2 (ICML 2025, official)", "55.0", "chain-state recall@10 0.915 \u2014 retrieval wins, adjudication loses"], ["lgstore / txtai / direct read", "55.0 / 53.3 / 51.7", ""], ["Summary RAG / cognee / MemOS", "46.7 / 46.7 / 45.0", "MemOS expands 4.1 nodes per session instead of consolidating"], ["A-MEM / LangMem", "43.3 / 40.0", ""], ["TRACE (LoCoMo config / factory)", "30.0 / 16.7", "0 supersession edges by default; full 576 q: 16.0"], ["Mem0 / BM25 / Graphiti / LightRAG", "26.7 / 13.3 / 3.3 / 1.7", "Mem0 131 s per question to build"]], { x: 0.6, y: 1.6, w: 12.1, colW: [4.2, 2.4, 5.5], fontSize: 10.5, rowH: 0.42 });
  s.addText("Shared failure mode: retrieval wins, adjudication loses. Competitors fix validity as a one-time scalar at write time (Zep / TRACE / MemStrata) or adjudicate at read time toward the current value only (EvoMem, APEX-MEM, StateAuditor, StateMemWrapper); none lets a superseded value be the correct answer. Middle of the table: CIs overlap, no ranking claimed.", { x: 0.6, y: 6.05, w: 12.1, h: 0.9, fontFace: BFONT, fontSize: 10.5, color: INK, margin: 0 });
  footer(s);
}
const out = process.argv[2] || "D:/ZZL_cluade/results/talk_qvf_wikistate_20260905.pptx";
pres.writeFile({ fileName: out }).then(f => console.log("written", f, "slides", n));
