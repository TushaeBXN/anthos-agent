"""DealForge reward catalog — tokens, XP curve, ranks, daily quests.

Pure data + pure functions. No I/O here; ``store.py`` owns persistence and
decides *when* a token is earned. Keeping the catalog separate means the
reward economy can be tuned without touching the ledger logic.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class Token:
    id: str
    emoji: str
    name: str
    xp: int
    description: str

    def as_dict(self) -> dict:
        return {
            "token": self.id,
            "label": f"{self.emoji} {self.name}",
            "xp": self.xp,
            "description": self.description,
        }


# One token per pipeline position. A pipeline has 3–8 stages; position N
# always mints the same token, so the economy is identical across presets
# ("Qualified" in sales and "Consultation Booked" in a clinic both mint
# Insight tokens).
STAGE_TOKENS: Tuple[Token, ...] = (
    Token("spark",   "🌱", "Spark",   5,  "A new deal enters the pipeline."),
    Token("insight", "🔍", "Insight", 10, "Deal advanced to the second stage."),
    Token("scroll",  "📜", "Scroll",  15, "Deal advanced to the third stage."),
    Token("duel",    "⚔️", "Duel",    20, "Deal advanced to the fourth stage."),
    Token("pact",    "🤝", "Pact",    40, "Deal advanced to the fifth stage."),
    Token("orbit",   "🚀", "Orbit",   30, "Deal advanced to the sixth stage."),
    Token("nexus",   "🌀", "Nexus",   30, "Deal advanced to the seventh stage."),
    Token("crown",   "👑", "Crown",   30, "Deal advanced to the eighth stage."),
)

MAX_STAGES = len(STAGE_TOKENS)
MIN_STAGES = 3

SPECIAL_TOKENS: Dict[str, Token] = {
    t.id: t
    for t in (
        Token("odyssey", "🏆", "Odyssey", 100,
              "Took one deal through every stage, first to last, earning each stage token on the way."),
        Token("lightning", "⚡", "Lightning", 50,
              "Completed an Odyssey within 7 days of the deal's creation."),
        Token("phoenix", "🐦‍🔥", "Phoenix", 30,
              "Advanced a deal that had been stuck in one stage for 14+ days."),
        Token("blaze", "🔥", "Blaze", 25,
              "Advanced deals on 3, 7, 14 or 30 consecutive days."),
        Token("honor", "🛡️", "Honor", 15,
              "Closed out a dead deal honestly, with a real loss reason."),
        Token("quest", "🎯", "Quest", 20, "Completed a daily quest."),
        Token("trifecta", "🌈", "Trifecta", 40, "Completed all three daily quests in one day."),
        Token("constellation", "🌟", "Constellation", 250,
              "Collected every stage token of the current pipeline plus an Odyssey."),
    )
}


def all_tokens() -> Dict[str, Token]:
    out = {t.id: t for t in STAGE_TOKENS}
    out.update(SPECIAL_TOKENS)
    return out


def get_token(token_id: str) -> Token:
    return all_tokens()[token_id]


# ---------------------------------------------------------------------------
# Anti-gaming knobs. Tokens reward real-world progress, not tool calls.
# ---------------------------------------------------------------------------

# A stage token is only minted if the deal sat in its previous stage at
# least this long. Moves still happen — only the token is withheld.
MIN_STAGE_DWELL_SECONDS = 10 * 60
# Advancing a deal requires a note describing what actually happened.
MIN_EVIDENCE_CHARS = 12
MIN_LOSS_REASON_CHARS = 8
PHOENIX_STALL_SECONDS = 14 * 86400
LIGHTNING_WINDOW_SECONDS = 7 * 86400
BLAZE_MILESTONES = (3, 7, 14, 30)
SPARK_DAILY_CAP = 25
HONOR_DAILY_CAP = 5


# ---------------------------------------------------------------------------
# Levels
# ---------------------------------------------------------------------------

LEVELS: Tuple[Tuple[int, str], ...] = (
    (0, "Rookie Closer"),
    (50, "Lead Whisperer"),
    (150, "Deal Scout"),
    (300, "Pipeline Ranger"),
    (500, "Pact Maker"),
    (800, "Revenue Knight"),
    (1200, "Quota Crusher"),
    (1800, "Rainmaker"),
    (2600, "Legendary Rainmaker"),
    (3600, "Mythic Closer"),
)


def level_for(xp: int) -> dict:
    idx = 0
    for i, (threshold, _) in enumerate(LEVELS):
        if xp >= threshold:
            idx = i
    threshold, rank = LEVELS[idx]
    nxt = LEVELS[idx + 1][0] if idx + 1 < len(LEVELS) else None
    return {
        "level": idx + 1,
        "rank": rank,
        "xp": xp,
        "next_level_xp": nxt,
        "xp_to_next": (nxt - xp) if nxt is not None else 0,
    }


# ---------------------------------------------------------------------------
# Daily quests
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Quest:
    id: str
    title: str
    metric: str  # which counter in store.quest_counters() it reads
    target: int


QUEST_POOL: Tuple[Quest, ...] = (
    Quest("advance_3", "Advance 3 deals one stage", "advances", 3),
    Quest("qualify_2", "Move 2 deals past the first stage", "qualifies", 2),
    Quest("new_deals_2", "Log 2 new deals", "created", 2),
    Quest("close_1", "Take a deal to the final stage", "closes", 1),
    Quest("plan_3", "Set next actions on 3 deals", "next_actions", 3),
    Quest("notes_4", "Log 4 notes on contacts or deals", "notes", 4),
    Quest("revive_1", "Revive a stalled deal (earn a Phoenix)", "phoenix", 1),
    Quest("honor_1", "Close out a dead deal with a real loss reason", "honor", 1),
)

DAILY_QUEST_COUNT = 3


def daily_quests(day: str) -> List[Quest]:
    """Deterministic pick of today's quests (same for every agent)."""
    ranked = sorted(
        QUEST_POOL,
        key=lambda q: hashlib.sha256(f"{day}:{q.id}".encode()).hexdigest(),
    )
    return ranked[:DAILY_QUEST_COUNT]
