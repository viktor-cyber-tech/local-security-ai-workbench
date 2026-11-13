#!/usr/bin/env python3
"""Build AICodex fine-tuning data (chat JSONL) from local dataset files.

Reads .json / .jsonl files (e.g. a local download of a Hugging Face dataset),
normalizes the common layouts into {"messages": [...]} records with the AICodex
system prompt, then filters, de-duplicates, samples, and writes train/test files.

Supported record layouts:
  - ShareGPT:      {"conversations": [{"from": "human"|"gpt"|"system", "value": "..."}]}
  - Chat:          {"messages": [{"role": "user"|"assistant"|"system", "content": "..."}]}
  - Instruction:   {"Instruction"/"instruction", "Input"/"input", "Output"/"output"}
  - Q&A pairs:     question/answer, prompt/response, prompt/completion

Usage (from the repo root):
  python scripts/prepare_dataset.py data/raw/cyber-security --sample 3000
  python scripts/prepare_dataset.py data/raw/cyber-security --own data/my-writeups.jsonl \
      --own-repeat 3 --domain web --domain forensics --sample 5000

Only Python's standard library is needed. Install `ijson` (pip install ijson)
to stream very large JSON-array files without loading them into memory.
"""

import argparse
import hashlib
import json
import random
import re
import sys
from pathlib import Path

try:
    import ijson  # optional: streams huge JSON arrays
except ImportError:
    ijson = None

ROLE_MAP = {
    "human": "user", "user": "user", "prompter": "user",
    "gpt": "assistant", "assistant": "assistant", "bot": "assistant", "model": "assistant",
    "system": "system",
}
PAIR_KEYS = [("question", "answer"), ("prompt", "response"), ("prompt", "completion"),
             ("input", "output"), ("query", "response")]
BIG_FILE_BYTES = 512 * 1024 * 1024


def get_ci(rec, *names):
    """Case-insensitive key lookup; returns the first non-empty string value."""
    lower = {k.lower(): v for k, v in rec.items()} if isinstance(rec, dict) else {}
    for n in names:
        v = lower.get(n.lower())
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def load_system_prompt(modelfile):
    text = Path(modelfile).read_text(encoding="utf-8")
    m = re.search(r'SYSTEM\s+"""(.*?)"""', text, re.S)
    if not m:
        sys.exit(f"No SYSTEM \"\"\"...\"\"\" block found in {modelfile}")
    return m.group(1).strip()


def normalize(rec):
    """Return a list of {"role","content"} turns (no system), or None if unrecognized."""
    if not isinstance(rec, dict):
        return None
    turns = None
    convo = rec.get("conversations") or rec.get("messages")
    if isinstance(convo, list):
        turns = []
        for t in convo:
            if not isinstance(t, dict):
                return None
            role = ROLE_MAP.get(str(t.get("from") or t.get("role") or "").lower())
            content = t.get("value") if "value" in t else t.get("content")
            if role is None or not isinstance(content, str):
                return None
            if role != "system":  # replaced by the AICodex system prompt
                turns.append({"role": role, "content": content.strip()})
    else:
        instr = get_ci(rec, "instruction")
        out = get_ci(rec, "output", "response", "answer")
        if instr and out:
            inp = get_ci(rec, "input", "context")
            user = f"{instr}\n\n{inp}" if inp else instr
            turns = [{"role": "user", "content": user}, {"role": "assistant", "content": out}]
        else:
            for qk, ak in PAIR_KEYS:
                q, a = get_ci(rec, qk), get_ci(rec, ak)
                if q and a:
                    turns = [{"role": "user", "content": q}, {"role": "assistant", "content": a}]
                    break
    if not turns or turns[0]["role"] != "user" or turns[-1]["role"] != "assistant":
        return None
    for prev, cur in zip(turns, turns[1:]):
        if prev["role"] == cur["role"]:
            return None  # must alternate user/assistant
    return turns


def domains_of(rec):
    meta = None
    if isinstance(rec, dict):
        meta = rec.get("Metadata") or rec.get("metadata")
    if not isinstance(meta, dict):
        return set()
    vals = []
    for key in ("domain", "subdomain"):
        v = meta.get(key)
        vals.extend(v if isinstance(v, list) else [v])
    return {str(v).lower() for v in vals if v}


def iter_records(path):
    """Yield records from a .jsonl or .json file (array, single object, or {"data": [...]})."""
    if path.suffix.lower() == ".jsonl":
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        yield None
        return
    size = path.stat().st_size
    if ijson is not None and size > BIG_FILE_BYTES:
        with path.open("rb") as fh:
            try:
                yield from ijson.items(fh, "item")
            except Exception:
                yield None
        return
    if size > BIG_FILE_BYTES:
        print(f"  skipping {path} ({size >> 20} MB): pip install ijson to stream large JSON files", file=sys.stderr)
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        yield None
        return
    if isinstance(data, dict) and isinstance(data.get("data"), list):
        data = data["data"]
    if isinstance(data, list):
        yield from data
    else:
        yield data


def collect(paths, system, wanted_domains, min_chars, max_chars, stats):
    files = []
    for p in paths:
        p = Path(p)
        files.extend(sorted(p.rglob("*")) if p.is_dir() else [p])
    for f in files:
        if f.suffix.lower() not in (".json", ".jsonl") or not f.is_file():
            continue
        stats["files"] += 1
        for rec in iter_records(f):
            stats["seen"] += 1
            if rec is None:
                stats["bad_json"] += 1
                continue
            if wanted_domains and not (domains_of(rec) & wanted_domains):
                stats["domain_filtered"] += 1
                continue
            turns = normalize(rec)
            if turns is None:
                stats["unrecognized"] += 1
                continue
            total = sum(len(t["content"]) for t in turns)
            if total < min_chars or total > max_chars or any(not t["content"] for t in turns):
                stats["length_filtered"] += 1
                continue
            yield {"messages": [{"role": "system", "content": system}] + turns}


def fingerprint(example):
    body = "\n".join(t["content"].lower() for t in example["messages"][1:3])
    return hashlib.sha1(re.sub(r"\s+", " ", body).encode()).hexdigest()


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="+", help="dataset files or folders (.json/.jsonl)")
    ap.add_argument("--own", action="append", default=[], help="your own verified JSONL (repeatable)")
    ap.add_argument("--own-repeat", type=int, default=2, help="repeat own examples N times to up-weight them")
    ap.add_argument("--domain", action="append", default=[], help="keep only records whose metadata domain/subdomain matches (repeatable)")
    ap.add_argument("--sample", type=int, default=3000, help="max examples taken from the inputs (0 = all)")
    ap.add_argument("--min-chars", type=int, default=80)
    ap.add_argument("--max-chars", type=int, default=12000, help="drop very long records (context/VRAM)")
    ap.add_argument("--test-frac", type=float, default=0.1)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--modelfile", default="Modelfile")
    ap.add_argument("--out", default="data/processed")
    opts = ap.parse_args()

    system = load_system_prompt(opts.modelfile)
    wanted = {d.lower() for d in opts.domain}
    rng = random.Random(opts.seed)
    stats = dict(files=0, seen=0, bad_json=0, unrecognized=0, domain_filtered=0, length_filtered=0, duplicates=0)

    # Reservoir sample so huge inputs never need to fit in memory.
    seen_fp, pool, kept = set(), [], 0
    for ex in collect(opts.inputs, system, wanted, opts.min_chars, opts.max_chars, stats):
        fp = fingerprint(ex)
        if fp in seen_fp:
            stats["duplicates"] += 1
            continue
        seen_fp.add(fp)
        kept += 1
        if opts.sample <= 0 or len(pool) < opts.sample:
            pool.append(ex)
        else:
            j = rng.randrange(kept)
            if j < opts.sample:
                pool[j] = ex

    own = []
    for f in opts.own:
        own.extend(collect([f], system, set(), 1, 10**9, dict(stats, files=0)))
    rng.shuffle(pool)
    rng.shuffle(own)

    def test_size(n):
        return max(1, int(n * opts.test_frac)) if n >= 10 and opts.test_frac > 0 else 0

    n_test = test_size(len(pool))
    n_own_test = test_size(len(own))
    test = pool[:n_test] + own[:n_own_test]
    train = pool[n_test:] + own[n_own_test:] * max(1, opts.own_repeat)
    rng.shuffle(train)

    out = Path(opts.out)
    write_jsonl(out / "train.jsonl", train)
    write_jsonl(out / "test.jsonl", test)

    print(json.dumps({**stats, "usable_unique": kept, "sampled": len(pool), "own_examples": len(own),
                      "train_rows": len(train), "test_rows": len(test), "output": str(out)}, indent=2))
    if stats["unrecognized"] and not kept:
        print("No records matched a known layout. Open one file and check its keys.", file=sys.stderr)


if __name__ == "__main__":
    main()
