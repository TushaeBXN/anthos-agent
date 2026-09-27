"""The learning loop: notice a gap, research, write notes, practice, check, learn, repeat."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass

from . import prompts
from .config import Config
from .llm import LLM, LLMError
from .practice import extract_code, run_code
from .research import Researcher
from .skills import Skill, SkillLibrary, slugify


def log(msg: str) -> None:
    print(f"[smart9b] {msg}", flush=True)


class Journal:
    def __init__(self, path):
        self.path = path

    def write(self, **entry) -> None:
        entry["time"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def entries(self) -> list[dict]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out


@dataclass
class Outcome:
    passed: bool
    answer: str
    skill: str
    attempts: int


class Agent:
    def __init__(self, cfg: Config, review: bool = False, ask=input):
        self.cfg = cfg
        self.worker = LLM(cfg.worker)
        self.teacher = LLM(cfg.teacher) if cfg.teacher else None
        self.library = SkillLibrary(cfg.skills_dir)
        self.researcher = Researcher(cfg.search_backend, cfg.searxng_url)
        self.journal = Journal(cfg.journal_path)
        self.review = review
        self.ask = ask

    # ---- 1. notice the gap ------------------------------------------------
    def find_skill(self, task: str) -> Skill | None:
        # Keyword search narrows the library to a few candidates; the model then
        # reads their descriptions and decides, like skimming a table of contents.
        hits = self.library.search(task[:500], k=3)
        if not hits:
            return None
        menu = "\n".join(f"- {s.name}: {s.description} ({s.status})" for _, s in hits)
        try:
            pick = self.worker.ask_json(prompts.PICK_SKILL, f"TASK:\n{task[:1500]}\n\nMY NOTES:\n{menu}")
        except (ValueError, json.JSONDecodeError):
            return None
        name = pick.get("skill") if isinstance(pick, dict) else None
        for _, skill in hits:
            if name and skill.name == name:
                log(f"I already have notes for this: '{skill.name}' ({skill.status})")
                return skill
        return None

    # ---- 2 + 3. research and write notes ----------------------------------
    def learn(self, task: str) -> Skill:
        log("I don't know how to do this yet. Researching...")
        plan = self.worker.ask_json(prompts.PLAN_RESEARCH, f"Task: {task}")
        queries = [q for q in plan.get("queries", []) if isinstance(q, str)][:3] or [task]
        name = plan.get("skill_name") or task
        log(f"Searching: {queries}")
        sources = self.researcher.gather(queries, self.cfg.max_sources)

        if not sources and self.teacher:
            log("Web search came back empty; asking the teacher instead.")
            return self.teach(name, task)

        reading = "\n\n".join(f"SOURCE {i+1}: {s['title']} ({s['url']})\n{s['text']}"
                              for i, s in enumerate(sources))
        if not reading:
            log("Couldn't read any sources; writing notes from what I already know.")
            reading = "(no sources found: use your own knowledge, be conservative)"
        body = self.worker.ask(prompts.WRITE_SKILL,
                               f"Task I need to be able to do: {task}\n\n{reading}")
        skill = Skill(name=slugify(name), description=plan.get("description", task)[:120],
                      body=body, status="untested", sources=[s["url"] for s in sources])
        path = self.library.save(skill)
        log(f"Wrote new notes: {path}")
        return skill

    # ---- 4 + 5. practice and check ----------------------------------------
    def attempt(self, task: str, skill: Skill, lessons: list[str]) -> dict:
        lesson_text = ("Lessons from earlier tries on THIS task:\n" +
                       "\n".join(f"- {l}" for l in lessons)) if lessons else ""
        system = prompts.SOLVE.format(skill=skill.as_prompt(), lessons=lesson_text)
        answer = self.worker.ask(system, task)

        run_output, code_ok = "", None
        code = extract_code(answer)
        if code:
            lang, src = code
            result = run_code(lang, src, self.cfg.sandbox_dir, self.cfg.code_timeout,
                              confirm=not self.cfg.auto_run_code, ask=self.ask)
            run_output = result.output
            code_ok = result.ok if result.ran else None
            log(f"Ran the code: {'worked' if result.ok else 'failed'}" if result.ran
                else "Code not run.")

        passed, grade = self.check(task, skill, answer, run_output, code_ok)
        return {"system": system, "answer": answer, "run_output": run_output,
                "code_ok": code_ok, "grade": grade, "passed": passed}

    def check(self, task, skill, answer, run_output, code_ok) -> tuple[bool, dict]:
        # Hard evidence first: code that crashes is a fail, no matter what the model thinks.
        if code_ok is False:
            return False, {"reason": "code failed", "output": run_output}
        checklist = skill.checklist() or ["The answer fully completes the task as asked."]
        evidence = f"TASK:\n{task}\n\nWORK:\n{answer}"
        if run_output:
            evidence += f"\n\nPROGRAM OUTPUT:\n{run_output}"
        evidence += "\n\nCHECKLIST:\n" + "\n".join(f"- {c}" for c in checklist)
        try:
            grade = self.worker.ask_json(prompts.GRADE, evidence, think=True)
        except (LLMError, ValueError, json.JSONDecodeError) as exc:
            grade = {"overall_pass": False, "error": str(exc)}
        items = grade.get("items", []) if isinstance(grade, dict) else []
        passed = bool(grade.get("overall_pass")) if isinstance(grade, dict) else False
        # Don't trust a PASS that contradicts its own item list.
        if items and not all(i.get("pass") for i in items if isinstance(i, dict)):
            passed = False
        return passed, grade

    # ---- the whole loop ---------------------------------------------------
    def run(self, task: str) -> Outcome:
        skill = self.find_skill(task) or self.learn(task)
        lessons: list[str] = []
        last = {}
        for n in range(1, self.cfg.max_attempts + 1):
            log(f"Attempt {n}/{self.cfg.max_attempts} using '{skill.name}'")
            last = self.attempt(task, skill, lessons)
            approved = None
            if last["passed"] and self.review:
                print("\n" + last["answer"] + "\n")
                approved = self.ask("It thinks this is correct. Do you approve? [y/N] ").strip().lower() == "y"
                if not approved:
                    last["passed"] = False
                    last["grade"] = {"reason": "you rejected it",
                                     "your_feedback": self.ask("What's wrong with it? ")}
            self.journal.write(task=task, skill=skill.name, attempt=n, approved=approved,
                               verified_by_code=last["code_ok"] is True, **last)
            if last["passed"]:
                skill.status = "proven"
                skill.successes += 1
                self.library.save(skill)
                log(f"Success. '{skill.name}' is now proven ({skill.successes} wins).")
                return Outcome(True, last["answer"], skill.name, n)

            feedback = json.dumps(last["grade"])[:2000]
            lesson = self.worker.ask(prompts.REFLECT,
                                     f"Task: {task}\n\nMy work:\n{last['answer'][:3000]}\n\n"
                                     f"Feedback:\n{feedback}\n\n{last['run_output'][:1500]}", think=False)
            log(f"Lesson: {lesson}")
            lessons.append(lesson)
            skill.add_lesson(lesson)
            skill.failures += 1
            self.library.save(skill)

        skill.status = "failed"
        self.library.save(skill)
        self.queue_for_teacher(task, skill, lessons, last)
        return Outcome(False, last.get("answer", ""), skill.name, self.cfg.max_attempts)

    # ---- asking for help --------------------------------------------------
    def queue_for_teacher(self, task, skill, lessons, last) -> None:
        path = self.cfg.queue_dir / f"{time.strftime('%Y%m%d-%H%M%S')}-{skill.name}.json"
        path.write_text(json.dumps({"task": task, "skill": skill.name, "lessons": lessons,
                                    "last_answer": last.get("answer", ""),
                                    "last_feedback": last.get("grade", {}),
                                    "run_output": last.get("run_output", "")}, indent=2))
        who = "the teacher" if self.teacher else "the teacher (run `smart9b teach --queue` once one is set up)"
        log(f"Stuck after {self.cfg.max_attempts} tries. Wrote up the problem for {who}: {path}")

    def teach(self, name: str, description: str) -> Skill:
        if not self.teacher:
            raise LLMError("no teacher model configured in smart9b.json")
        log(f"Teacher is writing notes for '{name}'...")
        body = self.teacher.ask(prompts.TEACHER_SKILL, f"Skill to teach: {name}\nWhat it is for: {description}")
        skill = Skill(name=slugify(name), description=description[:120], body=body, status="taught")
        self.library.save(skill)
        return skill

    def unstick(self) -> int:
        """Have the teacher answer every problem in the queue. Returns how many were fixed."""
        if not self.teacher:
            raise LLMError("no teacher model configured in smart9b.json")
        done = 0
        for path in sorted(self.cfg.queue_dir.glob("*.json")):
            item = json.loads(path.read_text())
            skill = self.library.get(item["skill"])
            notes = skill.as_prompt() if skill else "(no notes)"
            log(f"Teacher looking at: {item['task'][:80]}")
            body = self.teacher.ask(prompts.TEACHER_UNSTICK,
                                    f"TASK:\n{item['task']}\n\nSTUDENT NOTES:\n{notes}\n\n"
                                    f"LESSONS IT WROTE:\n" + "\n".join(item["lessons"]) +
                                    f"\n\nLAST ATTEMPT:\n{item['last_answer'][:4000]}\n\n"
                                    f"FEEDBACK:\n{json.dumps(item['last_feedback'])[:2000]}\n"
                                    f"{item.get('run_output', '')[:1500]}")
            new = Skill(name=item["skill"], description=skill.description if skill else item["task"][:120],
                        body=body, status="taught",
                        sources=skill.sources if skill else [])
            self.library.save(new)
            path.rename(path.with_suffix(".done"))
            done += 1
        return done
