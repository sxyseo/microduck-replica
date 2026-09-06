"""exp001b · IMU 安装旋转鲁棒性评估：对 A/B 两个 checkpoint 施加相同旋转，量性能衰减。

原理：训练期的 IMU 随机化 = 对 actor 观测的 gyro(0:3) 和 projected_gravity(3:6) 做
逐环境固定随机轴旋转（mdp.py 的 *_imu_misaligned）。本脚本在推理时对 obs 前 6 维
做同样的事后旋转 —— 物理等价，且对 A/B 完全公平（同一组旋转轴、同一 seed）。

用法（在 microduck_rl 仓库根目录）:
    CUDA_VISIBLE_DEVICES="" .venv/bin/python ../../rl-series/scripts/eval_imu_robustness.py

输出: rl-series/assets/exp001b-扰动测试.md + exp001b-扰动曲线.png
"""

import math
import sys
from dataclasses import asdict
from pathlib import Path

import torch

RUNS = {
    "A(随机化ON)": "logs/rsl_rl/velocity/2026-09-06_01-39-55_exp001-a/model_99.pt",
    "B(随机化OFF)": "logs/rsl_rl/velocity/2026-09-06_01-45-41_exp001-b/model_99.pt",
}
ANGLES = [0, 3, 6, 10, 15]
NUM_ENVS = 32
STEPS = 300
SEED = 42
TASK = "Mjlab-Velocity-Flat-MicroDuck"

_ASSETS = Path(__file__).resolve().parents[1] / "assets"
OUT_MD = _ASSETS / "exp001b-扰动测试.md"
OUT_PNG = _ASSETS / "exp001b-扰动曲线.png"


def axis_quat(axis: torch.Tensor, angle_rad: float) -> torch.Tensor:
    """轴角 → 四元数 [w,x,y,z]（每环境一个，batch 化）。"""
    axis = axis / axis.norm(dim=-1, keepdim=True).clamp_min(1e-9)
    half = angle_rad / 2
    w = torch.cos(torch.tensor(half)).expand(axis.shape[0])
    xyz = axis * math.sin(half)
    return torch.stack([w, xyz[:, 0], xyz[:, 1], xyz[:, 2]], dim=-1)


def quat_apply(q: torch.Tensor, v: torch.Tensor) -> torch.Tensor:
    """标准四元数旋转：v' = q ⊗ v ⊗ q*。与 mjlab quat_apply 同约定。"""
    w, x, y, z = q[:, 0], q[:, 1], q[:, 2], q[:, 3]
    uv = torch.stack([
        2 * (y * v[:, 2] - z * v[:, 1]),
        2 * (z * v[:, 0] - x * v[:, 2]),
        2 * (x * v[:, 1] - y * v[:, 0]),
    ], dim=-1)
    return v + w.unsqueeze(-1) * uv + torch.linalg.cross(uv, torch.stack([x, y, z], dim=-1))


def rotate_imu_block(obs_actor: torch.Tensor, q: torch.Tensor) -> None:
    """对 obs 前 6 维（gyro 0:3、gravity 3:6）施加逐环境旋转，原位修改。"""
    obs_actor[:, 0:3] = quat_apply(q, obs_actor[:, 0:3])
    obs_actor[:, 3:6] = quat_apply(q, obs_actor[:, 3:6])


def evaluate(ckpt: str, angles, generator: torch.Generator):
    from mjlab.envs import ManagerBasedRlEnv
    from mjlab.rl import MjlabOnPolicyRunner, RslRlVecEnvWrapper
    from mjlab.tasks.registry import load_env_cfg, load_rl_cfg, load_runner_cls

    env_cfg = load_env_cfg(TASK, play=True)
    env_cfg.scene.num_envs = NUM_ENVS
    for attr in ("seed",):
        if hasattr(env_cfg, attr):
            setattr(env_cfg, attr, SEED)
    env = ManagerBasedRlEnv(cfg=env_cfg, device="cpu", render_mode=None)
    env = RslRlVecEnvWrapper(env, clip_actions=None)

    agent_cfg = load_rl_cfg(TASK)
    runner_cls = load_runner_cls(TASK) or MjlabOnPolicyRunner
    runner = runner_cls(env, asdict(agent_cfg), device="cpu")
    runner.load(ckpt, load_cfg={"actor": True}, strict=True, map_location="cpu")
    policy = runner.get_inference_policy(device="cpu")

    results = []
    for angle in angles:
        torch.manual_seed(SEED)
        axis = torch.randn(NUM_ENVS, 3, generator=generator)
        q = axis_quat(axis, math.radians(angle))

        obs_dict, _ = env.reset()
        total_rew = torch.zeros(NUM_ENVS)
        falls, truncs = 0, 0
        for _ in range(STEPS):
            rotate_imu_block(obs_dict["actor"], q)
            out = policy(obs_dict)
            actions = out[0] if isinstance(out, tuple) else out
            obs_dict, rew, dones, extras = env.step(actions)
            total_rew += rew
            falls += int((dones == 1).sum())
            truncs += int(extras.get("time_outs", torch.zeros_like(dones)).sum())
        results.append({
            "angle": angle,
            "mean_step_reward": float(total_rew.sum() / (NUM_ENVS * STEPS)),
            "mean_return_per_env": float(total_rew.mean()),
            "falls": falls,
            "falls_per_100_steps": 100.0 * falls / (NUM_ENVS * STEPS),
        })
        print(f"  angle={angle:>2}°  rew/step={results[-1]['mean_step_reward']:.4f}  "
              f"falls/100步={results[-1]['falls_per_100_steps']:.2f}")
    del env, runner
    return results


def main():
    gen = torch.Generator().manual_seed(SEED)
    table = {}
    for name, ckpt in RUNS.items():
        print(f"== {name}: {Path(ckpt).name}")
        table[name] = evaluate(ckpt, ANGLES, gen)

    lines = ["# exp001b · IMU 安装旋转鲁棒性测试", "",
             f"> 评估设置：{NUM_ENVS} 环境 × {STEPS} 步，旋转轴对 A/B 完全一致（seed={SEED}），"
             "checkpoint = 各组 model_99（100 迭代）。reward 为**每步平均**（含摔倒惩罚）。",
             "", "| 旋转角 | A 奖励/步 | B 奖励/步 | A 摔倒/百步 | B 摔倒/百步 |",
             "|---|---|---|---|---|"]
    for i, angle in enumerate(ANGLES):
        a, b = table["A(随机化ON)"][i], table["B(随机化OFF)"][i]
        lines.append(f"| {angle}° | {a['mean_step_reward']:.4f} | {b['mean_step_reward']:.4f} "
                     f"| {a['falls_per_100_steps']:.2f} | {b['falls_per_100_steps']:.2f} |")
    OUT_MD.write_text("\n".join(lines) + "\n")
    print(f"written {OUT_MD}")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        plt.rcParams["font.family"] = ["Songti SC", "Hiragino Sans GB", "Arial Unicode MS", "sans-serif"]
        fig, ax = plt.subplots(figsize=(7, 4.2))
        for (name, rows), color in zip(table.items(), ["#d62728", "#1f77b4"]):
            ax.plot([r["angle"] for r in rows], [r["mean_step_reward"] for r in rows],
                    marker="o", label=name, color=color)
        ax.set_xlabel("IMU 安装旋转角（°）")
        ax.set_ylabel("平均每步奖励")
        ax.set_title("exp001b：IMU 随机化训练 vs 干净训练的抗扰对比（100 迭代 checkpoint）")
        ax.grid(alpha=0.3)
        ax.legend()
        fig.tight_layout()
        fig.savefig(OUT_PNG, dpi=160)
        print(f"written {OUT_PNG}")
    except Exception as e:
        print("plot skipped:", e)


if __name__ == "__main__":
    sys.exit(main())
