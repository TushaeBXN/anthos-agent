#!/usr/bin/env bash
# Fine-tune a LoRA adapter for the 9B on its own successful work, on an Apple-silicon Mac.
# Needs: pip install "mlx-lm>=0.20,<1"   and training data from:  python -m smart9b dataset
#
# Settings are sized for a 16 GB M4: 4-bit base model, batch size 1, only the last
# 8 layers trained, gradient checkpointing on. Stop the model server / `ollama stop` first
# and close other apps while it runs.
set -euo pipefail

# A 4-bit MLX copy of your Qwen model (8-bit + training will very likely run out of memory on 16 GB).
MODEL="${MODEL:-lukey03/Qwen3.5-9B-abliterated-MLX-4bit}"
DATA="${DATA:-training_data}"
ITERS="${ITERS:-600}"

if [ "$(wc -l < "$DATA/train.jsonl")" -lt 50 ]; then
  echo "Only $(wc -l < "$DATA/train.jsonl") examples in $DATA/train.jsonl - collect more first." >&2
  exit 1
fi

python -m mlx_lm lora \
  --model "$MODEL" \
  --train \
  --data "$DATA" \
  --adapter-path adapters \
  --batch-size 1 \
  --num-layers 8 \
  --iters "$ITERS" \
  --learning-rate 1e-5 \
  --grad-checkpoint \
  --mask-prompt

echo
echo "Done. Compare before/after on held-out tasks:"
echo "  python -m mlx_lm generate --model $MODEL --adapter-path adapters --prompt 'your test task'"
echo "Serve the tuned model to smart9b (OpenAI-compatible, set worker.backend=openai, base_url=http://localhost:8081/v1):"
echo "  python -m mlx_lm server --model $MODEL --adapter-path adapters --port 8081"
