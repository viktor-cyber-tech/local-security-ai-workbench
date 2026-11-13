#!/usr/bin/env python3
"""Fine-tune a LoRA for Workbench with Unsloth, then export a GGUF for Ollama.

Input: data/processed/train.jsonl and test.jsonl from scripts/prepare_dataset.py
(chat records: {"messages": [{"role": ..., "content": ...}, ...]}).

Examples (run from the repo root):
  # Laptop (Intel Core Ultra iGPU via Unsloth's Intel/XPU install), QLoRA 4-bit: time a few steps first
  python scripts/train_lora.py --model unsloth/Qwen3-4B-Instruct-2507 --max-steps 10
  python scripts/train_lora.py --model unsloth/Qwen3-Coder-30B-A3B-Instruct --max-steps 5

  # Rented NVIDIA GPU (24 GB+): the real Workbench base
  python scripts/train_lora.py --model unsloth/Qwen3-Coder-30B-A3B-Instruct --epochs 1

Outputs (all under --out, default outputs/workbench-lora, git-ignored):
  lora/   the LoRA adapter (small; keep it, you can re-export later)
  gguf/   merged GGUF for `ollama create` (unless --no-gguf)
"""

import argparse
import sys
from pathlib import Path


def pick_device():
    import torch
    if torch.cuda.is_available():
        return "cuda", torch.cuda.get_device_name(0)
    if hasattr(torch, "xpu") and torch.xpu.is_available():
        return "xpu", torch.xpu.get_device_name(0)
    return None, None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default="unsloth/Qwen3-4B-Instruct-2507", help="Hugging Face model id to fine-tune")
    ap.add_argument("--train", default="data/processed/train.jsonl")
    ap.add_argument("--test", default="data/processed/test.jsonl")
    ap.add_argument("--out", default="outputs/workbench-lora")
    ap.add_argument("--max-seq-len", type=int, default=4096)
    ap.add_argument("--no-4bit", action="store_true", help="plain LoRA on 16-bit weights instead of 4-bit QLoRA (needs ~4x the memory)")
    ap.add_argument("--rank", type=int, default=16, help="LoRA rank")
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--epochs", type=float, default=1.0)
    ap.add_argument("--max-steps", type=int, default=-1, help="stop after N steps (overrides --epochs); good for a first test run")
    ap.add_argument("--batch", type=int, default=2)
    ap.add_argument("--grad-accum", type=int, default=4)
    ap.add_argument("--quant", default="q4_k_m", help="GGUF quantization for export")
    ap.add_argument("--no-gguf", action="store_true", help="skip GGUF export (save the LoRA only)")
    ap.add_argument("--dtype", default="bfloat16", choices=["bfloat16", "float16"],
                    help="training precision; try float16 on Intel XPU if bf16 triggers a Triton 'llvm.fma.bf16' error")
    ap.add_argument("--no-grad-checkpoint", action="store_true",
                    help="disable gradient checkpointing: faster steps but more memory. Fine for small models; may OOM the 30B")
    opts = ap.parse_args()

    if not Path(opts.train).is_file():
        sys.exit(f"{opts.train} not found. Run scripts/prepare_dataset.py first.")

    device, name = pick_device()
    if device is None:
        sys.exit("No CUDA or Intel XPU GPU visible to PyTorch. Check: python -c \"import torch; print(torch.xpu.is_available())\"\n"
                 "Intel laptops need Unsloth's Intel install (oneAPI + XPU PyTorch). Otherwise train on a cloud NVIDIA GPU.")
    print(f"Training on {device}: {name}")

    # Unsloth must be imported before transformers/trl to apply its patches.
    from unsloth import FastLanguageModel
    from unsloth.chat_templates import train_on_responses_only
    from datasets import load_dataset
    from trl import SFTConfig, SFTTrainer

    import torch
    use_4bit = not opts.no_4bit
    want_f16 = opts.dtype == "float16"
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=opts.model,
        max_seq_length=opts.max_seq_len,
        load_in_4bit=use_4bit,
        dtype=torch.float16 if want_f16 else None,
    )
    model = FastLanguageModel.get_peft_model(
        model,
        r=opts.rank,
        lora_alpha=opts.rank,
        lora_dropout=0,
        bias="none",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        use_gradient_checkpointing=False if opts.no_grad_checkpoint else "unsloth",
        random_state=3407,
    )

    def to_text(batch):
        return {"text": [tokenizer.apply_chat_template(m, tokenize=False) for m in batch["messages"]]}

    files = {"train": opts.train}
    if Path(opts.test).is_file() and Path(opts.test).stat().st_size > 0:
        files["test"] = opts.test
    ds = load_dataset("json", data_files=files)
    ds = ds.map(to_text, batched=True, remove_columns=ds["train"].column_names)

    out = Path(opts.out)
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=ds["train"],
        eval_dataset=ds.get("test"),
        args=SFTConfig(
            dataset_text_field="text",
            fp16=want_f16,
            bf16=not want_f16,
            per_device_train_batch_size=opts.batch,
            gradient_accumulation_steps=opts.grad_accum,
            warmup_steps=5,
            num_train_epochs=opts.epochs,
            max_steps=opts.max_steps,
            learning_rate=opts.lr,
            lr_scheduler_type="linear",
            optim="adamw_8bit" if use_4bit else "adamw_torch",
            weight_decay=0.01,
            logging_steps=5,
            eval_strategy="steps" if "test" in ds else "no",
            eval_steps=50,
            save_strategy="no",
            output_dir=str(out / "checkpoints"),
            seed=3407,
            report_to="none",
        ),
    )

    # Learn only from the assistant replies, not from the system prompt or user turns.
    # These markers match Qwen's ChatML template; change them for other model families.
    trainer = train_on_responses_only(
        trainer,
        instruction_part="<|im_start|>user\n",
        response_part="<|im_start|>assistant\n",
    )

    stats = trainer.train()
    print(f"Training finished: {stats.metrics}")
    if "test" in ds:
        print(f"Eval: {trainer.evaluate()}")

    lora_dir = out / "lora"
    model.save_pretrained(str(lora_dir))
    tokenizer.save_pretrained(str(lora_dir))
    print(f"Saved LoRA adapter to {lora_dir}")

    if not opts.no_gguf:
        gguf_dir = out / "gguf"
        print(f"Exporting merged GGUF ({opts.quant}) to {gguf_dir} — this builds llama.cpp on first use and can take a while...")
        model.save_pretrained_gguf(str(gguf_dir), tokenizer, quantization_method=opts.quant)
        print(f"Done. Next: see docs/TRAINING.md → 'Import into Ollama'. GGUF files are in {gguf_dir}")


if __name__ == "__main__":
    main()
