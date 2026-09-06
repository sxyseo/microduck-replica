"""画出 61 维 observation 的分块布局图（actor），供文章 6 配图。

尺寸是写死的（与 duck-control/src/obs.rs 的布局表一致），不是算出来的：
  gyro(3) + gravity(3) + joint_pos(14) + joint_vel(14) + last_action(14) + command(13)
  command = twist(3) + head_pose(4) + body_pose(6)
"""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.family"] = ["Songti SC", "PingFang SC", "Arial Unicode MS", "sans-serif"]

blocks = [
    ("陀螺仪 gyro", 3, "#8ecae6"),
    ("投影重力 gravity", 3, "#219ebc"),
    ("关节位置−HOME", 14, "#ffb703"),
    ("关节速度", 14, "#fb8500"),
    ("上一步动作", 14, "#90be6d"),
    ("速度指令 twist", 3, "#e07a5f"),
    ("头部位姿指令", 4, "#d65d7a"),
    ("躯干位姿指令", 6, "#9b5de5"),
]

fig, ax = plt.subplots(figsize=(11, 3.0))
start = 0
for i, (name, width, color) in enumerate(blocks):
    ax.barh(0, width, left=start, height=0.5, color=color, edgecolor="white")
    ax.text(start + width / 2, 0.05, str(width), ha="center", va="center",
            fontsize=11, fontweight="bold")
    # 标签上下交错，避免窄块文字互相压住
    y = -0.38 if i % 2 == 0 else -0.78
    ax.text(start + width / 2, y, name, ha="center", va="top", fontsize=9)
    start += width
ax.text(start / 2, 0.62, f"合计 {start} 维  =  ONNX 输入 obs[1, 61]",
        ha="center", fontsize=12, fontweight="bold")
ax.set_xlim(0, start)
ax.set_ylim(-1.1, 1.0)
ax.axis("off")
fig.tight_layout()
fig.savefig("assets/obs-61维布局.png", dpi=170, bbox_inches="tight")
print("saved assets/obs-61维布局.png")
