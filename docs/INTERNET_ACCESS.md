# Giving AICodex Internet Access

By default AICodex is fully offline: `ollama run aicodex` never touches the network after the model is downloaded. A local model can't browse by itself. Something has to run the search and feed the results back into the chat. There are two ways to do that, and you can use both.

| Option | Search provider | Privacy | Setup |
| --- | --- | --- | --- |
| A. `aicodex_web.py` (this repo) | Ollama's hosted web search API | Queries go to ollama.com | 5 minutes, needs a free Ollama account and API key |
| B. Open WebUI + SearXNG | Your own SearXNG metasearch container | Queries go to search engines through your container, with no account | Docker, about 30 minutes |

> **Rules first.** Some CTFs restrict outside help or AI tools. Check the competition rules before you turn on web access. Never paste live flags or other teams' data into a web-connected tool.

---

## Option A: Terminal agent with Ollama web search

Ollama provides `web_search` and `web_fetch` APIs that a tool-calling model can use. `qwen3-coder:30b` supports tool calling.

1. Create a free account at ollama.com and generate an API key.
2. Install the Python client:

   ```powershell
   py -m pip install --upgrade ollama
   ```

3. Set the key for this terminal session (avoid saving it in the repo; `.env` is git-ignored):

   ```powershell
   $env:OLLAMA_API_KEY = "paste-key-here"
   ```

   Kali/WSL: `export OLLAMA_API_KEY="paste-key-here"`

4. Ask a question:

   ```powershell
   py scripts\aicodex_web.py "What hashcat mode is used for NetNTLMv2, and what does a sample hash look like?"
   ```

   Or start an interactive session with `py scripts\aicodex_web.py`.

The script uses your local `aicodex` model and lets it call `web_search` and `web_fetch` as needed. It prints each search or fetch it performs and ends with source URLs. Useful flags: `--model aicodex-ft` (to use a fine-tuned build), `--max-steps 8` (to allow more tool calls).

The model still runs locally. Only the search queries and fetched URLs go through Ollama's service.

---

## Option B: Open WebUI with SearXNG (browser chat, self-hosted search)

Open WebUI is a ChatGPT-style web interface for Ollama. It adds web search, file uploads and knowledge bases (see [`TRAINING.md`](TRAINING.md), Level 2).

Requirements: Docker Desktop for Windows, with Ollama running on the host (not in Docker).

### 1. Run Open WebUI

```powershell
docker run -d -p 3000:8080 --add-host=host.docker.internal:host-gateway `
  -v open-webui:/app/backend/data --name open-webui --restart always `
  ghcr.io/open-webui/open-webui:main
```

Open http://localhost:3000 and create the admin account. It should find Ollama at `http://host.docker.internal:11434`, and `aicodex` will appear in the model list.

### 2. Run SearXNG

Follow Open WebUI's SearXNG guide (docs.openwebui.com → Web Search → SearXNG). The important part is that SearXNG's `settings.yml` must allow **JSON** output (`search.formats` must include `json`), or Open WebUI gets no results. Run it on port 8080:

```powershell
docker run -d --name searxng -p 8080:8080 -v ${PWD}\searxng:/etc/searxng --restart always searxng/searxng:latest
```

Test it from inside the Open WebUI container:

```powershell
docker exec -it open-webui curl "http://host.docker.internal:8080/search?q=test&format=json"
```

### 3. Connect them

In Open WebUI: **Admin Panel → Settings → Web Search**.
- Turn on **Enable Web Search**
- Engine: `searxng`
- Query URL: `http://host.docker.internal:8080/search?q=<query>`

In a chat, turn web search on for that conversation from the **+** / tools menu next to the message box.

Keep both containers bound to `localhost`. Don't expose ports 3000 or 8080 to your network.

---

## Safety notes for a web-connected model

- **Prompt injection is real.** A fetched page can contain hidden text like "ignore your instructions". Treat everything the model gets from the web as untrusted, especially in CTF web challenges where the page itself is the challenge.
- **Read every command before you run it.** AICodex suggests commands. Neither option here runs commands on your machine.
- **Check the sources.** Ask for URLs and open the important ones yourself. Web results reduce made-up answers but don't eliminate them.
