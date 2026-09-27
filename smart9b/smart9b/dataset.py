"""Turn the journal's successful work into LoRA training data (mlx-lm chat format)."""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path


def trusted(entry: dict, include_self_graded: bool) -> bool:
    if not entry.get("passed"):
        return False
    if entry.get("approved") is True or entry.get("verified_by_code"):
        return True
    return include_self_graded and entry.get("approved") is None


def build(entries: list[dict], out_dir: Path, include_self_graded: bool = False,
          valid_fraction: float = 0.1, seed: int = 0) -> dict:
    seen, rows = set(), []
    for e in entries:
        if not trusted(e, include_self_graded):
            continue
        key = hashlib.sha256((e["task"] + "\0" + e["answer"]).encode()).hexdigest()
        if key in seen:
            continue
        seen.add(key)
        rows.append({"messages": [
            {"role": "system", "content": e["system"]},
            {"role": "user", "content": e["task"]},
            {"role": "assistant", "content": e["answer"]},
        ]})

    random.Random(seed).shuffle(rows)
    n_valid = max(1, int(len(rows) * valid_fraction)) if len(rows) >= 10 else 0
    valid, train = rows[:n_valid], rows[n_valid:]
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, part in (("train", train), ("valid", valid)):
        with open(out_dir / f"{name}.jsonl", "w", encoding="utf-8") as f:
            for r in part:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return {"train": len(train), "valid": len(valid)}
