# QuestDesk 🗺️🪙

A gamified sales CRM for Anthos that works in Telegram first. The agent
that chats with your leads also runs the pipeline, and it earns
**tokens + XP** for every real step it pushes a deal forward.

Inspired by [DeskcommCRM](https://github.com/melgarafael/DeskcommCRM) (MIT).
DeskcommCRM is a full Next.js + Supabase + WhatsApp stack. QuestDesk keeps its
best ideas (niche pipeline wording, contact records, a follow-up radar,
agents that *run* the CRM) and uses Anthos's existing messaging gateway
instead of a separate web app. So it works on Telegram, and on every other
platform Anthos supports, with zero extra infrastructure.

## Enable

```yaml
# ~/.anthos/config.yaml
plugins:
  enabled: [questdesk]
```

Then enable the `questdesk` toolset for your platform with `anthos tools`, and
optionally pick a pipeline:

```bash
anthos questdesk presets                 # sales, ecommerce, clinic, realestate, services, creator
anthos questdesk init --preset clinic    # or: --stages "Lead,Call,Signed,Paid"
```

Data lives in `<ANTHOS_HOME>/questdesk/questdesk.db` (one per profile).

## What you get

| Surface | What |
|---|---|
| `questdesk_contact` | add (auto-dedupe on handle/phone/email), update, get, search, note |
| `questdesk_deal` | create (auto-creates the contact), move, update, lose, get, list, board, radar, stages |
| `questdesk_rewards` | wallet, quests, leaderboard, catalog |
| `/pipeline [view]` | Board / radar / quests / wallet / leaderboard in chat, with no agent turn |
| `anthos questdesk …` | init, presets, board, radar, quests, wallet, leaderboard, catalog, export (CSV) |
| Skill `questdesk:sales-pilot` | The playbook the agent follows |

## The token economy

**Stage tokens.** Each pipeline position mints its own token, once per deal:
🌱 Spark → 🔍 Insight → 📜 Scroll → ⚔️ Duel → 🤝 Pact → 🚀 Orbit (→ 🌀 Nexus → 👑 Crown).

**Special tokens:**

| Token | Earned by |
|---|---|
| 🏆 Odyssey (+100) | Taking one deal through **every** stage, earning each stage token on the way |
| ⚡ Lightning (+50) | Finishing an Odyssey within 7 days |
| 🐦‍🔥 Phoenix (+30) | Advancing a deal that had been stuck 14+ days |
| 🔥 Blaze (+25) | Advancing deals on 3 / 7 / 14 / 30 days in a row |
| 🛡️ Honor (+15) | Marking a dead deal lost with a real reason |
| 🎯 Quest (+20) / 🌈 Trifecta (+40) | Today's three daily quests, and finishing all three |
| 🌟 Constellation (+250) | Collecting every stage token plus an Odyssey |

XP rolls up into ten ranks, from *Rookie Closer* to *Mythic Closer*. Every tool
result carries `rewards`, `celebration`, `level_up` and a `next_goal`
("2 stages to a 🏆 Odyssey"), so the agent always sees its next win.

**Anti-gaming.** Tokens should track real progress, not tool calls:

- Advancing needs an evidence note (≥12 chars).
- A stage token is withheld if the deal spent under 10 min in its previous
  stage. The move still happens.
- Skipped stages forfeit their tokens and the deal's Odyssey. Backward
  moves never mint anything.
- Every token has a unique dedupe key, and the ledger is append-only.
- Daily caps apply to Spark (new deals) and Honor.

## Improvements over the original

- Works in chat first: one tool call creates a deal *and* its contact; the
  board is one slash command away.
- A heat score (0–100) on every deal: pipeline progress + recency + value.
- The radar flags overdue next actions, missing next actions, quiet deals and
  stalled deals.
- The whole token/quest/level layer is new.
- No database server, no web stack: one SQLite file, and every change is
  atomic.
