"""账房先生 reflection-shaped tools.

These are skeleton implementations. They follow the BaseTool contract so
they auto-register when imported, but the data backing each tool is left
deliberately minimal — concrete data sources should be wired in only after
the conversation flow is validated end-to-end (don't optimize a UI you
haven't watched a real user fail at).
"""

from accountant.tools.personal_decision_history_tool import PersonalDecisionHistoryTool
from accountant.tools.behavioral_context_tool import BehavioralContextTool
from accountant.tools.volatility_reality_check_tool import VolatilityRealityCheckTool

__all__ = [
    "PersonalDecisionHistoryTool",
    "BehavioralContextTool",
    "VolatilityRealityCheckTool",
]
