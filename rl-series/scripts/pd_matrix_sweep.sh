#!/bin/bash
# pd_matrix_sweep.sh — S3 单命令驱动：健康门控 → P/D 矩阵扫描 → 自动辨识表。
#
# 组合两个已验证的环节（不新增协议逻辑）：
#   1) hl2915_bench.py 课 1 —— PING/固件/增益读取，判定通信与舵机健康（零响应先 REBOOT 清锁）
#   2) hl2915_bench.py 课 6 —— 按矩阵逐点录阶跃 CSV（每点每轮一个文件，bench 自动还原增益）
#   3) step_sweep_summary.py —— 自动剔除零响应取证，汇总出辨识表
#
# 用法：
#   ./pd_matrix_sweep.sh --port /dev/tty.usbserial-XXXX            # 真跑（默认 id=1，矩阵 P{16,32,64}×D{0,32} 各 3 轮）
#   ./pd_matrix_sweep.sh --dry-run                                 # 只打印将执行的命令，不碰硬件
#   ./pd_matrix_sweep.sh --port ... --id 1 --rounds 3 --kp-list "16 32 64" --kd-list "0 32"
#
# 前置：pyserial 已装（python3 -m pip install --user --break-system-packages pyserial）；
#       舵机 12V 限流供电；HL-2915 台架 12.1V 只验证流程，HL-1910 正式参数按 7.4V 重采。
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PORT="" ; ID=1 ; ROUNDS=3 ; KP_LIST="16 32 64" ; KD_LIST="0 32" ; DRY=0 ; BAUD=1000000

while [ $# -gt 0 ]; do
  case "$1" in
    --port) PORT="$2" ; shift 2 ;;
    --id) ID="$2" ; shift 2 ;;
    --rounds) ROUNDS="$2" ; shift 2 ;;
    --kp-list) KP_LIST="$2" ; shift 2 ;;
    --kd-list) KD_LIST="$2" ; shift 2 ;;
    --baud) BAUD="$2" ; shift 2 ;;
    --dry-run) DRY=1 ; shift ;;
    *) echo "不认识的参数：$1" >&2 ; exit 2 ;;
  esac
done
[ -n "$PORT" ] || { echo "必须给 --port（插上 URT2 后看 ls /dev/tty.usb*）" >&2 ; exit 2 ; }

run() { if [ "$DRY" = 1 ]; then echo "[dry-run] $*"; else "$@"; fi; }

echo "== 1/3 健康门控：课 1（id=${ID}）"
run python3 "$HERE/hl2915_bench.py" --port "$PORT" --baud "$BAUD" --id "$ID" 1

echo "== 2/3 P/D 矩阵扫描（P{$KP_LIST} × D{$KD_LIST} × $ROUNDS 轮，200 步幅）"
n=0
for kp in $KP_LIST; do
  for kd in $KD_LIST; do
    for r in $(seq 1 "$ROUNDS"); do
      # 不覆盖既有文件：已入库的零响应取证是证据，新轮次顺延编号
      while [ -e "$HERE/hl2915_step_id${ID}_kp${kp}_kd${kd}-${r}.csv" ]; do r=$((r+1)); done
      csv="hl2915_step_id${ID}_kp${kp}_kd${kd}-${r}.csv"
      echo "-- [$((++n))] kp=$kp kd=$kd 第 ${r} 轮 → $csv"
      run python3 "$HERE/hl2915_bench.py" --port "$PORT" --baud "$BAUD" --id "$ID" \
          --kp "$kp" --kd "$kd" --csv "$HERE/$csv" 6
    done
  done
done

echo "== 3/3 汇总辨识表（零响应取证自动剔除）"
run python3 "$HERE/step_sweep_summary.py" --out "$HERE/hl2915_step_sweep_summary.md"
echo "== 完成。辨识表：$HERE/hl2915_step_sweep_summary.md"
