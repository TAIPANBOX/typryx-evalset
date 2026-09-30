#!/usr/bin/env bash
# Runs ON the benchmark VM (Debian 12, n2-standard-8). Installs the three local
# backends the comparison needs, each speaking to typryx on loopback only:
#   ollama  qwen2.5:7b      :11434  (typryx openai-logprobs backend)
#   von     von-1.3.0 CPU   :8001   (typryx systemone-protocol backend)
#   laya    typed-decisions :8002   (typryx systemone-protocol backend)
# Nothing listens on a public interface: every server binds 127.0.0.1.
set -euo pipefail

sudo apt-get update -qq
sudo apt-get install -y -qq docker.io python3-venv python3-pip curl jq >/dev/null
sudo systemctl enable --now docker

# ollama + qwen2.5:7b
curl -fsSL https://ollama.com/install.sh | sh >/dev/null
sudo systemctl enable --now ollama
ollama pull qwen2.5:7b

# von (CPU image, OpenVINO)
sudo docker run -d --name von --restart unless-stopped -p 127.0.0.1:8001:8000 \
  -v von-hf:/data/huggingface ghcr.io/wfzyx/von:cpu

# laya (typed-decisions checkpoint, CPU)
python3 -m venv ~/laya-venv
~/laya-venv/bin/pip install -q "laya[serve]"
LAYA_HOST=127.0.0.1 LAYA_PORT=8002 LAYA_DEVICE=cpu LAYA_PRELOAD=1 \
  LAYA_MODELS=typed-decisions LAYA_THREADS=8 \
  nohup ~/laya-venv/bin/laya-serve > ~/laya.log 2>&1 &

echo "setup done; wait for von and laya to download weights, then check:"
echo "  curl -s 127.0.0.1:8001/healthz; curl -s 127.0.0.1:8002/healthz"
