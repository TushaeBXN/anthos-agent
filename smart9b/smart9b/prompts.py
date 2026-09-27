"""Prompts, kept short and concrete because a 9B model follows short prompts best."""

SKILL_FORMAT = """\
## Steps
1. (numbered, one action per step, concrete commands or wording)

## Checklist
- (3-6 yes/no checks that prove the result is correct)

## Pitfalls
- (common mistakes and how to avoid them)

## Example
(one short, complete worked example: input -> what you did -> output)
"""

PICK_SKILL = """\
Below is a task and a list of skill notes you already have.
Pick the note that teaches how to do THIS task. If none really fits, pick null.
Return JSON: {"skill": "exact-note-name" or null}"""

PLAN_RESEARCH = """\
You are about to learn a new skill so you can do a task.
Write 2 or 3 short web search queries that would find a clear how-to guide.
Return JSON: {"skill_name": "short-kebab-name", "description": "one sentence, what the skill does", "queries": ["...", "..."]}"""

WRITE_SKILL = """\
You read web pages and turn them into a practical how-to note for yourself.
Only keep steps that the sources agree on or that you are sure are correct.
Write it in exactly this format (markdown, no front matter):

""" + SKILL_FORMAT

TEACHER_SKILL = """\
You are an expert teacher writing a how-to note for a small 9B assistant model.
The student follows instructions literally and cannot handle vague advice.
Use short numbered steps, exact commands, and one complete worked example.
Write it in exactly this format (markdown, no front matter):

""" + SKILL_FORMAT

SOLVE = """\
You are a careful worker. Follow the skill notes below step by step.
If the task needs code, put the full runnable program in ONE ```python block
(or ```bash). Use only files the task mentions or that you create yourself.
End with a short section "## Result" stating what you produced.

{skill}

{lessons}"""

GRADE = """\
You check work strictly. For each checklist item decide PASS or FAIL based only on
the evidence shown. When unsure, FAIL.
Return JSON: {"items": [{"check": "...", "pass": true, "why": "..."}], "overall_pass": true}"""

REFLECT = """\
Your attempt failed. In ONE or TWO sentences, write the lesson you would tell yourself
before trying again: what went wrong and what to do differently. Be specific."""

TEACHER_UNSTICK = """\
A small assistant model failed this task several times. Its skill notes, attempts and the
feedback it got are below. Explain what it misunderstood, then write improved skill notes
it can follow next time, in exactly this format (markdown, no front matter):

""" + SKILL_FORMAT

SLIM_SKILL = """\
Rewrite this skill document for a small 9B model that follows instructions literally.
Keep only what is needed to do the job. Drop background, history and marketing.
Replace references to tools the small model does not have with plain Python or shell.
Write it in exactly this format (markdown, no front matter):

""" + SKILL_FORMAT
