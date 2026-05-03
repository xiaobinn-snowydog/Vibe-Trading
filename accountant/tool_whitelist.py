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

# ---------------------------------------------------------------------------
# Whitelist
# ---------------------------------------------------------------------------
#
# Each entry: (tool_name, required, justification).
#   required=True   → startup fails if the tool isn't registered (core capability)
#   required=False  → soft-fail with a warning, accountant still launches
#
# RULE: if you cannot write a one-line justification grounded in
# "helps the user think, not buys/sells/predicts", do NOT add it.
#

ACCOUNTANT_TOOLS: list[tuple[str, bool, str]] = [
    # ── Core (required): without these the product can't function ──
    # Note: `remember` exposes save/recall/forget as a single tool with an
    # `action` parameter — there is no separate `recall` tool.
    ("remember", True,
     "Write/read/delete decision log entries — the product's core data asset."),
    ("personal_decision_history", True,
     "Surface the user's past decisions on the same topic — pure mirror."),
    ("behavioral_context", True,
     "Surface behavioral facts about retail investors in similar situations "
     "(facts only, no opinion)."),
    ("volatility_reality_check", True,
     "Show the worst historical return for a holding period — forces the "
     "user to confront downside before deciding."),

    # ── Optional: nice to have, accountant degrades gracefully without ──
    # Market price lookup is NOT exposed as an agent tool in the upstream
    # registry (only via MCP). For v0 the accountant relies on web_search
    # if the user asks for a current price; revisit if conversation tests
    # show this is a real gap.
    ("web_search", False,
     "Background facts only (news, company basics). "
     "NOT for trading signals or ratings."),
    ("read_url", False,
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

    Imports ``accountant.tools`` first so the custom reflection tools register
    as ``BaseTool`` subclasses, then builds the full upstream registry (which
    walks ``BaseTool.__subclasses__()`` and now sees them), then filters down
    to the whitelist.

    Args:
        persistent_memory: Shared PersistentMemory instance for ``remember``.

    Returns:
        A ToolRegistry with only whitelisted tools.

    Raises:
        AssertionError: If the whitelist accidentally overlaps the denylist.
        RuntimeError: If a whitelisted tool isn't registered (typo or missing
            optional dependency).
    """
    import logging
    log = logging.getLogger(__name__)

    # Step 1: import custom reflection tools so they register as BaseTool subclasses.
    import accountant.tools  # noqa: F401  (registration side-effect)

    # Step 2: build the full upstream registry. build_registry handles the
    # PersistentMemory injection into RememberTool natively.
    from src.tools import build_registry
    from src.agent.tools import ToolRegistry

    full = build_registry(persistent_memory=persistent_memory)

    # Step 3: defense in depth — catch a developer who adds a denied tool.
    names = [name for name, _, _ in ACCOUNTANT_TOOLS]
    overlap = set(names) & ACCOUNTANT_DENYLIST
    assert not overlap, (
        f"Whitelist contains denied tools: {overlap}. "
        f"Review accountant/BOUNDARIES.md before changing."
    )

    # Step 4: register what's available; only fail hard for missing CORE tools.
    filtered = ToolRegistry()
    missing_core: list[str] = []
    missing_optional: list[str] = []
    for name, required, _ in ACCOUNTANT_TOOLS:
        tool = full.get(name)
        if tool is None:
            (missing_core if required else missing_optional).append(name)
            continue
        filtered.register(tool)

    if missing_optional:
        log.warning(
            "Optional accountant tools unavailable (missing deps?): %s. "
            "Accountant will run without them. Install ddgs + requests to enable.",
            missing_optional,
        )
        # Also surface to stderr so a non-DEBUG run still sees it.
        import sys
        print(
            f"  [optional tools skipped: {', '.join(missing_optional)} "
            f"— accountant will run without them]",
            file=sys.stderr,
        )

    if missing_core:
        raise RuntimeError(
            f"Required accountant tools not registered: {missing_core}. "
            f"This is a bug — these tools are core to the product. "
            f"Check accountant/tools/__init__.py imports."
        )

    return filtered


def whitelist_summary() -> str:
    """Return a human-readable summary, used by the CLI / docs / tests."""
    lines = ["账房先生 — allowed tools:\n"]
    for name, required, why in ACCOUNTANT_TOOLS:
        marker = "(required)" if required else "(optional)"
        lines.append(f"  - {name} {marker}: {why}")
    lines.append("\nExplicitly denied:")
    for name in sorted(ACCOUNTANT_DENYLIST):
        lines.append(f"  - {name}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(whitelist_summary())
