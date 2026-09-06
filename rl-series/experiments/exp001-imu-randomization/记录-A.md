# exp001 记录 · A 组（IMU 随机化 = ON）

```text
实验名称：exp001-A IMU 姿态随机化开启（默认配置）
代码 commit：microduck_rl @ 29e887e
本地改动：无（默认即 A 组）
修改参数：无
我的假设：（预注册于 README.md：B 前期涨更快、A 上限更高但 100 迭代难见反超）
训练命令：CUDA_VISIBLE_DEVICES="" uv run train Mjlab-Velocity-Flat-MicroDuck \
         --env.scene.num-envs 64 --agent.max_iterations 100 \
         --agent.logger tensorboard --agent.run_name exp001-a
机器与硬件：Mac mini（Apple Silicon），纯 CPU（MJWarp CPU 后端）
训练时长：训练 4 分 07 秒（约 2.3s/迭代 × 100），加启动共约 5 分钟
显存占用：-
TensorBoard 变化（iteration 99 终值）：
  Train/mean_reward：0.082 → **0.801**（单调爬升，迭代 45 后加速）
  Episode_Termination/fell_over：首迭代后稳定在 1.8–2.8，终值 ≈2.08
  Metrics/twist/error_vel_xy：稳定 0.026–0.040，终值 0.031
  Metrics/twist/error_vel_yaw：稳定 0.16–0.22，终值 0.194
  Policy/mean_std：0.999 → 0.903（平稳下降 = 策略在收敛）
对比图路径：rl-series/assets/exp001-AB对比.png（红）
最终结论：见 README 判定表——A 组在世界更"刁"（IMU 带随机旋转）下仍正常收敛
下一步：与 B 组对比（对比图已生成）；更长期的鲁棒性对比需 500+ 迭代或换 GPU
```

运行目录：`logs/rsl_rl/velocity/2026-09-06_01-39-55_exp001-a/`（含 model_0.pt 与导出的 ONNX）
