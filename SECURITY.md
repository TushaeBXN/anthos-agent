# Anthos Agent Security Policy

This document describes Anthos Agent's security model, the guardrail
system protecting the Anthos model, and vulnerability reporting.

## 1. Reporting a Vulnerability

Report privately via [GitHub Security Advisories](https://github.com/TushaeBXN/anthos-agent/security/advisories/new)
or email **brian.thomas.t@gmail.com**. Do not open public issues for
security vulnerabilities.

A useful report includes:

- A concise description and severity assessment.
- The affected component, identified by file path and line range.
- Environment details (`anthos version`, commit SHA, OS, Python version).
- A reproduction against `main` or the latest release.

---

## 2. Model Security — Anthos Guardrail System

Anthos Agent runs a self-hosted model (Qwen2.5-1.5B + LoRA fine-tune).
Unlike cloud-API providers that handle safety server-side, the Anthos
model requires its own safety layers. These are integrated directly
into the model server (`anthos_serve.py`).

### 2.1 Input Guardrails (Pre-Generation)

Every user prompt is screened **before** it reaches the model:

- **Jailbreak Defense** — Detects prompt injection, DAN mode, system
  override, and instruction-bypass patterns. Blocks the request
  entirely with a safety message.
- **HAP Filter** (Hate, Abuse, Profanity) — Keyword-based detection
  of slurs, hate speech, profanity, and derogatory language. Blocks
  the request.
- **Race/Ethnicity Blocker** — Prevents prompts that request
  stereotyping, racial classification, or discriminatory content.
- **PII Redaction** — Emails, phone numbers, SSNs, and IP addresses
  are masked (`[REDACTED_EMAIL]`, etc.) before reaching the model,
  so the model never sees raw PII.

### 2.2 Output Guardrails (Post-Generation)

Every model response is screened **after** generation:

- **HAP Filter** — Same hate/abuse/profanity check on model output.
  If the model generates toxic content, it is replaced with a safety
  message.
- **Race/Ethnicity Blocker** — Prevents the model from outputting
  racial/ethnic stereotyping even if the prompt was clean.
- **PII Redaction** — Any PII the model generates (emails, phones,
  SSNs, IPs) is masked before delivery.

### 2.3 Guardrail Response Format

When content is blocked, the API returns `finish_reason: "content_filter"`
and a `guardrail` object:

```json
{
  "choices": [{
    "message": {"role": "assistant", "content": "Request blocked: ..."},
    "finish_reason": "content_filter"
  }],
  "guardrail": {"status": "BLOCKED", "layer": "input"}
}
```

The `/v1/guardrails` endpoint reports which safety layers are active.

### 2.4 Godhead Armor (Deep Model Defense)

For the native Anthos architecture (Thought-Token Bifurcated Recurrent
Transformer), a 9-tier defense system protects the model's internal
computation:

| Tier | Name | What It Protects |
|------|------|------------------|
| 1 | Input Sanitizer | Catches jailbreaks, encoding tricks, flooding |
| 2 | Thought Stream Guard | Monitors thought token health, diversity, coherence |
| 3 | Memory Bank Armor | Rate-limits memory access, checksums, corruption repair |
| 4 | Loop Defender | Prevents divergence, stuck loops, amplification attacks |
| 5 | Adversarial Detector | Multi-signal attack detection (perplexity, entropy, distribution) |
| 6 | Behavioral Analyzer | Session-level pattern detection for coordinated attacks |
| 7 | Crypto Attestation | HMAC-SHA256 checkpoint signing and verification |
| 8 | Experimental | Honeypot tokens, entanglement defense, stochastic perturbation |
| 9 | Theoretical | Research-grade (consciousness detection, temporal shielding) |

The Godhead Armor is **not published** to GitHub. It lives in the
private Anthos model repository and is loaded at inference time.

---

## 3. Agent Security

### 3.1 Trust Model

Anthos Agent is a single-tenant personal agent. The trust model follows
a layered approach:

- **OS-level isolation** is the only hard security boundary. Nothing
  inside the agent process constitutes containment against an
  adversarial LLM.
- **Terminal-backend isolation** runs LLM-emitted commands in a
  container or sandbox.
- **Whole-process wrapping** (Docker) sandboxes the entire agent.

### 3.2 In-Process Heuristics

These are useful but are not boundaries:

- **Approval gate** — Detects destructive shell patterns and prompts
  before execution.
- **Output redaction** — Strips secret-like patterns from display.
- **Skills Guard** — Scans installable skill content for injection.
- **Credential scoping** — Filters environment variables passed to
  subprocesses.

### 3.3 Plugin & Skill Trust

Plugins and skills load into the agent process with full privileges.
The boundary is operator review before install.

### 3.4 External Surfaces

Network-exposed surfaces (gateway adapters, dashboard, API server)
require an operator-configured caller allowlist. Local-only surfaces
(ACP, TUI) rely on OS-level access control.

---

## 4. Credential & Secret Protection

- API keys and tokens are loaded from environment variables, never
  hardcoded or committed.
- The model checkpoint and LoRA weights are **not** in the public
  repository.
- The Anthos model server supports optional Bearer token
  authentication (`ANTHOS_API_KEY`).
- Credential files should have tight permissions (600).

---

## 5. Deployment Hardening

- Run as a non-root user.
- Do not expose `anthos serve` to the public internet without a
  reverse proxy, VPN, or firewall.
- Set `ANTHOS_API_KEY` when running the model server.
- The model server binds to `0.0.0.0` by default — restrict to
  `127.0.0.1` for local-only use.
- Review third-party skills and plugins before installing.
- Keep dependencies updated (`pip install --upgrade`).

---

## 6. Scope

### 6.1 In Scope

- Escape from OS-level isolation.
- Unauthorized access to external surfaces (gateway, API).
- Credential exfiltration via agent mechanisms.
- Guardrail bypasses that lead to real harm (not theoretical
  regex games).
- Checkpoint tampering or signature forgery.

### 6.2 Out of Scope

- Bypasses of in-process heuristics (approval gate, redaction) —
  these are not boundaries.
- Prompt injection without a chained harmful outcome.
- Third-party plugin/skill behavior — operator's review surface.
- Public exposure without authentication.

---

## 7. Disclosure

- **Coordinated disclosure window:** 90 days from report.
- **Credit:** reporters are credited in release notes unless
  anonymity is requested.
