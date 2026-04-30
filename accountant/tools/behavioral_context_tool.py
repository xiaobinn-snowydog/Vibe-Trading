"""behavioral_context — return behavioral facts about retail investors in a scenario.

Strict rules:
  - Returns *facts* (with source), never opinions or advice.
  - Returns at most 2-3 short lines so the agent can quote them tersely.
  - Never speculates. If no fact is on file for a scenario, return empty —
    do not invent.

The v0 fact set lives in ``data/behavioral_facts.json`` next to this file.
That file is the single source of truth and should be reviewed like a
content asset (not auto-generated).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.agent.tools import BaseTool


_FACTS_PATH = Path(__file__).parent / "data" / "behavioral_facts.json"


class BehavioralContextTool(BaseTool):
    """Return curated behavioral facts for a named scenario."""

    name = "behavioral_context"
    description = (
        "Retrieve curated behavioral-finance facts about how retail "
        "investors typically behave in a named scenario (e.g. 'after a "
        "30% rally', 'during a sharp drawdown'). Returns short factual "
        "lines with sources. Returns nothing if no facts are on file — "
        "do NOT fabricate. Use to ground a reflective question, never as "
        "a recommendation."
    )
    parameters = {
        "type": "object",
        "properties": {
            "scenario": {
                "type": "string",
                "description": "Scenario tag. See data/behavioral_facts.json "
                               "for the supported set.",
            },
        },
        "required": ["scenario"],
    }
    is_readonly = True
    repeatable = True

    def execute(self, **kwargs: Any) -> str:
        scenario = (kwargs.get("scenario") or "").strip().lower()
        if not scenario:
            return json.dumps(
                {"status": "error", "error": "scenario is required"},
                ensure_ascii=False,
            )

        facts = _load_facts().get(scenario, [])
        return json.dumps(
            {
                "status": "ok",
                "scenario": scenario,
                "facts": facts,
                "agent_hint": (
                    "Quote at most one fact, then ask the user how it "
                    "applies to their situation. Do NOT generalize the "
                    "fact into a recommendation."
                ),
            },
            ensure_ascii=False,
        )


def _load_facts() -> dict[str, list[dict[str, str]]]:
    if not _FACTS_PATH.exists():
        return {}
    try:
        return json.loads(_FACTS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
