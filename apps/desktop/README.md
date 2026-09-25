# Anthos Desktop ☤

<p align="center">
  <a href="https://github.com/TushaeBXN/anthos-agent/releases"><img src="https://img.shields.io/badge/Download-macOS%20%C2%B7%20Windows%20%C2%B7%20Linux-FFD700?style=for-the-badge" alt="Download"></a>
  <a href="https://anthos-agent.anthosai.com/docs/"><img src="https://img.shields.io/badge/Docs-anthos--agent.anthosai.com-FFD700?style=for-the-badge" alt="Documentation"></a>
  <a href="https://discord.gg/TushaeBXN"><img src="https://img.shields.io/badge/Discord-5865F2?style=for-the-badge&logo=discord&logoColor=white" alt="Discord"></a>
  <a href="https://github.com/TushaeBXN/anthos-agent/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License: MIT"></a>
</p>

**The native desktop app for [Anthos Agent](../../README.md) — the self-improving AI agent from [Anthos Intelligence](https://anthosai.com).** Same agent, same skills, same memory as the CLI and gateway, in a polished native window — chat with streaming tool output, side-by-side previews, a file browser, voice, and settings, no terminal required. Available for **macOS, Windows, and Linux**.

<table>
<tr><td><b>Chat with the full agent</b></td><td>Streaming responses, live tool activity, structured tool summaries, and the same conversation history as every other Anthos surface.</td></tr>
<tr><td><b>Side-by-side previews</b></td><td>Render web pages, files, and tool outputs in a right-hand pane while you keep chatting.</td></tr>
<tr><td><b>File browser</b></td><td>Explore and preview the working directory without leaving the app.</td></tr>
<tr><td><b>Voice</b></td><td>Talk to Anthos and hear it back.</td></tr>
<tr><td><b>Settings & onboarding</b></td><td>Manage providers, models, tools, and credentials from a real UI. First-run setup gets you to your first message in seconds.</td></tr>
<tr><td><b>Stays current</b></td><td>Built-in updates pull the latest agent and rebuild the app in place.</td></tr>
</table>

---

## Install

### Install with Anthos (recommended)

Already have the Anthos CLI? Just run:

```bash
anthos desktop
```

It builds and launches the GUI against your existing install — same config, keys, sessions, and skills. On first launch Anthos walks you through picking a provider and model; nothing else to configure.

### Prebuilt installers

Prebuilt installers are built and distributed via [the Anthos Desktop website.](https://anthos-agent.anthosai.com/).

---

## Updating

The app checks for updates in the background and offers a one-click update when one is ready. You can also update any time from the CLI:

```bash
anthos update
```

---

## Requirements

The installer handles everything for you (Python 3.11+, a portable Git, ripgrep).

---

## Development

Want to hack on the app itself? Install workspace deps from the repo root once, then run the dev server from this directory:

```bash
npm install          # from repo root — links apps/desktop, web, apps/shared
cd apps/desktop
npm run dev          # Vite renderer + Electron, which boots the Python backend
```

Point the app at a specific source checkout, or sandbox it away from your real config:

```bash
ANTHOS_DESKTOP_ANTHOS_ROOT=/path/to/clone npm run dev
ANTHOS_HOME=/tmp/throwaway npm run dev
npm run dev:fake-boot   # exercise the startup overlay with deterministic delays
```

### Building installers

```bash
npm run dist:mac     # DMG + zip
npm run dist:win     # NSIS + MSI
npm run dist:linux   # AppImage + deb + rpm
npm run pack         # unpacked app under release/ (no installer)
```

Installers are built and uploaded to GitHub Releases manually. macOS/Windows signing & notarization happen automatically when the relevant credentials are present in the environment (`CSC_LINK` / `CSC_KEY_PASSWORD` / `APPLE_*` for macOS, `WIN_CSC_*` for Windows).

### How it works

The packaged app ships the Electron shell and a native React chat surface. On first launch it can install the Anthos Agent runtime into `ANTHOS_HOME` (`~/.anthos`, or `%LOCALAPPDATA%\anthos` on Windows) — the **same layout a CLI install uses**, so the two are interchangeable. Backend resolution first honours `ANTHOS_DESKTOP_ANTHOS_ROOT`, then a completed managed install, then a probed `anthos` on `PATH` (unless `ANTHOS_DESKTOP_IGNORE_EXISTING=1` is set), and finally an explicit `ANTHOS_DESKTOP_ANTHOS` command override for packagers/troubleshooting. The renderer (React, in `src/`) talks to a `anthos dashboard` backend over the `tui_gateway`/dashboard APIs and reuses the agent runtime rather than embedding `anthos --tui`. The install, backend-resolution, and self-update logic all live in `electron/main.cjs`.

### Verification

Run before opening a PR (lint may surface pre-existing warnings but must exit cleanly):

```bash
npm run fix
npm run typecheck
npm run lint
npm run test:desktop:all
```

### Troubleshooting

Boot logs land in `ANTHOS_HOME/logs/desktop.log` (includes backend output and recent Python tracebacks) — check it first if the app reports a boot failure.

**macOS / Linux:**

```bash
# Force a clean first-launch setup
rm "$HOME/.anthos/anthos-agent/.anthos-bootstrap-complete"
# Rebuild a broken Python venv
rm -rf "$HOME/.anthos/anthos-agent/venv"
# Reset a stuck macOS microphone prompt (macOS only)
tccutil reset Microphone com.nousresearch.anthos
```

**Windows (PowerShell):**

```powershell
# Force a clean first-launch setup
Remove-Item "$env:LOCALAPPDATA\anthos\anthos-agent\.anthos-bootstrap-complete"
# Rebuild a broken Python venv
Remove-Item -Recurse -Force "$env:LOCALAPPDATA\anthos\anthos-agent\venv"
```

> The default Anthos home on Windows is `%LOCALAPPDATA%\anthos`. Set the `ANTHOS_HOME` env var if you've relocated it.

---

## Community

- 💬 [Discord](https://discord.gg/TushaeBXN)
- 📖 [Documentation](https://anthos-agent.anthosai.com/docs/)
- 🐛 [Issues](https://github.com/TushaeBXN/anthos-agent/issues)

---

## License

MIT — see [LICENSE](../../LICENSE).

Built by [Anthos Intelligence](https://anthosai.com).
