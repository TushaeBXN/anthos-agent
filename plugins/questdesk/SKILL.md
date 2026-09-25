---
name: sales-pilot
description: Run the QuestDesk CRM from chat and earn tokens.
version: 0.1.0
author: TushaeBXN, Anthos Agent
license: MIT
metadata:
  anthos:
    tags: [crm, sales, telegram, pipeline, gamification]
    category: productivity
---

# QuestDesk Sales Pilot Skill

Operate the QuestDesk CRM while chatting with leads on Telegram (or any
gateway platform): log contacts, move deals through the pipeline, keep the
follow-up radar clear, and earn tokens + XP for real progress. It does not
send messages to leads by itself — you still talk to them in the chat.

## When to Use

- A lead or customer shows buying intent in a conversation.
- The user asks "what's in my pipeline", "who should I follow up with",
  "move Ana to proposal", "log that call".
- Start of a work session: check the radar and today's quests.

## Prerequisites

- Plugin enabled: `plugins.enabled: [questdesk]` in `config.yaml`, and the
  `questdesk` toolset enabled for the platform (`anthos tools`).
- Optional: pick a niche pipeline with `anthos questdesk init --preset
  <sales|ecommerce|clinic|realestate|services|creator>` (default: sales).

## How to Run

Three tools, each with an `action`:

- `questdesk_contact` — add / update / get / search / note
- `questdesk_deal` — create / move / update / lose / get / list / board / radar / stages
- `questdesk_rewards` — wallet / quests / leaderboard / catalog

Users can check the board without an agent turn: `/pipeline`,
`/pipeline radar`, `/pipeline quests`, `/pipeline wallet`.

## Quick Reference

| Goal | Call |
|---|---|
| New lead from this chat | `questdesk_deal` action=create, title, contact_name, handle, value, next_action, next_action_due |
| Real progress happened | `questdesk_deal` action=move, deal_id, stage, note="what happened" |
| Plan the follow-up | `questdesk_deal` action=update, next_action, next_action_due="2d" |
| Deal is dead | `questdesk_deal` action=lose, loss_reason |
| Who needs attention | `questdesk_deal` action=radar |
| My progress | `questdesk_rewards` action=wallet |

## Procedure

1. **Session start:** call `questdesk_deal` action=radar and
   `questdesk_rewards` action=quests. Work overdue deals first.
2. **Search before creating:** `questdesk_contact` action=search with the
   Telegram handle or name. Contact `add` also dedupes on handle, phone and
   email.
3. **Create the deal in one call** with `contact_name` + `handle` when the
   contact is new, and always set `next_action` + `next_action_due`.
4. **Move only when it really happened**, with a note that says what
   happened (who said what, what was sent, what was paid). Advancing
   without a note of at least 12 characters is rejected.
5. **Read the result:** `rewards`, `celebration`, `level_up`, `notices`
   and `next_goal`. Share a win with the user in one short line. Don't
   paste the JSON.
6. **Close honestly:** mark lost deals with a real `loss_reason`. That
   earns a 🛡️ Honor token and keeps the win rate truthful.

## Pitfalls

- **Don't fast-forward deals for tokens.** A stage token is withheld if the
  deal spent less than 10 minutes in its previous stage, and a skipped
  stage forfeits the deal's 🏆 Odyssey. Moves still apply; only the token
  is lost.
- Backward moves never mint tokens, and each stage token mints once per deal.
- `next_action_due` takes `4h`, `2d`, `1w`, `YYYY-MM-DD` or ISO-8601 (UTC).
- Tokens go to the active profile unless you pass `agent`. Only pass it
  when a named subagent really did the work.

## Verification

- `questdesk_deal` action=get shows the deal's activity trail and
  `tokens_earned`.
- `/pipeline` board totals match what you logged.
- `anthos questdesk export` writes a CSV of every deal for a human check.
