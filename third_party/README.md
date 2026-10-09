# Third-party source

Code in this directory is vendored from other projects. It is **not** covered
by Anthos Agent's MIT [LICENSE](../LICENSE); each subdirectory keeps its own
licence, and those terms apply to it.

| Directory | Upstream | Pinned commit | Licence |
|---|---|---|---|
| [`voicestudio/`](voicestudio/) | <https://github.com/debpalash/VoiceStudio> (0.5.7) | `06c6e077f0fc35149efefc3561e9be5ae835d916` | AGPL-3.0-only (see below) |

## VoiceStudio

Open-source voice cloning, text-to-speech and transcription. Anthos uses it as
a **separate program**: the user runs VoiceStudio's backend and Anthos talks to
its MCP server over HTTP (catalog entry
[`optional-mcps/voicestudio`](../optional-mcps/voicestudio/manifest.yaml)).
Anthos code does not import VoiceStudio code.

### Licences inside the tree

- **VoiceStudio application** (`backend/`, `electron/`, `native/`, `scripts/`,
  `deploy/`, …): GNU AGPL-3.0-only, © 2024-present Palash Debnath and
  VoiceStudio contributors. Full text: [`voicestudio/LICENSE`](voicestudio/LICENSE);
  plain-language notice: [`voicestudio/LICENSE-NOTICE.md`](voicestudio/LICENSE-NOTICE.md).
- **`omnivoice/`** (the TTS model package by Han Zhu): Apache-2.0.
- **Electron parts adapted from T3 Code**: MIT, see
  [`voicestudio/electron/T3CODE-LICENSE.txt`](voicestudio/electron/T3CODE-LICENSE.txt).
- **Model weights** are downloaded at runtime and are *not* in this repo. They
  carry their own terms. The default `k2-fsa/OmniVoice` weights are
  **CC-BY-NC (non-commercial)** and its audio tokenizer carries Boson Higgs Audio 2
  and Meta Llama community terms. Check
  [`model_licenses.json`](voicestudio/backend/config/model_licenses.json)
  before commercial use.
- Third-party dependencies (`uv.lock`, `bun.lock`, `native/desktop-bridge/Cargo.lock`)
  keep their own licences.

### Keeping Anthos MIT

- The vendored tree is excluded from the `anthos-agent` wheel and sdist
  (`packages.find` never includes it; `MANIFEST.in` prunes `third_party`) and
  from the Docker build context (`.dockerignore`). Anthos's distributions stay
  pure MIT. `tests/test_packaging_metadata.py` enforces this.
- Do **not** import VoiceStudio modules into Anthos code or copy code from it
  into MIT-licensed files. Linking it in would make that Anthos code a combined
  work under the AGPL. Talk to it over its MCP or HTTP API instead.

### Obligations when you use this copy

AGPL-3.0 lets you use, modify and redistribute VoiceStudio, commercially too.
In return:

1. **Keep the notices.** Don't remove or alter `LICENSE`, `LICENSE-NOTICE.md`,
   copyright headers, or `electron/T3CODE-LICENSE.txt`.
2. **Mark your changes** (AGPL §5a). If you edit anything under
   `voicestudio/`, add a line to the modification log below: date, files, and
   what changed. Then the tree carries a prominent notice of the change.
3. **Share source when you distribute** (AGPL §4–6). If you give anyone a
   copy, in source or built form, it must come with (or offer) the complete
   corresponding source under AGPL-3.0, including your changes. Distributing
   this repository satisfies that for the vendored tree.
4. **Share source over the network** (AGPL §13). If you run a *modified*
   VoiceStudio and let other people use it over a network (a hosted service,
   a shared server, a bot others talk to), you must offer those users the
   source of your modified version, for example a link in the UI to this repo
   at the commit you run. Running it unmodified, or only for yourself, triggers
   nothing extra.
5. **No added restrictions.** You can't distribute it under terms stricter than
   the AGPL (no closed-source fork). For a proprietary embed, the upstream
   maintainer sells a commercial licence: <https://voicestudio.sh/pro>.
6. **Respect model and voice terms.** The AGPL covers code, not model weights
   or voices. Follow each model's licence, and only clone voices you have
   permission to use.

### Modification log

Unmodified upstream snapshot, except:

- 2026-10-09: the `omnivoice-gallery` git submodule (sample gallery, separate
  repo: <https://github.com/debpalash/omnivoice-gallery>) was not vendored. Its
  gitlink was dropped because this repo has no submodule mapping for it.
  The upstream `.gitmodules` file is left as-is.

### Updating

The tree was added with `git subtree --squash`, so it updates in place:

```bash
git subtree pull --squash --prefix=third_party/voicestudio \
  https://github.com/debpalash/VoiceStudio <tag-or-commit>
git rm --cached third_party/voicestudio/omnivoice-gallery   # if it reappears
```

Then update the pinned commit in the table above.
