# exp001 记录 · B 组（IMU 随机化 = OFF）

```text
实验名称：exp001-B IMU 姿态随机化关闭（对照）
代码 commit：microduck_rl @ 29e887e
本地改动：exp001.patch（仅 L40 一行：True → False），跑完已 git checkout 还原
修改参数：microduck_velocity_env_cfg.py:40 ENABLE_IMU_ORIENTATION_RANDOMIZATION True → False
我的假设：（预注册于 README.md，与 A 组一致）
训练命令：git apply exp001.patch && CUDA_VISIBLE_DEVICES="" uv run train ... \
         --env.scene.num-envs 64 --agent.max_iterations 100 \
         --agent.logger tensorboard --agent.run_name exp001-b
         （参数与 A 组完全一致，唯一差异是补丁那一行；跑完已还原）
机器与硬件：Mac mini（Apple Silicon），纯 CPU
训练时长：训练 4 分 02 秒（约 2.4s/迭代），与 A 组几乎一致（负载等价性 ✓）
显存占用：-
TensorBoard 变化（iteration 99 终值）：
  Train/mean_reward：0.065 → **1.014**（末 15 迭代甩开 A 组）
  Episode_Termination/fell_over：稳定 1.8–2.7，终值 ≈1.92（与 A 无显著差）
  Metrics/twist/error_vel_xy：终值 0.033（与 A 的 0.031 无显著差）
  Metrics/twist/error_vel_yaw：终值 0.195（与 A 的 0.194 几乎重合）
  Policy/mean_std：0.999 → 0.900（与 A 的 0.903 几乎重合）
对比图路径：rl-series/assets/exp001-AB对比.png（蓝）
最终结论：见 README 判定表——B 前期/中期 reward 与 A 纠缠，末段反超并领先
下一步：鲁棒性判定需扰动测试（对两个 checkpoint 施加 IMU 旋转看性能衰减），
本机 100 迭代无法回答"A 的耐心是否换来更硬的耳朵"
```

运行目录：`logs/rsl_rl/velocity/2026-09-06_01-45-41_exp001-b/`
