#!/usr/bin/env python3
"""Workbench agent: a local, offline-first CTF assistant with tools.

The model (your local `workbench` Ollama model) can:
  - list and read files in ONE folder you choose (--workdir), never outside it
  - write Python scripts into that folder (for scanning, recon, enumeration)
  - fetch a URL from THIS machine (reaches VPN / localhost / non-standard ports),
    so it can look at the web app in a web challenge
  - optionally search the web for docs/CVEs (needs an Ollama API key)

Safety boundary: the agent WRITES scripts, it never RUNS them. You review each
script and run it yourself. That keeps a human in the loop before anything touches
a target — the right workflow for authorized CTF / lab / pentest work.

Usage (run from the repo root, in your venv):
  python scripts/workbench_agent.py --workdir path\\to\\challenge
  python scripts/workbench_agent.py --workdir . "write a recon script for 10.10.10.5"

Requires: pip install --upgrade ollama   (requests is used if present, else stdlib)
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

try:
    from ollama import chat
except ImportError:
    sys.exit("The 'ollama' package is missing. Run: pip install --upgrade ollama")

try:
    import requests  # nicer HTTP if available
except ImportError:
    requests = None

MAX_READ = 20000       # chars returned from a file read
MAX_HTTP = 12000       # chars returned from an HTTP response body
MAX_TOOL = 12000       # hard cap on any tool result handed back to the model

AGENT_NOTE = (
    "\n\nYou are running as a local agent with tools: list_dir, read_file, write_file, "
    "http_request, and (maybe) web_search. All file access is confined to the user's "
    "chosen working folder. Use http_request to inspect a target web app in a web "
    "challenge. When asked for scanning, recon, or enumeration, WRITE a clear, commented "
    "Python script into the working folder with write_file and tell the user how to run "
    "it — never assume you have run it; you cannot execute anything. Only act against "
    "targets the user is authorized to test (their own lab, a CTF, a signed engagement). "
    "Prefer standard tools (nmap, ffuf, requests, httpx) and explain what each step does."
)


def load_system_prompt(modelfile):
    try:
        text = Path(modelfile).read_text(encoding="utf-8")
    except OSError:
        return "You are Workbench, a local cybersecurity CTF assistant."
    m = re.search(r'SYSTEM\s+"""(.*?)"""', text, re.S)
    return (m.group(1).strip() if m else "You are Workbench, a local cybersecurity CTF assistant.")


class Workspace:
    """All file tools resolve through here, confined to one folder."""

    def __init__(self, root):
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            sys.exit(f"--workdir is not a folder: {self.root}")

    def _resolve(self, rel):
        p = (self.root / (rel or ".")).resolve()
        if p != self.root and self.root not in p.parents:
            raise ValueError(f"path '{rel}' is outside the working folder")
        return p

    def list_dir(self, path="."):
        d = self._resolve(path)
        if not d.is_dir():
            return f"Not a directory: {path}"
        out = []
        for e in sorted(d.iterdir()):
            tag = "dir " if e.is_dir() else "file"
            size = e.stat().st_size if e.is_file() else ""
            out.append(f"{tag}  {e.relative_to(self.root)}  {size}")
        return "\n".join(out) or "(empty)"

    def read_file(self, path):
        f = self._resolve(path)
        if not f.is_file():
            return f"Not a file: {path}"
        data = f.read_bytes()[: MAX_READ * 2]
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            return f"[binary file, {f.stat().st_size} bytes] hex head: {data[:200].hex()}"
        return text[:MAX_READ] + ("\n...[truncated]" if len(text) > MAX_READ else "")

    def write_file(self, path, content):
        f = self._resolve(path)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content, encoding="utf-8", newline="\n")
        return f"Wrote {len(content)} chars to {f.relative_to(self.root)} (review it, then run it yourself)"


def http_request(url, method="GET", headers=None, body=None):
    method = (method or "GET").upper()
    headers = headers or {}
    if isinstance(headers, str):
        try:
            headers = json.loads(headers)
        except json.JSONDecodeError:
            headers = {}
    try:
        if requests is not None:
            r = requests.request(method, url, headers=headers, data=body, timeout=20, allow_redirects=True)
            head = f"{r.status_code} {r.reason}\n" + "\n".join(f"{k}: {v}" for k, v in r.headers.items())
            return f"{head}\n\n{r.text[:MAX_HTTP]}"
        data = body.encode() if isinstance(body, str) else body
        req = Request(url, data=data, headers=headers, method=method)
        with urlopen(req, timeout=20) as resp:
            head = f"{resp.status} {resp.reason}\n" + "\n".join(f"{k}: {v}" for k, v in resp.headers.items())
            text = resp.read(MAX_HTTP * 2).decode("utf-8", "replace")
            return f"{head}\n\n{text[:MAX_HTTP]}"
    except HTTPError as e:
        body_txt = e.read(MAX_HTTP).decode("utf-8", "replace") if hasattr(e, "read") else ""
        return f"{e.code} {e.reason}\n\n{body_txt}"
    except (URLError, Exception) as e:  # report, don't crash the loop
        return f"Request error: {e}"


def web_search(query):
    if not os.environ.get("OLLAMA_API_KEY"):
        return "web_search unavailable: set OLLAMA_API_KEY (free key from ollama.com) to enable it."
    try:
        from ollama import web_search as _ws
        return str(_ws(query))[:MAX_TOOL]
    except Exception as e:
        return f"web_search error: {e}"


TOOLS_SPEC = [
    {"type": "function", "function": {
        "name": "list_dir",
        "description": "List files and folders inside the working folder.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "Relative path inside the working folder. Default '.'"}}}}},
    {"type": "function", "function": {
        "name": "read_file",
        "description": "Read a text file inside the working folder.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "Relative path of the file to read."}}, "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "write_file",
        "description": "Write a text file (e.g. a Python script) into the working folder. Does not run it.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "Relative path to write, e.g. recon.py"},
            "content": {"type": "string", "description": "Full file contents."}}, "required": ["path", "content"]}}},
    {"type": "function", "function": {
        "name": "http_request",
        "description": "Make an HTTP request from this machine and return status, headers and body. Use for inspecting a target web app.",
        "parameters": {"type": "object", "properties": {
            "url": {"type": "string"},
            "method": {"type": "string", "description": "GET, POST, etc. Default GET."},
            "headers": {"type": "object", "description": "Optional request headers."},
            "body": {"type": "string", "description": "Optional request body."}}, "required": ["url"]}}},
    {"type": "function", "function": {
        "name": "web_search",
        "description": "Search the web for docs, CVEs, or tool usage. Needs an Ollama API key.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"}}, "required": ["query"]}}},
]


def run_turn(model, messages, ws, max_steps):
    dispatch = {
        "list_dir": lambda a: ws.list_dir(a.get("path", ".")),
        "read_file": lambda a: ws.read_file(a.get("path", "")),
        "write_file": lambda a: ws.write_file(a.get("path", ""), a.get("content", "")),
        "http_request": lambda a: http_request(a.get("url", ""), a.get("method", "GET"), a.get("headers"), a.get("body")),
        "web_search": lambda a: web_search(a.get("query", "")),
    }
    for _ in range(max_steps):
        resp = chat(model=model, messages=messages, tools=TOOLS_SPEC)
        msg = resp["message"]
        messages.append(msg)
        calls = msg.get("tool_calls") or []
        if not calls:
            return msg.get("content", "")
        for call in calls:
            fn = call["function"]["name"]
            args = call["function"].get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            shown = args.get("url") or args.get("path") or args.get("query") or ""
            print(f"  [{fn}] {shown}", file=sys.stderr)
            try:
                result = str(dispatch[fn](args))
            except Exception as e:
                result = f"tool error: {e}"
            messages.append({"role": "tool", "content": result[:MAX_TOOL], "tool_name": fn})
    messages.append({"role": "user", "content": "Stop using tools and give your answer now."})
    return chat(model=model, messages=messages)["message"].get("content", "")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("task", nargs="*", help="one-shot task (omit for interactive mode)")
    ap.add_argument("--workdir", default=".", help="the folder the agent may read/write (default: current)")
    ap.add_argument("--model", default="workbench", help="Ollama model (default: workbench)")
    ap.add_argument("--modelfile", default="Modelfile", help="Modelfile to read the system prompt from")
    ap.add_argument("--max-steps", type=int, default=16, help="max tool rounds per task")
    opts = ap.parse_args()

    ws = Workspace(opts.workdir)
    system = load_system_prompt(opts.modelfile) + AGENT_NOTE
    print(f"Workbench agent | model={opts.model} | folder={ws.root}", file=sys.stderr)
    print("The agent writes scripts; it never runs them. Review and run them yourself.\n", file=sys.stderr)

    messages = [{"role": "system", "content": system}]

    if opts.task:
        messages.append({"role": "user", "content": " ".join(opts.task)})
        print(run_turn(opts.model, messages, ws, opts.max_steps))
        return

    print("Interactive. Type a task, or 'exit'.", file=sys.stderr)
    while True:
        try:
            line = input("\n>>> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if line.lower() in {"exit", "quit"}:
            break
        if not line:
            continue
        messages.append({"role": "user", "content": line})
        print(run_turn(opts.model, messages, ws, opts.max_steps))


if __name__ == "__main__":
    main()
