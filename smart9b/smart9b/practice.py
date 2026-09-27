"""Practice sandbox: run code the model wrote, with a timeout, in its own folder."""

from __future__ import annotations

import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

_BLOCK = re.compile(r"```(python|py|bash|sh)\s*\n(.*?)```", re.DOTALL)


@dataclass
class RunResult:
    ran: bool
    ok: bool
    output: str


def extract_code(answer: str) -> tuple[str, str] | None:
    """Return (language, code) of the last runnable block in the answer, if any."""
    blocks = _BLOCK.findall(answer)
    if not blocks:
        return None
    lang, code = blocks[-1]
    return ("python" if lang in ("python", "py") else "bash"), code


def run_code(lang: str, code: str, sandbox: Path, timeout: int = 60,
             confirm: bool = True, ask=input) -> RunResult:
    work = sandbox / time.strftime("run-%Y%m%d-%H%M%S")
    work.mkdir(parents=True, exist_ok=True)
    script = work / ("main.py" if lang == "python" else "main.sh")
    script.write_text(code)

    if confirm:
        print(f"\n--- The model wants to run this {lang} code (saved at {script}) ---")
        print(code)
        print("--- end ---")
        if ask("Run it? [y/N] ").strip().lower() != "y":
            return RunResult(ran=False, ok=False, output="(you chose not to run it)")

    cmd = [sys.executable, script.name] if lang == "python" else ["bash", script.name]
    try:
        proc = subprocess.run(cmd, cwd=work, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return RunResult(ran=True, ok=False, output=f"Timed out after {timeout}s.")
    out = (proc.stdout + ("\n" + proc.stderr if proc.stderr else ""))[-4000:]
    ok = proc.returncode == 0 and "Traceback (most recent call last)" not in out
    return RunResult(ran=True, ok=ok, output=f"exit code {proc.returncode}\n{out}")
