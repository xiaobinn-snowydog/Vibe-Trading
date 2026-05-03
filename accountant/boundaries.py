"""Boundary checks — pure regex helpers, zero test dependencies.

Used by both:
  - accountant/run_accountant.py (runtime safety net on agent output)
  - accountant/tests/test_boundaries.py (CI assertions on pattern matching)

Keep this file dependency-free. No pytest, no LLM imports — just `re`.
"""

from __future__ import annotations

import re

# Disallowed: specific advice — verb + asset
_BUY_SELL_RE = re.compile(
    r"(买入|卖出|加仓|减仓|建仓|清仓|做多|做空)"
    r".{0,15}"
    r"([A-Z]{2,6}|[0-9]{6}|黄金|白银|比特币|以太坊|美债|国债|"
    r"茅台|腾讯|阿里|宁德|苹果|英伟达|特斯拉)",
)

# Disallowed: market-timing language
_TIMING_RE = re.compile(
    r"(现在是|目前是|当下是).{0,8}"
    r"(好时机|好的入场|入场点|抄底|逃顶|介入|布局)"
    r"|(建议|应当|应该|可以).{0,5}(谨慎|追高|抄底|入场|布局|减仓|加仓)"
    r"|(看涨|看跌|短期看|中长期看|看多|看空)"
)

# Disallowed: prediction
_PREDICTION_RE = re.compile(
    r"(会涨到|会跌到|目标价|预计涨|预计跌|大概率涨|大概率跌)"
)

# Disallowed: therapy drift
_THERAPY_RE = re.compile(
    r"(童年|原生家庭|创伤|心理健康|情绪根源|"
    r"我理解你的(感受|情绪|焦虑|痛苦)|"
    r"我们(慢慢来|来梳理你的|来探索你的))"
)

# Required: at least one question mark (any flavour)
_QUESTION_RE = re.compile(r"[?？]")


VIOLATION_KIND: dict[str, re.Pattern[str]] = {
    "specific_advice": _BUY_SELL_RE,
    "market_timing": _TIMING_RE,
    "prediction": _PREDICTION_RE,
    "therapy_drift": _THERAPY_RE,
}


def find_violations(text: str) -> list[str]:
    """Return list of violation kinds found in *text*. Empty = clean."""
    return [kind for kind, rx in VIOLATION_KIND.items() if rx.search(text)]


def has_question(text: str) -> bool:
    """Whether the response contains a question mark (any flavour)."""
    return bool(_QUESTION_RE.search(text))
