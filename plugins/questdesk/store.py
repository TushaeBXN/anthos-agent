"""QuestDesk storage + reward engine (SQLite, profile-scoped).

One database per profile at ``<ANTHOS_HOME>/questdesk/questdesk.db``.
Every mutating call runs in a single ``BEGIN IMMEDIATE`` transaction so the
deal change, the activity log row and any minted tokens land atomically —
concurrent gateway sessions can't double-mint.

Invariants:
  * ``activities`` and ``token_ledger`` are append-only.
  * Every token row carries a unique ``dedupe_key`` — a stage token can be
    minted once per deal, an Odyssey once per deal, a quest once per
    agent/day, etc. ``INSERT OR IGNORE`` makes re-awarding a no-op.
  * Moves always succeed if valid; the anti-gaming rules in ``rewards``
    only ever withhold *tokens*, never block real CRM work.
"""

from __future__ import annotations

import csv
import math
import re
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

from plugins.questdesk import rewards as R


def _now() -> float:
    """Clock seam — tests monkeypatch this."""
    return time.time()


def default_db_path() -> Path:
    from anthos_constants import get_anthos_home

    return Path(get_anthos_home()) / "questdesk" / "questdesk.db"


class QuestDeskError(ValueError):
    """User-facing validation error (bad id, bad stage, missing evidence)."""


PRESETS: Dict[str, Tuple[str, ...]] = {
    "sales": ("New Lead", "Qualified", "Proposal", "Negotiation", "Closed Won", "Onboarded"),
    "ecommerce": ("Lead", "Qualified", "Cart Built", "Paid", "Shipped", "Repeat Buyer"),
    "clinic": ("Inquiry", "Consultation Booked", "Attended", "Treatment Plan", "Paid", "Follow-up Done"),
    "realestate": ("Lead", "Showing Booked", "Showing Done", "Offer", "Under Contract", "Closed"),
    "services": ("Lead", "Discovery Call", "Proposal", "Signed", "Delivered", "Referral"),
    "creator": ("Fan", "Engaged", "Pitched", "Purchased", "Superfan"),
}
DEFAULT_PRESET = "sales"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS stages (
    position INTEGER PRIMARY KEY,
    key TEXT NOT NULL UNIQUE,
    label TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    handle TEXT,
    phone TEXT,
    email TEXT,
    company TEXT,
    tags TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS deals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id INTEGER NOT NULL REFERENCES contacts(id),
    title TEXT NOT NULL,
    value REAL NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'USD',
    stage_key TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    next_action TEXT,
    next_action_due REAL,
    loss_reason TEXT,
    owner TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    stage_entered_at REAL NOT NULL,
    last_activity_at REAL NOT NULL,
    closed_at REAL
);
CREATE TABLE IF NOT EXISTS activities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    deal_id INTEGER,
    contact_id INTEGER,
    agent TEXT NOT NULL,
    kind TEXT NOT NULL,
    from_pos INTEGER,
    to_pos INTEGER,
    note TEXT,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS token_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent TEXT NOT NULL,
    token TEXT NOT NULL,
    xp INTEGER NOT NULL,
    deal_id INTEGER,
    reason TEXT NOT NULL,
    dedupe_key TEXT NOT NULL UNIQUE,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_deals_stage ON deals(stage_key, status);
CREATE INDEX IF NOT EXISTS idx_act_agent ON activities(agent, created_at);
CREATE INDEX IF NOT EXISTS idx_act_deal ON activities(deal_id);
CREATE INDEX IF NOT EXISTS idx_ledger_agent ON token_ledger(agent, created_at);
"""

_CONTACT_FIELDS = ("name", "handle", "phone", "email", "company", "tags")


def slugify(label: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", label.strip().lower()).strip("_")
    return slug or "stage"


def iso(ts: Optional[float]) -> Optional[str]:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_day(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")


def _day_start(ts: float) -> float:
    return math.floor(ts / 86400) * 86400


_REL_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([mhdw])\s*$", re.IGNORECASE)
_REL_UNITS = {"m": 60, "h": 3600, "d": 86400, "w": 604800}


def parse_due(raw: Any, now: float) -> Optional[float]:
    """Accept ``"30m"``/``"4h"``/``"3d"``/``"1w"``, ``YYYY-MM-DD`` or ISO-8601."""
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    text = str(raw).strip()
    m = _REL_RE.match(text)
    if m:
        return now + float(m.group(1)) * _REL_UNITS[m.group(2).lower()]
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise QuestDeskError(
            f"Can't parse due '{text}'. Use 30m / 4h / 3d / 1w, YYYY-MM-DD, or ISO-8601."
        )
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def normalize_handle(handle: Optional[str]) -> Optional[str]:
    if not handle:
        return None
    h = handle.strip()
    if not h:
        return None
    return h if h.startswith("@") or h.isdigit() else f"@{h}"


def lead_score(position: int, stage_count: int, value: float, idle_days: float) -> int:
    """0–100 heat score: pipeline progress + recency + deal size."""
    progress = (position / max(1, stage_count - 1)) * 50
    recency = max(0.0, 30.0 - idle_days)
    size = min(20.0, 4.0 * math.log10(1 + max(0.0, value)))
    return int(round(min(100.0, progress + recency + size)))


class QuestDesk:
    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = Path(db_path) if db_path else default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = self._connect()
        try:
            conn.executescript(_SCHEMA)
            if not conn.execute("SELECT 1 FROM stages LIMIT 1").fetchone():
                self._write_stages(conn, PRESETS[DEFAULT_PRESET])
        finally:
            conn.close()

    # -- plumbing ------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=15, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            conn.execute("COMMIT")
        finally:
            conn.close()

    @contextmanager
    def _read(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            yield conn
        finally:
            conn.close()

    # -- pipeline ------------------------------------------------------------

    @staticmethod
    def _write_stages(conn: sqlite3.Connection, labels: Sequence[str]) -> None:
        conn.execute("DELETE FROM stages")
        for pos, label in enumerate(labels):
            conn.execute(
                "INSERT INTO stages(position, key, label) VALUES (?, ?, ?)",
                (pos, slugify(label), label.strip()),
            )

    @staticmethod
    def _stages(conn: sqlite3.Connection) -> List[dict]:
        rows = conn.execute("SELECT position, key, label FROM stages ORDER BY position").fetchall()
        out = []
        for r in rows:
            tok = R.STAGE_TOKENS[r["position"]]
            out.append({
                "position": r["position"],
                "key": r["key"],
                "label": r["label"],
                "token": f"{tok.emoji} {tok.name}",
                "xp": tok.xp,
            })
        return out

    def stages(self) -> List[dict]:
        with self._read() as conn:
            return self._stages(conn)

    def set_pipeline(self, preset: Optional[str] = None, labels: Optional[Sequence[str]] = None) -> List[dict]:
        if labels:
            clean = [l.strip() for l in labels if l and l.strip()]
        elif preset:
            key = preset.strip().lower()
            if key not in PRESETS:
                raise QuestDeskError(f"Unknown preset '{preset}'. Choose: {', '.join(PRESETS)}")
            clean = list(PRESETS[key])
        else:
            raise QuestDeskError("Pass a preset or a list of stage labels.")
        if not (R.MIN_STAGES <= len(clean) <= R.MAX_STAGES):
            raise QuestDeskError(f"A pipeline needs {R.MIN_STAGES}–{R.MAX_STAGES} stages (got {len(clean)}).")
        slugs = [slugify(l) for l in clean]
        if len(set(slugs)) != len(slugs):
            raise QuestDeskError("Stage labels must be distinct.")
        with self._tx() as conn:
            old = self._stages(conn)
            has_deals = conn.execute("SELECT 1 FROM deals LIMIT 1").fetchone()
            if has_deals and len(old) != len(clean):
                raise QuestDeskError(
                    f"Deals already exist on a {len(old)}-stage pipeline; a new pipeline "
                    f"must keep {len(old)} stages (positions are relabelled in place). "
                    "Export with `anthos questdesk export` and start a fresh profile to change the shape."
                )
            remap = {o["key"]: slugs[o["position"]] for o in old}
            self._write_stages(conn, clean)
            for old_key, new_key in remap.items():
                if old_key != new_key:
                    conn.execute("UPDATE deals SET stage_key=? WHERE stage_key=?", (new_key, old_key))
            return self._stages(conn)

    def _resolve_stage(self, stages: List[dict], stage: Any) -> dict:
        if stage is None or (isinstance(stage, str) and not stage.strip()):
            raise QuestDeskError("stage is required.")
        text = str(stage).strip()
        if text.lstrip("-").isdigit():
            pos = int(text)
            for s in stages:
                if s["position"] == pos:
                    return s
        want = slugify(text)
        for s in stages:
            if s["key"] == want or s["label"].lower() == text.lower():
                return s
        options = ", ".join(f"{s['position']}={s['label']}" for s in stages)
        raise QuestDeskError(f"Unknown stage '{text}'. Stages: {options}")

    # -- contacts ------------------------------------------------------------

    def _contact_row(self, conn: sqlite3.Connection, contact_id: Any) -> sqlite3.Row:
        try:
            cid = int(contact_id)
        except (TypeError, ValueError):
            raise QuestDeskError("contact_id must be an integer.")
        row = conn.execute("SELECT * FROM contacts WHERE id=?", (cid,)).fetchone()
        if not row:
            raise QuestDeskError(f"No contact #{cid}.")
        return row

    @staticmethod
    def _contact_dict(row: sqlite3.Row) -> dict:
        d = dict(row)
        d["tags"] = [t for t in (d.get("tags") or "").split(",") if t]
        d["created_at"] = iso(d["created_at"])
        d["updated_at"] = iso(d["updated_at"])
        return d

    @staticmethod
    def _tags(raw: Any) -> str:
        if raw is None:
            return ""
        items = raw if isinstance(raw, (list, tuple)) else str(raw).split(",")
        seen: List[str] = []
        for t in items:
            t = str(t).strip().lower()
            if t and t not in seen:
                seen.append(t)
        return ",".join(seen)

    def _find_duplicate(self, conn, handle, phone, email) -> Optional[sqlite3.Row]:
        for col, val in (("handle", handle), ("phone", phone), ("email", email)):
            if val:
                row = conn.execute(
                    f"SELECT * FROM contacts WHERE lower({col})=lower(?)", (val,)
                ).fetchone()
                if row:
                    return row
        return None

    def _insert_contact(self, conn, agent: str, now: float, name: str, handle=None,
                        phone=None, email=None, company=None, tags=None,
                        note: Optional[str] = None) -> Tuple[sqlite3.Row, bool]:
        if not name or not str(name).strip():
            raise QuestDeskError("name is required to add a contact.")
        handle = normalize_handle(handle)
        dup = self._find_duplicate(conn, handle, phone, email)
        if dup:
            return dup, False
        cur = conn.execute(
            "INSERT INTO contacts(name, handle, phone, email, company, tags, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (str(name).strip(), handle, phone, email, company, self._tags(tags), now, now),
        )
        cid = cur.lastrowid
        if note:
            self._log(conn, agent, "note", now, contact_id=cid, note=note)
        return conn.execute("SELECT * FROM contacts WHERE id=?", (cid,)).fetchone(), True

    def add_contact(self, agent: str, name: str, handle=None, phone=None, email=None,
                    company=None, tags=None, note=None) -> dict:
        now = _now()
        with self._tx() as conn:
            xp_before = self._xp(conn, agent)
            row, created = self._insert_contact(conn, agent, now, name, handle, phone,
                                                email, company, tags, note)
            awards = self._post_rewards(conn, agent, now, []) if (created and note) else []
            out = {"contact": self._contact_dict(row), "created": created}
            if not created:
                out["message"] = f"Matched existing contact #{row['id']} — no duplicate created."
            return self._attach_rewards(conn, out, agent, xp_before, awards)

    def update_contact(self, contact_id: Any, **fields: Any) -> dict:
        now = _now()
        with self._tx() as conn:
            row = self._contact_row(conn, contact_id)
            sets, vals = [], []
            for key in _CONTACT_FIELDS:
                if fields.get(key) is None:
                    continue
                val = fields[key]
                if key == "tags":
                    merged = [t for t in (row["tags"] or "").split(",") if t]
                    val = self._tags(merged + self._tags(val).split(","))
                elif key == "handle":
                    val = normalize_handle(val)
                sets.append(f"{key}=?")
                vals.append(val)
            if not sets:
                raise QuestDeskError("Nothing to update — pass at least one contact field.")
            sets.append("updated_at=?")
            vals.extend([now, row["id"]])
            conn.execute(f"UPDATE contacts SET {', '.join(sets)} WHERE id=?", vals)
            return {"contact": self._contact_dict(self._contact_row(conn, row["id"]))}

    def get_contact(self, contact_id: Any) -> dict:
        with self._read() as conn:
            row = self._contact_row(conn, contact_id)
            stages = self._stages(conn)
            deals = conn.execute(
                "SELECT * FROM deals WHERE contact_id=? ORDER BY updated_at DESC", (row["id"],)
            ).fetchall()
            acts = conn.execute(
                "SELECT * FROM activities WHERE contact_id=? ORDER BY id DESC LIMIT 15", (row["id"],)
            ).fetchall()
            return {
                "contact": self._contact_dict(row),
                "deals": [self._deal_dict(d, stages) for d in deals],
                "recent_activity": [self._activity_dict(a) for a in acts],
            }

    def search_contacts(self, query: str = "", limit: int = 10) -> dict:
        limit = max(1, min(50, int(limit or 10)))
        with self._read() as conn:
            if query and query.strip():
                like = f"%{query.strip().lower()}%"
                rows = conn.execute(
                    "SELECT * FROM contacts WHERE lower(name) LIKE ? OR lower(coalesce(handle,'')) LIKE ?"
                    " OR lower(coalesce(company,'')) LIKE ? OR lower(coalesce(email,'')) LIKE ?"
                    " OR coalesce(phone,'') LIKE ? OR tags LIKE ? ORDER BY updated_at DESC LIMIT ?",
                    (like, like, like, like, like, like, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM contacts ORDER BY updated_at DESC LIMIT ?", (limit,)
                ).fetchall()
            return {"contacts": [self._contact_dict(r) for r in rows], "count": len(rows)}

    def add_note(self, agent: str, note: str, contact_id: Any = None, deal_id: Any = None) -> dict:
        if not note or not note.strip():
            raise QuestDeskError("note text is required.")
        if contact_id is None and deal_id is None:
            raise QuestDeskError("Pass contact_id or deal_id for the note.")
        now = _now()
        with self._tx() as conn:
            xp_before = self._xp(conn, agent)
            cid = None
            did = None
            if deal_id is not None:
                deal = self._deal_row(conn, deal_id)
                did, cid = deal["id"], deal["contact_id"]
                conn.execute("UPDATE deals SET last_activity_at=?, updated_at=? WHERE id=?", (now, now, did))
            else:
                cid = self._contact_row(conn, contact_id)["id"]
            conn.execute("UPDATE contacts SET updated_at=? WHERE id=?", (now, cid))
            self._log(conn, agent, "note", now, deal_id=did, contact_id=cid, note=note.strip())
            awards = self._post_rewards(conn, agent, now, [])
            return self._attach_rewards(conn, {"logged": True, "contact_id": cid, "deal_id": did},
                                        agent, xp_before, awards)

    # -- deals ---------------------------------------------------------------

    def _deal_row(self, conn: sqlite3.Connection, deal_id: Any) -> sqlite3.Row:
        try:
            did = int(deal_id)
        except (TypeError, ValueError):
            raise QuestDeskError("deal_id must be an integer.")
        row = conn.execute("SELECT * FROM deals WHERE id=?", (did,)).fetchone()
        if not row:
            raise QuestDeskError(f"No deal #{did}.")
        return row

    def _deal_dict(self, row: sqlite3.Row, stages: List[dict], now: Optional[float] = None) -> dict:
        now = _now() if now is None else now
        by_key = {s["key"]: s for s in stages}
        stage = by_key.get(row["stage_key"], {"position": 0, "label": row["stage_key"]})
        idle_days = (now - row["last_activity_at"]) / 86400
        d = {
            "id": row["id"],
            "title": row["title"],
            "contact_id": row["contact_id"],
            "value": row["value"],
            "currency": row["currency"],
            "stage": stage["label"],
            "stage_position": stage["position"],
            "stage_count": len(stages),
            "status": row["status"],
            "owner": row["owner"],
            "next_action": row["next_action"],
            "next_action_due": iso(row["next_action_due"]),
            "overdue": bool(row["status"] == "open" and row["next_action_due"] and row["next_action_due"] < now),
            "idle_days": round(idle_days, 1),
            "score": lead_score(stage["position"], len(stages), row["value"], idle_days),
            "created_at": iso(row["created_at"]),
            "stage_entered_at": iso(row["stage_entered_at"]),
        }
        if row["loss_reason"]:
            d["loss_reason"] = row["loss_reason"]
        return d

    def create_deal(self, agent: str, title: str, contact_id: Any = None, contact_name: Optional[str] = None,
                    handle: Optional[str] = None, value: Any = 0, currency: Optional[str] = None,
                    stage: Any = None, note: Optional[str] = None, next_action: Optional[str] = None,
                    next_action_due: Any = None) -> dict:
        if not title or not str(title).strip():
            raise QuestDeskError("title is required to create a deal.")
        now = _now()
        with self._tx() as conn:
            xp_before = self._xp(conn, agent)
            stages = self._stages(conn)
            if contact_id is not None:
                contact = self._contact_row(conn, contact_id)
            elif contact_name or handle:
                contact, _ = self._insert_contact(conn, agent, now, contact_name or handle, handle=handle)
            else:
                raise QuestDeskError("Pass contact_id, or contact_name/handle to auto-create the contact.")
            st = self._resolve_stage(stages, stage) if stage is not None else stages[0]
            due = parse_due(next_action_due, now)
            cur = conn.execute(
                "INSERT INTO deals(contact_id, title, value, currency, stage_key, status, next_action,"
                " next_action_due, owner, created_at, updated_at, stage_entered_at, last_activity_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (contact["id"], str(title).strip(), _money(value), (currency or "USD").upper()[:8],
                 st["key"], "won" if st["position"] == len(stages) - 1 else "open",
                 next_action, due, agent, now, now, now, now),
            )
            did = cur.lastrowid
            self._log(conn, agent, "create", now, deal_id=did, contact_id=contact["id"],
                      to_pos=st["position"], note=note)
            if next_action:
                self._log(conn, agent, "next_action", now, deal_id=did, contact_id=contact["id"],
                          note=next_action)
            awards: List[dict] = []
            notices: List[str] = []
            spark_today = self._count_tokens_today(conn, agent, "spark", now)
            if spark_today < R.SPARK_DAILY_CAP:
                self._award(conn, agent, "spark", now, f"stage:{did}:0", did,
                            f"Deal #{did} entered the pipeline", awards)
            else:
                notices.append(f"Spark withheld: daily cap of {R.SPARK_DAILY_CAP} new-deal tokens reached.")
            if st["position"] != 0:
                notices.append("Deal started mid-pipeline — skipped stages forfeit this deal's 🏆 Odyssey.")
            awards = self._post_rewards(conn, agent, now, awards)
            deal = self._deal_dict(self._deal_row(conn, did), stages, now)
            out = {"deal": deal, "contact": self._contact_dict(contact)}
            if notices:
                out["notices"] = notices
            out["next_goal"] = self._next_goal(conn, deal, stages)
            return self._attach_rewards(conn, out, agent, xp_before, awards)

    def move_deal(self, agent: str, deal_id: Any, stage: Any, note: Optional[str]) -> dict:
        now = _now()
        with self._tx() as conn:
            xp_before = self._xp(conn, agent)
            stages = self._stages(conn)
            deal = self._deal_row(conn, deal_id)
            target = self._resolve_stage(stages, stage)
            by_key = {s["key"]: s for s in stages}
            cur_pos = by_key.get(deal["stage_key"], {"position": 0})["position"]
            to_pos = target["position"]
            forward = to_pos > cur_pos
            if to_pos == cur_pos and deal["status"] != "lost":
                raise QuestDeskError(f"Deal #{deal['id']} is already in '{target['label']}'.")
            if forward and len((note or "").strip()) < R.MIN_EVIDENCE_CHARS:
                raise QuestDeskError(
                    f"Advancing needs evidence: pass a note (≥{R.MIN_EVIDENCE_CHARS} chars) saying what "
                    "happened — e.g. 'Client confirmed budget on call, sending proposal'."
                )
            last = len(stages) - 1
            status = "won" if to_pos == last else "open"
            closed_at = now if status == "won" else None
            dwell = now - deal["stage_entered_at"]
            conn.execute(
                "UPDATE deals SET stage_key=?, status=?, closed_at=?, loss_reason=NULL, updated_at=?,"
                " stage_entered_at=?, last_activity_at=? WHERE id=?",
                (target["key"], status, closed_at, now, now, now, deal["id"]),
            )
            self._log(conn, agent, "move", now, deal_id=deal["id"], contact_id=deal["contact_id"],
                      from_pos=cur_pos, to_pos=to_pos, note=(note or "").strip() or None)

            awards: List[dict] = []
            notices: List[str] = []
            if deal["status"] == "lost":
                notices.append("Deal reopened.")
            if forward:
                if to_pos - cur_pos > 1:
                    notices.append("Skipped stage(s) — their tokens are forfeit, and so is this deal's 🏆 Odyssey.")
                if dwell < R.MIN_STAGE_DWELL_SECONDS:
                    if not self._has_key(conn, f"stage:{deal['id']}:{to_pos}"):
                        mins = R.MIN_STAGE_DWELL_SECONDS // 60
                        notices.append(
                            f"{R.STAGE_TOKENS[to_pos].emoji} token withheld: the deal spent under {mins} min "
                            "in its previous stage. Tokens reward real-world progress — move it when it happens."
                        )
                else:
                    tok = R.STAGE_TOKENS[to_pos]
                    self._award(conn, agent, tok.id, now, f"stage:{deal['id']}:{to_pos}", deal["id"],
                                f"Deal #{deal['id']} reached {target['label']}", awards)
                if dwell >= R.PHOENIX_STALL_SECONDS:
                    self._award(conn, agent, "phoenix", now, f"phoenix:{deal['id']}:{to_pos}", deal["id"],
                                f"Revived deal #{deal['id']} after {int(dwell // 86400)} days", awards)
                if to_pos == last:
                    earned = {
                        r["dedupe_key"] for r in conn.execute(
                            "SELECT dedupe_key FROM token_ledger WHERE deal_id=? AND dedupe_key LIKE 'stage:%'",
                            (deal["id"],),
                        )
                    }
                    needed = {f"stage:{deal['id']}:{p}" for p in range(len(stages))}
                    if needed <= earned:
                        self._award(conn, agent, "odyssey", now, f"odyssey:{deal['id']}", deal["id"],
                                    f"Deal #{deal['id']} completed the full journey", awards)
                        if now - deal["created_at"] <= R.LIGHTNING_WINDOW_SECONDS:
                            self._award(conn, agent, "lightning", now, f"lightning:{deal['id']}", deal["id"],
                                        f"Deal #{deal['id']} journey finished inside 7 days", awards)
                    else:
                        notices.append("Deal closed, but not every stage token was earned — no 🏆 Odyssey this time.")
                self._award_streak(conn, agent, now, awards)
            awards = self._post_rewards(conn, agent, now, awards)
            out_deal = self._deal_dict(self._deal_row(conn, deal["id"]), stages, now)
            out = {"deal": out_deal, "moved": {"from": stages[cur_pos]["label"], "to": target["label"]}}
            if notices:
                out["notices"] = notices
            out["next_goal"] = self._next_goal(conn, out_deal, stages)
            return self._attach_rewards(conn, out, agent, xp_before, awards)

    def update_deal(self, agent: str, deal_id: Any, title=None, value=None, currency=None,
                    next_action=None, next_action_due=None) -> dict:
        now = _now()
        with self._tx() as conn:
            xp_before = self._xp(conn, agent)
            deal = self._deal_row(conn, deal_id)
            sets, vals = [], []
            if title:
                sets.append("title=?"); vals.append(str(title).strip())
            if value is not None:
                sets.append("value=?"); vals.append(_money(value))
            if currency:
                sets.append("currency=?"); vals.append(str(currency).upper()[:8])
            if next_action is not None:
                sets.append("next_action=?"); vals.append(next_action or None)
            if next_action_due is not None:
                sets.append("next_action_due=?"); vals.append(parse_due(next_action_due, now))
            if not sets:
                raise QuestDeskError("Nothing to update — pass title, value, currency, next_action or next_action_due.")
            sets += ["updated_at=?", "last_activity_at=?"]
            vals += [now, now, deal["id"]]
            conn.execute(f"UPDATE deals SET {', '.join(sets)} WHERE id=?", vals)
            if next_action:
                self._log(conn, agent, "next_action", now, deal_id=deal["id"],
                          contact_id=deal["contact_id"], note=next_action)
            awards = self._post_rewards(conn, agent, now, [])
            stages = self._stages(conn)
            out = {"deal": self._deal_dict(self._deal_row(conn, deal["id"]), stages, now)}
            return self._attach_rewards(conn, out, agent, xp_before, awards)

    def lose_deal(self, agent: str, deal_id: Any, reason: Optional[str]) -> dict:
        reason = (reason or "").strip()
        if len(reason) < R.MIN_LOSS_REASON_CHARS:
            raise QuestDeskError(
                f"Pass a loss_reason (≥{R.MIN_LOSS_REASON_CHARS} chars) — e.g. 'Chose competitor on price'."
            )
        now = _now()
        with self._tx() as conn:
            xp_before = self._xp(conn, agent)
            deal = self._deal_row(conn, deal_id)
            if deal["status"] != "open":
                raise QuestDeskError(f"Deal #{deal['id']} is already {deal['status']}.")
            conn.execute(
                "UPDATE deals SET status='lost', loss_reason=?, closed_at=?, updated_at=?, last_activity_at=?"
                " WHERE id=?", (reason, now, now, now, deal["id"]),
            )
            self._log(conn, agent, "lost", now, deal_id=deal["id"], contact_id=deal["contact_id"], note=reason)
            awards: List[dict] = []
            notices: List[str] = []
            old_enough = now - deal["created_at"] >= R.MIN_STAGE_DWELL_SECONDS
            under_cap = self._count_tokens_today(conn, agent, "honor", now) < R.HONOR_DAILY_CAP
            if old_enough and under_cap:
                self._award(conn, agent, "honor", now, f"honor:{deal['id']}", deal["id"],
                            f"Closed out deal #{deal['id']} honestly", awards)
            elif not old_enough:
                notices.append("🛡️ Honor withheld: the deal is too new to be closed out.")
            awards = self._post_rewards(conn, agent, now, awards)
            stages = self._stages(conn)
            out = {"deal": self._deal_dict(self._deal_row(conn, deal["id"]), stages, now)}
            if notices:
                out["notices"] = notices
            return self._attach_rewards(conn, out, agent, xp_before, awards)

    def get_deal(self, deal_id: Any) -> dict:
        with self._read() as conn:
            stages = self._stages(conn)
            row = self._deal_row(conn, deal_id)
            acts = conn.execute(
                "SELECT * FROM activities WHERE deal_id=? ORDER BY id DESC LIMIT 20", (row["id"],)
            ).fetchall()
            toks = conn.execute(
                "SELECT agent, token, xp, created_at FROM token_ledger WHERE deal_id=? ORDER BY id", (row["id"],)
            ).fetchall()
            deal = self._deal_dict(row, stages)
            catalog = R.all_tokens()
            return {
                "deal": deal,
                "contact": self._contact_dict(self._contact_row(conn, row["contact_id"])),
                "tokens_earned": [
                    {"label": f"{catalog[t['token']].emoji} {catalog[t['token']].name}", "xp": t["xp"],
                     "agent": t["agent"], "at": iso(t["created_at"])} for t in toks
                ],
                "activity": [self._activity_dict(a) for a in acts],
                "next_goal": self._next_goal(conn, deal, stages),
            }

    def list_deals(self, stage: Any = None, status: Optional[str] = "open", contact_id: Any = None,
                   query: Optional[str] = None, limit: int = 20) -> dict:
        limit = max(1, min(100, int(limit or 20)))
        with self._read() as conn:
            stages = self._stages(conn)
            where, vals = [], []
            if stage is not None and str(stage).strip():
                where.append("stage_key=?"); vals.append(self._resolve_stage(stages, stage)["key"])
            if status and status != "all":
                where.append("status=?"); vals.append(status)
            if contact_id is not None:
                where.append("contact_id=?"); vals.append(int(contact_id))
            if query and query.strip():
                where.append("lower(title) LIKE ?"); vals.append(f"%{query.strip().lower()}%")
            sql = "SELECT * FROM deals" + (f" WHERE {' AND '.join(where)}" if where else "")
            rows = conn.execute(sql + " ORDER BY updated_at DESC", vals).fetchall()
            now = _now()
            deals = sorted((self._deal_dict(r, stages, now) for r in rows), key=lambda d: -d["score"])
            return {"deals": deals[:limit], "count": len(deals)}

    def board(self) -> dict:
        now = _now()
        with self._read() as conn:
            stages = self._stages(conn)
            rows = conn.execute("SELECT * FROM deals WHERE status IN ('open','won')").fetchall()
            deals = [self._deal_dict(r, stages, now) for r in rows]
            columns = []
            for s in stages:
                col = sorted((d for d in deals if d["stage_position"] == s["position"]),
                             key=lambda d: -d["score"])
                columns.append({
                    "stage": s["label"], "position": s["position"], "token": s["token"],
                    "count": len(col), "value": round(sum(d["value"] for d in col), 2),
                    "top": [{"id": d["id"], "title": d["title"], "value": d["value"],
                             "score": d["score"], "overdue": d["overdue"]} for d in col[:3]],
                })
            lost = conn.execute("SELECT COUNT(*) FROM deals WHERE status='lost'").fetchone()[0]
            won = sum(1 for d in deals if d["status"] == "won")
            closed = won + lost
            return {
                "columns": columns,
                "open_deals": sum(1 for d in deals if d["status"] == "open"),
                "open_value": round(sum(d["value"] for d in deals if d["status"] == "open"), 2),
                "won": won,
                "lost": lost,
                "win_rate": round(won / closed, 3) if closed else None,
                "overdue": sum(1 for d in deals if d["overdue"]),
            }

    def radar(self, stale_days: float = 7, limit: int = 10) -> dict:
        """Open deals that need attention: overdue next action or gone quiet."""
        now = _now()
        limit = max(1, min(50, int(limit or 10)))
        with self._read() as conn:
            stages = self._stages(conn)
            rows = conn.execute("SELECT * FROM deals WHERE status='open'").fetchall()
            hits = []
            for r in rows:
                d = self._deal_dict(r, stages, now)
                reasons = []
                if d["overdue"]:
                    reasons.append("next action overdue")
                if not r["next_action"]:
                    reasons.append("no next action set")
                if d["idle_days"] >= stale_days:
                    reasons.append(f"quiet for {int(d['idle_days'])}d")
                if now - r["stage_entered_at"] >= R.PHOENIX_STALL_SECONDS:
                    reasons.append("stalled 14d+ — advance it for a 🐦‍🔥 Phoenix")
                if reasons:
                    d["why"] = reasons
                    hits.append(d)
            hits.sort(key=lambda d: (not d["overdue"], -d["score"]))
            return {"deals": hits[:limit], "count": len(hits)}

    # -- rewards -------------------------------------------------------------

    @staticmethod
    def _log(conn, agent, kind, now, deal_id=None, contact_id=None, from_pos=None, to_pos=None, note=None):
        conn.execute(
            "INSERT INTO activities(deal_id, contact_id, agent, kind, from_pos, to_pos, note, created_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (deal_id, contact_id, agent, kind, from_pos, to_pos, note, now),
        )

    @staticmethod
    def _activity_dict(row: sqlite3.Row) -> dict:
        d = {k: row[k] for k in ("kind", "agent", "note") if row[k] is not None}
        if row["from_pos"] is not None or row["to_pos"] is not None:
            d["from_pos"], d["to_pos"] = row["from_pos"], row["to_pos"]
        if row["deal_id"] is not None:
            d["deal_id"] = row["deal_id"]
        d["at"] = iso(row["created_at"])
        return d

    @staticmethod
    def _has_key(conn, key: str) -> bool:
        return conn.execute("SELECT 1 FROM token_ledger WHERE dedupe_key=?", (key,)).fetchone() is not None

    @staticmethod
    def _award(conn, agent, token_id, now, dedupe_key, deal_id, reason, awards: List[dict]) -> bool:
        tok = R.get_token(token_id)
        cur = conn.execute(
            "INSERT OR IGNORE INTO token_ledger(agent, token, xp, deal_id, reason, dedupe_key, created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (agent, tok.id, tok.xp, deal_id, reason, dedupe_key, now),
        )
        if cur.rowcount:
            awards.append({**tok.as_dict(), "reason": reason})
            return True
        return False

    @staticmethod
    def _xp(conn, agent: str) -> int:
        return int(conn.execute(
            "SELECT coalesce(sum(xp),0) FROM token_ledger WHERE agent=?", (agent,)
        ).fetchone()[0])

    @staticmethod
    def _count_tokens_today(conn, agent, token_id, now) -> int:
        return int(conn.execute(
            "SELECT COUNT(*) FROM token_ledger WHERE agent=? AND token=? AND created_at>=?",
            (agent, token_id, _day_start(now)),
        ).fetchone()[0])

    def _award_streak(self, conn, agent, now, awards):
        days = [r[0] for r in conn.execute(
            "SELECT DISTINCT CAST(created_at/86400 AS INTEGER) AS d FROM activities"
            " WHERE agent=? AND kind='move' AND to_pos>from_pos ORDER BY d DESC", (agent,),
        )]
        today = int(now // 86400)
        streak = 0
        for i, d in enumerate(days):
            if d == today - i:
                streak += 1
            else:
                break
        if streak in R.BLAZE_MILESTONES:
            self._award(conn, agent, "blaze", now, f"blaze:{agent}:{streak}:{utc_day(now)}", None,
                        f"{streak}-day advance streak", awards)

    def quest_counters(self, conn, agent: str, now: float) -> Dict[str, int]:
        start = _day_start(now)
        last = len(self._stages(conn)) - 1

        def one(sql: str, *args) -> int:
            return int(conn.execute(sql, (agent, start, *args)).fetchone()[0])

        base = "FROM activities WHERE agent=? AND created_at>=?"
        return {
            "advances": one(f"SELECT COUNT(DISTINCT deal_id) {base} AND kind='move' AND to_pos>from_pos"),
            "qualifies": one(f"SELECT COUNT(DISTINCT deal_id) {base} AND kind='move' AND from_pos=0 AND to_pos>0"),
            "created": one(f"SELECT COUNT(*) {base} AND kind='create'"),
            "closes": one(f"SELECT COUNT(DISTINCT deal_id) {base} AND kind='move' AND to_pos=? AND to_pos>from_pos", last),
            "next_actions": one(f"SELECT COUNT(DISTINCT deal_id) {base} AND kind='next_action'"),
            "notes": one(f"SELECT COUNT(*) {base} AND kind='note' AND length(note)>=?", R.MIN_EVIDENCE_CHARS),
            "phoenix": one("SELECT COUNT(*) FROM token_ledger WHERE agent=? AND created_at>=? AND token='phoenix'"),
            "honor": one("SELECT COUNT(*) FROM token_ledger WHERE agent=? AND created_at>=? AND token='honor'"),
        }

    def _quest_status(self, conn, agent, now) -> List[dict]:
        counters = self.quest_counters(conn, agent, now)
        day = utc_day(now)
        out = []
        for q in R.daily_quests(day):
            progress = min(q.target, counters.get(q.metric, 0))
            out.append({
                "id": q.id, "title": q.title, "progress": progress, "target": q.target,
                "done": progress >= q.target,
                "claimed": self._has_key(conn, f"quest:{agent}:{day}:{q.id}"),
            })
        return out

    def _post_rewards(self, conn, agent, now, awards: List[dict]) -> List[dict]:
        """Quest, Trifecta and Constellation checks after any mutation."""
        day = utc_day(now)
        quests = self._quest_status(conn, agent, now)
        for q in quests:
            if q["done"]:
                self._award(conn, agent, "quest", now, f"quest:{agent}:{day}:{q['id']}", None,
                            f"Daily quest: {q['title']}", awards)
        if quests and all(q["done"] for q in quests):
            self._award(conn, agent, "trifecta", now, f"trifecta:{agent}:{day}", None,
                        "All daily quests complete", awards)
        n = len(self._stages(conn))
        have = {r[0] for r in conn.execute("SELECT DISTINCT token FROM token_ledger WHERE agent=?", (agent,))}
        need = {t.id for t in R.STAGE_TOKENS[:n]} | {"odyssey"}
        if need <= have:
            self._award(conn, agent, "constellation", now, f"constellation:{agent}", None,
                        "Every stage token plus an Odyssey", awards)
        return awards

    def _attach_rewards(self, conn, out: dict, agent: str, xp_before: int, awards: List[dict]) -> dict:
        if not awards:
            return out
        xp_after = self._xp(conn, agent)
        before, after = R.level_for(xp_before), R.level_for(xp_after)
        out["rewards"] = awards
        out["xp_gained"] = xp_after - xp_before
        out["agent"] = {"name": agent, **after}
        lines = [f"{a['label']} token +{a['xp']} XP — {a['reason']}" for a in awards]
        if after["level"] > before["level"]:
            out["level_up"] = {"from": before["rank"], "to": after["rank"], "level": after["level"]}
            lines.append(f"⬆️ LEVEL UP → Lv {after['level']} {after['rank']}!")
        out["celebration"] = " | ".join(lines)
        return out

    def _next_goal(self, conn, deal: dict, stages: List[dict]) -> Optional[str]:
        if deal["status"] != "open":
            return None
        pos, last = deal["stage_position"], len(stages) - 1
        nxt = stages[pos + 1]
        tok = R.STAGE_TOKENS[pos + 1]
        earned = {
            r[0] for r in conn.execute(
                "SELECT dedupe_key FROM token_ledger WHERE deal_id=? AND dedupe_key LIKE 'stage:%'", (deal["id"],)
            )
        }
        odyssey_alive = all(f"stage:{deal['id']}:{p}" in earned for p in range(pos + 1))
        msg = f"Move to '{nxt['label']}' for a {tok.emoji} {tok.name} (+{tok.xp} XP)"
        if odyssey_alive:
            left = last - pos
            msg += f"; {left} stage{'s' if left != 1 else ''} to a 🏆 Odyssey (+{R.SPECIAL_TOKENS['odyssey'].xp} XP)"
        return msg + "."

    def wallet(self, agent: str) -> dict:
        now = _now()
        with self._read() as conn:
            catalog = R.all_tokens()
            rows = conn.execute(
                "SELECT token, COUNT(*) AS n, SUM(xp) AS xp FROM token_ledger WHERE agent=? GROUP BY token",
                (agent,),
            ).fetchall()
            order = list(catalog)
            tokens = sorted(
                ({"label": f"{catalog[r['token']].emoji} {catalog[r['token']].name}", "count": r["n"],
                  "xp": r["xp"], "_o": order.index(r["token"])} for r in rows),
                key=lambda t: t["_o"],
            )
            for t in tokens:
                t.pop("_o")
            recent = conn.execute(
                "SELECT token, xp, reason, created_at FROM token_ledger WHERE agent=? ORDER BY id DESC LIMIT 5",
                (agent,),
            ).fetchall()
            return {
                "agent": agent,
                **R.level_for(self._xp(conn, agent)),
                "tokens": tokens,
                "recent": [{"label": f"{catalog[r['token']].emoji} {catalog[r['token']].name}", "xp": r["xp"],
                            "reason": r["reason"], "at": iso(r["created_at"])} for r in recent],
                "quests": self._quest_status(conn, agent, now),
            }

    def quests(self, agent: str) -> dict:
        now = _now()
        with self._read() as conn:
            return {"day": utc_day(now), "quests": self._quest_status(conn, agent, now),
                    "reward": f"🎯 +{R.SPECIAL_TOKENS['quest'].xp} XP each, 🌈 +{R.SPECIAL_TOKENS['trifecta'].xp} XP for all three"}

    def leaderboard(self, limit: int = 10) -> dict:
        limit = max(1, min(50, int(limit or 10)))
        with self._read() as conn:
            rows = conn.execute(
                "SELECT agent, SUM(xp) AS xp, COUNT(*) AS tokens,"
                " SUM(CASE WHEN token='odyssey' THEN 1 ELSE 0 END) AS odysseys"
                " FROM token_ledger GROUP BY agent ORDER BY xp DESC LIMIT ?", (limit,),
            ).fetchall()
            return {"leaders": [
                {"rank": i + 1, "agent": r["agent"], "xp": r["xp"], "tokens": r["tokens"],
                 "odysseys": r["odysseys"], "title": R.level_for(r["xp"])["rank"]}
                for i, r in enumerate(rows)
            ]}

    def export_csv(self, path: Path) -> int:
        with self._read() as conn:
            stages = self._stages(conn)
            rows = conn.execute(
                "SELECT d.*, c.name AS contact_name, c.handle, c.phone, c.email, c.company"
                " FROM deals d JOIN contacts c ON c.id=d.contact_id ORDER BY d.id"
            ).fetchall()
            by_key = {s["key"]: s["label"] for s in stages}
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(["deal_id", "title", "stage", "status", "value", "currency", "contact", "handle",
                            "phone", "email", "company", "next_action", "next_action_due", "loss_reason",
                            "owner", "created_at", "closed_at"])
                for r in rows:
                    w.writerow([r["id"], r["title"], by_key.get(r["stage_key"], r["stage_key"]), r["status"],
                                r["value"], r["currency"], r["contact_name"], r["handle"], r["phone"],
                                r["email"], r["company"], r["next_action"], iso(r["next_action_due"]),
                                r["loss_reason"], r["owner"], iso(r["created_at"]), iso(r["closed_at"])])
            return len(rows)


def _money(raw: Any) -> float:
    if raw is None or raw == "":
        return 0.0
    try:
        val = float(str(raw).replace(",", "").strip())
    except ValueError:
        raise QuestDeskError(f"value must be a number (got '{raw}').")
    if val < 0 or math.isinf(val) or math.isnan(val):
        raise QuestDeskError("value must be a non-negative number.")
    return round(val, 2)
