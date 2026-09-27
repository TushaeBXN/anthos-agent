"""Command line: python -m smart9b <command>."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from . import dataset, prompts
from .agent import Agent, log
from .config import load_config
from .llm import LLMError
from .skills import Skill, parse_skill


PACKAGE_ROOT = Path(__file__).resolve().parent.parent


def cmd_init(agent: Agent, args) -> int:
    """Copy the example config and starter skills into the data folder."""
    home = agent.cfg.home
    cfg = home / "smart9b.json"
    if not cfg.exists():
        shutil.copy(PACKAGE_ROOT / "smart9b.example.json", cfg)
        log(f"Wrote {cfg}; set worker.model to the name `ollama list` shows.")
    for src in sorted((PACKAGE_ROOT / "starter_skills").glob("*.md")):
        dest = agent.cfg.skills_dir / src.name
        if not dest.exists():
            shutil.copy(src, dest)
            log(f"Added starter skill {src.stem}")
    log(f"Ready. Data folder: {home}")
    return 0


def cmd_do(agent: Agent, args) -> int:
    task = " ".join(args.task)
    if args.file:
        task += "\n\n" + Path(args.file).read_text()
    for img in args.image:
        if not Path(img).is_file():
            print(f"error: image not found: {img}", file=sys.stderr)
            return 2
    out = agent.run(task, images=args.image)
    print("\n" + "=" * 60)
    print(out.answer)
    print("=" * 60)
    print(f"{'PASSED' if out.passed else 'NOT DONE'} after {out.attempts} attempt(s), skill: {out.skill}")
    return 0 if out.passed else 1


def cmd_learn(agent: Agent, args) -> int:
    agent.learn(" ".join(args.topic))
    return 0


def cmd_teach(agent: Agent, args) -> int:
    if args.queue:
        log(f"Teacher answered {agent.unstick()} stuck problem(s).")
    for topic in args.topics:
        agent.teach(topic, topic)
    return 0


def cmd_import(agent: Agent, args) -> int:
    """Slim existing SKILL.md files (e.g. from a skills repo) into 9B-sized notes."""
    model = agent.teacher or agent.worker
    if not agent.teacher:
        log("No teacher configured; the 9B will slim the skills itself (lower quality).")
    paths = []
    for p in map(Path, args.paths):
        paths += sorted(p.rglob("SKILL.md")) if p.is_dir() else [p]
    for p in paths:
        src = parse_skill(p.read_text(), p)
        if agent.library.get(src.name) and not args.overwrite:
            log(f"skip {src.name} (already in library)")
            continue
        body = model.ask(prompts.SLIM_SKILL, f"# {src.name}\n{src.description}\n\n{src.body[:20000]}")
        agent.library.save(Skill(name=src.name, description=src.description[:120], body=body,
                                 status="taught" if agent.teacher else "untested"))
        log(f"imported {src.name}")
    return 0


def cmd_skills(agent: Agent, args) -> int:
    skills = agent.library.all()
    if args.query:
        for score, s in agent.library.search(" ".join(args.query), k=10):
            print(f"{score:5.1f}  {s.status:9} {s.name}  - {s.description}")
        return 0
    for s in skills:
        print(f"{s.status:9} +{s.successes}/-{s.failures}  {s.name}  - {s.description}")
    print(f"\n{len(skills)} skills, {sum(s.status == 'proven' for s in skills)} proven, "
          f"{len(list(agent.cfg.queue_dir.glob('*.json')))} waiting for the teacher")
    return 0


def cmd_dataset(agent: Agent, args) -> int:
    counts = dataset.build(agent.journal.entries(), agent.cfg.data_dir,
                           include_self_graded=args.include_self_graded)
    log(f"Wrote {counts['train']} training and {counts['valid']} validation examples to "
        f"{agent.cfg.data_dir}")
    if counts["train"] < 100:
        log("Tip: aim for a few hundred examples before fine-tuning; keep using `do --review`.")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="smart9b", description="A self-teaching loop for a small local model.")
    ap.add_argument("--home", help="data folder (default: current folder or $SMART9B_HOME)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="set up a data folder with config and starter skills")
    p.set_defaults(fn=cmd_init)

    p = sub.add_parser("do", help="do a task, learning the skill first if needed")
    p.add_argument("task", nargs="+")
    p.add_argument("--file", help="attach a file's contents to the task")
    p.add_argument("--image", action="append", default=[],
                   help="attach a picture (repeatable; needs a vision model)")
    p.add_argument("--review", action="store_true", help="you approve each result (best training data)")
    p.set_defaults(fn=cmd_do)

    p = sub.add_parser("learn", help="research a topic online and write skill notes")
    p.add_argument("topic", nargs="+")
    p.set_defaults(fn=cmd_learn)

    p = sub.add_parser("teach", help="have the teacher model write notes or unstick problems")
    p.add_argument("topics", nargs="*")
    p.add_argument("--queue", action="store_true", help="answer everything in teacher_queue/")
    p.set_defaults(fn=cmd_teach)

    p = sub.add_parser("import", help="slim existing SKILL.md files into the library")
    p.add_argument("paths", nargs="+")
    p.add_argument("--overwrite", action="store_true")
    p.set_defaults(fn=cmd_import)

    p = sub.add_parser("skills", help="list or search the skill library")
    p.add_argument("query", nargs="*")
    p.set_defaults(fn=cmd_skills)

    p = sub.add_parser("dataset", help="build LoRA training data from successful work")
    p.add_argument("--include-self-graded", action="store_true",
                   help="also use results only the model itself checked (noisier)")
    p.set_defaults(fn=cmd_dataset)

    args = ap.parse_args(argv)
    agent = Agent(load_config(args.home), review=getattr(args, "review", False))
    try:
        return args.fn(agent, args)
    except LLMError as exc:
        print(f"error: {exc}", file=sys.stderr)
        print("Is Ollama running? Try: ollama serve  (and: ollama list)", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
