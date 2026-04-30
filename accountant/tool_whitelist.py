"""账房先生 — Tool whitelist.

This module is the SINGLE SOURCE OF TRUTH for which tools the accountant
agent is allowed to call. Adding a tool here is a deliberate act — review
against accountant/BOUNDARIES.md before touching this list.

Why a separate whitelist (instead of editing build_registry):
  The main repo's auto-discovery is correct for the developer-facing
  CLI/MCP/API. The accountant is a *product layer* on top — it should
  use a strict subset, and that subset should be visible at a glance.

Usage:
    from accountant.tool_whitelist import build_accountant_registry
    registry = build_accountant_registry(persistent_memory=memory)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.agent.tools import ToolRegistry
    from src.memory.persistent import PersistentMemory


# ---------------------------------------------------------------------------
# Whitelist
# ---------------------------------------------------------------------------
#
# Each entry: (tool_name, justification).
# The justification is checked against BOUNDARIES.md during review.
#
# RULE: if you cannot write a one-line justification grounded in
# "helps the user think, not buys/sells/predicts", do NOT add it.
#

ACCOUNTANT_TOOLS: list[tuple[str, str]] = [
    # ── Memory: the agent's most important capability ──
    ("remember",
     "Write decision log entries — the product's core data asset."),
    ("recall",
     "Read user's past decisions to anchor reflection in their own history."),

    # ── Reflection-shaped data tools (custom, see accountant/tools/) ──
    ("personal_decision_history",
     "Surface the user's past decisions on the same topic — pure mirror."),
    ("behavioral_context",
     "Surface behavioral facts about retail investors in similar situations "
     "(facts only, no opinion)."),
    ("volatility_reality_check",
     "Show the worst historical return for a holding period — forces the "
     "user to confront downside before deciding."),

    # ── Plain fact lookup (allowed under BOUNDARIES §C) ──
    ("get_market_data",
     "Current price / historical return / max drawdown. "
     "MUST be paired with the data-template in system_prompt.md."),
    ("web_search",
     "Background facts only (news, company basics). "
     "NOT for trading signals or ratings."),
    ("read_url",
     "Read a specific URL the user mentions. Same constraints as web_search."),
]


# ---------------------------------------------------------------------------
# Hard denylist — these tools must NEVER be exposed to the accountant.
# Used as an assertion safety net in build_accountant_registry.
# ---------------------------------------------------------------------------

ACCOUNTANT_DENYLIST: frozenset[str] = frozenset({
    # Generates buy/sell signals or strategy code:
    "backtest",
    "factor_analysis",
    "pattern_recognition",
    "analyze_options",
    "pine_script",
    "vnpy_export",
    # Shadow account tools — useful for the trader-facing product, but they
    # generate explicit "what you should have done" output that conflicts
    # with the accountant's no-advice rule:
    "extract_shadow_strategy",
    "run_shadow_backtest",
    "render_shadow_report",
    "scan_shadow_signals",
    "analyze_trade_journal",
    # Code execution / file write — accountant has no reason to write code:
    "bash",
    "write_file",
    "edit_file",
    # Swarm — too heavy and produces "research reports" that read as advice:
    "list_swarm_presets",
    "run_swarm",
    "get_swarm_status",
    # Skill writer — accountant should not edit its own skills at runtime:
    "skill_writer",
    "save_skill",
    "patch_skill",
    "delete_skill",
})


def build_accountant_registry(
    *,
    persistent_memory: "PersistentMemory | None" = None,
) -> "ToolRegistry":
    """Build a ToolRegistry containing exactly the accountant whitelist.

    Args:
        persistent_memory: Shared PersistentMemory instance for remember/recall.

    Returns:
        A ToolRegistry with only whitelisted tools.

    Raises:
        AssertionError: If the whitelist accidentally overlaps the denylist
            (defense in depth — catches careless edits to ACCOUNTANT_TOOLS).
    """
    from src.tools import build_filtered_registry

    names = [name for name, _ in ACCOUNTANT_TOOLS]

    # Defense in depth: catch a developer who adds a denied tool to the list.
    overlap = set(names) & ACCOUNTANT_DENYLIST
    assert not overlap, (
        f"Whitelist contains denied tools: {overlap}. "
        f"Review accountant/BOUNDARIES.md before changing."
    )

    registry = build_filtered_registry(names)

    # Inject the shared PersistentMemory into RememberTool, mirroring the
    # main build_registry behaviour so all memory ops share one instance.
    if persistent_memory is not None:
        remember = registry.get("remember")
        if remember is not None and hasattr(remember, "memory"):
            remember.memory = persistent_memory

    return registry


def whitelist_summary() -> str:
    """Return a human-readable summary, used by the CLI / docs / tests."""
    lines = ["账房先生 — allowed tools:\n"]
    for name, why in ACCOUNTANT_TOOLS:
        lines.append(f"  - {name}: {why}")
    lines.append("\nExplicitly denied:")
    for name in sorted(ACCOUNTANT_DENYLIST):
        lines.append(f"  - {name}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(whitelist_summary())
