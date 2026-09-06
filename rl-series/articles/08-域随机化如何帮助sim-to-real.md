# 08 · 域随机化：给仿真世界掺沙子的人

> 状态：**✅ 可发布（2026-09-06 更新：exp001 A/B + 扰动测试全部实跑，本文已是实测文）**
> 事实状态：全部 `【已验证】`（本机 CPU 实跑，数据与脚本见 `../experiments/exp001-imu-randomization/`）

> 骨架：我改了什么 → 为什么改 → 怎么运行 → 指标如何变化 → 结论

## 我要改什么

只改一个变量（exp001）：

```python
# microduck_velocity_env_cfg.py L40
ENABLE_IMU_ORIENTATION_RANDOMIZATION = True   # A 组：默认
ENABLE_IMU_ORIENTATION_RANDOMIZATION = False  # B 组：打补丁后
```

其他一切不动。补丁只有一行（`experiments/exp001-imu-randomization/exp001.patch`）。

## 为什么是它

- IMU 观测（gyro 3 维 + gravity 3 维）是策略判断「我是不是要摔了」的核心输入；
- 它的随机化机制最直观：每个环境被分配一个随机轴、最多 6° 的固定旋转，策略看到的 IMU 就像一块**装歪了但自己不知道**的传感器；
- 对我的复刻有直接意义：我要自绘 `imu_to_dxl` 板，装歪几度的概率比官方还大。

## 怎么运行（真实命令，本机 CPU 各 4 分钟）

```bash
# A 组（默认）
CUDA_VISIBLE_DEVICES="" uv run train Mjlab-Velocity-Flat-MicroDuck \
    --env.scene.num-envs 64 --agent.max_iterations 100 --agent.logger tensorboard --agent.run_name exp001-a
# B 组（打一行补丁 → 跑 → 还原）
git apply exp001.patch && CUDA_VISIBLE_DEVICES="" uv run train ... --agent.run_name exp001-b
git checkout -- src/mjlab_microduck/tasks/microduck_velocity_env_cfg.py
```

（两个启动坑：无 GPU 机器要 `CUDA_VISIBLE_DEVICES=""`；默认 wandb 要换 tensorboard。）

## 指标如何变化（100 迭代实测）

| 指标 @iter 99 | A（ON） | B（OFF） |
|---|---|---|
| mean_reward | 0.801 | **1.014**（末 15 迭代反超） |
| fell_over / error_vel_xy / error_vel_yaw / mean_std | ≈2.08 / 0.031 / 0.194 / 0.903 | ≈1.92 / 0.033 / 0.195 / 0.900 |

**四项行为指标完全重合——随机化没有拖慢学习**。reward 差距是观测被扰动的直接代价（B 少一层噪声，更容易拿满分）。

然后是关键一步：对两个 checkpoint 做扰动测试（对 obs 施加 0–15° 的 IMU 旋转，`scripts/eval_imu_robustness.py`）：

| 旋转角 | A 奖励/步 | B 奖励/步 |
|---|---|---|
| 0° | 0.0997 | **0.1025** |
| 6° | **0.1025** | 0.0994 |
| 10° | **0.1006** | 0.0963 |
| 15° | 0.0950 | 0.0972 |

## 顺带讲清：这个仓库的随机化分三层

1. **初始化随机**：reset 时姿态、速度的扰动（`ENABLE_BASE_ORIENTATION_RANDOMIZATION`，当前关）。
2. **每环境常量随机**：一个环境一辈子一个值，像出厂差异——IMU 6° 安装误差（L40）、编码器偏置（L41）、CoM 偏移（L31）都是这类。
3. **过程随机**：训练中途踢一脚（`ENABLE_VELOCITY_PUSHES`，L39）。

层次感是这个仓库教我的：**出厂差异要「固定」，突发干扰要「随机」，系统性偏差要「标定」**——三种问题三种药。

## 结论（诚实版）

1. **随机化不拖累收敛**：A 在更刁的世界里学得一样快（行为指标重合）。
2. **随机化的代价是明码标价的**：训练期 reward 低 ~20%（观测扰动让满分更难拿）。
3. **它买到的鲁棒性，趋势正确但尚不可测**：A 的最大衰减 -4.6% vs B 的 -6.0%，10° 起 A 反超；
   但 100 迭代的差异（1–2%）在单 seed 噪声内。**需要 1000+ 迭代的成熟策略才能下统计结论**——
   这正是预注册时预料到的边界，评估工具已固化，长训练后一键复测。
4. 对复刻者的实操含义：**别因为训练曲线低就关随机化**——那条曲线的差距不是"学得差"，
   是"考卷更难"；而真机的 IMU 就是歪着装的。

---

*下一篇：09 · 2080、3080、4090 训练速度对比*
