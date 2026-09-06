"""pi_sg90_bench.py — 树莓派 + SG90 PWM 台架（四步实验，跑在树莓派上）。

依赖：Raspberry Pi OS 自带 gpiozero（无则 `sudo apt install python3-gpiozero`）。
接线：舵机信号(橙) → GPIO 17/27/22/23/24/25；电源红 → **外接 5V≥3A**（勿用 Pi 5V！）；
      地(棕/黑) → 外接电源地，且与树莓派 GND **共地**。
跑法：python3 pi_sg90_bench.py [步骤号 1-4，缺省全跑]
"""

import time

from gpiozero import Servo

PINS = [17, 27, 22, 23, 24]  # 5 只 SG90：原机器狗 4 脚 + 1 尾
# SG90 典型脉宽 0.5–2.5ms；gpiozero 用 -1..1 归一
MIN, MAX = -0.9, 0.9


def sv(i):
    return Servo(PINS[i], min_pulse_width=0.0005, max_pulse_width=0.0025)


def step1_single():
    """① 单舵机扫角：确认接线/脉宽/行程。"""
    print("① 单舵机扫角（GPIO17）——观察行程与方向")
    s = sv(0)
    for pos in (0, MIN, 0, MAX, 0):
        s.value = pos
        time.sleep(1.2)
    print("   若舵机不动：查信号线脚号、共地、外接供电。")
    input("   回车继续…")


def step2_load():
    """② 负载保持：挂重物（如电池），命令 90° 保持 30 秒。
    观察两点：齿轮有没有『咔咔』打滑；撤载后是否还回得来。"""
    print("② 负载保持 30s——给舵机轴挂点重量（约 100–200g）")
    s = sv(0)
    s.value = 0.5
    for left in range(30, 0, -10):
        print(f"   剩余 {left}s（听：有无扫齿异响；摸：是否烫手）")
        time.sleep(10)
    s.detach()
    print("   释放信号——注意：没有任何反馈告诉我们它实际停在哪。")
    input("   回车继续…")


def step3_six():
    """③ 六舵机序列：简易动作组，体验供电与协同。"""
    print("③ 6 舵机波浪序列 x3——供电要扛得住同时动作")
    servos = [sv(i) for i in range(5)]
    for _ in range(3):
        for s in servos:
            s.value = MAX
            time.sleep(0.25)
        for s in reversed(servos):
            s.value = MIN
            time.sleep(0.25)
    for s in servos:
        s.value = 0
    print("   若 Pi 重启/舵机抽搐 = 供电不足：必须独立 5V≥3A 且共地。")
    input("   回车继续…")


def step4_openloop():
    """④ 开环漂移实验（本台架的核心课程）：
    同一命令 90°，空载 vs 手指轻捏输出轴（模拟负载）——你无法从软件知道差了多少。"""
    print("④ 开环漂移：命令 90° 后用手指轻捏输出轴施加阻力")
    s = sv(0)
    s.value = 0.5
    time.sleep(2)
    print("   软件读到的『位置』永远是我们写的 0.5——真实角度无人知晓。")
    time.sleep(3)
    print("   这就是 Microduck 必须用带编码器的总线舵机的原因：61 维观测里")
    print("   的 joint_pos/joint_vel 若是假的，策略等于蒙眼走路。")
    s.detach()


if __name__ == "__main__":
    import sys
    steps = {1: step1_single, 2: step2_load, 3: step3_six, 4: step4_openloop}
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg.isdigit():
        steps[int(arg)]()
    else:
        for fn in steps.values():
            fn()
    print("\n台架完成。把现象记进构建日志，然后去下 G2 的真正门票：总线舵机。")
