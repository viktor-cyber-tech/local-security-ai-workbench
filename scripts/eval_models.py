#!/usr/bin/env python3
"""Compare Ollama models side by side on held-out test prompts.

Sends the user turns from each test record to every model and writes a Markdown
report with the reference answer next to each model's answer, for manual grading.

Usage:
  python scripts/eval_models.py --models workbench workbench-ft --limit 25
  python scripts/eval_models.py --test data/processed/test.jsonl --models workbench --out data/eval-baseline.md

Needs: pip install ollama (and the Ollama app running).
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

try:
    from ollama import chat
except ImportError:
    sys.exit("Missing package: pip install --upgrade ollama")


def load_cases(path, limit):
    cases = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            msgs = json.loads(line)["messages"]
            # Drop the system turn (each model uses its own Modelfile SYSTEM) and the final reference answer.
            convo = [m for m in msgs if m["role"] != "system"]
            if len(convo) < 2 or convo[-1]["role"] != "assistant":
                continue
            cases.append((convo[:-1], convo[-1]["content"]))
            if limit and len(cases) >= limit:
                break
    return cases


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--test", default="data/processed/test.jsonl")
    ap.add_argument("--models", nargs="+", default=["workbench", "workbench-ft"])
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--out", default="data/eval-report.md")
    opts = ap.parse_args()

    if not Path(opts.test).is_file():
        sys.exit(f"{opts.test} not found. Run scripts/prepare_dataset.py first.")
    cases = load_cases(opts.test, opts.limit)
    if not cases:
        sys.exit("No usable test cases found.")

    lines = [f"# Workbench evaluation\n\n", f"Models: {', '.join(opts.models)} — {len(cases)} cases from `{opts.test}`\n\n",
             "Grade each answer: correct / partly / wrong, and note any made-up flags or commands.\n"]
    timing = {m: 0.0 for m in opts.models}
    for i, (convo, reference) in enumerate(cases, 1):
        print(f"[{i}/{len(cases)}]", file=sys.stderr)
        lines.append(f"\n---\n\n## Case {i}\n\n**Prompt:**\n\n{convo[-1]['content']}\n")
        lines.append(f"\n**Reference:**\n\n{reference}\n")
        for model in opts.models:
            start = time.time()
            try:
                answer = chat(model=model, messages=convo)["message"]["content"]
                answer = re.sub(r"\n{3,}", "\n\n", re.sub(r"</?tool_call>", "", answer)).strip()
            except Exception as exc:
                answer = f"(error: {exc})"
            timing[model] += time.time() - start
            lines.append(f"\n**{model}:**\n\n{answer}\n")

    lines.append("\n---\n\n## Average response time\n")
    for model, total in timing.items():
        lines.append(f"- {model}: {total / len(cases):.1f} s\n")

    out = Path(opts.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(lines), encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
