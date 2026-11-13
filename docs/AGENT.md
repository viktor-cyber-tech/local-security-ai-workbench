# Workbench Agent

`scripts/workbench_agent.py` turns the local `workbench` model into a small agent for
CTF and lab work. It gives the model tools to work a challenge without you copy-pasting
everything into a chat.

## What it can do

| Tool | Purpose |
| --- | --- |
| `list_dir` / `read_file` | See and read the files in one folder you choose |
| `write_file` | Write a Python script (scanning, recon, enumeration) into that folder |
| `http_request` | Fetch a URL **from your machine** — reaches VPN, localhost, and odd ports, so it can inspect a target web app |
| `web_search` | Look up docs/CVEs (optional; needs a free Ollama API key) |

## The one rule: it writes, you run

The agent **never executes anything**. It reads, fetches, and writes scripts; you review
each script and run it yourself. That keeps a human between the model and any target —
which is what you want before a scan or an exploit touches a box, and it means a wrong
turn by the model costs you nothing but a file you can delete.

Only point it at targets you're authorized to test: your own lab, a CTF, or a signed
engagement.

## Use it

From the repo root, in your virtual environment:

```powershell
# Point it at a challenge folder
python scripts\workbench_agent.py --workdir path\to\challenge

# Or give it a one-shot task
python scripts\workbench_agent.py --workdir . "read notes.txt and write an nmap recon script for 10.10.10.5"
```

It prints each tool call as it goes (`[read_file] notes.txt`, `[http_request] http://...`),
so you can watch what it's doing. File access is locked to `--workdir`; it can't read or
write anywhere else.

### Web challenges

`http_request` runs locally, so it works against a VPN target (HTB/THM), `localhost`, or a
non-standard port. Ask it to fetch the target, look at the response headers and body, and
write a script from what it finds:

```
>>> fetch http://10.10.10.5:8080, note the server and any forms, then write a Python
    script that brute-forces the login with a wordlist I'll provide
```

### Enabling web search (optional)

For looking up CVEs or tool flags, set a free key from ollama.com once per terminal:

```powershell
$env:OLLAMA_API_KEY = "paste-key-here"
```

Without it, the other tools still work; only `web_search` is disabled.

## Options

- `--model workbench-ft` — use a fine-tuned build instead of the base model
- `--max-steps 24` — allow more tool rounds for a big task (default 16)
- `--modelfile Modelfile` — where the system prompt is read from

## Notes

- Tool calling needs a model that supports it. `workbench` (built on `qwen3-coder:30b`) does.
- Large files and web responses are truncated before they reach the model, to protect the
  context window. For a huge file, ask the agent to write a script that parses it instead.
- Treat anything the agent fetches from the web as untrusted — a page can contain text
  that tries to redirect the model. Read the scripts before running them.
