"""DealForge — a gamified, Telegram-first sales CRM for Anthos agents.

Inspired by DeskcommCRM (MIT, github.com/melgarafael/DeskcommCRM): contacts,
a niche-configurable pipeline, a follow-up radar. Instead of a separate web
stack, it rides the Anthos messaging gateway, so the same agent that chats
with a lead on Telegram operates the CRM directly.

On top of that, deals are quests: every real stage advance mints a stage
token, taking a deal through the whole pipeline mints an 🏆 Odyssey, and
daily quests, streaks and revivals mint special tokens that roll up into
XP levels. Anti-gaming rules (evidence notes, stage dwell time, per-deal
dedupe) make sure tokens track real-world progress.

Opt-in standalone plugin: enable with ``plugins.enabled: [dealforge]``.
"""

from __future__ import annotations

from pathlib import Path

from plugins.dealforge.cli import pipeline_slash, dealforge_command, register_cli
from plugins.dealforge.tools import (
    DEALFORGE_CONTACT_SCHEMA,
    DEALFORGE_DEAL_SCHEMA,
    DEALFORGE_REWARDS_SCHEMA,
    check_dealforge_available,
    handle_dealforge_contact,
    handle_dealforge_deal,
    handle_dealforge_rewards,
)

_TOOLS = (
    ("dealforge_contact", DEALFORGE_CONTACT_SCHEMA, handle_dealforge_contact, "📇"),
    ("dealforge_deal",    DEALFORGE_DEAL_SCHEMA,    handle_dealforge_deal,    "🗺️"),
    ("dealforge_rewards", DEALFORGE_REWARDS_SCHEMA, handle_dealforge_rewards, "🪙"),
)


def register(ctx) -> None:
    for name, schema, handler, emoji in _TOOLS:
        ctx.register_tool(
            name=name,
            toolset="dealforge",
            schema=schema,
            handler=handler,
            check_fn=check_dealforge_available,
            emoji=emoji,
        )

    ctx.register_cli_command(
        name="dealforge",
        help="DealForge CRM (pipeline, radar, token rewards)",
        setup_fn=register_cli,
        handler_fn=dealforge_command,
        description="Gamified Telegram-first sales CRM. Start with: anthos dealforge init --preset sales",
    )

    ctx.register_command(
        "pipeline",
        pipeline_slash,
        description="DealForge board, radar, quests, wallet or leaderboard",
        args_hint="[board|radar|quests|wallet|leaderboard|catalog]",
    )

    ctx.register_skill(
        "sales-pilot",
        Path(__file__).parent / "SKILL.md",
        description="Run the DealForge CRM from chat and earn tokens.",
    )
