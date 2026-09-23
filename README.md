# Local Security AI Workbench

> A local-first cybersecurity AI workbench for authorized learning, CTFs, and defensive analysis.

## Overview

Local Security AI Workbench is an early-stage portfolio project exploring how locally run AI can support cybersecurity learning and defensive workflows without sending sensitive material to a cloud service.

The project is designed for controlled environments such as personal homelabs, explicitly authorized CTFs, and defensive security exercises. It is not a finished security product, and it does not replace human judgment or established security controls.

## Project goals

- Run AI-assisted cybersecurity workflows locally with Ollama-compatible models.
- Analyze user-provided CTF artifacts and practice data.
- Explain encodings, logs, alerts, and command output in plain language.
- Support SOC-style triage notes, IOC extraction, and investigation checklists.
- Document reproducible workflows for Windows PowerShell, Bash, Kali Linux, and WSL.

## Current focus

This repository is in its initial build stage. The first deliverables will be:

1. A documented local setup for an Ollama-compatible model.
2. Safe prompt templates for authorized CTF and defensive-analysis tasks.
3. Reproducible examples for Hex, Base64, ROT13, gzip, and layered-encoding analysis.
4. Clear validation steps and troubleshooting notes.

## Safety and authorized use

Use this project only with systems, data, and environments you own or are explicitly authorized to assess.

- Allowed: personal labs, approved CTFs, coursework, and defensive analysis of provided data.
- Not allowed: unauthorized access, credential theft, persistence, evasion, disruption, malware deployment, or targeting third-party systems.
- Confirm scope and authorization before scanning, testing, or collecting data.

## Planned repository layout

```text
docs/       Setup guides, workflows, and troubleshooting
prompts/    Reusable authorized-use prompt templates
scripts/    Small helper scripts for safe data transformation
examples/   Sanitized practice artifacts and expected outputs
```

## Status

**Stage:** Initial setup

This repository will grow through small, documented milestones. Each capability will include an intended use case, validation steps, and clear limitations.

## Author

Built by [Viktor Huynh](https://github.com/viktor-cyber-tech).

---

This repository is an educational portfolio project. It does not provide a warranty, professional security services, or permission to test systems without authorization.
