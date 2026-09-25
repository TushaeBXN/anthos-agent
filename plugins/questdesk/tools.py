"""QuestDesk model tools — three action-dispatched tools, one toolset.

Three tools instead of fifteen keeps the per-call schema footprint small
while still covering the whole CRM surface.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Callable, Dict

from tools.registry import tool_error, tool_result

from plugins.questdesk import rewards as R
from plugins.questdesk.store import QuestDesk, QuestDeskError

logger = logging.getLogger(__name__)

_AGENT_RE = re.compile(r"[^\w .@-]+")


def check_questdesk_available() -> bool:
    # Pure local SQLite — available whenever the plugin is enabled.
    return True


def _desk() -> QuestDesk:
    return QuestDesk()


def resolve_agent(raw: Any = None) -> str:
    """Who earns the tokens: explicit ``agent`` arg, else the active profile."""
    if isinstance(raw, str) and raw.strip():
        name = _AGENT_RE.sub("", raw.strip())[:64].strip()
        if name:
            return name
    try:
        from anthos_cli.profiles import get_active_profile_name

        return get_active_profile_name() or "anthos"
    except Exception:
        return "anthos"


def _run(fn: Callable[[], dict]) -> str:
    try:
        return tool_result({"success": True, **fn()})
    except QuestDeskError as exc:
        return tool_error(str(exc), success=False)
    except Exception as exc:  # pragma: no cover — defensive
        logger.exception("questdesk tool failed")
        return tool_error(f"QuestDesk failed: {type(exc).__name__}: {exc}", success=False)


_AGENT_PROP = {
    "type": "string",
    "description": "Name credited with any tokens earned. Defaults to the active profile.",
}

QUESTDESK_CONTACT_SCHEMA: Dict[str, Any] = {
    "name": "questdesk_contact",
    "description": (
        "QuestDesk CRM contacts. add (dedupes on handle/phone/email), update, get (with deals + "
        "history), search, note (log an interaction on a contact or deal)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["add", "update", "get", "search", "note"]},
            "contact_id": {"type": "integer"},
            "deal_id": {"type": "integer", "description": "For note: attach the note to this deal."},
            "name": {"type": "string"},
            "handle": {"type": "string", "description": "Telegram @username or numeric user id."},
            "phone": {"type": "string"},
            "email": {"type": "string"},
            "company": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "note": {"type": "string"},
            "query": {"type": "string", "description": "For search."},
            "limit": {"type": "integer"},
            "agent": _AGENT_PROP,
        },
        "required": ["action"],
    },
}

QUESTDESK_DEAL_SCHEMA: Dict[str, Any] = {
    "name": "questdesk_deal",
    "description": (
        "QuestDesk CRM pipeline. create, move (advancing needs a note with evidence), update, lose "
        "(needs loss_reason), get, list, board (pipeline snapshot), radar (deals needing follow-up), "
        "stages. Real progress mints tokens + XP for the agent; results include rewards and next_goal."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["create", "move", "update", "lose", "get", "list", "board", "radar", "stages"],
            },
            "deal_id": {"type": "integer"},
            "title": {"type": "string"},
            "contact_id": {"type": "integer"},
            "contact_name": {"type": "string", "description": "For create without contact_id: auto-creates the contact."},
            "handle": {"type": "string", "description": "For create: contact's Telegram @username."},
            "value": {"type": "number"},
            "currency": {"type": "string"},
            "stage": {"type": "string", "description": "Stage label, key or position number."},
            "note": {"type": "string", "description": "What happened. Required (≥12 chars) to advance a deal."},
            "next_action": {"type": "string"},
            "next_action_due": {"type": "string", "description": "e.g. 4h, 2d, 1w, 2026-10-01 or ISO-8601."},
            "loss_reason": {"type": "string"},
            "status": {"type": "string", "enum": ["open", "won", "lost", "all"], "description": "For list (default open)."},
            "query": {"type": "string", "description": "For list: title substring."},
            "stale_days": {"type": "number", "description": "For radar (default 7)."},
            "limit": {"type": "integer"},
            "agent": _AGENT_PROP,
        },
        "required": ["action"],
    },
}

QUESTDESK_REWARDS_SCHEMA: Dict[str, Any] = {
    "name": "questdesk_rewards",
    "description": "QuestDesk token rewards: wallet (XP, level, tokens), quests (today's), leaderboard, catalog.",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["wallet", "quests", "leaderboard", "catalog"]},
            "agent": _AGENT_PROP,
            "limit": {"type": "integer"},
        },
        "required": ["action"],
    },
}


def handle_questdesk_contact(args: dict, **_kw) -> str:
    action = (args.get("action") or "").strip().lower()
    agent = resolve_agent(args.get("agent"))

    def go() -> dict:
        desk = _desk()
        if action == "add":
            return desk.add_contact(agent, args.get("name"), args.get("handle"), args.get("phone"),
                                    args.get("email"), args.get("company"), args.get("tags"), args.get("note"))
        if action == "update":
            return desk.update_contact(args.get("contact_id"), **{
                k: args.get(k) for k in ("name", "handle", "phone", "email", "company", "tags")
            })
        if action == "get":
            return desk.get_contact(args.get("contact_id"))
        if action == "search":
            return desk.search_contacts(args.get("query") or "", args.get("limit") or 10)
        if action == "note":
            return desk.add_note(agent, args.get("note") or "", args.get("contact_id"), args.get("deal_id"))
        raise QuestDeskError("action must be one of: add, update, get, search, note")

    return _run(go)


def handle_questdesk_deal(args: dict, **_kw) -> str:
    action = (args.get("action") or "").strip().lower()
    agent = resolve_agent(args.get("agent"))

    def go() -> dict:
        desk = _desk()
        if action == "create":
            return desk.create_deal(
                agent, args.get("title"), contact_id=args.get("contact_id"),
                contact_name=args.get("contact_name"), handle=args.get("handle"),
                value=args.get("value"), currency=args.get("currency"), stage=args.get("stage"),
                note=args.get("note"), next_action=args.get("next_action"),
                next_action_due=args.get("next_action_due"),
            )
        if action == "move":
            return desk.move_deal(agent, args.get("deal_id"), args.get("stage"), args.get("note"))
        if action == "update":
            return desk.update_deal(agent, args.get("deal_id"), title=args.get("title"),
                                    value=args.get("value"), currency=args.get("currency"),
                                    next_action=args.get("next_action"),
                                    next_action_due=args.get("next_action_due"))
        if action == "lose":
            return desk.lose_deal(agent, args.get("deal_id"), args.get("loss_reason") or args.get("note"))
        if action == "get":
            return desk.get_deal(args.get("deal_id"))
        if action == "list":
            return desk.list_deals(stage=args.get("stage"), status=args.get("status") or "open",
                                   contact_id=args.get("contact_id"), query=args.get("query"),
                                   limit=args.get("limit") or 20)
        if action == "board":
            return desk.board()
        if action == "radar":
            return desk.radar(stale_days=args.get("stale_days") or 7, limit=args.get("limit") or 10)
        if action == "stages":
            return {"stages": desk.stages()}
        raise QuestDeskError("action must be one of: create, move, update, lose, get, list, board, radar, stages")

    return _run(go)


def handle_questdesk_rewards(args: dict, **_kw) -> str:
    action = (args.get("action") or "").strip().lower()
    agent = resolve_agent(args.get("agent"))

    def go() -> dict:
        desk = _desk()
        if action == "wallet":
            return desk.wallet(agent)
        if action == "quests":
            return desk.quests(agent)
        if action == "leaderboard":
            return desk.leaderboard(args.get("limit") or 10)
        if action == "catalog":
            return {
                "stage_tokens": desk.stages(),
                "special_tokens": [t.as_dict() for t in R.SPECIAL_TOKENS.values()],
                "rules": [
                    f"Advancing a deal needs a note of ≥{R.MIN_EVIDENCE_CHARS} chars describing what happened.",
                    f"Stage tokens mint once per deal, only after ≥{R.MIN_STAGE_DWELL_SECONDS // 60} min in the previous stage.",
                    "Skipping a stage forfeits its token and the deal's Odyssey.",
                    "Backward moves never mint tokens.",
                ],
            }
        raise QuestDeskError("action must be one of: wallet, quests, leaderboard, catalog")

    return _run(go)
