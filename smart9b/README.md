# smart9b

Makes a small local model (like a 9B Qwen on a 16 GB Mac mini) smarter in two ways:

1. **It teaches itself, the way a person does.** When it gets a task it doesn't know
   how to do, it searches the web, reads a few guides, writes its own how-to notes,
   practices, checks whether it worked, writes down what it learned, and tries again.
   Notes that work get marked **proven** and are reused next time.
2. **It trains on its own successes.** Every task it gets right (checked by running the
   code, or approved by you) is saved as training data. Once you have a few hundred,
   `train_lora.sh` fine-tunes a small add-on (a LoRA) so the skill is built into the
   model instead of looked up.

A stronger **teacher** model (for example Meta's Muse Glimmer, Apache 2.0) is optional.
When the 9B gets stuck three times, it writes up the problem; the teacher answers it later
and the answer becomes a new note.

It uses only the Python standard library. Nothing is sent, posted or bought; it only
reads the web and works inside its own `sandbox/` folder.

## How the loop works

```
task ──► do I have notes for this?  ── yes ─────────────────────────┐
              │ no                                                  │
              ▼                                                     ▼
      search the web ─► read 3 sources ─► write notes ─► practice the task
                                                             │
                              check: does the code run? do all checklist items pass?
                                    │ pass                        │ fail
                                    ▼                             ▼
                     mark notes "proven", save as     write a lesson into the notes,
                     training data                    try again (up to 3 times)
                                                                  │ still failing
                                                                  ▼
                                                   write up the problem for the teacher
```

## Setup on the Mac

The example config is set up for an MLX model such as
`lukey03/Qwen3.5-9B-abliterated-MLX-8bit` (about 9-10 GB of memory at 8-bit).
MLX models don't run in Ollama; use LM Studio or `mlx_lm.server`, which both speak the
OpenAI-style API smart9b uses.

```bash
# 1a. The model, the easy way: LM Studio (https://lmstudio.ai)
#     Search for the model, download it, load it, then Developer tab -> Start Server.
#     It serves at http://localhost:1234/v1, which is what smart9b.example.json expects.

# 1b. Or from the terminal with mlx-lm (then set base_url to http://localhost:8081/v1):
pip install "mlx-lm>=0.20,<1"
python -m mlx_lm server --model lukey03/Qwen3.5-9B-abliterated-MLX-8bit --port 8081
#     If it errors about vision/processor files, the model needs mlx-vlm; use LM Studio instead.

# 2. smart9b
cd smart9b
python3.11 -m venv .venv && source .venv/bin/activate   # brew install python@3.11 if needed
pip install -e .

# 3. A data folder for its notes, journal and training data
mkdir -p ~/smart9b-data && cd ~/smart9b-data
smart9b init              # creates smart9b.json and the starter skills
```

Open `~/smart9b-data/smart9b.json`:
- `worker.model`: the model name your server shows (LM Studio lists it under the loaded model).
- Delete the `teacher` block until you have a teacher to point it at.

Using Ollama instead? Set `"backend": "ollama"`, `"base_url": "http://localhost:11434"` and
the name `ollama list` shows.

**Memory on a 16 GB Mac:** the 8-bit 9B leaves about 5-6 GB for macOS and everything else,
which is fine for running it. It is very likely too tight for fine-tuning, so train on a 4-bit copy
(see below). A 4-bit version also runs faster and leaves more headroom, with a small quality loss.

**About "abliterated" models:** abliteration removes the model's ability to refuse. That can
cost a little quality, and it matters for an agent that reads random web pages: text on a page
can tell the model to do something, and it won't push back. smart9b only shows you code
and asks before running it; leave `auto_run_code` off with this model.

## Using it

```bash
smart9b do "clean up sales.csv: fix the headers and remove duplicate rows" --file sales.csv
smart9b do "write 3 product descriptions for a leather wallet" --review
smart9b learn "how to write a cold email to a small business"
smart9b skills                     # what it knows, and how often each note worked
smart9b skills email               # search its notes
```

- **`--review`**: you approve or reject each result and say what's wrong. This is the best
  training data, and the only real check for writing tasks, where no program can test it.
- Before running any code the model wrote, it shows you the code and asks. Set
  `"auto_run_code": true` only once you trust it.

## Bring in existing skills

Any `SKILL.md` files (for example this repo's `skills/` folder, or public skill libraries)
can be rewritten into short notes a 9B can follow:

```bash
smart9b import ../skills/data-science ../skills/productivity
```

This is much better with a teacher configured; without one, the 9B slims them itself.

## Using a teacher (Muse Glimmer or any stronger model)

Glimmer is 30B and needs about 18 GB of memory, so it won't run well on a 16 GB Mac. Run it
for a few hours on a rented GPU (vLLM or Ollama) or use a hosted provider, then fill in the
`teacher` block in `smart9b.json` (any OpenAI-compatible server works; put the API key in an
environment variable, and write that variable's name in `api_key_env`).

```bash
smart9b teach --queue                               # answer everything the 9B got stuck on
smart9b teach "write product descriptions" "clean messy csv" "fix a python error"
```

## Fine-tuning on its own successes

```bash
smart9b dataset                    # -> training_data/train.jsonl, valid.jsonl
pip install -e ".[train]"
MODEL=<a 4-bit MLX copy of your Qwen3.5 9B> ./train_lora.sh
```

Train on a **4-bit** copy of your model: the 8-bit one plus training will very likely run out of memory on 16 GB.
If you can't find a 4-bit MLX copy of the same abliterated model, make one from the
original full-size (non-MLX) version of it:
`python -m mlx_lm convert --hf-path <full-size model> -q --q-bits 4 --mlx-path qwen9b-4bit`

Only work that was **verified by running code** or **approved by you** is used
(add `--include-self-graded` to also use work the model only checked itself; it's noisier).
Test the tuned model on tasks it hasn't seen before you switch over. The script prints how to
serve it so smart9b can use it as the worker.

## Honest limits

- Web notes are only as good as what it finds and understands. That's why notes start as
  `untested` and only become `proven` after the work actually passes.
- A 9B grades its own writing too kindly. For anything non-code, use `--review`.
- Fine-tuning helps most on narrow, repeated tasks. It won't turn a 9B into a 30B.

## Files it creates

| Path | What |
|---|---|
| `skills/*.md` | its notes, with status, win/loss counts, sources and lessons |
| `journal.jsonl` | every attempt: task, answer, check results |
| `teacher_queue/` | problems it got stuck on |
| `sandbox/` | where its code runs |
| `training_data/` | fine-tuning data built from successes |

## Tests

```bash
pip install -e ".[test]" && python -m pytest
```

The tests run the whole loop against a fake model server, so no real model is needed.
