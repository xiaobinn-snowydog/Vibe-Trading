#!/usr/bin/env python3
"""run_accountant.py — minimal end-to-end CLI for 账房先生.

Why a tiny custom loop instead of reusing AgentLoop:
  AgentLoop hardcodes its system prompt via ContextBuilder, which is the
  finance-research persona. The accountant needs a completely different
  persona, plus a thin output filter (BOUNDARIES.md compliance check),
  plus a much shorter tool description block. Easier to read 100 lines
  here than fight ContextBuilder.

What this script does NOT do (intentionally, for v0):
  - 5-layer context compression (conversations are short)
  - SSE streaming (not a UX requirement for CLI smoke tests)
  - Background tasks
  - Run-dir / trace artifacts
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# ── sys.path bootstrap ────────────────────────────────────────────────────
# Match what agent/tests/conftest.py does: put `agent/` on sys.path so
# `from src.foo import ...` works the same way the rest of the repo does.
REPO_ROOT = Path(__file__).resolve().parents[1]
AGENT_DIR = REPO_ROOT / "agent"
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Load .env (same convention as cli.py)
try:
    from dotenv import load_dotenv

    load_dotenv(AGENT_DIR / ".env")
except ImportError:
    pass

# ── Imports that depend on the path bootstrap ─────────────────────────────
from accountant.tests.test_boundaries import find_violations, has_question
from accountant.tool_whitelist import build_accountant_registry


SYSTEM_PROMPT_PATH = Path(__file__).parent / "prompts" / "system_prompt.md"
MAX_REACT_ITERATIONS = 12


# ── Helpers ───────────────────────────────────────────────────────────────


def load_system_prompt() -> str:
    """Read the persona prompt from disk so iteration doesn't require code edits."""
    if not SYSTEM_PROMPT_PATH.exists():
        sys.exit(f"system prompt not found: {SYSTEM_PROMPT_PATH}")
    return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")


def format_tool_descriptions(registry) -> str:
    """Render available tools as a markdown block for the system prompt."""
    lines = []
    for tool in registry._tools.values():
        lines.append(f"### {tool.name}\n{tool.description}")
    return "\n\n".join(lines)


def warn_if_violates(text: str) -> None:
    """Print a visible warning when the agent's output crosses a boundary.

    This is a safety net, not enforcement — for v0 we surface drift to
    the human operator rather than auto-rewrite, so we can see *what* the
    model produced before deciding how to handle it.
    """
    violations = find_violations(text)
    missing_question = not has_question(text) and len(text.strip()) > 30
    if violations or missing_question:
        flags = list(violations)
        if missing_question:
            flags.append("missing_question_mark")
        print(f"\n  [boundary-warning: {', '.join(flags)}]", file=sys.stderr)


# ── ReAct loop ────────────────────────────────────────────────────────────


def react_turn(llm, registry, messages: list, on_text=None) -> str:
    """Run one user turn through the ReAct loop until a final text answer.

    Mutates `messages` in place: appends assistant + tool messages so that
    subsequent turns inherit history naturally.

    Returns:
        Final assistant text (also already appended to messages).
    """
    from src.agent.context import ContextBuilder

    tools_def = registry.get_definitions()

    for _ in range(MAX_REACT_ITERATIONS):
        response = llm.chat(messages, tools=tools_def)

        if response.has_tool_calls:
            messages.append(
                ContextBuilder.format_assistant_tool_calls(
                    response.tool_calls,
                    content=response.content or "",
                    reasoning_content=response.reasoning_content,
                )
            )
            for tc in response.tool_calls:
                result = registry.execute(tc.name, tc.arguments)
                messages.append(
                    ContextBuilder.format_tool_result(tc.id, tc.name, result)
                )
            continue

        text = response.content or ""
        messages.append({"role": "assistant", "content": text})
        if on_text:
            on_text(text)
        return text

    fallback = "(我陷入了思考循环。请你直接告诉我你现在面对的具体决定。)"
    messages.append({"role": "assistant", "content": fallback})
    return fallback


# ── Entry ─────────────────────────────────────────────────────────────────


GREETING = (
    "我是账房先生。\n"
    "我不会告诉你买什么，也不替你处理情绪。\n"
    "我帮你把你自己的话钉回桌面，让你看着自己的话做决定。\n"
    "\n"
    "你现在面对什么决定？\n"
    "(输入 /quit 退出)"
)


def main() -> None:
    if not os.getenv("LANGCHAIN_PROVIDER"):
        sys.exit(
            "LANGCHAIN_PROVIDER not set.\n"
            f"Copy {AGENT_DIR}/.env.example to {AGENT_DIR}/.env "
            "and uncomment one provider block."
        )

    from src.memory.persistent import PersistentMemory
    from src.providers.chat import ChatLLM

    pm = PersistentMemory()
    registry = build_accountant_registry(persistent_memory=pm)
    llm = ChatLLM()

    system_prompt = (
        load_system_prompt()
        + "\n\n## 当前可用工具（运行时注入）\n\n"
        + format_tool_descriptions(registry)
    )
    messages: list = [{"role": "system", "content": system_prompt}]

    print(GREETING)
    print(f"\n  [tools loaded: {', '.join(registry.tool_names)}]\n", file=sys.stderr)

    while True:
        try:
            user_input = input("\n你：").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见。")
            break

        if not user_input:
            continue
        if user_input in ("/quit", "/exit", "/q"):
            print("再见。")
            break
        if user_input == "/dump":
            print(json.dumps(messages, ensure_ascii=False, indent=2))
            continue
        if user_input == "/tools":
            for name, tool in registry._tools.items():
                print(f"  - {name}: {tool.description}")
            continue

        messages.append({"role": "user", "content": user_input})
        print("\n账房先生：", end="", flush=True)
        text = react_turn(llm, registry, messages)
        print(text)
        warn_if_violates(text)


if __name__ == "__main__":
    main()
