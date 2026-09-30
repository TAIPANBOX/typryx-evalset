#!/usr/bin/env bash
# Runs ON the benchmark VM (Debian 12, n2-standard-8). Installs the local model
# the comparison reports, speaking to typryx on loopback only:
#   ollama  qwen2.5:7b      :11434  (typryx openai-logprobs backend)
# Nothing listens on a public interface: the server binds 127.0.0.1.
set -euo pipefail

sudo apt-get update -qq
sudo apt-get install -y -qq curl jq >/dev/null

# ollama + qwen2.5:7b
curl -fsSL https://ollama.com/install.sh | sh >/dev/null
sudo systemctl enable --now ollama
ollama pull qwen2.5:7b

echo "setup done; check: curl -s 127.0.0.1:11434/api/tags"
