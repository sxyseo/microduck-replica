# exp001 · IMU 姿态随机化 A/B 对比

> 状态：**✅ 已完成（2026-09-06，本机 CPU 实跑，100 迭代 × 64 环境，A/B 各 4 分钟）**
> 一次只改一个变量：`ENABLE_IMU_ORIENTATION_RANDOMIZATION`（`microduck_velocity_env_cfg.py` L40，随机幅度 6° 见 L84）

## 结果（对比图：`../../assets/exp001-AB对比.png`）

| 指标 @ iter 99 | A（ON） | B（OFF） | 差异 |
|---|---|---|---|
| **Train/mean_reward** | 0.801 | **1.014** | B 末段反超领先 |
| fell_over | ≈2.08 | ≈1.92 | 无显著差 |
| error_vel_xy | 0.031 | 0.033 | 无显著差 |
| error_vel_yaw | 0.194 | 0.195 | 几乎重合 |
| Policy/mean_std | 0.903 | 0.900 | 几乎重合（都在收敛） |

## 判定（对照预注册标准）

- 预注册假设之一（"B 世界更乖，前期涨更快"）**部分成立**：前 85 迭代两线纠缠，末 15 迭代 B 甩开。
- 预注册预案"100 迭代只能得出前期动力学差异"**命中**：速度跟踪误差、摔倒率、探索噪声完全重合——
  说明随机化在 100 迭代内没有显著拖慢学习，reward 差距来自 B 少了一层观测扰动（更容易拿满分）。
- **A 的鲁棒性收益（随机化的真正目的）本实验无法回答**：需要对两个 checkpoint 做扰动测试
  （施加 IMU 旋转看性能衰减曲线）。→ **已于同日完成，见 `记录-exp001b.md`**：
  趋势符合假设（A 最大衰减 -4.6% vs B -6.0%，10° 起 A 反超），但 100 迭代尺度上差异
  （1–2%）在噪声内，不构成统计结论；工具已固化，待长训练复测。
- 结论一句话：**IMU 随机化不拖累收敛速度，代价是训练期 reward 低 ~20%（观测被扰动的直接代价）；
  它买到的鲁棒性要用扰动测试才能看见。**

## 执行记录

完整命令、指标、运行目录：`记录-A.md` / `记录-B.md`。
过程问题与解决：构建日志 `../../../构建日志.md` 2026-09-06 条目（GPU 选择器、wandb 两个启动坑）。

## 假设（预注册存档，跑之前写好的）

- B 组（无随机化）训练前期 `Train/mean_reward` 涨得更快——它面对的世界更「乖」。
- A 组（默认，有随机化）同迭代数下 `fell_over` 下降更慢。
- 50–100 迭代内大概率看不出两者「最终上限」的差别（鲁棒性差异要更长训练 + 扰动测试才显形），所以本实验的结论很可能是「前期动力学差异」——这也是有效结论。

## 变量

| 组 | L40 值 | 含义 |
|---|---|---|
| A | `True`（默认，不打补丁） | 每环境一个随机轴、≤6° 的固定 IMU 旋转（actor 的 gyro/gravity 被旋转，critic 保持真值） |
| B | `False`（应用 `exp001.patch`） | 无 IMU 随机化，其余全部相同 |

## 执行

```bash
# A 组（默认配置，直接跑；路径无关，脚本自己找仓库）
bash rl-series/experiments/exp001-imu-randomization/run_a.sh

# B 组（打一行补丁 → 跑 → 还原）
cd upstream/microduck_rl
git apply ../../rl-series/experiments/exp001-imu-randomization/exp001.patch
bash ../../rl-series/experiments/exp001-imu-randomization/run_b.sh
git checkout -- src/mjlab_microduck/tasks/microduck_velocity_env_cfg.py   # 跑完还原
```

跑完后两组各有一个 `logs/rsl_rl/velocity/<时间戳>_exp001-{a,b}/` 目录。

## 对比出图

```bash
python ../../rl-series/scripts/plot_ab_compare.py \
  --a logs/rsl_rl/velocity/<A时间戳>_exp001-a \
  --b logs/rsl_rl/velocity/<B时间戳>_exp001-b \
  --label-a "IMU随机化=ON(6°)" --label-b "IMU随机化=OFF" \
  --tags Train/mean_reward Episode_Termination/fell_over \
         Metrics/twist/error_vel_xy Metrics/twist/error_vel_yaw Policy/mean_std \
  --out ../../rl-series/assets/exp001-AB对比.png
```

## 判定标准

| 观察 | 结论 |
|---|---|
| B 前期 reward 更高、A 后期反超 | 经典 sim-to-real 教科书结果，假设成立 |
| 两者曲线几乎重合 | 50/100 迭代不足以体现；如实写，迭代数加到 300 再试一次 |
| B 反而更差 | 【推测】不太可能；若出现，检查补丁是否只改了 L40（`git diff` 留证） |

## 记录表

跑完各填一份：`记录-A.md`、`记录-B.md`（按 `../TEMPLATE.md` 格式）。
