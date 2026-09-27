"""Tests run the real loop end to end against a fake Ollama HTTP server (no real model)."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from smart9b import dataset, prompts
from smart9b.__main__ import main
from smart9b.agent import Agent
from smart9b.config import load_config
from smart9b.llm import extract_json, strip_thinking
from smart9b.practice import extract_code
from smart9b.research import html_to_text
from smart9b.skills import Skill, SkillLibrary, parse_skill


class FakeModel:
    """Answers each request from a script keyed by which prompt the agent sent."""

    def __init__(self, script: dict[str, list[str]]):
        self.script = {k: list(v) for k, v in script.items()}
        self.calls: list[str] = []

    def reply(self, system: str) -> str:
        for key, marker in [("pick", "skill notes you already have"), ("plan", "web search queries"), ("write", "turn them into a practical"),
                            ("solve", "careful worker"), ("grade", "check work strictly"),
                            ("reflect", "attempt failed"), ("unstick", "failed this task several"),
                            ("teach", "expert teacher"), ("slim", "Rewrite this skill")]:
            if marker in system:
                self.calls.append(key)
                queue = self.script.get(key) or ["(no scripted reply)"]
                return queue.pop(0) if len(queue) > 1 else queue[0]
        raise AssertionError(f"unexpected prompt: {system[:80]}")


@pytest.fixture
def serve():
    servers = []

    def start(model: FakeModel) -> str:
        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                system = body["messages"][0]["content"]
                content = model.reply(system)
                if self.path.endswith("/api/chat"):
                    out = {"message": {"role": "assistant", "content": content}}
                else:
                    out = {"choices": [{"message": {"role": "assistant", "content": content}}]}
                data = json.dumps(out).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *a):
                pass

        srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        servers.append(srv)
        return f"http://127.0.0.1:{srv.server_address[1]}"

    yield start
    for s in servers:
        s.shutdown()


def make_home(tmp_path: Path, worker_url: str, teacher_url: str | None = None) -> Path:
    cfg = {"worker": {"backend": "ollama", "base_url": worker_url, "model": "fake"},
           "auto_run_code": True, "max_attempts": 2}
    if teacher_url:
        cfg["teacher"] = {"backend": "openai", "base_url": teacher_url, "model": "teacher"}
    (tmp_path / "smart9b.json").write_text(json.dumps(cfg))
    return tmp_path


GOOD_CODE = "```python\nopen('out.txt','w').write('hi')\nprint('rows in: 3, rows out: 1')\n```\n## Result\nok"
BAD_CODE = "```python\nraise ValueError('boom')\n```"
PASS = json.dumps({"items": [{"check": "ran", "pass": True, "why": "ok"}], "overall_pass": True})
PICK_CSV = '{"skill": "clean-messy-csv"}'
SKILL_BODY = "## Steps\n1. Do it.\n\n## Checklist\n- It ran.\n\n## Pitfalls\n- none\n\n## Example\nx"


def test_uses_starter_skill_learns_from_crash_and_logs_training_data(tmp_path, serve):
    model = FakeModel({"pick": [PICK_CSV], "solve": [BAD_CODE, GOOD_CODE], "grade": [PASS],
                       "reflect": ["Don't raise errors; write the file."]})
    home = make_home(tmp_path, serve(model))
    assert main(["--home", str(home), "init"]) == 0

    rc = main(["--home", str(home), "do", "clean", "my", "messy", "csv", "file"])
    assert rc == 0
    # Crash is judged by running the code, not by asking the model.
    assert model.calls == ["pick", "solve", "reflect", "solve", "grade"]

    skill = SkillLibrary(home / "skills").get("clean-messy-csv")
    assert skill.status == "proven" and skill.successes == 1 and skill.failures == 1
    assert "Don't raise errors" in skill.section("Lessons")

    entries = [json.loads(l) for l in (home / "journal.jsonl").read_text().splitlines()]
    assert [e["passed"] for e in entries] == [False, True]
    assert entries[1]["verified_by_code"] is True

    assert main(["--home", str(home), "dataset"]) == 0
    rows = (home / "training_data" / "train.jsonl").read_text().splitlines()
    assert len(rows) == 1
    msgs = json.loads(rows[0])["messages"]
    assert [m["role"] for m in msgs] == ["system", "user", "assistant"]
    assert msgs[2]["content"] == GOOD_CODE


def test_unknown_task_researches_writes_notes(tmp_path, serve, monkeypatch):
    model = FakeModel({
        "plan": [json.dumps({"skill_name": "write product description",
                             "description": "Write short product copy.", "queries": ["how to write product copy"]})],
        "write": [SKILL_BODY], "solve": ["Here is the copy.\n## Result\ndone"], "grade": [PASS],
    })
    home = make_home(tmp_path, serve(model))
    monkeypatch.setattr("smart9b.research.Researcher.gather",
                        lambda self, q, n=3: [{"url": "https://example.com/guide", "title": "Guide",
                                               "text": "Lead with the benefit. " * 30}])
    agent = Agent(load_config(home))
    out = agent.run("write a product description for a leather wallet")
    assert out.passed
    skill = agent.library.get("write-product-description")
    assert skill.sources == ["https://example.com/guide"]
    assert skill.checklist() == ["It ran."]
    assert skill.status == "proven"


def test_model_can_decide_existing_notes_do_not_fit(tmp_path, serve, monkeypatch):
    model = FakeModel({"pick": ['{"skill": null}'],
                       "plan": [json.dumps({"skill_name": "csv to json", "queries": ["csv to json python"]})],
                       "write": [SKILL_BODY], "solve": [GOOD_CODE], "grade": [PASS]})
    home = make_home(tmp_path, serve(model))
    main(["--home", str(home), "init"])
    monkeypatch.setattr("smart9b.research.Researcher.gather", lambda self, q, n=3: [])
    agent = Agent(load_config(home))
    assert agent.run("convert a csv file to json").passed
    assert model.calls[:3] == ["pick", "plan", "write"]
    assert agent.library.get("csv-to-json").status == "proven"


def test_stuck_task_goes_to_teacher_and_comes_back_taught(tmp_path, serve):
    worker = FakeModel({"pick": ['{"skill": "parse-dates"}'], "solve": [BAD_CODE], "reflect": ["still broken"]})
    teacher = FakeModel({"unstick": ["## Steps\n1. The real fix.\n\n## Checklist\n- Fixed."]})
    home = make_home(tmp_path, serve(worker), serve(teacher))
    agent = Agent(load_config(home))
    agent.library.save(Skill(name="parse-dates", description="Parse dates.", body=SKILL_BODY))

    out = agent.run("parse dates in a column")
    assert not out.passed
    assert agent.library.get("parse-dates").status == "failed"
    assert len(list((home / "teacher_queue").glob("*.json"))) == 1

    assert agent.unstick() == 1
    fixed = agent.library.get("parse-dates")
    assert fixed.status == "taught" and "The real fix." in fixed.body
    assert not list((home / "teacher_queue").glob("*.json"))


def test_review_rejection_blocks_training_data(tmp_path, serve):
    model = FakeModel({"pick": [PICK_CSV], "solve": [GOOD_CODE], "grade": [PASS],
                       "reflect": ["listen to the human"]})
    home = make_home(tmp_path, serve(model))
    main(["--home", str(home), "init"])
    answers = iter(["n", "wrong column names", "n", "still wrong"])
    agent = Agent(load_config(home), review=True, ask=lambda _: next(answers))
    assert not agent.run("clean messy csv").passed
    counts = dataset.build(agent.journal.entries(), home / "training_data", include_self_graded=True)
    assert counts["train"] == 0


def test_grade_cannot_pass_with_a_failed_item():
    agent = Agent.__new__(Agent)

    class W:
        def ask_json(self, *_):
            return {"items": [{"check": "a", "pass": True}, {"check": "b", "pass": False}],
                    "overall_pass": True}

    agent.worker = W()
    passed, _ = agent.check("t", Skill("s", "", SKILL_BODY), "answer", "", None)
    assert passed is False


def test_skill_roundtrip_and_search_prefers_matching_skill(tmp_path):
    lib = SkillLibrary(tmp_path)
    lib.save(Skill("clean messy csv", "Fix CSV files.", SKILL_BODY, sources=["https://a"]))
    lib.save(Skill("write product copy", "Short product descriptions.", SKILL_BODY))
    s = lib.get("clean-messy-csv")
    assert parse_skill(s.render()).render() == s.render()
    assert lib.search("my csv is messy")[0][1].name == "clean-messy-csv"
    assert lib.search("product description for a wallet")[0][1].name == "write-product-copy"


def test_helpers():
    assert extract_json('sure! ```json\n{"a": [1]}\n``` done') == {"a": [1]}
    assert strip_thinking("<think>hmm</think>answer") == "answer"
    assert extract_code("x\n```bash\necho 1\n```\n```python\nprint(2)\n```") == ("python", "print(2)\n")
    text = html_to_text("<html><script>bad()</script><nav>Home About</nav>"
                        "<h2>Install</h2><p>Run the installer and follow every prompt carefully.</p></html>")
    assert "bad()" not in text and "Home About" not in text
    assert "## Install" in text and "Run the installer" in text


def test_prompts_share_one_skill_format():
    for p in (prompts.WRITE_SKILL, prompts.TEACHER_SKILL, prompts.TEACHER_UNSTICK, prompts.SLIM_SKILL):
        assert prompts.SKILL_FORMAT in p
