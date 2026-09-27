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

```bash
# 1. The model (use whatever name `ollama list` shows for your Qwen 9B)
brew install ollama python@3.11
ollama serve &            # or open the Ollama app
ollama pull qwen3.5:9b    # skip if you already have it

# 2. smart9b
cd smart9b
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e .

# 3. A data folder for its notes, journal and training data
mkdir -p ~/smart9b-data && cd ~/smart9b-data
smart9b init              # creates smart9b.json and the starter skills
```

Open `~/smart9b-data/smart9b.json` and set `worker.model` to your model's name. Delete the
`teacher` block until you have a teacher to point it at.

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
MODEL=mlx-community/<your-qwen-9b>-4bit ./train_lora.sh
```

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
