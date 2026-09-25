"""Tests for the QuestDesk plugin (gamified Telegram-first CRM).

Exercises the real SQLite store under a temp ANTHOS_HOME through the tool
handlers the model calls. The clock is driven via ``store._now`` so dwell,
streak and stall rules are deterministic.
"""

from __future__ import annotations

import json

import pytest


@pytest.fixture(autouse=True)
def _isolate_home(tmp_path, monkeypatch):
    home = tmp_path / ".anthos"
    home.mkdir()
    monkeypatch.setenv("ANTHOS_HOME", str(home))
    yield home


class Clock:
    def __init__(self, start: float = 1_800_000_000.0):
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


@pytest.fixture
def clock(monkeypatch):
    from plugins.questdesk import store

    c = Clock()
    monkeypatch.setattr(store, "_now", c)
    return c


def deal(args):
    from plugins.questdesk.tools import handle_questdesk_deal

    return json.loads(handle_questdesk_deal({"agent": "closer", **args}))


def contact(args):
    from plugins.questdesk.tools import handle_questdesk_contact

    return json.loads(handle_questdesk_contact({"agent": "closer", **args}))


def rewards(args):
    from plugins.questdesk.tools import handle_questdesk_rewards

    return json.loads(handle_questdesk_rewards({"agent": "closer", **args}))


def token_ids(result):
    return [r["token"] for r in result.get("rewards", [])]


def new_deal(**extra):
    r = deal({"action": "create", "title": "Website", "contact_name": "Ana", "handle": "ana", "value": 1000, **extra})
    assert r["success"], r
    return r


def walk(deal_id, clock, stages, step=3600):
    out = []
    for s in stages:
        clock.advance(step)
        r = deal({"action": "move", "deal_id": deal_id, "stage": s, "note": f"Real progress: reached {s} today"})
        assert r["success"], r
        out.append(r)
    return out


def labels():
    from plugins.questdesk.store import QuestDesk

    return [s["label"] for s in QuestDesk().stages()]


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def test_register_wires_tools_cli_slash_and_skill():
    import plugins.questdesk as plugin

    calls = {"tools": [], "cli": [], "cmd": [], "skill": []}

    class Ctx:
        def register_tool(self, **kw):
            calls["tools"].append(kw)

        def register_cli_command(self, **kw):
            calls["cli"].append(kw["name"])

        def register_command(self, name, handler, **kw):
            calls["cmd"].append(name)

        def register_skill(self, name, path, **kw):
            assert path.exists()
            calls["skill"].append(name)

    plugin.register(Ctx())
    assert {t["toolset"] for t in calls["tools"]} == {"questdesk"}
    for t in calls["tools"]:
        assert t["schema"]["name"] == t["name"]
        assert t["check_fn"]() is True
    assert calls["cli"] == ["questdesk"]
    assert calls["cmd"] == ["pipeline"]
    assert calls["skill"] == ["sales-pilot"]


def test_manifest_lists_every_registered_tool():
    from pathlib import Path

    import yaml

    import plugins.questdesk as plugin

    manifest = yaml.safe_load((Path(plugin.__file__).parent / "plugin.yaml").read_text())
    assert set(manifest["provides_tools"]) == {name for name, *_ in plugin._TOOLS}


def test_skill_description_meets_authoring_limit():
    import re
    from pathlib import Path

    import plugins.questdesk as plugin

    text = (Path(plugin.__file__).parent / "SKILL.md").read_text()
    desc = re.search(r"^description: (.*)$", text, re.MULTILINE).group(1)
    assert len(desc) <= 60 and desc.endswith(".")


# ---------------------------------------------------------------------------
# Token economy
# ---------------------------------------------------------------------------

def test_full_journey_mints_every_stage_token_then_odyssey_and_lightning(clock):
    r = new_deal()
    assert token_ids(r) == ["spark"]
    did = r["deal"]["id"]
    stages = labels()
    results = walk(did, clock, stages[1:])

    from plugins.questdesk.rewards import STAGE_TOKENS

    minted = [t for res in results for t in token_ids(res)]
    for pos in range(1, len(stages)):
        assert STAGE_TOKENS[pos].id in minted
    final = token_ids(results[-1])
    assert "odyssey" in final and "lightning" in final
    assert results[-1]["deal"]["status"] == "won"

    got = deal({"action": "get", "deal_id": did})
    assert len([t for t in got["tokens_earned"] if "Odyssey" in t["label"]]) == 1


def test_stage_tokens_mint_once_per_deal_and_never_on_backward_moves(clock):
    did = new_deal()["deal"]["id"]
    stages = labels()
    first = walk(did, clock, [stages[1]])[0]
    assert token_ids(first) == ["insight"] or "insight" in token_ids(first)

    clock.advance(3600)
    back = deal({"action": "move", "deal_id": did, "stage": stages[0]})
    assert back["success"] and "insight" not in token_ids(back)

    again = walk(did, clock, [stages[1]])[0]
    assert "insight" not in token_ids(again)


def test_advancing_requires_evidence_note(clock):
    did = new_deal()["deal"]["id"]
    clock.advance(3600)
    r = deal({"action": "move", "deal_id": did, "stage": 1, "note": "ok"})
    assert r["success"] is False and "evidence" in r["error"]
    # Deal did not move.
    assert deal({"action": "get", "deal_id": did})["deal"]["stage_position"] == 0


def test_fast_moves_withhold_token_and_forfeit_odyssey(clock):
    did = new_deal()["deal"]["id"]
    stages = labels()
    clock.advance(60)  # under the dwell window
    r = deal({"action": "move", "deal_id": did, "stage": 1, "note": "Qualified after a quick chat"})
    assert r["success"] and r["deal"]["stage_position"] == 1  # move applied
    assert "insight" not in token_ids(r)
    assert any("withheld" in n for n in r["notices"])

    results = walk(did, clock, stages[2:])
    assert "odyssey" not in token_ids(results[-1])


def test_skipping_stages_forfeits_skipped_tokens_and_odyssey(clock):
    did = new_deal()["deal"]["id"]
    stages = labels()
    clock.advance(3600)
    r = deal({"action": "move", "deal_id": did, "stage": 3, "note": "Jumped straight to negotiation"})
    assert token_ids(r) == ["duel"] or "duel" in token_ids(r)
    assert "insight" not in token_ids(r) and "scroll" not in token_ids(r)
    results = walk(did, clock, stages[4:])
    assert "odyssey" not in token_ids(results[-1])


def test_odyssey_outside_seven_days_gets_no_lightning(clock):
    did = new_deal()["deal"]["id"]
    results = walk(did, clock, labels()[1:], step=2 * 86400)
    final = token_ids(results[-1])
    assert "odyssey" in final and "lightning" not in final


def test_phoenix_for_reviving_stalled_deal(clock):
    did = new_deal()["deal"]["id"]
    clock.advance(15 * 86400)
    radar = deal({"action": "radar"})
    assert any("Phoenix" in " ".join(d["why"]) for d in radar["deals"])
    r = walk(did, clock, [labels()[1]], step=1)[0]
    assert "phoenix" in token_ids(r)


def test_blaze_streak_on_three_consecutive_days(clock):
    stages = labels()
    ids = []
    for _ in range(3):
        ids.append(new_deal(title=f"D{len(ids)}")["deal"]["id"])
    awarded = []
    for i, did in enumerate(ids):
        res = walk(did, clock, [stages[1]], step=86400 if i else 3600)[0]
        awarded.append("blaze" in token_ids(res))
    assert awarded == [False, False, True]


def test_lose_needs_reason_and_earns_honor_once(clock):
    did = new_deal()["deal"]["id"]
    assert deal({"action": "lose", "deal_id": did, "loss_reason": "meh"})["success"] is False
    clock.advance(3600)
    r = deal({"action": "lose", "deal_id": did, "loss_reason": "Chose a competitor on price"})
    assert r["deal"]["status"] == "lost" and "honor" in token_ids(r)
    assert deal({"action": "lose", "deal_id": did, "loss_reason": "Chose a competitor on price"})["success"] is False


def test_daily_quest_and_trifecta_pay_out_once(clock, monkeypatch):
    from plugins.questdesk import rewards as R

    picked = [q for q in R.QUEST_POOL if q.id in ("new_deals_2", "plan_3", "notes_4")]
    monkeypatch.setattr(R, "daily_quests", lambda day: picked)

    for i in range(3):
        did = new_deal(title=f"Q{i}", next_action="Send proposal", next_action_due="1d")["deal"]["id"]
    for _ in range(4):
        r = contact({"action": "note", "deal_id": did, "note": "Client asked about delivery dates"})
    status = rewards({"action": "quests"})
    assert all(q["done"] and q["claimed"] for q in status["quests"])

    w = rewards({"action": "wallet"})
    counts = {t["label"]: t["count"] for t in w["tokens"]}
    assert counts["🎯 Quest"] == 3
    assert counts["🌈 Trifecta"] == 1


def test_level_up_reported_when_threshold_crossed(clock):
    from plugins.questdesk import rewards as R

    did = new_deal()["deal"]["id"]
    results = walk(did, clock, labels()[1:])
    ups = [r for r in results if "level_up" in r]
    assert ups, "a full journey should cross at least one level threshold"
    total = rewards({"action": "wallet"})
    assert total["level"] == R.level_for(total["xp"])["level"]


def test_xp_is_sum_of_ledger_and_leaderboard_orders_by_xp(clock):
    did = new_deal()["deal"]["id"]
    walk(did, clock, labels()[1:3])
    deal({"action": "create", "title": "Other", "contact_name": "Bo", "agent": "rookie"})
    w = rewards({"action": "wallet"})
    assert w["xp"] == sum(t["xp"] for t in w["tokens"])
    lb = rewards({"action": "leaderboard"})["leaders"]
    assert [r["xp"] for r in lb] == sorted((r["xp"] for r in lb), reverse=True)
    assert lb[0]["agent"] == "closer"


# ---------------------------------------------------------------------------
# CRM behavior
# ---------------------------------------------------------------------------

def test_contact_add_dedupes_on_handle_phone_email(clock):
    a = contact({"action": "add", "name": "Ana", "handle": "ana", "email": "a@x.io"})
    assert a["created"] is True
    for dup in ({"handle": "@ANA"}, {"email": "A@X.IO"}):
        b = contact({"action": "add", "name": "Ana 2", **dup})
        assert b["created"] is False and b["contact"]["id"] == a["contact"]["id"]
    found = contact({"action": "search", "query": "ana"})
    assert found["count"] == 1


def test_board_totals_match_deals(clock):
    for v in (100, 250.5, 1000):
        new_deal(title=f"V{v}", value=v)
    board = deal({"action": "board"})
    assert board["open_deals"] == 3
    assert board["open_value"] == pytest.approx(sum(c["value"] for c in board["columns"]))


def test_radar_flags_overdue_first(clock):
    fresh = new_deal(title="Fresh", next_action="Call", next_action_due="3d")["deal"]["id"]
    late = new_deal(title="Late", next_action="Call", next_action_due="1h")["deal"]["id"]
    clock.advance(2 * 3600)
    radar = deal({"action": "radar"})
    assert radar["deals"][0]["id"] == late
    assert fresh not in [d["id"] for d in radar["deals"]]


def test_pipeline_preset_and_relabel_rules(clock):
    from plugins.questdesk.store import PRESETS, QuestDesk, QuestDeskError

    desk = QuestDesk()
    desk.set_pipeline(preset="clinic")
    assert labels() == list(PRESETS["clinic"])
    did = new_deal()["deal"]["id"]
    # Same stage count relabels in place and keeps the deal's position.
    desk.set_pipeline(labels=[f"S{i}" for i in range(len(PRESETS["clinic"]))])
    assert deal({"action": "get", "deal_id": did})["deal"]["stage"] == "S0"
    with pytest.raises(QuestDeskError):
        desk.set_pipeline(labels=["A", "B", "C"])


def test_errors_are_json_not_exceptions(clock):
    assert deal({"action": "move", "deal_id": 999, "stage": 1, "note": "x" * 20})["success"] is False
    assert deal({"action": "bogus"})["success"] is False
    assert deal({"action": "create", "title": "x", "contact_name": "y", "next_action_due": "someday"})["success"] is False


def test_pipeline_slash_and_cli_views(clock, capsys):
    import argparse

    from plugins.questdesk.cli import pipeline_slash, questdesk_command, register_cli

    new_deal()
    assert "QuestDesk pipeline" in pipeline_slash("")
    for view in ("radar", "quests", "wallet", "leaderboard", "catalog"):
        assert pipeline_slash(view).strip()
    assert pipeline_slash("nope").startswith("⚠️")

    parser = argparse.ArgumentParser()
    register_cli(parser)
    assert questdesk_command(parser.parse_args(["init", "--stages", "A,B,C,D,E,F"])) == 0
    assert questdesk_command(parser.parse_args(["board"])) == 0
    assert questdesk_command(parser.parse_args(["export"])) == 0
    assert "Exported 1 deal" in capsys.readouterr().out
