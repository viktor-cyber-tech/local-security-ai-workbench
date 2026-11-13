# Datasets for fine-tuning Workbench

Workbench is a **defensive / authorized-use** assistant, and this is a public repo, so the
datasets below are chosen to be permissively licensed and alignment-safe. The goal is to add
breadth **without** training away the authorization rules in the `Modelfile`.

`scripts/prepare_dataset.py` normalizes ShareGPT (`conversations`), chat (`messages`),
Instruction/Input/Output, and question/answer formats, so all of these drop into the same
pipeline. Open one file first and check its keys; if a layout isn't recognized, add it to
`normalize()`.

## Recommended (permissive, defensive, good fit)

| Dataset | Size | License | Format | Role |
| --- | --- | --- | --- | --- |
| `AlicanKiraz0/Cybersecurity-Dataset-Fenrir-v2.0` | ~83,920 triples | Apache-2.0 | system/user/assistant | Broad defensive security knowledge — best all-rounder |
| `carosh/cli-1m` (load the `security` domain subset) | 975k NL→shell pairs | Apache-2.0 | NL→command | Command-generation core (bash, PowerShell, zsh, …) |
| `Trendyol/...-cybersecurity-instruction-tuning` | ~17k | Apache-2.0 | instruction | Trusted defensive instruction building block |
| `True2456/cybersecurity-theory-sft-gemma12b` | ~21,265 rows | check page | instruction | CTF reasoning, CISA KEV, CTFtime writeups |
| `Frost2o24/bash-instruct-II-55k` | ~55k | check page | chat `messages` | Pure CLI / coreutils fluency |
| `TahaGorji/BlackHat-KaliLinux-CyberSecurity-dataset-Instruct` | — | check page | instruction/IO | Kali-tool focused; matches the pipeline exactly |

Always confirm the license on each dataset's Hugging Face page before using it in a public
project; the "check page" ones didn't state it clearly in search.

## Your own writeups are the most valuable part

Public datasets add breadth; your own verified NCL / CyberSEED / TryHackMe solves (added
*after* each event ends) are what make the model *yours*. Keep them in `data\my-writeups.jsonl`
using the format in `examples/own-examples.sample.jsonl`, and up-weight them with `--own-repeat`.

## Starter mix

```powershell
py -m pip install --upgrade huggingface_hub
# Ungated, Apache-2.0 — no login needed:
hf download AlicanKiraz0/Cybersecurity-Dataset-Fenrir-v2.0 --repo-type dataset --local-dir data\raw\fenrir
hf download carosh/cli-1m --repo-type dataset --local-dir data\raw\cli-1m --include "*security*"

py scripts\prepare_dataset.py data\raw\fenrir data\raw\cli-1m --own data\my-writeups.jsonl --own-repeat 3 --sample 5000
```

Then spot-check `data\processed\train.jsonl` before training.

## Skip these for a portfolio model

These are the opposite of what Workbench is for — they strip safety or are built for
refusal-removal research. Training on them undoes the Modelfile's authorization rules and
looks bad on a public repo:

- `Panagiotis12/hackingai-training` — "think like an APT group… never refuse security-related requests"
- `lukehinds/linux_shell_attacks` and similar — literal reverse-shell / backdoor answers, often for abliteration
- `CyberLLMInstruct` — the authors' own paper shows it severely degrades safety resilience
- `Vyber07/cyber-security` — gated, "no restrictions / full offensive," unverified quality (sample carefully if at all)
