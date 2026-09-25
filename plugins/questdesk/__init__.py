"""QuestDesk — a gamified, Telegram-first sales CRM for Anthos agents.

Inspired by DeskcommCRM (MIT, github.com/melgarafael/DeskcommCRM): contacts,
a niche-configurable pipeline, a follow-up radar. Instead of a separate web
stack, it rides the Anthos messaging gateway, so the same agent that chats
with a lead on Telegram operates the CRM directly.

On top of that, deals are quests: every real stage advance mints a stage
token, taking a deal through the whole pipeline mints an 🏆 Odyssey, and
daily quests, streaks and revivals mint special tokens that roll up into
XP levels. Anti-gaming rules (evidence notes, stage dwell time, per-deal
dedupe) make sure tokens track real-world progress.

Opt-in standalone plugin: enable with ``plugins.enabled: [questdesk]``.
"""

from __future__ import annotations

from pathlib import Path

from plugins.questdesk.cli import pipeline_slash, questdesk_command, register_cli
from plugins.questdesk.tools import (
    QUESTDESK_CONTACT_SCHEMA,
    QUESTDESK_DEAL_SCHEMA,
    QUESTDESK_REWARDS_SCHEMA,
    check_questdesk_available,
    handle_questdesk_contact,
    handle_questdesk_deal,
    handle_questdesk_rewards,
)

_TOOLS = (
    ("questdesk_contact", QUESTDESK_CONTACT_SCHEMA, handle_questdesk_contact, "📇"),
    ("questdesk_deal",    QUESTDESK_DEAL_SCHEMA,    handle_questdesk_deal,    "🗺️"),
    ("questdesk_rewards", QUESTDESK_REWARDS_SCHEMA, handle_questdesk_rewards, "🪙"),
)


def register(ctx) -> None:
    for name, schema, handler, emoji in _TOOLS:
        ctx.register_tool(
            name=name,
            toolset="questdesk",
            schema=schema,
            handler=handler,
            check_fn=check_questdesk_available,
            emoji=emoji,
        )

    ctx.register_cli_command(
        name="questdesk",
        help="QuestDesk CRM (pipeline, radar, token rewards)",
        setup_fn=register_cli,
        handler_fn=questdesk_command,
        description="Gamified Telegram-first sales CRM. Start with: anthos questdesk init --preset sales",
    )

    ctx.register_command(
        "pipeline",
        pipeline_slash,
        description="QuestDesk board, radar, quests, wallet or leaderboard",
        args_hint="[board|radar|quests|wallet|leaderboard|catalog]",
    )

    ctx.register_skill(
        "sales-pilot",
        Path(__file__).parent / "SKILL.md",
        description="Run the QuestDesk CRM from chat and earn tokens.",
    )
