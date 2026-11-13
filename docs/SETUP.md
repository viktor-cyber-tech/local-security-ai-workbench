# Setup

## Prerequisites

- Ollama installed and available in your terminal. Get it from [ollama.com/download](https://ollama.com/download).
- Git installed.
- At least 22 GB free disk space for the base model and local cache.
- 32 GB RAM minimum for `qwen3-coder:30b` (~19 GB download); 64 GB is comfortable.

## Performance recommendation

Run Ollama and Workbench directly on the host operating system—Windows or Linux—for the best use of available CPU, system memory, and supported GPU acceleration. Running the model inside a virtual machine adds resource limits and virtualization overhead.

If you use Kali in VirtualBox or another VM, keep it as a separate terminal for authorized CTF tools. Run Workbench on the host, then copy commands into Kali when you need its tools.

## Clone and build

### Windows PowerShell

```powershell
git clone https://github.com/viktor-cyber-tech/local-security-ai-workbench.git
cd local-security-ai-workbench
.\scripts\setup-workbench.ps1 -Run
```

If execution policy prevents the script from starting, use this temporary, current-terminal-only setting:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\setup-workbench.ps1 -Run
```

### Kali Linux, Debian, or WSL

```bash
git clone https://github.com/viktor-cyber-tech/local-security-ai-workbench.git
cd local-security-ai-workbench
bash scripts/setup-workbench.sh --install-ollama --run
```

The `--install-ollama` flag uses [Ollama’s official Linux installer](https://docs.ollama.com/) only if Ollama is missing. Omit that flag after the first install.

Both scripts:

1. Check that Ollama is installed; the Bash script can install it when passed `--install-ollama`.
2. Download the base model named in the `Modelfile` `FROM` line (`qwen3-coder:30b`) if necessary.
3. Build or rebuild the local `workbench` model using the repository’s `Modelfile`.
4. Start `ollama run workbench` when passed `-Run` or `--run`.

You can reopen it later from any folder:

```text
ollama run workbench
```

## Manual Ollama CLI

From the cloned repository folder, these commands perform the same model download, build, and launch without using a helper script:

```bash
ollama pull qwen3-coder:30b
ollama create workbench -f ./Modelfile
ollama run workbench
```

In Windows PowerShell, `ollama create workbench -f .\\Modelfile` is equivalent.

Confirm it exists:

```text
ollama list
```

## Recommended prompts

### Command generation

```text
Authorized offline CTF on Kali Linux.
Return only one copyable Bash command—no explanation.
[describe the supplied artifact and desired transformation]
```

### PowerShell 5.1 compatibility

```text
This is an authorized CTF. Give a Windows PowerShell 5.1-compatible command.
Do not use APIs introduced after Windows PowerShell 5.1.
```

## Use a separate terminal

The Ollama CLI is a chat interface; it does not execute generated commands. Keep Workbench open in one terminal and run the generated command in a separate Kali, WSL, or PowerShell terminal.
