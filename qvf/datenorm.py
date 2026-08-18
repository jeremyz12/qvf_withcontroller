# -*- coding: utf-8 -*-
"""日期咽喉点规范化(08-18 新增,由 QVF_DATE_STRICT 门控,默认关)。

# 为什么是"咽喉点校验"而不是"重写比较"

08-18 的去特调诊断在全部 30 个 `results/wt_cards*` 库、40,088 条带日期记录
上复算,推翻了此前"裸字符串比较是缺陷"的判断:

- 在实际出现的 **10,422 种合规日期串**上,字符串序与日历序 **54,303,831 对
  中 0 对不一致** —— 即**只要输入合规,现行字符串比较就是正确的**。
- 此前记载的"306 条未补零(如 `2019-3`)"**不可复现**:`YYYY-M` / `YYYY-MM-D`
  形态实测 **0 条**。

真正的缺陷是 `_rec_date()` **不校验它返回的东西是不是日期**,于是把
`April` / `02-10` / `1920s` / `2025-02-20 to 2025-02-25` 这类值透传下去。
后果(实测 `wt_cards_v42`):**216 条"幽灵记录"占着链位但对 ASOF/WINDOW
隐形**(`_chain()` 按真值入链,`WINDOW`/`ASOF` 按 `_pdate is not None` 可见,
两个判据不同),其中 **121 条在链尾**,直接污染 `current = PICK(C,-1)` ——
实测 `current` 会向读者输出 `since 'March 19'`、
`since '2025-10-22 and 2025-10-29'` 这类系统自己解析不了的串。

因此本模块**只做一件事**:把日期串规范成合规形态(四位年、补零的
`YYYY` / `YYYY-MM` / `YYYY-MM-DD`),或明确判为不可解析。**下游所有字符串
比较一字不改** —— 诊断已证明它们在合规输入上正确。

# 真实世界优先(而非数据集优先)

实测违约形态按频次:`April`(61)、`March`(38)、`04-15`(33)、`January`(33)、
`1920s`(31)、`02-10`(56)、`06`(23)。**这些正是真人说话的样子**,而 WikiState
由 Wikidata 限定符生成、产出干净的 `YYYY-MM-DD`,**把这个问题藏了起来**。

更根本:建卡契约 Rule 4 写的是 "copy the date the TEXT states",所以
**完全不解析相对时间表达**("上周五""两年前""昨天")。这是真实部署中
必然遇到、而本项目基准从不考察的缺口;同期工作 MAGMA(ACL 2026 主会)
有专门的 temporal parser 处理它,而 APEX-MEM 附录 E 案例 3 记录了
A-MEM 直接抄会话戳、MemoryOS 幻觉出日期的失败。故本模块一并处理。

# 语义决定(预注册于实施之前,不得因数字不好看而改)

1. **偏粒度不折叠成单日**:`YYYY` 保持 `YYYY`,不补成 `YYYY-01-01`。理由:
   `stated_date="1976"` 的语义是"文本说始于 1976 年",真实日期在年内未知;
   补成某一天等于编造原文没给的信息。合规的偏粒度串本来就可正确比较。
2. **区间/多日期串取最早那个**:`2025-02-20 to 2025-02-25` → `2025-02-20`。
   理由:状态自区间起点开始生效。
3. **裸月份按"base 之前最近的那一个"解**:`April` + base `2025-07-01`
   → `2025-04`。理由:会话中说"四月"默认指刚过去的那个四月。
4. **年份段非四位一律拒绝**(`2` / `22`):世纪不可知,猜测会污染链序。
   `001898` 去前导零后为四位,接受。
5. **年代(`1920s`)拒绝**:它是十年区间,规范成 `1920` 会把区间伪装成点。
6. 不可解析 → 返回 None,由调用方回退会话日期并计数,**绝不透传**。
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Optional, Tuple

_MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}
_WEEKDAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
             "friday": 4, "saturday": 5, "sunday": 6}

# 合规文法 G:四位年,可选补零月、可选补零日
_OK = re.compile(r"^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?$")
_SPLIT = re.compile(r"\s+(?:to|and|through|until|till)\s+|[,;]|\s*[–—~]\s*",
                    re.IGNORECASE)


def _is_compliant(s: str) -> bool:
    m = _OK.match(s)
    if not m:
        return False
    # 年 0000 不是有效年份(parse_partial_date 亦返 None);实测 wt_cards_v42
    # 有 4 条 `0000-02-20` / `0000-06` 形态,若放行会造出一个下游解析不了的
    # "合规"串——即本模块要消灭的那类幽灵。
    if int(m.group(1)) < 1:
        return False
    mo, d = m.group(2), m.group(3)
    if mo is not None and not (1 <= int(mo) <= 12):
        return False
    if d is not None and not (1 <= int(d) <= 31):
        return False
    return True


def _parse_base(base: Optional[str]) -> Optional[date]:
    if not base:
        return None
    m = _OK.match(str(base).strip())
    if not m:
        return None
    y = int(m.group(1))
    mo = int(m.group(2) or 1)
    d = int(m.group(3) or 1)
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def _fmt(y: int, mo: Optional[int] = None, d: Optional[int] = None) -> str:
    if mo is None:
        return f"{y:04d}"
    if d is None:
        return f"{y:04d}-{mo:02d}"
    return f"{y:04d}-{mo:02d}-{d:02d}"


def _relative(s: str, b: date) -> Optional[str]:
    """相对时间表达 → 绝对日期(需要 base)。覆盖真实对话里的常见形态。"""
    t = s.lower().strip()
    if t in ("today", "now", "just now", "今天", "现在"):
        return _fmt(b.year, b.month, b.day)
    if t in ("yesterday", "昨天"):
        r = b - timedelta(days=1)
        return _fmt(r.year, r.month, r.day)
    if t in ("the day before yesterday", "前天"):
        r = b - timedelta(days=2)
        return _fmt(r.year, r.month, r.day)
    if t in ("tomorrow", "明天"):
        r = b + timedelta(days=1)
        return _fmt(r.year, r.month, r.day)
    # last/this <weekday>
    m = re.match(r"^(last|this|past)\s+(\w+)$", t)
    if m and m.group(2) in _WEEKDAYS:
        delta = (b.weekday() - _WEEKDAYS[m.group(2)]) % 7 or 7
        r = b - timedelta(days=delta)
        return _fmt(r.year, r.month, r.day)
    # N <unit> ago
    m = re.match(r"^(?:about\s+|around\s+)?(\d+|a|an|one|two|three|four|five|"
                 r"six|seven|eight|nine|ten)\s+(day|week|month|year)s?\s+ago$", t)
    if m:
        w = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4,
             "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
        n = int(m.group(1)) if m.group(1).isdigit() else w[m.group(1)]
        u = m.group(2)
        if u == "day":
            r = b - timedelta(days=n)
            return _fmt(r.year, r.month, r.day)
        if u == "week":
            r = b - timedelta(weeks=n)
            return _fmt(r.year, r.month, r.day)
        if u == "month":
            tot = (b.year * 12 + b.month - 1) - n
            return _fmt(tot // 12, tot % 12 + 1)      # 月粒度,不编造日
        return _fmt(b.year - n)                        # 年粒度,不编造月日
    # last/this month|year
    m = re.match(r"^(last|this|past)\s+(month|year)$", t)
    if m:
        if m.group(2) == "year":
            return _fmt(b.year - (0 if m.group(1) == "this" else 1))
        tot = (b.year * 12 + b.month - 1) - (0 if m.group(1) == "this" else 1)
        return _fmt(tot // 12, tot % 12 + 1)
    return None


def normalize(s, base: Optional[str] = None) -> Tuple[Optional[str], str]:
    """把日期串规范成合规形态。返回 (规范串 或 None, 原因标签)。

    原因标签用于可观测性计数:compliant / range_head / bare_month /
    bare_month_day / relative / stripped_zeros / reject_*。
    """
    if s is None:
        return None, "empty"
    t = str(s).strip()
    if not t:
        return None, "empty"
    if _is_compliant(t):
        return t, "compliant"

    b = _parse_base(base)

    # 决定 2:区间/多日期串取最早那个,对首段递归
    parts = [p.strip() for p in _SPLIT.split(t) if p and p.strip()]
    if len(parts) > 1:
        head, why = normalize(parts[0], base)
        if head:
            return head, "range_head"
        return None, "reject_range"

    # 决定 6 的前置:相对时间表达(需要 base)
    if b is not None:
        rel = _relative(t, b)
        if rel:
            return rel, "relative"

    # 决定 5:年代拒绝
    if re.match(r"^\d{3,4}s$", t):
        return None, "reject_decade"

    # 去前导零后为四位年(001898 → 1898);而 2 / 22 拒绝(决定 4)
    m = re.match(r"^0*(\d{1,4})$", t)
    if m:
        y = m.group(1)
        if len(y) == 4:
            return _fmt(int(y)), "stripped_zeros"
        return None, "reject_short_year"

    # 数字形态:补零后再判合规(YYYY-M / YYYY-M-D 等)
    m = re.match(r"^(\d{4})-(\d{1,2})(?:-(\d{1,2}))?$", t)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        d = int(m.group(3)) if m.group(3) else None
        if y < 1:                      # 年 0000:与 _is_compliant 同一判据
            return None, "reject_year_zero"
        if 1 <= mo <= 12 and (d is None or 1 <= d <= 31):
            return _fmt(y, mo, d), "padded"
        return None, "reject_out_of_range"

    # 无年份的 MM-DD / M-D:需要 base 补年(决定 3 的数字版)
    m = re.match(r"^(\d{1,2})-(\d{1,2})$", t)
    if m and b is not None:
        mo, d = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            y = b.year if (mo, d) <= (b.month, b.day) else b.year - 1
            return _fmt(y, mo, d), "bare_month_day"
        return None, "reject_out_of_range"

    # 决定 3:裸月份(可带日)按 base 之前最近的那一个解
    m = re.match(r"^([A-Za-z]+)\.?(?:\s+(\d{1,2})(?:st|nd|rd|th)?)?$", t)
    if m and m.group(1).lower() in _MONTHS and b is not None:
        mo = _MONTHS[m.group(1).lower()]
        d = int(m.group(2)) if m.group(2) else None
        y = b.year if (mo <= b.month) else b.year - 1
        if d is not None and not (1 <= d <= 31):
            d = None
        return _fmt(y, mo, d), "bare_month"

    return None, "reject_unparseable"
