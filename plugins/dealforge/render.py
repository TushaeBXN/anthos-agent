"""Compact plain-text renderers for chat surfaces (Telegram, CLI).

Plain text + emoji only — no Markdown — so the output survives every
gateway adapter's escaping rules unchanged.
"""

from __future__ import annotations

from typing import Optional


def _money(v: float) -> str:
    return f"{v:,.0f}" if v == int(v) else f"{v:,.2f}"


def _bar(done: int, total: int, width: int = 10) -> str:
    filled = 0 if total <= 0 else round(width * min(done, total) / total)
    return "▰" * filled + "▱" * (width - filled)


def board(b: dict) -> str:
    lines = ["📊 DealForge pipeline"]
    for col in b["columns"]:
        lines.append(f"{col['token'].split()[0]} {col['stage']} — {col['count']} deal(s), {_money(col['value'])}")
        for d in col["top"]:
            flag = " ⏰" if d["overdue"] else ""
            lines.append(f"   #{d['id']} {d['title']} · {_money(d['value'])} · 🌡{d['score']}{flag}")
    rate = f"{b['win_rate'] * 100:.0f}%" if b["win_rate"] is not None else "—"
    lines.append(
        f"Open {b['open_deals']} ({_money(b['open_value'])}) · Won {b['won']} · Lost {b['lost']} · "
        f"Win rate {rate} · Overdue {b['overdue']}"
    )
    return "\n".join(lines)


def radar(r: dict) -> str:
    if not r["deals"]:
        return "🛰️ Radar clear — every open deal has a fresh next action."
    lines = [f"🛰️ Follow-up radar — {r['count']} deal(s) need attention"]
    for d in r["deals"]:
        lines.append(f"#{d['id']} {d['title']} [{d['stage']}] 🌡{d['score']} — {', '.join(d['why'])}")
    return "\n".join(lines)


def quests(q: dict) -> str:
    lines = [f"🎯 Daily quests ({q['day']})"]
    for item in q["quests"]:
        mark = "✅" if item["done"] else "⬜"
        lines.append(f"{mark} {item['title']} {_bar(item['progress'], item['target'], 6)} "
                     f"{item['progress']}/{item['target']}")
    lines.append(q["reward"])
    return "\n".join(lines)


def wallet(w: dict) -> str:
    nxt = f" · {w['xp_to_next']} XP to next level" if w["next_level_xp"] else " · max level"
    lines = [
        f"👛 {w['agent']} — Lv {w['level']} {w['rank']}",
        f"{w['xp']} XP {_bar(w['xp'], w['next_level_xp'] or w['xp'])}{nxt}",
    ]
    if w["tokens"]:
        lines.append("  ".join(f"{t['label']}×{t['count']}" for t in w["tokens"]))
    else:
        lines.append("No tokens yet — create a deal to mint your first 🌱 Spark.")
    return "\n".join(lines)


def leaderboard(lb: dict) -> str:
    if not lb["leaders"]:
        return "🏁 Leaderboard is empty — first token wins the top spot."
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    lines = ["🏁 DealForge leaderboard"]
    for row in lb["leaders"]:
        place = medals.get(row["rank"], f"{row['rank']}.")
        lines.append(f"{place} {row['agent']} — {row['xp']} XP · {row['title']} · 🏆×{row['odysseys']}")
    return "\n".join(lines)


def catalog(stages: list, special: list) -> str:
    lines = ["🪙 Token catalog", "Stage tokens (one per deal per stage):"]
    for s in stages:
        lines.append(f"  {s['token']} +{s['xp']} XP — reach '{s['label']}'")
    lines.append("Special tokens:")
    for t in special:
        lines.append(f"  {t['label']} +{t['xp']} XP — {t['description']}")
    return "\n".join(lines)


def celebration(result: dict) -> Optional[str]:
    return result.get("celebration")
