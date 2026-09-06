#!/usr/bin/env bash
# serve_play.sh — 一键启动 3D 回放服务器（viser 浏览器方案），带自检
# 用法:
#   rl-series/scripts/serve_play.sh                    # 默认加载 exp001-a 的 model_99
#   rl-series/scripts/serve_play.sh <checkpoint.pt>    # 指定 checkpoint
# 启动后浏览器打开 http://localhost:8080
set -euo pipefail

RL_DIR="$(cd "$(dirname "$0")/../../upstream/microduck_rl" && pwd)"
CKPT="${1:-$RL_DIR/logs/rsl_rl/velocity/2026-09-06_01-39-55_exp001-a/model_99.pt}"

if [[ ! -f "$CKPT" ]]; then
  echo "checkpoint 不存在: $CKPT"; echo "可用的运行:"; ls "$RL_DIR/logs/rsl_rl/velocity/" | tail -8; exit 1
fi

# 已在运行则不打断
if curl -s -o /dev/null --max-time 2 http://localhost:8080/; then
  echo "服务器已在运行: http://localhost:8080 （浏览器直接打开即可）"; exit 0
fi

echo "启动 3D 回放服务器（首次约 1 分钟构建环境，之后保持运行）…"
cd "$RL_DIR"
CUDA_VISIBLE_DEVICES="" nohup uv run play Mjlab-Velocity-Flat-MicroDuck \
  --checkpoint-file "$CKPT" --viewer viser --num-envs 1 \
  > /tmp/viser_server.log 2>&1 & disown

for i in $(seq 1 30); do
  sleep 5
  if curl -s -o /dev/null --max-time 2 http://localhost:8080/; then
    echo "✅ 服务就绪 → 浏览器打开 http://localhost:8080"
    exit 0
  fi
done
echo "❌ 60 秒内未就绪，查看日志: tail -30 /tmp/viser_server.log"; exit 1
