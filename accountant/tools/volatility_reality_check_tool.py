"""volatility_reality_check — show the worst historical return for a holding period.

The product job: when a user says "I want to buy X and hold for N years",
make them confront the *worst* N-year window in X's history before they
commit. Not the average. Not the best. The worst.

This tool is fact-only. It returns numbers, not opinions. The agent must
follow the data-template in system_prompt.md when quoting the result:
  fact + reflective question, never a recommendation.

v0 implementation note:
  Wraps ``get_market_data`` to fetch history, then computes rolling
  N-year returns and returns the min. If get_market_data is unavailable
  for the asset, returns ``{"status": "no_data"}`` and the agent is
  instructed (via system prompt) to say so honestly rather than guess.
"""

from __future__ import annotations

import json
from typing import Any

from src.agent.tools import BaseTool


class VolatilityRealityCheckTool(BaseTool):
    """Return worst historical return for a (asset, holding_period) pair."""

    name = "volatility_reality_check"
    description = (
        "Given an asset symbol and a holding period in months, return the "
        "WORST historical rolling return for that period (plus the window "
        "it occurred in). This is intended to force the user to confront "
        "downside before deciding. Returns ONLY the worst case, not the "
        "average — by design. Use to ask: 'if this happened to you, would "
        "you still want to be in?'"
    )
    parameters = {
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": "Asset symbol (e.g. 'GLD', 'BTC-USDT', '600519.SH').",
            },
            "holding_months": {
                "type": "integer",
                "description": "Holding period in months. Common: 6, 12, 24, 36, 60.",
                "minimum": 1,
            },
            "lookback_years": {
                "type": "integer",
                "description": "How many years of history to scan. Default 10.",
                "default": 10,
            },
        },
        "required": ["symbol", "holding_months"],
    }
    is_readonly = True
    repeatable = True

    def execute(self, **kwargs: Any) -> str:
        symbol = (kwargs.get("symbol") or "").strip()
        holding_months = int(kwargs.get("holding_months") or 0)
        lookback_years = int(kwargs.get("lookback_years") or 10)

        if not symbol or holding_months <= 0:
            return json.dumps(
                {"status": "error", "error": "symbol and holding_months required"},
                ensure_ascii=False,
            )

        try:
            worst = _compute_worst_rolling_return(
                symbol=symbol,
                holding_months=holding_months,
                lookback_years=lookback_years,
            )
        except _NoDataError as exc:
            return json.dumps(
                {
                    "status": "no_data",
                    "symbol": symbol,
                    "reason": str(exc),
                    "agent_hint": (
                        "Tell the user honestly that you don't have enough "
                        "history for this asset/period. Do NOT substitute a "
                        "different asset or period without asking."
                    ),
                },
                ensure_ascii=False,
            )

        return json.dumps(
            {
                "status": "ok",
                "symbol": symbol,
                "holding_months": holding_months,
                "lookback_years": lookback_years,
                "worst_return_pct": worst["worst_return_pct"],
                "window_start": worst["window_start"],
                "window_end": worst["window_end"],
                "agent_hint": (
                    "Quote the worst-case number plainly. Then ask the user: "
                    "'如果这种情况发生在你身上，你还会买吗？' Do NOT add "
                    "'but the average is...' — the point is to confront the "
                    "downside."
                ),
            },
            ensure_ascii=False,
        )


# ---------------------------------------------------------------------------
# Computation (skeleton — wires to the existing market data layer)
# ---------------------------------------------------------------------------


class _NoDataError(Exception):
    pass


def _compute_worst_rolling_return(
    *, symbol: str, holding_months: int, lookback_years: int,
) -> dict[str, Any]:
    """Compute worst rolling return over the lookback window.

    v0: implemented via the existing ``get_market_data`` loader chain.
    Replace the stub below with a concrete call once the loader interface
    for monthly bars is finalized for your accountant deployment.
    """
    # NOTE: deliberate stub — the real implementation should:
    #   1. Resolve the loader for `symbol` via backtest.loaders.registry.
    #   2. Fetch monthly closes for the past `lookback_years` years.
    #   3. Compute rolling `holding_months`-month returns.
    #   4. Return the min, plus the (start, end) of that window.
    # Kept as a stub here so the tool registers and the system can be
    # exercised end-to-end with `status: no_data`. Wire to real data only
    # after the conversation flow has been validated.
    raise _NoDataError(
        "volatility_reality_check is a v0 stub; concrete data wiring "
        "pending. Tool returns no_data so the agent admits the gap "
        "instead of fabricating numbers."
    )
