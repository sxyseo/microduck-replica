# rl-series · MicroDuck RL 公众号系列工作区

> **源码拆解 + 可复现实验 + 复刻过程**。不做代码翻译，每篇文章讲一个
> 「我改了什么 → 为什么改 → 怎么运行 → 指标如何变化 → 结论和失败原因」的完整故事。

## 诚实性三标签（每篇必带）

- **【已验证】** 我实际运行过，附命令与产物路径
- **【推测】** 根据代码/注释推断，明确说出依据
- **【未完成】** 还没有验证，写明计划何时验证

## 目录

```
rl-series/
├── 30天计划.md            ← 总纲：日历 + 主链路 + 每周退出标准
├── articles/              ← 12 篇（01–06、10 可发布/近可发布，其余框架稿）
├── experiments/
│   ├── TEMPLATE.md        ← 实验记录模板（预注册假设）
│   ├── exp000-*.md        ← 已完成：5 迭代冒烟，真实指标已入库
│   └── exp001-imu-randomization/  ← 待执行：A/B 一行补丁 + 脚本 + 记录表
├── scripts/               ← 全部可复跑：指标提取 / A-B 出图 / ONNX 验形状 /
│                             flags 导出 / 渲染封面 / obs 布局图
└── assets/                ← 已生成资产 + 待截清单（截图清单.md）
```

## 快速开始（对应 30 天计划 D1–D4）

```bash
cd upstream/microduck_rl
uv run list-envs                                   # 环境自检
uv run train Mjlab-Velocity-Flat-MicroDuck \
    --env.scene.num-envs 64 --agent.max_iterations 5   # 冒烟（AGENTS.md 官方写法）
uv run tensorboard --logdir logs/rsl_rl
```

已验证事实速览（上游 `29e887e`，本机 Mac mini 实测）：

- 训练/回放/导出链路全通；lesson-01（5 迭代 ×8 env）reward `-0.061 → 0.095`，`fell_over ≈ 1.0`（还不会走，真实且诚实）。
- **exp001 A/B + exp001b 扰动测试全部实跑完成**（`experiments/exp001-imu-randomization/`）；
  **3D 回放已通**：`scripts/capture_rollout.py` 离屏渲染 GIF + 关键帧（`assets/回放-*.gif`）。
- ONNX 输入 `obs[1,61]` / 输出 `actions[1,14]`；Rust 运行时同款布局 `3+3+14+14+14+13=61`；
  本机评估时网络结构实证 critic 输入 76 维。
- 本系列所有脚本只依赖 `upstream/microduck_rl/.venv`（tensorboard/matplotlib/onnx/mujoco），无需 GPU。

## 3D 仿真怎么看

```bash
cd upstream/microduck_rl

# 离屏捕获（无窗口，产出 GIF + 关键帧到 rl-series/assets/）
CUDA_VISIBLE_DEVICES="" .venv/bin/python ../../rl-series/scripts/capture_rollout.py \
    --ckpt logs/rsl_rl/velocity/<run>/model_99.pt --label <标签>

# 交互式实时查看 —— 浏览器方案（已验证 ✓，macOS 上最稳）
CUDA_VISIBLE_DEVICES="" uv run play Mjlab-Velocity-Flat-MicroDuck \
    --checkpoint-file logs/rsl_rl/velocity/<run>/model_99.pt \
    --viewer viser --num-envs 1
# 然后浏览器打开 http://localhost:8080
```

> ⚠️ **macOS + uv 环境勿用 `--viewer native`**：MuJoCo 原生窗口要求 `mjpython`，
> 而 uv 安装的独立版 Python 与 mjpython 的动态库搜索路径不兼容（`dlopen libpython3.12.dylib`
> 失败，DYLD_LIBRARY_PATH 覆盖无效）。浏览器方案 `viser` 不经 `launch_passive`，实测可用。

## 与其他目录的关系

- `../`（microduck-replica）：机械/电控复刻研究 —— 本系列是它的「大脑」续篇
- `../../OpenMicroDuck/`：社区完全开源复刻计划 —— 文章 02 讲三者关系
- 上游 `upstream/microduck_rl`：**只读不改**；实验改动一律走 patch + 跑完还原
