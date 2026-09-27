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

The example config uses `lukey03/qwen3.5-9b-abliterated-vision` in Ollama (~6.1 GB, can
see pictures).

```bash
# 1. The model
brew install ollama python@3.11      # or install the Ollama app
ollama serve &                       # skip if the Ollama app is running
ollama pull lukey03/qwen3.5-9b-abliterated-vision

# 2. smart9b
cd smart9b
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e .

# 3. A data folder for its notes, journal and training data
mkdir -p ~/smart9b-data && cd ~/smart9b-data
smart9b init              # creates smart9b.json and the starter skills
```

In `~/smart9b-data/smart9b.json`, delete the `teacher` block until you have one.

Other ways to run it:
- **Text-only MLX 8-bit** (a bit higher quality text, no pictures, ~9.5 GB):
  `python -m mlx_lm server --model lukey03/Qwen3.5-9B-abliterated-MLX-8bit --port 8081`, then set
  `"backend": "openai"`, `"base_url": "http://localhost:8081/v1"` and that model name.
- **LM Studio**: load a model, start the server, `"backend": "openai"`,
  `"base_url": "http://localhost:1234/v1"`.

**Thinking mode.** Qwen3.5 thinks before it answers, which is slower but smarter.
With `"no_think_suffix": true`, smart9b adds `/no_think` only to quick steps (picking
notes, planning searches, writing short lessons). Solving tasks, writing notes, and
grading still think.

**Memory on a 16 GB Mac.** The vision model (~6.1 GB) leaves plenty of room. The 8-bit MLX
one leaves about 5-6 GB, which is fine but tight; close heavy apps while it works.

**About this model being "abliterated".** Its refusals were removed. That matters for an
agent that reads random web pages: text on a page can tell the model to do something, and
it won't push back. smart9b shows you any code and asks before running it; keep
`auto_run_code` off with this model and read the code before typing `y`.

## Using it

```bash
smart9b do "clean up sales.csv: fix the headers and remove duplicate rows" --file sales.csv
smart9b do "write 3 product descriptions for a leather wallet" --review
smart9b learn "how to write a cold email to a small business"
smart9b skills                     # what it knows, and how often each note worked
smart9b skills email               # search its notes
```

Pictures: add `--image` (as many as you like) and the model looks at them while it works
and while it checks its work:

```bash
smart9b do "write a product listing for the item in these photos" --image front.jpg --image back.jpg --review
smart9b do "type up this receipt as a CSV with date, item, price" --image receipt.jpg
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
ollama stop lukey03/qwen3.5-9b-abliterated-vision   # free the memory first
./train_lora.sh                    # trains on lukey03/Qwen3.5-9B-abliterated-MLX-4bit
```

Fine-tuning runs on the **text-only 4-bit MLX** copy of the same model (~4.7 GB), because
that's what MLX can train on a 16 GB Mac. The result is a tuned **text** model:
- Use the tuned model for the text jobs it was trained on (the script prints how to serve it).
- Keep using the vision model for anything with pictures. Tasks that had pictures are left out
  of the training data automatically, since the text model can't see them.

Only work that was **verified by running code** or **approved by you** is used
(add `--include-self-graded` to also use work the model only checked itself; it's noisier).
Test the tuned model on tasks it hasn't seen before you switch over.

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
