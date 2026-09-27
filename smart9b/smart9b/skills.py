"""The skill library: one markdown file per skill, found by keyword search.

A skill file looks like:

    ---
    name: clean-messy-csv
    description: Fix headers, types and duplicates in a CSV file.
    status: untested        # untested | proven | failed | taught
    successes: 0
    failures: 0
    sources: https://..., https://...
    ---
    ## Steps
    ...
    ## Checklist
    ...
    ## Pitfalls
    ...
    ## Example
    ...
    ## Lessons
    - (appended after every attempt)
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

_WORD = re.compile(r"[a-z0-9]+")
_STOP = set("a an the and or of to in on for with is are be this that it as by at from "
            "how do i my me you your can what into".split())


def tokenize(text: str) -> list[str]:
    return [w for w in _WORD.findall(text.lower()) if w not in _STOP and len(w) > 1]


def slugify(text: str) -> str:
    return "-".join(tokenize(text))[:60].strip("-") or "skill"


@dataclass
class Skill:
    name: str
    description: str
    body: str
    status: str = "untested"
    successes: int = 0
    failures: int = 0
    sources: list[str] = field(default_factory=list)
    path: Path | None = None

    def section(self, title: str) -> str:
        m = re.search(rf"^## {re.escape(title)}\s*\n(.*?)(?=^## |\Z)", self.body,
                      re.MULTILINE | re.DOTALL)
        return m.group(1).strip() if m else ""

    def checklist(self) -> list[str]:
        items = []
        for line in self.section("Checklist").splitlines():
            line = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*(?:\[.?\]\s*)?", "", line).strip()
            if line:
                items.append(line)
        return items

    def add_lesson(self, lesson: str) -> None:
        lesson = " ".join(lesson.split())
        if not lesson:
            return
        if "## Lessons" not in self.body:
            self.body = self.body.rstrip() + "\n\n## Lessons\n"
        self.body = self.body.rstrip() + f"\n- {lesson}\n"

    def render(self) -> str:
        head = [
            "---",
            f"name: {self.name}",
            f"description: {self.description}",
            f"status: {self.status}",
            f"successes: {self.successes}",
            f"failures: {self.failures}",
        ]
        if self.sources:
            head.append("sources: " + ", ".join(self.sources))
        head.append("---")
        return "\n".join(head) + "\n\n" + self.body.strip() + "\n"

    def as_prompt(self) -> str:
        return f"# Skill: {self.name}\n{self.description}\n\n{self.body.strip()}"


def parse_skill(text: str, path: Path | None = None) -> Skill:
    meta: dict[str, str] = {}
    body = text
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.DOTALL)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line and not line.startswith((" ", "\t")):
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip().strip('"').strip("'")
        body = m.group(2)
    name = meta.get("name") or (path.stem if path else "skill")
    return Skill(
        name=name,
        description=meta.get("description", ""),
        body=body.strip(),
        status=meta.get("status", "untested"),
        successes=int(meta.get("successes", 0) or 0),
        failures=int(meta.get("failures", 0) or 0),
        sources=[s.strip() for s in meta.get("sources", "").split(",") if s.strip()],
        path=path,
    )


class SkillLibrary:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def all(self) -> list[Skill]:
        return [parse_skill(p.read_text(), p) for p in sorted(self.root.glob("*.md"))]

    def get(self, name: str) -> Skill | None:
        p = self.root / f"{slugify(name)}.md"
        return parse_skill(p.read_text(), p) if p.exists() else None

    def save(self, skill: Skill) -> Path:
        skill.name = slugify(skill.name)
        path = self.root / f"{skill.name}.md"
        path.write_text(skill.render())
        skill.path = path
        return path

    def search(self, query: str, k: int = 3) -> list[tuple[float, Skill]]:
        """BM25 over name (weighted x3), description (x2) and body."""
        skills = self.all()
        if not skills:
            return []
        docs = [tokenize(f"{s.name.replace('-', ' ')} " * 3 + f"{s.description} " * 2 + s.body)
                for s in skills]
        avgdl = sum(len(d) for d in docs) / len(docs) or 1
        df = Counter(t for d in docs for t in set(d))
        n = len(docs)
        q = set(tokenize(query))
        scored = []
        for skill, doc in zip(skills, docs):
            tf = Counter(doc)
            score = 0.0
            for t in q:
                if t not in tf:
                    continue
                idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                f = tf[t]
                score += idf * f * 2.2 / (f + 1.2 * (0.25 + 0.75 * len(doc) / avgdl))
            # Proven skills win ties; failed ones sink.
            score *= {"proven": 1.2, "failed": 0.6}.get(skill.status, 1.0)
            if score > 0:
                scored.append((score, skill))
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[:k]
