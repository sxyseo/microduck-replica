"""3D 仿真回放捕获：加载训练好的 checkpoint，在 MuJoCo 里滚动并离屏渲染成 GIF + 关键帧。

用法（在 microduck_rl 仓库根目录）:
    CUDA_VISIBLE_DEVICES="" .venv/bin/python ../../rl-series/scripts/capture_rollout.py \
        --ckpt logs/rsl_rl/velocity/<run>/model_99.pt --label A-100迭代

输出: rl-series/assets/回放-<label>.gif + 回放-<label>-关键帧*.png
注意：100 迭代的策略还不会走路 —— GIF 里的踉跄和摔倒就是"第一次回放"的诚实素材。
"""

import argparse
import math
from dataclasses import asdict
from pathlib import Path

import torch

_ASSETS = Path(__file__).resolve().parents[1] / "assets"
TASK = "Mjlab-Velocity-Flat-MicroDuck"
STEPS = 240
CAPTURE_EVERY = 2
GIF_FPS = 15


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--steps", type=int, default=STEPS)
    args = ap.parse_args()

    from mjlab.envs import ManagerBasedRlEnv
    from mjlab.rl import MjlabOnPolicyRunner, RslRlVecEnvWrapper
    from mjlab.tasks.registry import load_env_cfg, load_rl_cfg, load_runner_cls

    env_cfg = load_env_cfg(TASK, play=True)
    env_cfg.scene.num_envs = 1
    # 相机：跟随鸭子本体，四分之三视角（与 render_duck.py 的出图角度一致）
    v = env_cfg.viewer
    v.height, v.width = 480, 640
    v.lookat = (0.0, 0.0, 0.12)
    v.distance = 0.55
    v.elevation = -12
    v.azimuth = -135
    try:
        v.origin_type = v.OriginType.ASSET_ROOT
        v.entity_name = "robot"
    except Exception as e:
        print(f"[warn] ASSET_ROOT 跟拍不可用（{e}），退回 AUTO")

    env = ManagerBasedRlEnv(cfg=env_cfg, device="cpu", render_mode="rgb_array")
    wrapped = RslRlVecEnvWrapper(env, clip_actions=None)

    agent_cfg = load_rl_cfg(TASK)
    runner_cls = load_runner_cls(TASK) or MjlabOnPolicyRunner
    runner = runner_cls(wrapped, asdict(agent_cfg), device="cpu")
    ckpt = Path(args.ckpt)
    runner.load(str(ckpt), load_cfg={"actor": True}, strict=True, map_location="cpu")
    policy = runner.get_inference_policy(device="cpu")

    obs_dict, _ = wrapped.reset()
    frames, rewards, falls = [], 0.0, 0
    for step in range(args.steps):
        out = policy(obs_dict)
        actions = out[0] if isinstance(out, tuple) else out
        obs_dict, rew, dones, _ = wrapped.step(actions)
        rewards += float(rew.sum())
        falls += int((dones == 1).sum())
        if step % CAPTURE_EVERY == 0:
            frames.append(env.render())  # HWC uint8
    env.close()

    import numpy as np
    from PIL import Image

    _ASSETS.mkdir(parents=True, exist_ok=True)
    gif_frames = [
        Image.fromarray(f).resize((480, 360)) for f in frames if f.ndim == 3
    ]
    gif_path = _ASSETS / f"回放-{args.label}.gif"
    gif_frames[0].save(
        gif_path, save_all=True, append_images=gif_frames[1:],
        duration=int(1000 / GIF_FPS), loop=0,
    )
    # 关键帧：开始 / 1/3 / 2/3 / 结束
    for i, idx in enumerate([0, len(gif_frames) // 3, 2 * len(gif_frames) // 3, len(gif_frames) - 1]):
        Image.fromarray(frames[min(idx * CAPTURE_EVERY, len(frames) - 1)]).save(
            _ASSETS / f"回放-{args.label}-关键帧{i + 1}.png"
        )
    print(f"saved {gif_path.name}: {len(gif_frames)} 帧, "
          f"reward/step={rewards / args.steps:.4f}, 摔倒 {falls} 次, "
          f"帧亮度均值 {float(np.mean([f.mean() for f in frames])):.0f}/255")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
