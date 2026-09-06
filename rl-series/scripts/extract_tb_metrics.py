"""从 rsl_rl 的 TensorBoard 事件文件里导出关键标量，生成 Markdown 表格。

用法:
    python scripts/extract_tb_metrics.py <logs/rsl_rl/velocity 目录> [输出.md]

不依赖 GPU，也不需要加载 mjlab —— 只读事件文件。
"""

import os
import sys

from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

KEY = ["mean_reward", "fell_over", "error_vel", "mean_std", "Episode_Length"]


def dump(runs_dir: str) -> str:
    lines = ["| 运行 | 指标 | step: 值 |", "|---|---|---|"]
    for run in sorted(os.listdir(runs_dir)):
        d = os.path.join(runs_dir, run)
        if not os.path.isdir(d):
            continue
        ea = EventAccumulator(d)
        ea.Reload()
        tags = [t for t in ea.Tags()["scalars"] if any(k in t for k in KEY)]
        for t in sorted(tags):
            pts = ea.Scalars(t)
            vals = " | ".join(f"{p.step}: `{p.value:.3f}`" for p in pts)
            lines.append(f"| {run} | `{t}` | {vals} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    text = dump(sys.argv[1])
    print(text)
    if len(sys.argv) > 2:
        with open(sys.argv[2], "w") as f:
            f.write(text)
        print("written to", sys.argv[2])
