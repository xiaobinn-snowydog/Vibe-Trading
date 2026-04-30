"""personal_decision_history — surface the user's past decisions on the same topic.

This is the accountant's single most valuable tool: it returns the user's
own historical reasoning, so the agent can hold the user accountable to
their previous frame instead of fabricating a new one each session.

Data source (v0): the same file-backed PersistentMemory + a sidecar
``decisions.jsonl`` log, both under ``~/.vibe-trading/memory/``.

The tool is READ-ONLY. Writes happen through ``remember`` (which the
agent calls when it observes a decision being made).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.agent.tools import BaseTool


DECISIONS_LOG = Path.home() / ".vibe-trading" / "memory" / "decisions.jsonl"


class PersonalDecisionHistoryTool(BaseTool):
    """Return past decisions matching a topic / asset / theme."""

    name = "personal_decision_history"
    description = (
        "Recall the user's past decisions on a specific topic (asset, theme, "
        "or general decision type). Returns up to N recent matching entries "
        "with the user's own stated reasons at the time. Use this to anchor "
        "reflection in the user's own history; do NOT use it to suggest a "
        "course of action."
    )
    parameters = {
        "type": "object",
        "properties": {
            "topic": {
                "type": "string",
                "description": "Topic / asset / theme. Free-text match against "
                               "decision logs (e.g. '黄金', 'AAPL', '加仓', '换房').",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of entries to return.",
                "default": 5,
            },
        },
        "required": ["topic"],
    }
    is_readonly = True
    repeatable = True

    def execute(self, **kwargs: Any) -> str:
        topic = (kwargs.get("topic") or "").strip()
        limit = int(kwargs.get("limit") or 5)
        if not topic:
            return json.dumps(
                {"status": "error", "error": "topic is required"},
                ensure_ascii=False,
            )

        entries = _load_entries()
        matches = [e for e in entries if _matches(e, topic)]
        matches.sort(key=lambda e: e.get("date", ""), reverse=True)
        matches = matches[:limit]

        return json.dumps(
            {
                "status": "ok",
                "topic": topic,
                "count": len(matches),
                "entries": matches,
                "agent_hint": (
                    "Quote the user's own stated_reason back to them. "
                    "Do NOT add commentary about what they 'should' do now."
                ),
            },
            ensure_ascii=False,
        )


def _load_entries() -> list[dict[str, Any]]:
    if not DECISIONS_LOG.exists():
        return []
    out: list[dict[str, Any]] = []
    try:
        with DECISIONS_LOG.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return out


def _matches(entry: dict[str, Any], topic: str) -> bool:
    """Loose match: topic token appears in any stringy field."""
    needle = topic.lower()
    for key in ("trigger", "topic", "initial_lean", "stated_reason",
                "final_decision", "asset", "tags"):
        val = entry.get(key)
        if isinstance(val, str) and needle in val.lower():
            return True
        if isinstance(val, list):
            for item in val:
                if isinstance(item, str) and needle in item.lower():
                    return True
    return False
