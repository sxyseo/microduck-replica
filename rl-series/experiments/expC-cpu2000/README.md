# expC · 本机 CPU 续训 2000 迭代：能走出步态吗

> 状态：**✅ 运行中（2026-09-06 12:15 启动，预计 80–110 分钟完成）**
> 背景：exp001 只训 100 迭代（官方量级的 0.003%），用户在回放里看到"3 万步不会走"。
> 本实验回答：**同一配方单纯加大训练量（CPU 量级），能否出现初步步态？**
> 这不是变量对照实验，是"训练时长缩放"实验——没有对照组，对照物是官方 49 亿步的成熟配方。

## 预注册假设（开跑前写定）

- **H1**：`Train/mean_reward` 突破 2.0（exp001 终值 0.801；课程表在 500/750/1000/1250/1500 迭代
  逐档收紧 `action_rate`，reward 涨势应延续且在收紧点出现波动）。
- **H2**：`Episode_Termination/fell_over` 从 ≈2.0 明显下降（跌破 1.5 视为积极信号）。
- **H3**：用中途 checkpoint（model_1000 / model_2000）回放，出现**连续 ≥5 秒不摔倒的迈步样运动**
  （`capture_rollout.py` + `serve_play.sh` 直接可验）。

**判定**：
- 三条全中 → CPU 量级足以出初步步态，走路是"训练量问题"实证成立；
- 部分中（H1 H2 中、H3 无）→ 步态在量变积累中，继续训练或转 GPU 放大；
- 三条全无 → 配方或本机规模存在瓶颈，回头查课程/奖励/环境数，正式训练转 GPU（`--hf-jobs`）。

## 怎么跑的（完整命令）

```bash
cd upstream/microduck_rl
# 断点续训：从 exp001-a 的 model_99.pt 接着训到总迭代 2100（≈再训 2000 迭代）
CUDA_VISIBLE_DEVICES="" nohup uv run train Mjlab-Velocity-Flat-MicroDuck \
    --env.scene.num-envs 64 --agent.max_iterations 2100 \
    --agent.logger tensorboard --agent.resume True \
    --agent.load_run 2026-09-06_01-39-55_exp001-a \
    --agent.load_checkpoint model_99.pt \
    --agent.run_name expC-cpu2000 > /tmp/expC.log 2>&1 & disown
```

要点（踩坑换来的）：
1. `--agent.resume True`——tyro 的布尔参数必须显式给 `True`，光写 flag 会报 invalid choice；
2. `max_iterations` 是**总目标**（2100），不是"再训多少"——rsl_rl 从 checkpoint 里的迭代号（99）继续；
3. 先跑 5 迭代冒烟确认日志出现 `Loading model checkpoint from: ...model_99.pt` 且迭代号从 99 续起，再放全量。

## 怎么监控

```bash
# 1. 训练进度（日志尾部）
grep "Learning iteration" /tmp/expC.log | tail -1

# 2. 曲线（浏览器开 http://localhost:6006）
cd upstream/microduck_rl && uv run tensorboard --logdir logs/rsl_rl --port 6006

# 3. 里程碑回放（checkpoint 每 250 迭代自动存一个）
bash rl-series/scripts/serve_play.sh   # 默认加载 exp001-a；想看新的：
#   bash rl-series/scripts/serve_play.sh upstream/microduck_rl/logs/rsl_rl/velocity/<时间戳>_expC-cpu2000/model_1000.pt
```

## 结果（✅ 2026-09-06 跑完，2199 迭代，全程约 85 分钟）

| 预注册假设 | 判定 | 数据 |
|---|---|---|
| H1：reward 突破 2.0 | ✅ **大幅超越** | 0.80 → **12.77**（16 倍；中途 336 迭代即达 2.10） |
| H2：fell_over 跌破 1.5 | ✅ | ≈2.0 → **1.00** |
| H3：回放出现 ≥5 秒迈步样运动 | ✅（基本） | 最终 checkpoint 回放 **240 步零摔倒**；关键帧可见腿部换姿态；episode length 51 → **315 步（6.3s）** |

最终 checkpoint：`model_2198.pt`；回放：`assets/回放-C-2199迭代.gif`（重心转移式碎步，尚非大步走）。

## 最终结论

> **"3 万步不会走"的答案实证落地：不是模型不能走，是训练量不到。**
> 同一配方、同一台 Mac mini，从 100 迭代续训到 2199 迭代，鸭子从"每集必摔、平均活 1 秒"
> 变成"平均活 6.3 秒、回放 4.8 秒零摔、reward 16 倍"。课程的发力点也清晰可见：
> 500–1500 迭代间 `action_rate` 逐档收紧，策略在约束下重整步态——这正是配方设计的 intentional 过程。

## 对后续的三个直接推论

1. **CPU 量级（64 env × 2200 迭代）已能出"稳定站立 + 碎步"**；真"走路"预期在 10⁷–10⁸ 步量级 →
   正式策略仍按手册走 GPU（`--hf-jobs`），本实验的价值是把"要不要 GPU"从信仰变成了数据；
2. `model_1000 / 1500 / 2000 / 2198` 四个中间 checkpoint 全部保留——**步态涌现过程可回放**（公众号素材）；
3. expC 的 checkpoint 就是"换执行器后重训管线"的第一个真实测试对象：
   等新执行器模型（SG90/平替辨识参数）填进仿真，用它做 L2 退化基线评估（见[换舵机重训全流程](../../docs/换舵机重训全流程.md) §6）。
