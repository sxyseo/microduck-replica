"""对比两次训练运行的 TensorBoard 曲线，画成一张 A/B 对比图（PNG）。

用法:
    python scripts/plot_ab_compare.py --a <runA目录> --b <runB目录> \
        --tags Train/mean_reward Episode_Termination/fell_over --out 对比图.png

标题里 A/B 的含义由 --label-a / --label-b 指定（如 "IMU随机化=ON" / "=OFF"）。
"""

import argparse
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

plt.rcParams["font.family"] = ["Songti SC", "PingFang SC", "Arial Unicode MS", "sans-serif"]


def scalars(run_dir: str, tag: str):
    ea = EventAccumulator(run_dir, size_guidance={"scalars": 0})
    ea.Reload()
    if tag not in ea.Tags()["scalars"]:
        return None, None
    pts = ea.Scalars(tag)
    return [p.step for p in pts], [p.value for p in pts]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", required=True)
    ap.add_argument("--b", required=True)
    ap.add_argument("--label-a", default="A")
    ap.add_argument("--label-b", default="B")
    ap.add_argument("--tags", nargs="+", default=["Train/mean_reward"])
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    fig, axes = plt.subplots(len(args.tags), 1, figsize=(8, 3.2 * len(args.tags)), squeeze=False)
    for ax, tag in zip(axes[:, 0], args.tags):
        for run, label, color in (
            (args.a, f"A: {args.label_a}", "#d62728"),
            (args.b, f"B: {args.label_b}", "#1f77b4"),
        ):
            xs, ys = scalars(run, tag)
            if xs is None:
                print(f"[warn] {os.path.basename(run)} 里没有 {tag}")
                continue
            ax.plot(xs, ys, marker="o", label=label, color=color)
        ax.set_title(tag)
        ax.set_xlabel("iteration")
        ax.grid(alpha=0.3)
        ax.legend()
    fig.tight_layout()
    fig.savefig(args.out, dpi=160)
    print("saved", args.out)


if __name__ == "__main__":
    main()
