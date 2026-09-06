# 10 · 从 checkpoint 到鸭子张嘴：ONNX 导出与运行时推理

> 状态：**可发布**（D22–24 补 infer_policy 实跑截图后发）
> 事实状态：布局与代码引用 `【已验证】`；真机部署 `【未完成】`（等实物）

> 骨架：导出链路 → 一个意外发现（51D vs 61D）→ Rust 运行时怎么喂 → 为什么「普通 PyTorch 转换」不够

## 导出链路（比想象中短）

训练结束不等于拿到策略文件。链路是：

```
model_N.pt (PyTorch checkpoint) → 导出器 → policy.onnx → 机器人运行时加载
```

这个仓库在导出上做了两件超出「torch.onnx.export」常规操作的事（list-envs 启动时那行 `Patch 4 active: ONNX export filters passive_* joints` 就是其一）：

1. **导出时过滤 passive_\* 关节**——训练时动作空间里就没有嘴，导出再兜底过滤一次，双保险防止 15/14 混淆流进部署件。
2. **策略打包（bundle）**：真机上不止一个策略（走路、站立、滚轮模式……），运行时按指令幅值切换（`policy.rs` 里有 `standing_threshold`——速度指令小到一定程度就切到站立策略）。

## 一个意外发现：脚本里藏着两套 obs 布局

读 `scripts/infer_policy.py` 时发现（L655 附近注释）：

```python
Order for velocity/standing task:
1. base_ang_vel (3D)
2. raw_accelerometer OR projected_gravity (3D)
3. joint_pos (14D) - relative to default
4. joint_vel (14D)
5. actions (14D) - last action
6. command (3D) - ...
Total: 51D
```

51 维？可 ONNX 明明是 61 维。往深处读才明白（L297/333、L422）：

```python
"--sitstand policies use the unified 13D command obs (61D); run with --new-cmd-obs"
self.command = np.zeros(13 if self.new_cmd_obs else 3, dtype=np.float32)
```

**旧布局 51D（指令只有 3 维速度）是给老策略的兼容模式；新布局 61D（13 维指令块）要 `--new-cmd-obs` 显式打开。** 训练配方一变（加了头/躯干指令），仿真脚本、导出、真机运行时三处都要同步——这个仓库选择「新旧行为都保留、用开关切换」，代价是每个新人都可能在这里懵一次（比如我）。

教训：**obs 布局是策略的指纹。** 换布局 = 换物种，旧策略喂新布局不会报错，只会安静地输出垃圾，鸭子会以非常自信的姿态摔倒。

## Rust 运行时怎么喂（duck-control/src）

- `policy.rs` L246 起，`Policy::load`：加载后**先用全零观测预热一次推理**——第一次推理永远是最慢的（懒初始化、冷页），不在 50Hz 控制环的第一拍付这笔钱。注释原话：「paying that on tick one would look exactly like a control loop that missed its deadline」。工程细节动人。
- `obs.rs`：按布局表把 gyro/gravity/关节/指令填进 61 维缓冲，编译期断言块宽总和 == OBS_LEN；关节位置减 HOME；last_action 用上一步**原始输出**（缩放前）。

## 为什么不能只做「普通的 PyTorch 转换」

ONNX 导出只是把计算图搬过去；**真正要同步的是图外的一切**：obs 顺序、单位（弧度/度）、action scale、减 HOME、延迟模型、被动关节过滤。这个项目用三重锁保证：布局常量互检（Rust 断言）、导出补丁、推理脚本的显式模式开关。我复刻换硬件时，重训后要过的第一道关就是这里的逐项核对。

（【未完成】拿到实物后补：树莓派/Radxa 上 ONNX Runtime 的实测推理耗时与 50Hz 预算对比。）
