"""``anthos questdesk`` CLI + the ``/pipeline`` in-chat slash command.

  anthos questdesk init [--preset NAME | --stages "A,B,C"]
  anthos questdesk presets | board | radar | quests | wallet | leaderboard | catalog
  anthos questdesk export [--out PATH]

``/pipeline [board|radar|quests|wallet|leaderboard|catalog]`` renders the same
views as compact plain text, so a Telegram user can check the board without
spending an agent turn.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from plugins.questdesk import render
from plugins.questdesk import rewards as R
from plugins.questdesk.store import PRESETS, QuestDesk, QuestDeskError
from plugins.questdesk.tools import resolve_agent

_VIEWS = ("board", "radar", "quests", "wallet", "leaderboard", "catalog")


def _view(desk: QuestDesk, view: str, agent: str) -> str:
    if view == "board":
        return render.board(desk.board())
    if view == "radar":
        return render.radar(desk.radar())
    if view == "quests":
        return render.quests(desk.quests(agent))
    if view == "wallet":
        return render.wallet(desk.wallet(agent))
    if view == "leaderboard":
        return render.leaderboard(desk.leaderboard())
    if view == "catalog":
        return render.catalog(desk.stages(), [t.as_dict() for t in R.SPECIAL_TOKENS.values()])
    raise QuestDeskError(f"Unknown view '{view}'. Try: {', '.join(_VIEWS)}")


def pipeline_slash(raw_args: str = "") -> str:
    """Handler for ``/pipeline`` in CLI and gateway sessions."""
    view = (raw_args or "").strip().split()[0].lower() if (raw_args or "").strip() else "board"
    try:
        desk = QuestDesk()
        agent = resolve_agent()
        text = _view(desk, view, agent)
        if view == "board":
            radar = desk.radar()
            if radar["count"]:
                text += f"\n🛰️ {radar['count']} deal(s) on the follow-up radar — /pipeline radar"
        return text
    except QuestDeskError as exc:
        return f"⚠️ {exc}"


def register_cli(subparser: argparse.ArgumentParser) -> None:
    subs = subparser.add_subparsers(dest="questdesk_command")
    init_p = subs.add_parser("init", help="Choose the pipeline stages")
    group = init_p.add_mutually_exclusive_group(required=True)
    group.add_argument("--preset", choices=sorted(PRESETS), help="Built-in niche pipeline")
    group.add_argument("--stages", help='Comma-separated custom stages, e.g. "Lead,Call,Won"')
    subs.add_parser("presets", help="List built-in pipeline presets")
    for view in _VIEWS:
        p = subs.add_parser(view, help=f"Show the {view}")
        if view in ("wallet", "quests"):
            p.add_argument("--agent", help="Agent name (default: active profile)")
    exp = subs.add_parser("export", help="Export deals + contacts to CSV")
    exp.add_argument("--out", help="Output path (default: <ANTHOS_HOME>/questdesk/export.csv)")


def questdesk_command(args: argparse.Namespace) -> int:
    sub = getattr(args, "questdesk_command", None)
    if not sub:
        print("usage: anthos questdesk {init,presets,board,radar,quests,wallet,leaderboard,catalog,export}")
        return 2
    try:
        if sub == "presets":
            for name, labels in PRESETS.items():
                print(f"{name:<11} {' → '.join(labels)}")
            return 0
        desk = QuestDesk()
        if sub == "init":
            labels = [s for s in (args.stages or "").split(",")] if args.stages else None
            stages = desk.set_pipeline(preset=args.preset, labels=labels)
            print("Pipeline set:")
            for s in stages:
                print(f"  {s['position']}. {s['label']:<22} {s['token']} +{s['xp']} XP")
            return 0
        if sub == "export":
            from anthos_constants import display_anthos_home

            out = Path(args.out) if args.out else desk.db_path.parent / "export.csv"
            n = desk.export_csv(out)
            shown = str(out) if args.out else f"{display_anthos_home()}/questdesk/export.csv"
            print(f"Exported {n} deal(s) to {shown}")
            return 0
        print(_view(desk, sub, resolve_agent(getattr(args, "agent", None))))
        return 0
    except QuestDeskError as exc:
        print(f"error: {exc}")
        return 1
