# Anthos Agent Security Policy

This document describes Anthos Agent's trust model, the guardrail
system protecting the Anthos model, names the security boundaries
the project treats as load-bearing, and defines the scope for
vulnerability reports.

## 1. Reporting a Vulnerability

Report privately via [GitHub Security Advisories](https://github.com/TushaeBXN/anthos-agent/security/advisories/new)
or email **brian.thomas.t@gmail.com**. Do not open public issues for
security vulnerabilities.

A useful report includes:

- A concise description and severity assessment.
- The affected component, identified by file path and line range
  (e.g. `path/to/file.py:120-145`).
- Environment details (`anthos version`, commit SHA, OS, Python
  version).
- A reproduction against `main` or the latest release.
- A statement of which trust boundary in §3 or §4 is crossed.

Please read §3, §4, and §5 before submitting. Reports that
demonstrate limits of an in-process heuristic this policy does not
treat as a boundary will be closed as out-of-scope under §5 — but
see §5.2: they are still welcome as regular issues or pull requests,
just not through the private security channel.

---

## 2. Model Security — Anthos Guardrail System

Anthos Agent runs a self-hosted model (Qwen2.5-1.5B + LoRA fine-tune
by Brian Tushae Thomas). Unlike cloud-API providers that handle safety
server-side, the Anthos model requires its own safety layers. These
are integrated directly into the model server (`anthos_serve.py`).

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

### 2.4 Guardrail Limitations

The guardrail system uses keyword matching and regex patterns. It is
a useful safety net, not a boundary. A motivated adversary can craft
inputs that evade keyword filters. The guardrails catch cooperative-
mode mistakes and casual misuse; they do not constitute containment
against a determined attacker. Defense-in-depth through the Godhead
Armor (§2.5) and OS-level isolation (§3.2) provides the real
boundaries.

### 2.5 Godhead Armor (Deep Model Defense)

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

## 3. Agent Trust Model

Anthos Agent is a single-tenant personal agent. Its posture is
layered, and the layers are not equally load-bearing. Reporters and
operators should reason about them in the same terms.

### 3.1 Definitions

- **Agent process.** The Python interpreter running Anthos Agent,
  including any Python modules it has loaded (skills, plugins,
  hook handlers).
- **Terminal backend.** A pluggable execution target for the
  `terminal()` tool. The default runs commands directly on the host.
  Other backends run commands inside a container, cloud sandbox, or
  remote host.
- **Input surface.** Any channel through which content enters the
  agent's context: operator input, web fetches, email, gateway
  messages, file reads, MCP server responses, tool results.
- **Trust envelope.** The set of resources an operator has implicitly
  granted Anthos Agent access to by running it — typically, whatever
  the operator's own user account can reach on the host.
- **Stance.** An explicit statement in Anthos Agent's documentation
  or code about how a consuming layer (adapter, UI, file writer,
  shell) should treat agent output — e.g. "the dashboard renders
  agent output as inert HTML."

### 3.2 The Boundary: OS-Level Isolation

**The only security boundary against an adversarial LLM is the
operating system.** Nothing inside the agent process constitutes
containment — not the approval gate, not output redaction, not the
guardrail system (§2), not any pattern scanner, not any tool
allowlist. Any in-process component that screens LLM output is a
heuristic operating on an attacker-influenced string, and this
policy treats it as such.

Anthos Agent supports two OS-level isolation postures. They address
different threats and an operator should choose deliberately.

#### Terminal-backend isolation

A non-default terminal backend runs LLM-emitted shell commands
inside a container, remote host, or cloud sandbox. The file tools
(`read_file`, `write_file`, `patch`) also run through this backend,
since they are implemented on top of the shell contract — they
cannot reach paths the backend doesn't expose.

What this confines: anything the agent does by issuing shell or
file operations. What this does **not** confine: everything the
agent does in its own Python process. That includes the
code-execution tool (spawned as a host subprocess), MCP subprocesses
(spawned from the agent's environment), plugin loading, hook
dispatch, and skill loading (all imported into the agent
interpreter).

Terminal-backend isolation is the right posture when the concern is
LLM-emitted destructive shell or unwanted file-tool writes, and the
operator is otherwise trusted.

#### Whole-process wrapping

Whole-process wrapping runs the entire agent process tree inside a
sandbox. Every code path — shell, code-execution, MCP, file tools,
plugins, hooks, skill loading — is subject to the same filesystem,
network, process, and (where applicable) inference policy.

Anthos Agent supports this via its Docker image and Compose setup.
The agent runs in a standard container with operator-configured
mounts and network policy.

Under a whole-process wrapper, Anthos Agent's in-process heuristics
(§3.4) and model guardrails (§2) function as accident-prevention
layered on top of a real boundary. This is the supported posture
when the agent ingests content from surfaces the operator does not
control — the open web, inbound email, multi-user channels,
untrusted MCP servers — and for production or shared deployments.

Operators running the default local backend with untrusted input
surfaces, or running a terminal-backend sandbox and expecting it to
contain code paths that don't go through the shell, are operating
outside the supported security posture.

### 3.3 Credential Scoping

Anthos Agent filters the environment it passes to its lower-trust
in-process components: shell subprocesses, MCP subprocesses,
cron job scripts, and the code-execution child. Credentials like
provider API keys and gateway tokens are stripped by default;
variables explicitly declared by the operator or by a loaded
skill are passed through.

This reduces casual exfiltration. It is not containment. Any
component running inside the agent process (skills, plugins, hook
handlers) can read whatever the agent itself can read, including
in-memory credentials. The mitigation against a compromised
in-process component is operator review before install (§3.4,
§3.5), not environment scrubbing.

### 3.4 In-Process Heuristics

The following components screen or warn about LLM behavior. They
are useful. They are not boundaries.

- The **approval gate** detects common destructive shell patterns
  and prompts the operator before execution. Shell is Turing-
  complete; a denylist over shell strings is structurally
  incomplete. The gate catches cooperative-mode mistakes, not
  adversarial output.
- **Output redaction** strips secret-like patterns from display.
  A motivated output producer will defeat it.
- **Skills Guard** scans installable skill content for injection
  patterns. It is a review aid; the boundary for third-party skills
  is operator review before install. Reviewing a skill means
  reading its Python code and scripts, not just its SKILL.md
  description — skills execute arbitrary Python at import time.
- **Model guardrails** (§2) screen input/output for harmful content.
  They are keyword-based heuristics, not boundaries (§2.4).

### 3.5 Plugin Trust Model

Plugins load into the agent process and run with full agent
privileges: they can read the same credentials, call the same
tools, register the same hooks, and import the same modules as
anything shipped in-tree. The boundary for third-party plugins is
operator review before install — the same rule as skills (§3.4),
called out separately because plugins are architecturally heavier
and often ship their own background services, network listeners,
and dependencies.

A malicious or buggy plugin is not a vulnerability in Anthos Agent
itself. Bugs in Anthos Agent's plugin-install or plugin-discovery
path that prevent the operator from seeing what they're installing
are in scope under §5.1.

---

## 4. External Surfaces

An **external surface** is any channel outside the local agent
process through which a caller can dispatch agent work, resolve
approvals, or receive agent output. Each surface has its own
authorization model, but the rules below apply uniformly.

**Surfaces in Anthos Agent:**

- **Gateway platform adapters.** Messaging integrations in
  `gateway/platforms/` (Telegram, Discord, Slack, email, SMS, etc.)
  and analogous adapters shipped as plugins.
- **Network-exposed HTTP surfaces.** The API server adapter, the
  dashboard plugin, the Anthos model server (`anthos_serve.py`),
  and any other plugin that binds a listening socket.
- **Editor / IDE adapters.** The ACP adapter (`acp_adapter/`) and
  equivalent integrations that accept requests from a local client
  process.
- **The TUI gateway (`tui_gateway/`).** JSON-RPC backend for the
  Ink terminal UI, reached over local IPC.

**Uniform rules:**

1. **Authorization is required at every surface that crosses a
   trust boundary.** For messaging and network HTTP surfaces, the
   boundary is the network: authorization means an operator-
   configured caller allowlist. For editor and local-IPC surfaces
   (ACP, TUI gateway), the boundary is the host's user account:
   authorization means relying on OS-level access control (file
   permissions, loopback-only binds) and not exposing the surface
   beyond the local user without an explicit network auth layer.
2. **An allowlist is required for every enabled network-exposed
   adapter.** Adapters must refuse to dispatch agent work, resolve
   approvals, or relay output until an allowlist is set. Code paths
   that fail open when no allowlist is configured are code bugs in
   scope under §5.1.
3. **Session identifiers are routing handles, not authorization
   boundaries.** Knowing another caller's session ID does not grant
   access to their approvals or output; authorization is always
   re-checked against the allowlist (or OS-level equivalent).
4. **Within the authorized set, all callers are equally trusted.**
   Anthos Agent does not model per-caller capabilities inside a
   single adapter. Operators who need capability separation should
   run separate agent instances with separate allowlists.
5. **Binding a local-only surface to a non-loopback interface is a
   break-glass operator decision (§5.2).** The dashboard and other
   plugin HTTP servers default to loopback; exposing them via
   `--host 0.0.0.0` or equivalent makes public-exposure hardening
   (§6) the operator's responsibility.

---

## 5. Scope

### 5.1 In Scope

- Escape from a declared OS-level isolation posture (§3.2): an
  attacker-controlled code path reaching state that the posture
  claimed to confine.
- Unauthorized external-surface access: a caller outside the
  configured authorization set (allowlist, or OS-level equivalent
  for local-IPC surfaces) dispatching work, receiving output, or
  resolving approvals (§4).
- Credential exfiltration: leakage of operator credentials or
  session authorization material to a destination outside the
  trust envelope, via a mechanism that should have prevented it
  (environment scrubbing bug, adapter logging, transport error
  that flushes credentials to an upstream, etc.).
- Trust-model documentation violations: code behaving contrary to
  what this policy, Anthos Agent's own documentation, or reasonable
  operator expectations would predict — including cases where
  Anthos Agent has documented a stance about how its output should
  be rendered by a consuming layer (dashboard, gateway adapter,
  file writer, shell) and a code path breaks that stance.
- Checkpoint tampering: bypassing the Godhead Armor's cryptographic
  attestation (Tier 7) to load a modified checkpoint without
  detection.

### 5.2 Out of Scope

"Out of scope" here means "not a security vulnerability under this
policy." It does not mean "not worth reporting." Improvements to the
in-process heuristics, hardening ideas, and UX fixes are welcome as
regular issues or pull requests — the approval gate can always catch
more patterns, redaction can always get smarter, guardrails can
always filter more. These items just don't go through the private-
disclosure channel and don't receive advisories.

- **Bypasses of in-process heuristics (§3.4)** — approval-gate regex
  bypasses, redaction bypasses, Skills Guard pattern bypasses,
  guardrail keyword bypasses (§2.4), and analogous reports against
  future heuristics. These components are not boundaries; defeating
  them is not a vulnerability under this policy.
- **Prompt injection per se.** Getting the LLM to emit unusual
  output — via injected content, hallucination, training artifacts,
  or any other cause — is not itself a vulnerability. "I achieved
  prompt injection" without a chained §5.1 outcome is not an
  actionable report under this policy.
- **Consequences of a chosen isolation posture.** Reports that a
  code path operating within its posture's scope can do what that
  posture permits are not vulnerabilities. Examples: shell or file
  tools reaching host state under the local backend; code-execution
  or MCP subprocesses reaching host state under terminal-backend
  isolation that only sandboxes shell; reports whose preconditions
  require pre-existing write access to operator-owned configuration
  or credential files (those are already inside the trust envelope).
- **Documented break-glass settings.** Operator-selected trade-offs
  that explicitly disable protections: `--insecure` and equivalent
  flags on the dashboard or other components, disabled approvals,
  local backend in production, development profiles, and similar.
  Reports against those configurations are not vulnerabilities —
  that's the flag's job.
- **Community-contributed skills and plugins.** Third-party skills
  and third-party plugins are in the operator's review surface, not
  Anthos Agent's trust surface (§3.4, §3.5). A skill or plugin
  doing something malicious is the expected failure mode of one that
  wasn't reviewed, not a vulnerability in Anthos Agent. Bugs in
  Anthos Agent's skill-install or plugin-install path that prevent
  the operator from seeing what they're installing are in scope
  under §5.1.
- **Public exposure without external controls.** Exposing the
  gateway, API, or model server to the public internet without
  authentication, VPN, or firewall.
- **Tool-level read/write restrictions on a posture where shell is
  permitted.** If a path is reachable via the terminal tool, reports
  that other file tools can reach it add nothing.

---

## 6. Deployment Hardening

The single most important hardening decision is matching isolation
(§3.2) to the trust of the content the agent will ingest. Beyond
that:

- Run the agent as a non-root user. The supplied container image
  does this by default.
- Keep credentials in the operator credential file with tight
  permissions (600), never in the main config, never in version
  control.
- The model checkpoint and LoRA weights are **not** in the public
  repository. The Godhead Armor defense code is `.gitignore`'d.
- Set `ANTHOS_API_KEY` when running the model server. The server
  binds to `0.0.0.0` by default — restrict to `127.0.0.1` for
  local-only use.
- Do not expose the gateway, API, or model server to the public
  internet without VPN, Tailscale, or firewall protection.
- Configure a caller allowlist for every network-exposed adapter
  you enable (§4).
- Review third-party skills and plugins before install (§3.4,
  §3.5). For skills, this means reading the Python and scripts,
  not just SKILL.md. Skills Guard reports and the install audit
  log are the review surface.

---

## 7. Disclosure

- **Coordinated disclosure window:** 90 days from report, or until a
  fix is released, whichever comes first.
- **Channel:** the GHSA thread or email correspondence with
  brian.thomas.t@gmail.com.
- **Credit:** reporters are credited in release notes unless
  anonymity is requested.
