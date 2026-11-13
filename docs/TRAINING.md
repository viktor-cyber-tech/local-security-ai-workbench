# Training AICodex for CTF Challenges

"Training" can mean three very different things. Start at Level 1 and only move down when the level above has stopped improving results.

| Level | What changes | Cost | Hardware | Best for |
| --- | --- | --- | --- | --- |
| 1. Prompt tuning | `SYSTEM` prompt + example conversations in the `Modelfile` | Minutes | This laptop | Output format, shell choice, workflow habits |
| 2. Knowledge base (RAG) | Your notes and writeups are searched and pasted into context | An afternoon | This laptop | Remembering *your* tools, cheat sheets, past solves |
| 3. Fine-tuning (LoRA) | The model's weights | Days of data work + GPU time | NVIDIA GPU or cloud GPU | Consistent style/skills the prompt can't teach |

For most CTF work, **Levels 1 and 2 give the biggest gains**. Fine-tuning rarely teaches new facts reliably. It is better at teaching a consistent *behavior*.

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
ollama create aicodex -f .\Modelfile
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
4. **Workspace → Models → +**. Create a model based on `aicodex` and attach the `ctf-notes` knowledge.
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
- **Fine-tune a smaller model** (Qwen3 4B–14B class) on free Colab, and use it as a fast specialist next to AICodex

### 1. Build a dataset (most of the work)

Use chat-format JSONL, one conversation per line:

```json
{"messages": [
  {"role": "system", "content": "You are AICodex..."},
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

### 2. Train with Unsloth

Follow Unsloth's official Qwen3 / Qwen3-Coder fine-tuning notebook (docs.unsloth.ai). It uses LoRA, keeps the MoE router frozen by default, and can export straight to GGUF. Typical starting settings: LoRA rank 16, 1–3 epochs, learning rate around 2e-4. Watch the validation loss and stop if it starts rising.

### 3. Export and run in Ollama

Export the merged model as GGUF (Q4_K_M is a good size/quality balance), copy it into this repo folder, and create `Modelfile.finetuned`:

```text
FROM ./aicodex-ft-Q4_K_M.gguf
# Paste the TEMPLATE block from: ollama show qwen3-coder:30b --modelfile
TEMPLATE """..."""
SYSTEM """(same system prompt as Modelfile)"""
PARAMETER temperature 0.4
PARAMETER num_ctx 16384
```

```powershell
ollama create aicodex-ft -f .\Modelfile.finetuned
ollama run aicodex-ft
```

`*.gguf` files are large. Don't commit them to Git (they're already listed in `.gitignore`).

### 4. Prove it's better

Run the held-out test set and `VALIDATION.md` against **both** `aicodex` and `aicodex-ft`. Keep the fine-tune only if it wins. Fine-tunes often get better at the trained style and worse at everything else.
