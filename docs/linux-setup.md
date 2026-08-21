# Linux setup

From a clean machine.

## 1. System packages

```bash
sudo apt update
sudo apt install -y git curl build-essential
```

Install uv:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source "$HOME/.local/bin/env"
```

Install VSCodium (Code-OSS, no Microsoft telemetry, no Copilot):

```bash
# see https://vscodium.com/  — Debian/Ubuntu example:
wget -qO - https://gitlab.com/paulcarroza/vscodium-deb-rpm-repo/raw/master/pub.gpg \
  | gpg --dearmor | sudo tee /usr/share/keyrings/vscodium-archive-keyring.gpg >/dev/null
echo 'deb [signed-by=/usr/share/keyrings/vscodium-archive-keyring.gpg] https://download.vscodium.com/debs vscodium main' \
  | sudo tee /etc/apt/sources.list.d/vscodium.list
sudo apt update && sudo apt install -y codium
```

Optional local models (16GB RAM / 8GB VRAM): [Ollama](https://ollama.com)

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5-coder:7b-instruct
```

## 2. This repo

```bash
git clone <this-repo> taknee
cd taknee
uv sync --group dev
uv run pytest -q
uv run taknee
```

Kernel listens on `http://127.0.0.1:47821`. Leave that terminal open.

## 3. Extension

```bash
codium --install-extension ./apps/extension
# or: open the folder apps/extension in codium and Run Extension
```

Open a **project folder** in VSCodium (the codebase to edit). The kernel indexes that folder only.

## 4. API keys (mandatory)

Command Palette → **Taknee: Settings / API Keys**.

| Provider | Where to get a key (free-tier / PAYG, no subscription) | Field |
| --- | --- | --- |
| Groq | https://console.groq.com/keys | Groq |
| NVIDIA NIM | https://build.nvidia.com/settings/api-keys | NVIDIA NIM |
| OpenRouter | https://openrouter.ai/keys | OpenRouter |
| Ollama | local, no key | Ollama base URL `http://127.0.0.1:11434/v1` |

Save. The status bar chip should leave `idle`.

## 5. Run a task

1. Open the Taknee activity bar (left).
2. Type a task in Agent. Ctrl+Enter to run.
3. Watch the route chip (model + why).
4. Accept/reject hunks in Review.
5. Inspect spans in Traces (works live and after stop).

`/bytheway how does login work?` asks an isolated question and does not touch the task snapshot.

## Windows / macOS

Same kernel: `uv run taknee`. Install [VSCodium](https://github.com/VSCodium/vscodium/releases) for your OS, then `codium --install-extension ./apps/extension`. On Windows PowerShell use `uv run taknee` from the repo root.
