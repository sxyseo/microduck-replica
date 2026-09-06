#!/usr/bin/env bash
# exp001 B 组：IMU 姿态随机化 = OFF（需先 git apply exp001.patch）
# 任意位置执行均可：脚本自动定位 microduck_rl 仓库
set -euo pipefail
RL_DIR="$(cd "$(dirname "$0")/../../../upstream/microduck_rl" && pwd)"
cd "$RL_DIR"

RUN_NAME="exp001-b-$(date +%H%M)"
uv run train Mjlab-Velocity-Flat-MicroDuck \
  --env.scene.num-envs 64 \
  --agent.max_iterations 100 \
  --agent.run_name "$RUN_NAME"
