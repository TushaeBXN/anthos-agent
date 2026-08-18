"""
Anthos Trajectory Viewer — standalone HTTP server.

Reads directly from ~/.hermes/state.db and serves a session trajectory
inspection UI at http://localhost:9121.  Zero extra dependencies beyond
the Python standard library.

Invoked via:  anthos trajectory [--port N] [--no-open]
"""

from __future__ import annotations

import html
import json
import logging
import math
import os
import sqlite3
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _db_path() -> Path:
    from hermes_constants import get_hermes_home  # local import to avoid circular
    return get_hermes_home() / "state.db"


def _connect() -> sqlite3.Connection:
    db = _db_path()
    if not db.exists():
        raise FileNotFoundError(
            f"No session database found at {db}. "
            "Start Anthos Agent at least once to create it."
        )
    conn = sqlite3.connect(str(db), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA query_only=1")
    return conn


def _list_sessions(conn: sqlite3.Connection, limit: int = 100) -> list[dict]:
    cur = conn.execute(
        """
        SELECT id, title, source, model, started_at, ended_at,
               message_count, tool_call_count,
               input_tokens, output_tokens,
               estimated_cost_usd, actual_cost_usd
        FROM sessions
        WHERE parent_session_id IS NULL
          AND archived = 0
        ORDER BY started_at DESC
        LIMIT ?
        """,
        (limit,),
    )
    rows = cur.fetchall()
    return [dict(r) for r in rows]


def _get_session(conn: sqlite3.Connection, session_id: str) -> dict | None:
    cur = conn.execute(
        "SELECT * FROM sessions WHERE id = ?", (session_id,)
    )
    row = cur.fetchone()
    return dict(row) if row else None


def _get_messages(conn: sqlite3.Connection, session_id: str) -> list[dict]:
    cur = conn.execute(
        """
        SELECT id, role, content, tool_call_id, tool_calls, tool_name,
               timestamp, token_count, finish_reason,
               reasoning, reasoning_content, reasoning_details,
               active, compacted
        FROM messages
        WHERE session_id = ?
        ORDER BY timestamp ASC, id ASC
        """,
        (session_id,),
    )
    rows = cur.fetchall()
    out = []
    for r in rows:
        d = dict(r)
        if d.get("tool_calls"):
            try:
                d["tool_calls"] = json.loads(d["tool_calls"])
            except Exception:
                d["tool_calls"] = []
        out.append(d)
    return out


# ---------------------------------------------------------------------------
# HTML page (self-contained, inlined CSS + JS)
# ---------------------------------------------------------------------------

_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Anthos Trajectory Viewer</title>
<style>
:root {
  --bg: #0d1117;
  --sidebar-bg: #161b22;
  --panel-bg: #161b22;
  --border: #30363d;
  --text: #e6edf3;
  --text-muted: #7d8590;
  --accent: #58a6ff;
  --accent2: #3fb950;
  --warn: #d29922;
  --danger: #f85149;
  --tool-bg: #1c2128;
  --think-bg: #161b22;
  --think-border: #3d444d;
  --user-accent: #388bfd;
  --assistant-accent: #3fb950;
  --system-accent: #8b949e;
  --tool-call-accent: #e3b341;
  --tool-result-accent: #bc8cff;
  --radius: 8px;
  --mono: 'SF Mono', 'Fira Code', 'Cascadia Code', Consolas, monospace;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; font-size: 14px; height: 100vh; display: flex; overflow: hidden; }

/* ---- Sidebar ---- */
#sidebar {
  width: 280px; min-width: 220px; max-width: 360px;
  background: var(--sidebar-bg);
  border-right: 1px solid var(--border);
  display: flex; flex-direction: column;
  flex-shrink: 0;
}
#sidebar-header {
  padding: 16px;
  border-bottom: 1px solid var(--border);
  display: flex; align-items: center; gap: 10px;
}
#sidebar-header h1 { font-size: 15px; font-weight: 600; color: var(--accent); }
#sidebar-header .logo { font-size: 22px; }
#session-list { flex: 1; overflow-y: auto; padding: 8px 0; }
.session-item {
  padding: 10px 16px;
  cursor: pointer;
  border-left: 3px solid transparent;
  transition: background 0.1s, border-color 0.1s;
}
.session-item:hover { background: rgba(88,166,255,0.06); }
.session-item.active { border-left-color: var(--accent); background: rgba(88,166,255,0.1); }
.session-title { font-weight: 500; font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.session-meta { color: var(--text-muted); font-size: 11px; margin-top: 3px; display: flex; gap: 8px; }
.session-meta span { display: flex; align-items: center; gap: 3px; }

#empty-state {
  padding: 40px 20px; text-align: center; color: var(--text-muted);
  font-size: 13px; line-height: 1.6;
}
#empty-state .icon { font-size: 40px; display: block; margin-bottom: 12px; }

/* ---- Main ---- */
#main {
  flex: 1; display: flex; flex-direction: column; overflow: hidden;
}

/* Stats bar */
#stats-bar {
  padding: 10px 20px;
  border-bottom: 1px solid var(--border);
  background: var(--panel-bg);
  display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
  font-size: 12px; color: var(--text-muted);
  min-height: 42px;
}
.stat { display: flex; align-items: center; gap: 5px; }
.stat .label { color: var(--text-muted); }
.stat .val { color: var(--text); font-weight: 500; }
.stat .badge {
  background: rgba(88,166,255,0.15); color: var(--accent);
  border-radius: 4px; padding: 1px 6px; font-size: 11px; font-weight: 600;
}
#session-title-bar {
  font-size: 14px; font-weight: 600; color: var(--text);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  flex: 1; min-width: 0;
}

/* Trajectory */
#trajectory {
  flex: 1; overflow-y: auto;
  padding: 20px 0;
}
#placeholder {
  display: flex; align-items: center; justify-content: center;
  height: 100%; color: var(--text-muted); font-size: 15px;
  flex-direction: column; gap: 12px;
}
#placeholder .big-icon { font-size: 56px; }

/* Message blocks */
.msg-block {
  display: flex; gap: 0; margin-bottom: 4px;
  padding: 0 20px;
}
.role-tag {
  width: 80px; min-width: 80px;
  font-size: 10px; font-weight: 700; letter-spacing: 0.5px;
  text-transform: uppercase; padding-top: 12px;
  flex-shrink: 0; color: var(--text-muted);
  text-align: right; padding-right: 12px;
}
.msg-inner {
  flex: 1; border-radius: var(--radius);
  padding: 10px 14px; min-width: 0;
  border-left: 3px solid transparent;
}
.msg-block.role-system .role-tag { color: var(--system-accent); }
.msg-block.role-system .msg-inner { border-left-color: var(--system-accent); background: rgba(139,148,158,0.07); }
.msg-block.role-user .role-tag { color: var(--user-accent); }
.msg-block.role-user .msg-inner { border-left-color: var(--user-accent); background: rgba(56,139,253,0.07); }
.msg-block.role-assistant .role-tag { color: var(--assistant-accent); }
.msg-block.role-assistant .msg-inner { border-left-color: var(--assistant-accent); background: rgba(63,185,80,0.06); }
.msg-block.role-tool .role-tag { color: var(--tool-result-accent); }
.msg-block.role-tool .msg-inner { border-left-color: var(--tool-result-accent); background: rgba(188,140,255,0.06); }
.msg-block.inactive { opacity: 0.4; }
.msg-block.compacted .msg-inner { border-style: dashed; }

.msg-ts {
  font-size: 10px; color: var(--text-muted); margin-bottom: 5px;
  display: flex; align-items: center; gap: 8px;
}
.msg-ts .tool-name-tag {
  background: rgba(188,140,255,0.15); color: var(--tool-result-accent);
  border-radius: 3px; padding: 1px 5px; font-size: 10px;
}
.msg-ts .tc-badge {
  background: rgba(227,179,65,0.15); color: var(--tool-call-accent);
  border-radius: 3px; padding: 1px 5px; font-size: 10px;
}
.msg-content { white-space: pre-wrap; word-break: break-word; line-height: 1.6; font-size: 13px; }
.msg-content code { font-family: var(--mono); font-size: 12px; background: rgba(110,118,129,0.15); padding: 1px 4px; border-radius: 3px; }

/* Thinking block */
.think-block {
  margin-top: 8px; border: 1px solid var(--think-border);
  border-radius: 6px; overflow: hidden;
}
.think-toggle {
  padding: 6px 10px; cursor: pointer;
  background: var(--think-bg); border: none; width: 100%;
  text-align: left; color: var(--text-muted); font-size: 11px;
  display: flex; align-items: center; gap: 6px;
  transition: background 0.1s;
}
.think-toggle:hover { background: rgba(110,118,129,0.15); }
.think-toggle .chevron { transition: transform 0.15s; display: inline-block; }
.think-toggle.open .chevron { transform: rotate(90deg); }
.think-content {
  display: none; padding: 10px; background: rgba(110,118,129,0.05);
  white-space: pre-wrap; font-size: 12px; color: var(--text-muted);
  font-family: var(--mono); line-height: 1.5; max-height: 300px; overflow-y: auto;
}
.think-content.open { display: block; }

/* Tool calls */
.tool-calls-wrap { margin-top: 8px; display: flex; flex-direction: column; gap: 6px; }
.tool-call-block { border: 1px solid rgba(227,179,65,0.25); border-radius: 6px; overflow: hidden; }
.tool-call-header {
  padding: 7px 10px; cursor: pointer; background: rgba(227,179,65,0.07);
  border: none; width: 100%; text-align: left; color: var(--tool-call-accent);
  font-size: 12px; font-weight: 600; display: flex; align-items: center; gap: 8px;
  font-family: var(--mono);
}
.tool-call-header:hover { background: rgba(227,179,65,0.12); }
.tool-call-header .chevron { margin-left: auto; color: var(--text-muted); transition: transform 0.15s; }
.tool-call-header.open .chevron { transform: rotate(180deg); }
.tool-call-body { display: none; padding: 10px; background: rgba(227,179,65,0.04); }
.tool-call-body.open { display: block; }
.tool-call-body pre {
  font-family: var(--mono); font-size: 11px; white-space: pre-wrap;
  word-break: break-all; color: var(--text); line-height: 1.5;
  max-height: 240px; overflow-y: auto;
}

/* Scrollbar */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #484f58; }

/* Separator */
.day-sep {
  text-align: center; color: var(--text-muted); font-size: 11px;
  padding: 8px 0 4px; position: relative; margin: 8px 20px;
}
.day-sep::before {
  content: ''; position: absolute; left: 0; right: 0; top: 50%;
  border-top: 1px solid var(--border); z-index: 0;
}
.day-sep span { background: var(--bg); padding: 0 10px; position: relative; z-index: 1; }
</style>
</head>
<body>

<div id="sidebar">
  <div id="sidebar-header">
    <span class="logo">⚡</span>
    <h1>Anthos Trajectory</h1>
  </div>
  <div id="session-list"></div>
</div>

<div id="main">
  <div id="stats-bar">
    <span id="session-title-bar" style="color:var(--text-muted);font-weight:400;">Select a session</span>
  </div>
  <div id="trajectory">
    <div id="placeholder">
      <span class="big-icon">🔭</span>
      <span>Select a session to inspect its trajectory</span>
    </div>
  </div>
</div>

<script>
const $ = id => document.getElementById(id);

function esc(s) {
  if (!s) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function fmtDate(ts) {
  if (!ts) return '—';
  const d = new Date(ts * 1000);
  return d.toLocaleDateString(undefined, {month:'short', day:'numeric'}) + ' ' +
         d.toLocaleTimeString(undefined, {hour:'2-digit', minute:'2-digit'});
}

function fmtDur(start, end) {
  if (!start || !end) return null;
  const s = Math.round(end - start);
  if (s < 60) return s + 's';
  const m = Math.floor(s/60), sec = s % 60;
  return `${m}m ${sec}s`;
}

function fmtTokens(n) {
  if (!n) return '0';
  if (n >= 1000) return (n/1000).toFixed(1) + 'k';
  return String(n);
}

function relTime(ts) {
  if (!ts) return '';
  const now = Date.now() / 1000;
  const diff = now - ts;
  if (diff < 60) return 'just now';
  if (diff < 3600) return Math.round(diff/60) + 'm ago';
  if (diff < 86400) return Math.round(diff/3600) + 'h ago';
  return Math.round(diff/86400) + 'd ago';
}

// ---- Session list ----
async function loadSessions() {
  const resp = await fetch('/api/sessions');
  const sessions = await resp.json();
  const list = $('session-list');
  if (!sessions.length) {
    list.innerHTML = '<div id="empty-state"><span class="icon">💬</span>No sessions yet.<br>Start a conversation in Anthos Agent to see trajectories here.</div>';
    return;
  }
  list.innerHTML = sessions.map(s => `
    <div class="session-item" data-id="${esc(s.id)}" onclick="loadSession('${esc(s.id)}')">
      <div class="session-title">${esc(s.title || 'Untitled session')}</div>
      <div class="session-meta">
        <span title="${fmtDate(s.started_at)}">${relTime(s.started_at)}</span>
        <span>💬 ${s.message_count || 0}</span>
        <span>🔧 ${s.tool_call_count || 0}</span>
        ${s.source && s.source !== 'cli' ? `<span>${esc(s.source)}</span>` : ''}
      </div>
    </div>
  `).join('');
}

// ---- Session trajectory ----
let activeId = null;
async function loadSession(id) {
  activeId = id;
  document.querySelectorAll('.session-item').forEach(el => {
    el.classList.toggle('active', el.dataset.id === id);
  });

  const [sessResp, msgsResp] = await Promise.all([
    fetch(`/api/sessions/${encodeURIComponent(id)}`),
    fetch(`/api/sessions/${encodeURIComponent(id)}/messages`),
  ]);
  const sess = await sessResp.json();
  const msgs = await msgsResp.json();

  // Stats bar
  const dur = fmtDur(sess.started_at, sess.ended_at);
  const model = sess.model || '—';
  const totalTok = (sess.input_tokens || 0) + (sess.output_tokens || 0);
  const cost = sess.actual_cost_usd != null
    ? '$' + sess.actual_cost_usd.toFixed(4)
    : sess.estimated_cost_usd != null
    ? '~$' + sess.estimated_cost_usd.toFixed(4)
    : null;

  $('stats-bar').innerHTML = `
    <span id="session-title-bar">${esc(sess.title || 'Untitled session')}</span>
    <span class="stat"><span class="label">model</span><span class="badge">${esc(model.split('/').pop())}</span></span>
    <span class="stat"><span class="label">turns</span><span class="val">${sess.message_count || msgs.length}</span></span>
    <span class="stat"><span class="label">tools</span><span class="val">${sess.tool_call_count || 0}</span></span>
    ${totalTok ? `<span class="stat"><span class="label">tokens</span><span class="val">${fmtTokens(totalTok)}</span></span>` : ''}
    ${dur ? `<span class="stat"><span class="label">duration</span><span class="val">${dur}</span></span>` : ''}
    ${cost ? `<span class="stat"><span class="label">cost</span><span class="val">${esc(cost)}</span></span>` : ''}
    <span class="stat"><span class="label">source</span><span class="val">${esc(sess.source || '—')}</span></span>
    <span class="stat"><span class="label">started</span><span class="val">${fmtDate(sess.started_at)}</span></span>
  `;

  renderTrajectory(msgs);
}

function renderTrajectory(msgs) {
  const traj = $('trajectory');
  if (!msgs.length) {
    traj.innerHTML = '<div id="placeholder"><span class="big-icon">📭</span><span>No messages in this session.</span></div>';
    return;
  }

  let html = '';
  let lastDay = null;

  msgs.forEach((m, i) => {
    const d = new Date((m.timestamp || 0) * 1000);
    const day = d.toDateString();
    if (day !== lastDay) {
      lastDay = day;
      html += `<div class="day-sep"><span>${esc(d.toLocaleDateString(undefined,{weekday:'short',month:'short',day:'numeric'}))}</span></div>`;
    }

    const role = m.role || 'unknown';
    const inactive = !m.active ? ' inactive' : '';
    const compacted = m.compacted ? ' compacted' : '';

    html += `<div class="msg-block role-${esc(role)}${inactive}${compacted}">`;
    html += `<div class="role-tag">${esc(role)}</div>`;
    html += `<div class="msg-inner">`;

    // timestamp + tool name badge
    const tsStr = m.timestamp
      ? new Date(m.timestamp * 1000).toLocaleTimeString(undefined, {hour:'2-digit', minute:'2-digit', second:'2-digit'})
      : '';
    html += `<div class="msg-ts"><span>${tsStr}</span>`;
    if (m.tool_name) html += `<span class="tool-name-tag">⚙ ${esc(m.tool_name)}</span>`;
    if (m.tool_calls && m.tool_calls.length) html += `<span class="tc-badge">🔧 ${m.tool_calls.length} call${m.tool_calls.length > 1 ? 's' : ''}</span>`;
    if (!m.active) html += `<span style="color:var(--text-muted);font-size:10px">compacted</span>`;
    html += `</div>`;

    // Thinking / reasoning
    const thinking = m.reasoning_content || m.reasoning;
    if (thinking) {
      const uid = `think-${i}`;
      html += `<div class="think-block">
        <button class="think-toggle" onclick="toggleThink('${uid}')">
          <span class="chevron">▶</span> <span>Reasoning</span>
          <span style="margin-left:auto;font-size:10px">${esc(thinking.length.toLocaleString())} chars</span>
        </button>
        <div class="think-content" id="${uid}">${esc(thinking)}</div>
      </div>`;
    }

    // Main content
    if (m.content) {
      html += `<div class="msg-content">${esc(m.content)}</div>`;
    }

    // Tool calls
    if (m.tool_calls && m.tool_calls.length) {
      html += `<div class="tool-calls-wrap">`;
      m.tool_calls.forEach((tc, j) => {
        const uid = `tc-${i}-${j}`;
        const fname = tc.function?.name || tc.name || 'tool';
        let args = '';
        try {
          const raw = tc.function?.arguments || tc.arguments || '';
          args = typeof raw === 'string' ? JSON.stringify(JSON.parse(raw), null, 2) : JSON.stringify(raw, null, 2);
        } catch { args = String(tc.function?.arguments || tc.arguments || ''); }
        html += `<div class="tool-call-block">
          <button class="tool-call-header" onclick="toggleTc('${uid}')">
            <span>⚙</span> <span>${esc(fname)}</span>
            <span class="chevron" style="font-size:10px">▼</span>
          </button>
          <div class="tool-call-body" id="${uid}">
            <pre>${esc(args)}</pre>
          </div>
        </div>`;
      });
      html += `</div>`;
    }

    html += `</div></div>`;
  });

  traj.innerHTML = html;
  traj.scrollTop = 0;
}

function toggleThink(id) {
  const btn = document.querySelector(`[onclick="toggleThink('${id}')"]`);
  const content = document.getElementById(id);
  btn.classList.toggle('open');
  content.classList.toggle('open');
}

function toggleTc(id) {
  const btn = document.querySelector(`[onclick="toggleTc('${id}')"]`);
  const body = document.getElementById(id);
  btn.classList.toggle('open');
  body.classList.toggle('open');
}

loadSessions();
setInterval(loadSessions, 30000);
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# HTTP request handler
# ---------------------------------------------------------------------------

class _Handler(BaseHTTPRequestHandler):
    conn: sqlite3.Connection

    def log_message(self, fmt, *args):  # suppress access log spam
        pass

    def _send_json(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, body: str) -> None:
        b = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        try:
            if path == "/":
                self._send_html(_HTML)
                return

            if path == "/api/sessions":
                self._send_json(_list_sessions(self.server._conn))
                return

            # /api/sessions/<id>  or  /api/sessions/<id>/messages
            parts = path.split("/")
            if len(parts) >= 4 and parts[1] == "api" and parts[2] == "sessions":
                session_id = parts[3]
                if len(parts) == 4:
                    sess = _get_session(self.server._conn, session_id)
                    if sess is None:
                        self._send_json({"error": "not found"}, 404)
                    else:
                        self._send_json(sess)
                    return
                if len(parts) == 5 and parts[4] == "messages":
                    msgs = _get_messages(self.server._conn, session_id)
                    self._send_json(msgs)
                    return

            self._send_json({"error": "not found"}, 404)

        except Exception as exc:
            logger.exception("trajectory viewer error")
            self._send_json({"error": str(exc)}, 500)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def serve(port: int = 9121, open_browser: bool = True) -> None:
    """Start the trajectory viewer server. Blocks until Ctrl-C."""
    try:
        conn = _connect()
    except FileNotFoundError as exc:
        print(f"[trajectory] {exc}", file=sys.stderr)
        sys.exit(1)

    server = HTTPServer(("127.0.0.1", port), _Handler)
    server._conn = conn  # type: ignore[attr-defined]

    url = f"http://127.0.0.1:{port}"
    print(f"⚡ Anthos Trajectory Viewer  →  {url}")
    print("   Press Ctrl-C to stop.\n")

    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        conn.close()
