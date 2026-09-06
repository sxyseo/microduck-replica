# 07 · reward 函数到底在奖励什么

> 状态：**初稿**（D15–D19 期间补齐 mdp.py 逐函数解读与自己的 reward 实验后发布）
> 事实状态：权重与函数名 `【已验证】`；权重背后的取舍动机多为注释原文 `【已验证】`，我的解读部分 `【推测】`

> 骨架：读什么 → 最大的坑（配置 vs 数学分家）→ reward 账本 → 我准备改什么

## 最大的坑：配置不是公式

我一开始以为读懂了环境配置就读懂了 reward——比如这句：

```python
# microduck_velocity_env_cfg.py L342
cfg.rewards["track_linear_velocity"].weight = 2.0
```

错。**这只是给一个函数调了权重，函数本身在另一个 7188 行的文件里**：`tasks/mdp.py`。配置文件是「账本」，mdp.py 才是「怎么算钱」。这个分家是 mjlab 框架的设计，也是新手最容易迷路的地方。

## reward 账本（vel 任务主要条目）

| 项 | 权重 | 在奖励什么行为 |
|---|---|---|
| `upright` | 2.0 (L300) | 保持身体直立——活着的基本盘 |
| `track_linear_velocity` | 2.0 (L342) | 线速度跟踪，std=√0.1 |
| `track_angular_velocity` | 2.0 (L344) | 角速度跟踪（转弯） |
| `head_pose_tracking` | 主目标之一 | 头部独立看方向——这鸭子的招牌动作 |
| `action_rate_l2` | **curriculum**：-0.1 → -1.0 | 惩罚动作抖动，分 5 档收紧（iter 1500 拉满） |
| `foot_slip` | **-0.1，故意调弱** | 惩罚脚滑。注释原话：调强了「too restrictive for this robot's pivot-heavy turning」——这鸭子靠原地 pivot 转弯，脚必须允许蹭地 |
| `feet_air_time` 等 | 步态项 | 鼓励交替迈步 |

## 三个值得讲的「反直觉」

**1. 惩罚项是慢慢拧紧的。** `action_rate` 的权重不是常数，是课程表：从 -0.1 开始，500/750/1000/1250/1500 迭代各加一档，最后到 -1.0。为什么？训练初期动作本来就抖，一上来重罚抖动，策略会学出「一动不如一静」。先让它敢走，再教它走好看。

**2. 转弯是喂出来的。** 文件头注释（L14–16）写了：速度指令如果只是独立均匀采样，「spin-on-the-spot ~2% of data → untrained」。所以有了 `TURN_IN_PLACE_FRACTION = 0.15`：强制 15% 的环境专门练原地转。**数据分布也是 reward 设计的一部分。**

**3. 指令范围宁小勿变。** 曾经试过把指令范围随训练逐渐加宽（curriculum widening），结果注释里写着「outpaced the robot's capability and tracked a post-iter-1000 reward/episode-length decline」——课程跑得比学生的能力快，reward 涨了、实际表现在退化。最后改成固定的小范围（ang ±1.0），「makes turning learnable」。

## 我准备做的实验（exp002 候选）

把 `foot_slip` 从 -0.1 调到 -0.3，假设：转弯跟踪误差（`error_vel_yaw`）变差、脚滑减少。验证方式：50 迭代 A/B + play 回放看步态。

（此处等 exp001 跑完、GPU 长训练发起后补充实测数据 —— 【未完成】）

---

*下一篇：08 · 域随机化如何帮仿真练出的本事搬到真机*
