# Training Workbench for CTF Challenges

"Training" can mean three very different things. Start at Level 1 and only move down when the level above has stopped improving results.

| Level | What changes | Cost | Hardware | Best for |
| --- | --- | --- | --- | --- |
| 1. Prompt tuning | `SYSTEM` prompt + example conversations in the `Modelfile` | Minutes | This laptop | Output format, shell choice, workflow habits |
| 2. Knowledge base (RAG) | Your notes and writeups are searched and pasted into context | An afternoon | This laptop | Remembering *your* tools, cheat sheets, past solves |
| 3. Fine-tuning (LoRA) | The model's weights | Days of data work + GPU time | NVIDIA GPU or cloud GPU | Consistent style/skills the prompt can't teach |

For most CTF work, **Levels 1 and 2 give the biggest gains**. Fine-tuning rarely teaches new facts reliably. It is better at teaching a consistent *behavior*.

---

## Step-by-step: from install to a trained model

Run everything in PowerShell from the repo folder (`cd ~\local-security-ai-workbench`). The scripts write to `data/` and `outputs/`, which are git-ignored.

> ### Intel Core Ultra (iGPU) — measured working recipe
>
> Training on an Intel integrated GPU under Windows works, but has three gotchas we hit and solved on a Core Ultra 7 255U (measured Nov 2026):
>
> 1. **Run training in Command Prompt (`cmd`), not PowerShell** — the env setup uses `call` / `set VAR=val` syntax. Activate the venv with `.venv-unsloth\Scripts\activate.bat` and confirm the prompt shows `(.venv-unsloth)`.
> 2. **Load only the MSVC compiler, not full oneAPI.** Triton needs a C compiler, so `call "...\VC\Auxiliary\Build\vcvars64.bat"` + `set CC=cl` + `set ZE_PATH=C:\Tools\level-zero-win-sdk-1.20.2`. Do **not** run oneAPI's `setvars.bat` — it overrides PyTorch's bundled Intel runtime and breaks XPU.
> 3. **Use `--dtype float16`.** bf16 fails with `InvalidFunctionCall: llvm.fma.bf16` in Intel's Triton SPIR-V translator.
>
> Always `ollama stop workbench` first to free shared GPU memory, and keep **4-bit QLoRA** (the default) — a full fp16 load won't fit alongside Ollama.
>
> **Fast settings:** `--dtype float16 --max-seq-len 1024 --no-grad-checkpoint` measured ~35 s/step vs ~86 s/step at defaults (~2.5x). Note `--max-seq-len 1024` truncates long examples — fine for short CTF exchanges, but raise it to 2048 for Fenrir-style long answers. This speed is only practical for small/medium runs (a few thousand examples overnight); for the full dataset or the 30B, run the same script on a cloud NVIDIA GPU.

### Step 0: Check that Unsloth can see a GPU

```powershell
git pull
py -m pip install --upgrade ollama datasets trl
py -c "import torch; print(torch.__version__, 'cuda', torch.cuda.is_available(), 'xpu', torch.xpu.is_available())"
```

- `xpu True`: Unsloth can train on your Intel Core Ultra graphics with 4-bit QLoRA. Time a few steps before committing to a long run (Step 4).
- Both `False`: you have the regular (NVIDIA-only) Unsloth build. Follow Unsloth's **Intel GPU install guide** (unsloth.ai/docs → Install → Intel). It needs a fresh Python environment, Intel oneAPI Base Toolkit and `pip install .[intel-gpu-torch290]`. Or skip local training and use a cloud NVIDIA GPU for Step 4.

### Step 1: Record a baseline

```powershell
ollama create workbench -f .\Modelfile
ollama run workbench
```

Run the prompts in [`VALIDATION.md`](VALIDATION.md) and note how it does. Every later step is measured against this.

### Step 2: Write your own examples (the most valuable data)

Copy the format of [`examples/own-examples.sample.jsonl`](../examples/own-examples.sample.jsonl) into `data\my-writeups.jsonl`, one conversation per line. Good sources are your NCL, CyberSEED and TryHackMe solves **after** each event ends, using only commands you ran and confirmed. Aim for 50 to start and add more after every event.

There's also a ready-made, verified set of ~16 command-first examples in [`examples/ctf-seed.jsonl`](../examples/ctf-seed.jsonl) (encoding, hashing, nmap, tshark, log analysis, forensics) — use it directly as `--own` seed data to anchor the command-first style while you build up your own writeups.

### Step 3: Build the training set

```powershell
py scripts\prepare_dataset.py data\raw\cyber-security --sample 3000 --own data\my-writeups.jsonl --own-repeat 3
```

(See Level 3 → *Adding a public dataset* for downloading `data\raw\cyber-security`. To train on only your own examples, pass `examples\own-examples.sample.jsonl` or your file as the input instead.)

Open `data\processed\train.jsonl` and read about 20 random lines. Delete bad data now, because it's much harder to fix after training.

### Step 4: Train

**On this laptop** (Intel XPU, 4-bit QLoRA, which is the script's default). Time a few steps first:

```powershell
# Small model: quick check that the whole pipeline works
py scripts\train_lora.py --model unsloth/Qwen3-4B-Instruct-2507 --max-steps 10
# The real Workbench base (30B MoE): see if it fits and how long a step takes
py scripts\train_lora.py --model unsloth/Qwen3-Coder-30B-A3B-Instruct --max-steps 5 --no-gguf
```

Watch the seconds per step in the progress bar. A full run is about `(train rows ÷ 8) × epochs` steps at the default batch settings, so multiply it out before starting a long run. Close other apps and keep the laptop plugged in.

Notes for the 30B on this laptop:
- 4-bit QLoRA needs about 17.5 GB of GPU memory for this model. Integrated graphics can borrow roughly half your RAM, so with 64 GB it fits on paper.
- For MoE models, Unsloth downloads the **full 16-bit model (~61 GB)** and converts it to 4-bit while loading. You need that much free disk space, and the RAM spike while loading can run out of memory. If it does, train on a cloud GPU or a smaller dense model.
- If the timing works out to days, use `--max-steps` with a smaller `--sample` in Step 3, or train on a rented GPU.

**On a rented NVIDIA GPU (24 GB+), for the real Workbench base:** copy the repo and `data\processed\` to the machine, install Unsloth, then:

```powershell
python scripts/train_lora.py --model unsloth/Qwen3-Coder-30B-A3B-Instruct --epochs 1
```

Copy `outputs/workbench-lora/` back to your laptop when it finishes.

Watch the printed loss. It should drop and then level off. If the eval loss starts **rising** while the training loss keeps falling, the model is memorizing. Use fewer steps or epochs.

### Step 5: Import into Ollama

```powershell
Get-ChildItem outputs\workbench-lora\gguf -Recurse -Filter *.gguf
# Copy the main Modelfile, swapping the FROM line for your GGUF path:
(Get-Content Modelfile) -replace '^FROM .*', 'FROM ./outputs/workbench-lora/gguf/YOUR-FILE.gguf' | Set-Content Modelfile.finetuned
ollama create workbench-ft -f .\Modelfile.finetuned
ollama run workbench-ft
```

Ollama reads the chat template from the GGUF. If replies look garbled or never stop, paste the `TEMPLATE` block from `ollama show qwen3-coder:30b --modelfile` (or the matching small base model) into `Modelfile.finetuned` and run `ollama create` again.

### Step 6: Compare against the baseline

```powershell
py scripts\eval_models.py --models workbench workbench-ft --test examples\ctf-eval.jsonl
```

Open `data\eval-report.md` and grade each answer. Also rerun `VALIDATION.md`. **Keep `workbench-ft` only if it wins.** Otherwise keep improving your data (Step 2), which helps more than changing settings.

### Before each CTF event

1. Check the event's rules on AI tools and internet use.
2. `ollama run workbench` (or `workbench-ft`) once beforehand, so the model is already loaded and responding.
3. Turn on web access only if the rules allow it ([`INTERNET_ACCESS.md`](INTERNET_ACCESS.md)).
4. After the event, write up your solves as new examples (Step 2), then rerun Steps 3–6.

---

## Level 1: Prompt tuning with the Modelfile

The `Modelfile` already sets the persona and rules. Two more Modelfile features help:

### Few-shot examples with `MESSAGE`

`MESSAGE` lines are baked into every chat as if they were earlier turns. Use 2–5 short, high-quality examples of exactly the behavior you want:

```text
MESSAGE user """Authorized CTF, Kali. Artifact is hex, then base64. Value: 5a6d78685a3374305a584e3066513d3d. One Bash command."""
MESSAGE assistant """```bash
echo '5a6d78685a3374305a584e3066513d3d' | xxd -r -p | base64 -d
```
Hex → bytes with `xxd -r -p`, then Base64-decode. Run it and paste the output if another layer remains."""
```

Add these lines after the `SYSTEM` block, then rebuild:

```powershell
ollama create workbench -f .\Modelfile
```

Tips:
- Keep examples short. Every `MESSAGE` uses context on every chat.
- Show the *workflow* (give a command → user runs it → user pastes output → next step), not just answers.
- Cover each category you care about: encoding, log analysis (grep/awk/jq), password cracking command syntax, network/pcap (tshark), web (curl), forensics (file, binwalk, exiftool, strings).

### See what the base model already ships with

To view the official template and default parameters the base model pulls from the Ollama library:

```powershell
ollama show qwen3-coder:30b --modelfile
```

You need this `TEMPLATE` if you ever import a custom GGUF (Level 3).

### Measure, don't guess

Use [`VALIDATION.md`](VALIDATION.md) as a regression test. After every Modelfile change, rerun the same prompts and check the outputs. Add one test for each challenge type you care about. Keep a few tests the model has **never** seen as `MESSAGE` examples, otherwise you're only testing memorization.

---

## Level 2: Give it your knowledge (RAG)

A model can't remember last month's NCL writeup. It can read the writeup if a retrieval system adds it to the prompt.

The easiest way is **Open WebUI Knowledge** (see [`INTERNET_ACCESS.md`](INTERNET_ACCESS.md) for installing Open WebUI):

1. Pull an embedding model: `ollama pull nomic-embed-text`
2. In Open WebUI: **Admin Panel → Settings → Documents**. Set the embedding engine to Ollama and the model to `nomic-embed-text`.
3. **Workspace → Knowledge → +**. Create a collection such as `ctf-notes` and upload Markdown/PDF/TXT files.
4. **Workspace → Models → +**. Create a model based on `workbench` and attach the `ctf-notes` knowledge.
5. In chat, select that model. You can also type `#` to attach a collection to one message.

Good things to load:
- Your own writeups (Markdown is best: one challenge per file, with category, tools, commands that worked, and dead ends)
- Tool cheat sheets you've verified yourself (hashcat modes, tshark filters, Zeek field names, Sigma/KQL snippets)
- Man pages or `--help` output for tools you use often (`hashcat --help > hashcat-help.txt`)

Avoid:
- Answers or flags from **active** competitions. Most CTFs (including NCL) forbid sharing solutions while the game is running.
- Anything with real credentials, client data or personal information

---

## Level 3: Fine-tuning with LoRA

### Reality check for this hardware

Fine-tuning needs an **NVIDIA GPU**. Intel integrated graphics and the NPU can't train these models in a practical way. Unsloth reports that its MoE fine-tuning fits Qwen3-30B-A3B in about **17.5 GB of VRAM**. That is more than a free Colab T4 (16 GB), so options are:

- **Fine-tune `qwen3-coder:30b`** on a rented 24 GB+ GPU (an L4/A10/RTX 4090 on Colab Pro, RunPod, Vast.ai, etc.)
- **Fine-tune a smaller model** (Qwen3 4B–14B class) on free Colab, and use it as a fast specialist next to Workbench

### 1. Build a dataset (most of the work)

Use chat-format JSONL, one conversation per line:

```json
{"messages": [
  {"role": "system", "content": "You are Workbench..."},
  {"role": "user", "content": "Authorized CTF, Kali. I have capture.pcap and need HTTP POST bodies. One command."},
  {"role": "assistant", "content": "```bash\ntshark -r capture.pcap -Y 'http.request.method == \"POST\"' -T fields -e http.file_data\n```\nFilters POST requests and prints their bodies. Paste the output for the next step."}
]}
```

Guidelines:
- **Quality beats quantity.** 300–1,000 verified examples beat 20,000 scraped ones.
- Every command in the dataset should be one **you actually ran** and confirmed works.
- Include multi-turn examples where the user pastes output and the assistant takes the next step. That teaches the workflow.
- Include examples where the right answer is "I'm not sure of that flag. Check `tool --help`." That teaches honesty instead of confident guessing.
- Hold back 10% as a test set and never train on it.
- Sources: your own NCL/CyberSEED/TryHackMe writeups (after the competition ends), plus retired public challenges where the license allows reuse.

### 1b. Adding a public dataset (`Vyber07/cyber-security`)

[`Vyber07/cyber-security`](https://huggingface.co/datasets/Vyber07/cyber-security) is a large Apache-2.0 cybersecurity dataset in mixed JSON layouts (ShareGPT conversations and Instruction/Input/Output records with domain metadata). Use it to add breadth, and keep your own verified examples as the core.

**Before you use it:**
- **Gated access.** Open the dataset page while signed in to Hugging Face and accept the access conditions first.
- **It is huge.** The card lists hundreds of files and tens of GB, and the size figures on the card disagree with each other. Don't train on all of it. A few thousand well-chosen examples is plenty for a LoRA, and more mostly costs GPU time.
- **Quality is unverified.** The card doesn't explain how the records were generated or how they're licensed from the sources it lists. Spot-check a sample before training. Wrong commands in the data teach wrong commands.
- **It's described as "no restrictions" offensive and defensive content.** Training on it can weaken the authorization rules in the Workbench system prompt. Check the held-out test set for that as well as for accuracy.

**Download only what you need** (PowerShell, from the repo folder; `data/` is git-ignored):

```powershell
py -m pip install --upgrade huggingface_hub ijson
hf auth login                                  # older versions: huggingface-cli login
# Look at the file list on the dataset's "Files" tab first, then download a subset:
hf download Vyber07/cyber-security --repo-type dataset --local-dir data\raw\cyber-security --include "*.jsonl"
```

Older `huggingface_hub` versions use `huggingface-cli download` with the same arguments. Adjust `--include` to match the folders or files you picked.

**Convert it to Workbench training data:**

```powershell
py scripts\prepare_dataset.py data\raw\cyber-security --sample 3000 `
   --own data\my-writeups.jsonl --own-repeat 3
```

What the script does:
- Normalizes ShareGPT, chat, Instruction/Input/Output and question/answer records into `{"messages": [...]}`
- Replaces each record's system prompt with the Workbench one from the `Modelfile`
- Drops broken JSON, unrecognized layouts, non-alternating conversations, near-empty and very long records, and duplicates
- Randomly samples `--sample` examples without loading everything into memory (install `ijson` for very large JSON-array files)
- Mixes in your own verified examples (`--own`), repeated `--own-repeat` times so they outweigh the public data
- Writes `data/processed/train.jsonl` and `data/processed/test.jsonl` (10% held out), and prints counts of what it kept and skipped

Use `--domain web --domain forensics` (matched against record metadata) to keep only the categories you care about. Records without metadata are dropped when you use this filter. If most records come back "unrecognized", open one file, check its keys, and add the layout to `normalize()`.

**Spot-check before training:**

```powershell
Get-Content data\processed\train.jsonl -TotalCount 5
```

Upload `train.jsonl` and `test.jsonl` to the notebook and load them with `load_dataset("json", data_files={"train": "train.jsonl", "test": "test.jsonl"})`.

### 2. Train with Unsloth

Follow Unsloth's official Qwen3 / Qwen3-Coder fine-tuning notebook (docs.unsloth.ai). It uses LoRA, keeps the MoE router frozen by default, and can export straight to GGUF. Typical starting settings: LoRA rank 16, 1–3 epochs, learning rate around 2e-4. Watch the validation loss and stop if it starts rising.

### 3. Export and run in Ollama

Export the merged model as GGUF (Q4_K_M is a good size/quality balance), copy it into this repo folder, and create `Modelfile.finetuned`:

```text
FROM ./workbench-ft-Q4_K_M.gguf
# Paste the TEMPLATE block from: ollama show qwen3-coder:30b --modelfile
TEMPLATE """..."""
SYSTEM """(same system prompt as Modelfile)"""
PARAMETER temperature 0.4
PARAMETER num_ctx 16384
```

```powershell
ollama create workbench-ft -f .\Modelfile.finetuned
ollama run workbench-ft
```

`*.gguf` files are large. Don't commit them to Git (they're already listed in `.gitignore`).

### 4. Prove it's better

Run the held-out test set and `VALIDATION.md` against **both** `workbench` and `workbench-ft`. Keep the fine-tune only if it wins. Fine-tunes often get better at the trained style and worse at everything else.
