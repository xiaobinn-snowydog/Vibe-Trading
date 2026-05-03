#!/usr/bin/env python3
"""run_accountant.py — minimal end-to-end CLI for 账房先生.

Quiet by default. Pass --verbose to see tool-loading diagnostics.

Why a tiny custom loop instead of reusing AgentLoop:
  AgentLoop hardcodes its system prompt via ContextBuilder, which is the
  finance-research persona. The accountant needs a completely different
  persona, plus a thin output filter (BOUNDARIES.md compliance check).
  Easier to read this file than fight ContextBuilder.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

# ── sys.path bootstrap ────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[1]
AGENT_DIR = REPO_ROOT / "agent"
for p in (str(AGENT_DIR), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

# Load .env (same convention as cli.py)
try:
    from dotenv import load_dotenv

    load_dotenv(AGENT_DIR / ".env")
except ImportError:
    pass

# ── Silence upstream noise BEFORE imports that emit it ────────────────────
# The tool auto-discovery emits `Skipped src.tools.X` warnings for every
# upstream tool whose optional deps (numpy/pandas/scipy) aren't installed.
# That's irrelevant to a non-technical end user — hide it.
logging.getLogger().setLevel(logging.ERROR)
os.environ.setdefault("ACCOUNTANT_QUIET", "1")  # consumed by tool_whitelist

from accountant.boundaries import find_violations
from accountant.tool_whitelist import build_accountant_registry


SYSTEM_PROMPT_PATH = Path(__file__).parent / "prompts" / "system_prompt.md"
MAX_REACT_ITERATIONS = 12


# ── Helpers ───────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="账房先生 — 资产配置思考伙伴")
    p.add_argument(
        "--verbose", "-v", action="store_true",
        help="show tool-loading diagnostics (for developers)",
    )
    return p.parse_args()


def load_system_prompt() -> str:
    if not SYSTEM_PROMPT_PATH.exists():
        sys.exit(f"system prompt not found: {SYSTEM_PROMPT_PATH}")
    return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")


def format_tool_descriptions(registry) -> str:
    return "\n\n".join(
        f"### {t.name}\n{t.description}" for t in registry._tools.values()
    )


# ── ReAct loop with streaming ─────────────────────────────────────────────


def react_turn(llm, registry, messages: list, on_chunk=None) -> str:
    """One user turn through the ReAct loop. Streams via on_chunk if given."""
    from src.agent.context import ContextBuilder

    tools_def = registry.get_definitions()

    for _ in range(MAX_REACT_ITERATIONS):
        if on_chunk is not None:
            response = llm.stream_chat(
                messages, tools=tools_def, on_text_chunk=on_chunk,
            )
        else:
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
        return text

    fallback = "(我陷入了思考循环。请你直接告诉我你现在面对的具体决定。)"
    messages.append({"role": "assistant", "content": fallback})
    return fallback


# ── Entry ─────────────────────────────────────────────────────────────────


def main() -> None:
    args = parse_args()

    if not os.getenv("LANGCHAIN_PROVIDER"):
        sys.exit(
            "LANGCHAIN_PROVIDER 没设置。\n"
            f"先 cp {AGENT_DIR}/.env.example {AGENT_DIR}/.env，"
            "在 .env 里取消注释一段 provider 配置。"
        )

    from rich.console import Console
    from rich.panel import Panel
    from rich.theme import Theme

    from src.memory.persistent import PersistentMemory
    from src.providers.chat import ChatLLM

    theme = Theme({
        "user": "bold cyan",
        "agent": "bold green",
        "thinking": "dim italic",
        "warning": "yellow",
        "rule": "dim",
        "boot": "dim",
    })
    console = Console(theme=theme)

    # ── Boot ──
    pm = PersistentMemory()
    registry = build_accountant_registry(persistent_memory=pm)
    llm = ChatLLM()

    system_prompt = (
        load_system_prompt()
        + "\n\n## 当前可用工具\n\n"
        + format_tool_descriptions(registry)
    )
    messages: list = [{"role": "system", "content": system_prompt}]

    # ── Greet ──
    console.print()
    console.print(Panel.fit(
        "[bold]账房先生[/bold]\n\n"
        "我不告诉你买什么，也不替你处理情绪。\n"
        "我帮你把自己的话钉回桌面，让你看着自己的话做决定。\n\n"
        "[dim]你现在面对什么决定？[/dim]\n"
        "[dim]/quit 退出 · /tools 看工具 · /clear 清屏[/dim]",
        border_style="rule",
        padding=(1, 3),
        title="[dim]v0[/dim]",
        title_align="right",
    ))

    if args.verbose:
        console.print(
            f"\n[boot]工具：{', '.join(registry.tool_names)}[/boot]",
        )

    # ── Chat loop ──
    while True:
        try:
            console.print()
            user_input = console.input("[user]你 ▷[/user] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]再见。[/dim]")
            break

        if not user_input:
            continue
        if user_input in ("/quit", "/exit", "/q"):
            console.print("[dim]再见。[/dim]")
            break
        if user_input == "/clear":
            console.clear()
            continue
        if user_input == "/tools":
            for name, tool in registry._tools.items():
                console.print(f"  · [agent]{name}[/agent]: {tool.description}")
            continue
        if user_input == "/dump":
            console.print(json.dumps(messages, ensure_ascii=False, indent=2))
            continue

        messages.append({"role": "user", "content": user_input})

        console.print()
        console.print("[agent]账房先生 ◁[/agent] ", end="")

        # Spinner while waiting for first token, then stream the rest.
        status = console.status("[thinking]思考中…[/thinking]", spinner="dots")
        status.start()
        first_chunk = {"seen": False}

        def on_chunk(chunk: str) -> None:
            if not first_chunk["seen"]:
                status.stop()
                first_chunk["seen"] = True
            console.print(chunk, end="", soft_wrap=True, highlight=False)

        try:
            text = react_turn(llm, registry, messages, on_chunk=on_chunk)
        finally:
            if not first_chunk["seen"]:
                status.stop()

        console.print()  # newline after streamed output

        # Subtle boundary warning — surface only, never censor.
        violations = find_violations(text)
        if violations:
            console.print(
                f"[warning]  · 注：这条回复可能踩到「{', '.join(violations)}」"
                f"边界，请自行打折扣。[/warning]"
            )


if __name__ == "__main__":
    main()
