# 01 · 我为什么研究 MicroDuck 强化学习

> 状态：**可发布**（待你补一段个人动机后发）
> 事实状态：本文所有技术事实均为 `【已验证】`（本机运行/代码核实，上游 commit `29e887e`）

## 缘起

我在复刻 Pollen Robotics 的 MicroDuck——一只 25cm、737g 的双足机器鸭。机械部分我已经从官方公开的 MJCF 仿真模型反推出了装配图、紧固件清单和完整电控方案（见 microduck-replica 仓库）。但做到一半我意识到一个问题：

**机械抄得再准，鸭子不会走路就只是个摆件。**

让它走路的东西是一只「神经网络大脑」：强化学习策略。官方把它训练在 MuJoCo 仿真里，导出成 ONNX 文件，机器人上的 Rust 运行时以 50Hz 的频率喂给它传感器数据、取回 14 个关节的目标角度。这套大脑的训练代码官方开源了，就是 `microduck_rl` 仓库。

这个仓库对我来说是最好的强化学习教材，原因有三：

1. **它小**。核心胶水代码就几个文件：一个 949 行的环境配置，一个任务注册文件，一个常量文件。不需要先啃完 mjlab 框架就能看懂主干。
2. **它是真的**。它的每一行随机化、每一个 reward 权重，都对应真机上真实存在的物理问题——舵机回差、IMU 安装误差、编码器偏置。这不是教程项目，是打过仗的代码。
3. **注释里全是「为什么」**。比如：

```python
# microduck_velocity_env_cfg.py L40
ENABLE_IMU_ORIENTATION_RANDOMIZATION = True  # Simulates mounting errors
```

```python
# L84（我最喜欢的一条注释）
IMU_ORIENTATION_RANDOMIZATION_ANGLE = 6.0
# up-to-6° random-axis IMU mounting error. NOTE: zero-centered (random axis) —
# trains tolerance to misalignment *magnitude*, NOT a pitch bias. The real
# board's systematic ~5° pitch offset is corrected at the source in the
# runtime (imu-pitch-offset), not here.
```

翻译过来：训练时给 IMU 加最大 6° 的随机安装误差，让策略学会容忍「装歪的传感器」；但真机上那块板子系统性偏了约 5° 的俯仰角，这个**不在训练里修，而在机器人运行时里修**。一句话讲清了 sim-to-real 里「随机化」和「标定」的分工。这种知识，教科书上没有。

## 本系列要做什么

把这个项目从训练到真机的主链路拆开讲一遍：

```
任务注册 → 环境配置 → observation/action → MuJoCo 仿真 → reward
        → PPO 更新 → checkpoint → ONNX → 机器人运行时(Rust)
```

但**不做代码翻译**。每篇都按这个骨架来：

> 我改了什么 → 为什么改 → 怎么运行 → 指标如何变化 → 结论和失败原因

每篇文章我会跑真实实验、贴真实指标，并明确标注：

- `【已验证】`我实际运行过
- `【推测】`根据代码推断
- `【未完成】`还没有验证

比如现在就可以诚实地说（【已验证】）：

> 我在 Mac mini 上用 CPU 冒烟跑了一轮 5 次迭代的训练，成功验证了「训练 → TensorBoard → checkpoint → ONNX 导出」整条链路。但 `Episode_Termination/fell_over` 稳定在 1.0——鸭子每一集都以摔倒告终。它离学会走路还很远。

## 配图

- 封面：`../assets/duck-render-03-四分之三.png`（我自己用 MuJoCo 离屏渲染的，渲染脚本 `../scripts/render_duck.py`，踩了两个坑：MJCF 离屏缓冲默认 640 宽、原模型没灯光——都写在脚本注释里）

---

*下一篇：02 · OpenMicroDuck、microduck-replica、microduck_rl 到底什么关系？*
