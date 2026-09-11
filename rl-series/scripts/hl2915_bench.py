#!/usr/bin/env python3
"""HL-2915-C001 单舵机台架脚本 —— 飞特磁编码协议（TTL 半双工，1 Mbps，8N1，低位在前）。

用法与 pi_sg90_bench.py 同一套"课次"风格：

    python3 hl2915_bench.py list                 # 找串口（FE-URT-1 在 macOS 上是 /dev/tty.usb*）
    python3 hl2915_bench.py 1                    # ① 体检：PING + 出厂寄存器快照
    python3 hl2915_bench.py 2                    # ② 遥测流：位置/速度/负载/电压/温度/电流
    python3 hl2915_bench.py 3                    # ③ 闭环小步幅动作（验证编码器真的在反馈）
    python3 hl2915_bench.py 4 --minutes 10       # ④ 拷机：50 Hz 连续收发 10 分钟，统计丢包
    python3 hl2915_bench.py 5 --ids 1,2          # ⑤ 双舵机 SYNC_READ / SYNC_WRITE（真机控制环的形状）
    python3 hl2915_bench.py 6 --kp 800 --kd 80   # ⑥ 阶跃录制：改 21/22 做阶跃，50Hz 曲线→CSV+指标（阶段 F 辨识 kp/kd）
    python3 hl2915_bench.py set-id --new-id 2    # 设 ID（一次只接一只！）
    python3 hl2915_bench.py set-baud --new-baud 115200
    python3 hl2915_bench.py cal                  # 读位置校正（零位）
    python3 hl2915_bench.py cal --set-zero-here  # 把当前物理位置标定为中位 2048
    python3 hl2915_bench.py cal --rezero-2048    # 写 40=128，固件把当前位置校正为 2048（会动！）

硬件前提：
  - 调试板 FE-URT-1（或任何飞特半双工 TTL USB 调试板）
  - 12V 限流电源（限流先设 0.5A）—— HL-2915-C001 是 9-14V，接 5V/2S 都不动
  - 线序 1=GND / 2=Vcc / 3=Signal，插头 PH1.25-3P（1.25mm 间距，与 5264/JST-EH 不通用）
  - 接线、改线前永远先断电

依赖：pip3 install pyserial
"""

import argparse
import csv
import glob
import os
import sys
import time

try:
    import serial
except ImportError:
    sys.exit("缺 pyserial：pip3 install pyserial")

# ---- 寄存器（来源：飞特《舵机协议内存表-磁编码版本》220328；《HL-2915-C001 规格书》A/0）----
REG_FIRMWARE = 0
REG_ID = 5
REG_BAUD = 6
REG_RETURN_DELAY = 7      # ×2µs；内存表注"STS此地址无功能"，HL 上是否生效待实测
REG_RESPONSE_LEVEL = 8    # 1=所有指令都应答；0=只有 read/ping 应答
REG_ANGLE_MIN = 9         # 2B，步
REG_ANGLE_MAX = 11        # 2B，步
REG_TEMP_LIMIT = 13       # °C
REG_VOLT_MAX = 14         # 0.1V —— 12V 供电前必须确认它 ≥ 140，否则上电即过压保护
REG_VOLT_MIN = 15         # 0.1V
REG_MAX_TORQUE = 16       # 2B，1000=100%堵转
REG_P_GAIN = 21           # 位置环 P
REG_D_GAIN = 22           # 位置环 D
REG_I_GAIN = 23           # 位置环 I
REG_OFFSET = 31           # 2B 位置校正（零位标定），±2047 步，BIT11=方向
REG_MODE = 33             # 0=位置伺服（默认）
REG_LOCK = 55             # 0=EPROM 可写（掉电保存）；1=锁定
REG_TORQUE = 40           # 0=关；1=开；128=把当前位置校正为 2048
REG_ACCEL = 41            # ×100 步/s²
REG_GOAL = 42             # 2B 目标位置
REG_TIME = 44             # 2B 运行时间（PWM 模式用）
REG_SPEED = 46            # 2B 目标速度，步/s
REG_TORQUE_LIMIT = 48     # 2B，1000=100%
REG_POS = 56              # 2B 当前位置 —— 起，遥测块 56..69
REG_SPEED_NOW = 58        # 2B
REG_LOAD = 60             # 2B，0.1% 占空比
REG_VOLT = 62             # 1B，0.1V
REG_TEMP = 63             # 1B，°C
REG_STATUS = 65           # 位段：BIT0 电压 BIT1 磁编码 BIT2 温度 BIT3 电流 BIT5 负载
REG_MOVING = 66
REG_CURRENT = 69          # 2B，×6.5mA

BAUD_INDEX = {1000000: 0, 500000: 1, 250000: 2, 128000: 3,
              115200: 4, 76800: 5, 57600: 6, 38400: 7}

DEAD_ZONE_STEPS = 3        # 26/27 号不灵敏区出厂 1 步，再留点余量
STATUS_BITS = {
    0: "过压/欠压", 1: "磁编码异常", 2: "过热",
    3: "过流", 5: "过载",
}


# ---------------------------------------------------------------- 数据链路

def packet(sid, instr, params=b""):
    body = bytes([sid, len(params) + 2, instr]) + params
    return b"\xff\xff" + body + bytes([(~sum(body)) & 0xFF])


def parse(rx):
    """从字节流里切出第一个完整应答包，容忍串口里残留的 0xFF 填充。"""
    i = 0
    while i + 6 <= len(rx):
        if rx[i] != 0xFF or rx[i + 1] != 0xFF:
            i += 1
            continue
        length = rx[i + 3]
        total = 4 + length  # FF FF ID LEN + (ERR+参数 N) + CHK
        if i + total > len(rx):
            return None  # 半包，让调用方继续收
        body = rx[i + 2:i + 2 + length + 1]
        if (~sum(body)) & 0xFF != rx[i + total - 1]:
            i += 1
            continue
        return rx[i + 2], rx[i + 4], rx[i + 5:i + total - 1]
    return None


class Bus:
    def __init__(self, port, baud):
        self.s = serial.Serial(port, baud, bytesize=8, parity="N",
                               stopbits=1, timeout=0.05)
        self.tx_count = 0
        self.timeout_count = 0

    def close(self):
        self.s.close()

    def transact(self, sid, instr, params=b"", rx_params=0):
        """发一条指令并等应答；rx_params=期望的参数字节数（write 应答为 0）。

        广播(0xFE)的 write 不应答，调用方传 rx_params=None 跳过收包。
        """
        self.tx_count += 1
        self.s.reset_input_buffer()
        self.s.write(packet(sid, instr, params))
        self.s.flush()
        if rx_params is None:
            return b""
        want = 6 + rx_params
        deadline = time.monotonic() + 0.1
        buf = b""
        while time.monotonic() < deadline:
            buf += self.s.read(want - len(buf))
            p = parse(buf)
            if p and p[0] == sid:
                return p[2]
            time.sleep(0.0002)
        self.timeout_count += 1
        return None

    def read(self, sid, addr, length):
        rx = self.transact(sid, 0x02, bytes([addr, length]), rx_params=length)
        return rx

    def read_u16(self, sid, addr):
        rx = self.read(sid, addr, 2)
        if rx is None or len(rx) != 2:
            return None
        return rx[0] | (rx[1] << 8)

    def read_u8(self, sid, addr):
        rx = self.read(sid, addr, 1)
        return rx[0] if rx else None

    def write(self, sid, addr, data, rx=True):
        params = bytes([addr]) + bytes(data)
        return self.transact(sid, 0x03, params,
                             rx_params=(0 if rx else None))

    def sync_read(self, sids, addr, length):
        """一条 SYNC_READ 问多只；各舵机按 ID 顺序逐个回独立应答包。"""
        params = bytes([addr, length]) + bytes(sids)
        rx = self.transact(0xFE, 0x82, params, rx_params=None)
        want = len(sids) * (6 + length)
        deadline = time.monotonic() + 0.15
        buf = rx if rx else b""
        while len(buf) < want and time.monotonic() < deadline:
            buf += self.s.read(want - len(buf))
        out = {}
        p = parse(buf)
        while p:
            out[p[0]] = p[2]
            buf = buf[4 + 2 + len(p[2]) + 1:]
            p = parse(buf)
        return out

    def sync_write(self, items, addr, per_len):
        """items: [(sid, bytes), ...]；广播发出、无应答。"""
        payload = b""
        for sid, data in items:
            assert len(data) == per_len
            payload += bytes([sid]) + data
        params = bytes([addr, per_len]) + payload
        self.transact(0xFE, 0x83, params, rx_params=None)


def telemetry(bus, sid):
    """读 56..69 连续 14 字节 —— 位置/速度/负载/电压/温度/电流一次拿全。"""
    rx = bus.read(sid, REG_POS, 14)
    if rx is None or len(rx) != 14:
        return None
    u16 = lambda o: rx[o] | (rx[o + 1] << 8)
    return {
        "pos": u16(0), "speed": u16(2), "load": u16(4),
        "volt": rx[6] / 10.0, "temp": rx[7],
        "status": rx[8], "moving": rx[9], "current_ma": u16(10) * 6.5,
    }


def status_text(status):
    bits = [name for bit, name in STATUS_BITS.items() if status & (1 << bit)]
    return "正常" if not bits else "、".join(bits)


# ---------------------------------------------------------------- 课次

def find_ports():
    pats = ["/dev/tty.usb*", "/dev/ttyACM*", "/dev/ttyUSB*"]
    ports = sorted({p for pat in pats for p in glob.glob(pat)})
    if not ports:
        sys.exit("没找到 USB 串口。FE-URT-1 插好后 ls /dev/tty.usb* 确认。")
    for p in ports:
        print(" ", p)
    return ports


def lesson1(bus, sid):
    """体检：PING + 出厂寄存器快照。第一次上电只跑这个。"""
    rx = bus.transact(sid, 0x01, rx_params=0)
    if rx is None:
        sys.exit(f"ID {sid} 无应答：查线序(1=GND 2=Vcc 3=Signal)、电压(要 9-14V)、"
                 f"波特率(默认 1Mbps)。只有一只舵机时也可以试广播：--id 254")
    print(f"✔ PING 成功，ERROR=0x{rx[0]:02X} {status_text(rx[0])}")

    snap = bus.read(sid, 0, 17)
    if snap:
        print(f"固件 v{snap[0]}.{snap[1]}（内存表 2.43 对应主版本 2）")
        print(f"ID={snap[5]}  波特率档位={snap[6]}（0=1M）  "
              f"返回延时={snap[7]}×2µs  应答级别={snap[8]}（1=全应答）")
        amin = snap[9] | (snap[10] << 8)
        amax = snap[11] | (snap[12] << 8)
        print(f"行程限制 [{amin}, {amax}] 步  |  温度上限 {snap[13]}°C  |  "
              f"电压窗 [{snap[15] / 10:.1f}, {snap[14] / 10:.1f}]V")
        if snap[14] and snap[14] < 140:
            print(f"⚠️ 最高输入电压只有 {snap[14] / 10:.1f}V —— 12V 供电会立刻过压保护，"
                  f"先把它写 140（cal --volt-max 14.0 里已有该逻辑前先手工放开）")
    mode = bus.read_u8(sid, REG_MODE)
    torque = bus.read_u8(sid, REG_TORQUE)
    print(f"运行模式={mode}（0=位置伺服）  扭矩开关={torque}")
    off = read_offset(bus, sid)
    print(f"位置校正(31)={off} 步")
    t = telemetry(bus, sid)
    if t:
        print(f"遥测：位置={t['pos']}  电压={t['volt']}V  温度={t['temp']}°C  "
              f"电流={t['current_ma']:.0f}mA  状态={status_text(t['status'])}")
    print("\n出厂速查：中位=2048，全行程 0..4095（360°），0.088°/步，方向顺时针。")


def read_offset(bus, sid):
    rx = bus.read(sid, REG_OFFSET, 2)
    if not rx or len(rx) != 2:
        return None
    raw = rx[0] | (rx[1] << 8)
    negative = raw & 0x800          # BIT11 方向位
    magnitude = raw & 0x7FF
    return -magnitude if negative else magnitude


def write_offset(bus, sid, value):
    value = max(-2047, min(2047, value))
    raw = (abs(value) & 0x7FF) | (0x800 if value < 0 else 0)
    bus.write(sid, REG_OFFSET, [raw & 0xFF, raw >> 8])


def lesson2(bus, sid, seconds):
    """遥测流：验证读数连续、无丢包、数值物理上合理。"""
    print(f"连读遥测 {seconds}s（每次 READ 56 起 14 字节）… Ctrl-C 结束")
    n = miss = 0
    t_end = time.monotonic() + seconds
    v_min, t_max = 99.0, 0
    while time.monotonic() < t_end:
        t = telemetry(bus, sid)
        n += 1
        if t is None:
            miss += 1
            continue
        v_min, t_max = min(v_min, t["volt"]), max(t_max, t["temp"])
        if n % 25 == 0:
            print(f"pos={t['pos']:5d}  speed={t['speed']:6d}  load={t['load']:5d}  "
                  f"{t['volt']:5.1f}V  {t['temp']:3d}°C  {t['current_ma']:6.0f}mA  "
                  f"{'运动中' if t['moving'] else '静止'}")
        time.sleep(0.02)
    print(f"\n{n} 次读取，丢 {miss}（{miss / max(n, 1) * 100:.2f}%）；"
          f"电压最低 {v_min}V，温度最高 {t_max}°C")
    if miss:
        print("⚠️ 有丢包：先查共地与线长，再把波特率降到 500k/115200 对照（set-baud）。")


def lesson3(bus, sid):
    """闭环小步幅：命令位置 vs 反馈位置对得上，编码器才是真的在工作。

    这是 SG90 第④课（开环漂移）的总线版对照：绝对编码器不该有"无人知晓"。
    """
    start = bus.read_u16(sid, REG_POS)
    if start is None:
        sys.exit("读不到当前位置，先跑课次 1")
    span = 100  # ±100 步 ≈ ±8.8°，安全
    bus.write(sid, REG_ACCEL, [10])
    bus.write(sid, REG_TORQUE_LIMIT, [0xF4, 0x01])  # 500 = 50% 堵转
    print(f"起始 {start}，目标 ±{span} 步（≈±8.8°），速度 300 步/s")
    try:
        bus.write(sid, REG_TORQUE, [1])
        for target in (start + span, start - span, start):
            move_to(bus, sid, target)
            t = telemetry(bus, sid)
            if t is None:
                print(f"✗ 到 {target} 后读不到反馈")
                continue
            err = t["pos"] - target
            ok = abs(err) <= DEAD_ZONE_STEPS + 2
            print(f"目标 {target} → 实际 {t['pos']}（误差 {err:+d} 步）"
                  f"{'✔' if ok else ' ✗ 超差：查机械是否被卡、26/27 号不灵敏区'}")
        print("全程结束，扭矩关闭。")
    finally:
        bus.write(sid, REG_TORQUE, [0])


def move_to(bus, sid, target):
    # 与协议手册例 4 同构：42 起连写 位置(2B)+时间(2B=0)+速度(2B)
    bus.write(sid, REG_GOAL,
              [target & 0xFF, target >> 8, 0, 0, 300 & 0xFF, 300 >> 8])
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        moving = bus.read_u8(sid, REG_MOVING)
        if moving == 0:
            break
        time.sleep(0.01)
    time.sleep(0.3)  # 稳定


def lesson4(bus, sid, minutes):
    """拷机：50 Hz 连续收发 + 周期性小幅动作，统计丢包与温升。"""
    start = bus.read_u16(sid, REG_POS)
    if start is None:
        sys.exit("读不到当前位置，先跑课次 1")
    bus.write(sid, REG_ACCEL, [10])
    bus.write(sid, REG_TORQUE_LIMIT, [0xF4, 0x01])
    n = miss = 0
    t_max = 0
    v_min = 99.0
    phase = 0
    t_end = time.monotonic() + minutes * 60
    t_move = 0.0
    print(f"拷机 {minutes} 分钟，目标 50 Hz，每 5s 在 ±200 步间摆动。Ctrl-C 中止。")
    try:
        bus.write(sid, REG_TORQUE, [1])
        while time.monotonic() < t_end:
            t0 = time.monotonic()
            t = telemetry(bus, sid)
            n += 1
            if t is None:
                miss += 1
            else:
                v_min, t_max = min(v_min, t["volt"]), max(t_max, t["temp"])
                if t_max >= 70:
                    print(f"✗ 温度 {t_max}°C 触到上限，立即停")
                    break
            if t0 - t_move > 5:
                t_move = t0
                phase ^= 1
                target = start + (200 if phase else -200)
                bus.write(sid, REG_GOAL,
                          [target & 0xFF, target >> 8, 0, 0, 0xE8, 0x03])
            print(f"\r{n} 次 / 丢 {miss} / {t_max}°C / {v_min:.1f}V ",
                  end="", flush=True)
            time.sleep(max(0.0, 0.02 - (time.monotonic() - t0)))
    except KeyboardInterrupt:
        print("\n手动中止")
    finally:
        bus.write(sid, REG_GOAL,
                  [start & 0xFF, start >> 8, 0, 0, 0xE8, 0x03])
        time.sleep(1.5)
        bus.write(sid, REG_TORQUE, [0])
    rate = miss / max(n, 1)
    print(f"\n结果：{n} 次，丢 {miss}（{rate * 100:.2f}%），最高 {t_max}°C，"
          f"最低 {v_min}V")
    verdict = "PASS ✔" if rate < 0.001 and t_max < 65 else "FAIL ✗（查供电/共地/波特率）"
    print(verdict)
    return 0 if rate < 0.001 else 1


def lesson5(bus, args):
    """双舵机 SYNC 验证：一条 SYNC_READ 同时读、一条 SYNC_WRITE 同时动。

    真机 50Hz 控制环就是这两个指令的形状（15 只舵机一次收发），先用 2 只把它跑通。
    """
    ids = [int(x) for x in args.ids.split(",") if x.strip()]
    if len(ids) < 2:
        sys.exit("课 5 需要 ≥2 只舵机：--ids 1,2（先逐只跑课 1 设好 ID）")
    for sid in ids:
        if bus.read_u16(sid, REG_POS) is None:
            sys.exit(f"ID {sid} 无应答，先单独跑课 1 确认它在总线上")

    starts = {}
    blocks = bus.sync_read(ids, REG_POS, 14)
    for sid in ids:
        rx = blocks.get(sid)
        if rx is None or len(rx) != 14:
            sys.exit(f"SYNC_READ 漏了 ID {sid} —— 检查应答包切分")
        starts[sid] = rx[0] | (rx[1] << 8)
    print(f"✔ SYNC_READ 一次拿到 {len(blocks)} 只遥测："
          + "  ".join(f"ID{s}={starts[s]}" for s in ids))

    span = 100
    bus.write(ids[0], REG_ACCEL, [10])
    bus.write(ids[1], REG_ACCEL, [10])
    bus.write(ids[0], REG_TORQUE, [1])
    bus.write(ids[1], REG_TORQUE, [1])
    print(f"SYNC_WRITE：两舵机反向摆动 ±{span} 步，速度 300 步/s")
    try:
        for phase in (1, -1, 1, -1):
            items = []
            for i, sid in enumerate(ids):
                target = starts[sid] + span * phase * (1 if i == 0 else -1)
                items.append((sid, bytes([target & 0xFF, (target >> 8) & 0xFF,
                                          0, 0, 0x2C, 0x01])))
            bus.sync_write(items, REG_GOAL, 6)
            time.sleep(1.2)
            blocks = bus.sync_read(ids, REG_POS, 14)
            for i, sid in enumerate(ids):
                rx = blocks.get(sid)
                pos = (rx[0] | (rx[1] << 8)) if rx else -1
                want = starts[sid] + span * phase * (1 if i == 0 else -1)
                ok = 0 <= abs(pos - want) <= DEAD_ZONE_STEPS + 4
                print(f"  ID{sid}: 目标 {want} → 实际 {pos} {'✔' if ok else '✗'}")
    finally:
        for sid in ids:
            bus.write(sid, REG_TORQUE, [0])
    print("课 5 完成：SYNC 收发都闭环了。")


def unique_path(path):
    """同名 CSV 不覆盖——扫 kp 时会出一串文件，一个都不能少。"""
    stem, ext = os.path.splitext(path)
    cand, i = path, 1
    while os.path.exists(cand):
        cand = f"{stem}-{i}{ext}"
        i += 1
    return cand


def clamp_to_stroke(bus, sid, targets):
    """把阶跃目标收进行程限制（9/11 号）里，防呆但不替人做主——收到就明说。"""
    lo = bus.read_u16(sid, REG_ANGLE_MIN)
    hi = bus.read_u16(sid, REG_ANGLE_MAX)
    out = []
    for t in targets:
        c = t
        if lo is not None:
            c = max(lo, c)
        if hi is not None:
            c = min(hi, c)
        if c != t:
            print(f"⚠️ 目标 {t} 超出行程限制 [{lo}, {hi}]，已收到 {c}")
        out.append(c)
    return out


def record_phase(bus, sid, writer, rows, phase, target, seconds):
    """录一个阶段：t=0 写目标（pre 段不写），50 Hz 采样逐行落盘。

    丢包也记时间格（数值留空），拟合时看得到空洞在哪，而不是曲线被悄悄拉直。
    """
    if phase != "pre":
        # 与协议手册例 4 同构：42 起连写 位置(2B)+时间(2B=0)+速度(2B=0 全速)。
        # 阶跃要"陡"，速度写 0（不限速），加速度由 41 号决定，越陡越接近真阶跃。
        bus.write(sid, REG_GOAL, [target & 0xFF, target >> 8, 0, 0, 0, 0])
    t0 = time.monotonic()
    miss = 0
    while time.monotonic() - t0 < seconds:
        t = telemetry(bus, sid)
        t_ms = int((time.monotonic() - t0) * 1000)
        if t is None:
            miss += 1
            writer.writerow([phase, t_ms, target, "", "", "", "", "", ""])
            continue
        speed = t["speed"]
        if speed >= 0x8000:      # 58 号带方向：负速是两位补码
            speed -= 0x10000
        writer.writerow([phase, t_ms, target, t["pos"], speed, t["load"],
                         f"{t['volt']:.1f}", t["temp"], f"{t['current_ma']:.0f}"])
        rows.append((phase, t_ms, target, t["pos"], speed, t["load"],
                     t["current_ma"]))
        time.sleep(max(0.0, 0.02 - (time.monotonic() - t0)))
    return miss


def step_metrics(rows, phase, target, tol):
    """从一段采样里算超调/稳态误差/整定时间——辨识 kp/kd 看的就是这三个数。"""
    pts = [r for r in rows if r[0] == phase]
    if len(pts) < 5:
        return None
    p0 = pts[0][3]
    travel = target - p0
    if abs(travel) < 10:
        return None
    tail = [p for _, _, _, p, _, _, _ in pts[-10:]]
    err = sum(tail) / len(tail) - target
    dirn = 1 if travel > 0 else -1
    extreme = max(p for _, _, _, p, _, _, _ in pts) if dirn > 0 else \
        min(p for _, _, _, p, _, _, _ in pts)
    over_steps = max(0.0, (extreme - target) * dirn)
    settle_ms = None
    for i in range(len(pts)):
        if all(abs(p - target) <= tol for _, _, _, p, _, _, _ in pts[i:]):
            settle_ms = pts[i][1]
            break
    return {
        "err": err,
        "over_pct": 100.0 * over_steps / abs(travel),
        "settle_ms": settle_ms,
        "vmax": max(abs(v) for _, _, _, _, v, _, _ in pts),
        "imax": max(c for _, _, _, _, _, _, c in pts),
        "load_max": max(l for _, _, _, _, _, l, _ in pts),
    }


def lesson6(bus, sid, args):
    """阶跃录制：改 21/22 号做阶跃，50 Hz 录"目标-实际"曲线 → CSV + 指标。

    阶段 F 辨识 kp/kd 的数据就出自这里（换舵机重训全流程.md 的"PD 阶跃响应"一行）。
    21/22/23 是 EPROM（掉电保存、有擦写寿命），测完自动还原；--keep 才保留新值。
    先跑 --kp 单扫 P，再固定 P 扫 D；每组指标记进辨识表，最后填 microduck_constants.py。
    """
    start = bus.read_u16(sid, REG_POS)
    if start is None:
        sys.exit("读不到当前位置，先跑课次 1")
    kp0 = bus.read_u8(sid, REG_P_GAIN)
    kd0 = bus.read_u8(sid, REG_D_GAIN)
    ki0 = bus.read_u8(sid, REG_I_GAIN)
    tl0 = bus.read_u16(sid, REG_TORQUE_LIMIT)
    if kp0 is None or kd0 is None:
        sys.exit("读不到 21/22 号增益，先跑课次 1 确认通信")
    kp = args.kp if args.kp is not None else kp0
    kd = args.kd if args.kd is not None else kd0
    for name, v in (("--kp", args.kp), ("--kd", args.kd)):
        if v is not None and not 0 <= v <= 255:
            sys.exit(f"{name}={v} 超出 21/22 号一字节范围（0–255）")
    if args.steps <= 0:
        sys.exit("--steps（阶跃幅度）要 > 0")
    print(f"当前增益 P={kp0} D={kd0} I={ki0}，扭矩限制={tl0}；本次用 P={kp} D={kd}")

    up, back = clamp_to_stroke(bus, sid, [start + args.steps, start])
    if up <= start + 10:
        sys.exit(f"起始 {start} 离行程上限太近，正方向阶不出 {args.steps} 步——"
                 f"先把舵机转到中位附近（≈2048）再测")

    gains_changed = args.kp is not None or args.kd is not None
    if gains_changed:
        unlock(bus, sid)
        bus.write(sid, REG_P_GAIN, [kp & 0xFF])
        bus.write(sid, REG_D_GAIN, [kd & 0xFF])
        time.sleep(0.05)         # EPROM 写入要一点落笔时间

    path = unique_path(args.csv or f"hl2915_step_id{sid}_kp{kp}_kd{kd}.csv")
    f = open(path, "w", newline="", buffering=1)   # 行缓冲：Ctrl-C 不丢已采的点
    writer = csv.writer(f)
    writer.writerow(["phase", "t_ms", "target", "pos", "speed", "load",
                     "volt", "temp_c", "current_ma"])
    rows, miss = [], 0
    print(f"录制 → {path}：静置 {args.pre}s → 阶跃 {start}→{up}→{back}，"
          f"每段保持 {args.hold}s，50Hz。Ctrl-C 随时中止，数据照常落盘。")
    try:
        bus.write(sid, REG_ACCEL, [args.accel & 0xFF])
        bus.write(sid, REG_TORQUE_LIMIT,
                  [args.torque_limit & 0xFF, args.torque_limit >> 8])
        bus.write(sid, REG_TORQUE, [1])
        time.sleep(0.3)
        miss += record_phase(bus, sid, writer, rows, "pre", start, args.pre)
        miss += record_phase(bus, sid, writer, rows, "up", up, args.hold)
        miss += record_phase(bus, sid, writer, rows, "back", back, args.hold)
    except KeyboardInterrupt:
        print("\n手动中止")
    finally:
        bus.write(sid, REG_TORQUE, [0])
        if gains_changed and not args.keep:
            unlock(bus, sid)
            bus.write(sid, REG_P_GAIN, [kp0 & 0xFF])
            bus.write(sid, REG_D_GAIN, [kd0 & 0xFF])
        if tl0 is not None:
            bus.write(sid, REG_TORQUE_LIMIT, [tl0 & 0xFF, tl0 >> 8])
        f.close()
    print(f"有效样本 {len(rows)} 个，丢包 {miss} 次" +
          ("⚠️ 有丢包，曲线可能有洞，先查共地/线长再信指标" if miss else ""))

    for phase, target in (("up", up), ("back", back)):
        m = step_metrics(rows, phase, target, DEAD_ZONE_STEPS + 2)
        if m is None:
            print(f"{phase}: 样本不足或行程太小，跳过指标")
            continue
        settle = (f"{m['settle_ms']}ms" if m["settle_ms"] is not None
                  else f">{args.hold * 1000:.0f}ms 未整定")
        print(f"{phase}: 稳态误差 {m['err']:+.1f} 步 | 超调 {m['over_pct']:.1f}% | "
              f"整定 {settle} | 峰速 {m['vmax']} 步/s | "
              f"峰值电流 {m['imax']:.0f}mA | 峰值负载 {m['load_max']}")
    print(f"\n辨识记录：P={kp} D={kd}。up/back 两向稳态误差的差 ≈ 回差佐证（≠课 6 的正式回差）。"
          f"把每组 (P, D, 超调, 稳态误差, 整定) 记进换舵机重训全流程.md 的辨识表，"
          f"最终填 microduck_constants.py。")

    if args.plot:
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            print("没装 matplotlib（pip3 install matplotlib），跳过画图；"
                  "CSV 可直接丢给 pandas/Excel 看曲线。")
            return
        fig, (ax1, ax2) = plt.subplots(2, 1, sharex=True, figsize=(8, 6))
        for phase, color in (("up", "tab:red"), ("back", "tab:blue")):
            pts = [r for r in rows if r[0] == phase]
            if not pts:
                continue
            ax1.plot([p[1] for p in pts], [p[3] for p in pts],
                     color=color, label=f"{phase} 实际")
            ax1.plot([p[1] for p in pts], [p[2] for p in pts],
                     color=color, ls="--", alpha=0.4)
            ax2.plot([p[1] for p in pts], [p[4] for p in pts], color=color)
        ax1.set_ylabel("位置（步）")
        ax1.legend()
        ax1.set_title(f"HL-2915 阶跃响应  P={kp} D={kd}（虚线=目标）")
        ax2.set_ylabel("速度（步/s）")
        ax2.set_xlabel("t（ms）")
        fig.tight_layout()
        png = os.path.splitext(path)[0] + ".png"
        fig.savefig(png, dpi=150)
        print(f"曲线 → {png}")


def unlock(bus, sid):
    bus.write(sid, REG_LOCK, [0])


def cmd_set_id(bus, sid, args):
    if args.new_id is None:
        sys.exit("set-id 需要 --new-id（0-253）。一次只接一只舵机！")
    unlock(bus, sid)
    bus.write(sid, REG_ID, [args.new_id])
    time.sleep(0.05)
    rx = bus.transact(args.new_id, 0x01, rx_params=0)
    print("✔ 新 ID 有应答" if rx else "✗ 新 ID 无应答，回旧 ID 重试")
    print("提示：装上整机前，把每只舵机按 model.rs 的关节 ID 表设好并贴标签。")


def cmd_set_baud(bus, sid, args):
    if args.new_baud not in BAUD_INDEX:
        sys.exit(f"波特率只支持 {sorted(BAUD_INDEX)}")
    unlock(bus, sid)
    bus.write(sid, REG_BAUD, [BAUD_INDEX[args.new_baud]])
    print(f"✔ 已写入档位 {BAUD_INDEX[args.new_baud]}（={args.new_baud}）。"
          f"用 --baud {args.new_baud} 重连验证。")


def cmd_cal(bus, sid, args):
    pos = bus.read_u16(sid, REG_POS)
    off = read_offset(bus, sid)
    print(f"当前位置={pos}  位置校正={off}")
    if args.rezero_2048:
        print("写 40=128：固件把当前位置校正为 2048（舵机轴须停在你要的机械零位）…")
        bus.write(sid, REG_TORQUE, [128])
        time.sleep(0.2)
        print(f"现在 读数={bus.read_u16(sid, REG_POS)}（应为 2048）")
    elif args.set_zero_here:
        new = (off or 0) + (2048 - pos)
        print(f"改位置校正 {off} → {new}（把当前物理位置标定为 2048）")
        write_offset(bus, sid, new)
        print(f"现在 读数={bus.read_u16(sid, REG_POS)}")
    elif args.volt_max:
        v = int(round(args.volt_max * 10))
        unlock(bus, sid)
        bus.write(sid, REG_VOLT_MAX, [v])
        print(f"最高输入电压 → {v / 10:.1f}V")
    else:
        print("只读不改。要标零位用 --set-zero-here，或固件一键 --rezero-2048（先固定好轴！）")
        print("注意：40 写 128 和 31 号校正都会改变零位，装配后再标，标完记录进构建日志。")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", help="list / 1 / 2 / 3 / 4 / 5 / 6 / set-id / set-baud / cal")
    ap.add_argument("--port")
    ap.add_argument("--baud", type=int, default=1000000)
    ap.add_argument("--id", type=int, default=1)
    ap.add_argument("--ids", default="1,2", help="课 5 的舵机 ID 列表，逗号分隔")
    ap.add_argument("--minutes", type=float, default=10)
    ap.add_argument("--seconds", type=float, default=10)
    ap.add_argument("--kp", type=int, help="课 6：位置环 P（21 号，EPROM，测完自动还原）")
    ap.add_argument("--kd", type=int, help="课 6：位置环 D（22 号，EPROM，测完自动还原）")
    ap.add_argument("--steps", type=int, default=200,
                    help="课 6：阶跃幅度，步（默认 200 ≈ 17.6°）")
    ap.add_argument("--accel", type=int, default=50,
                    help="课 6：41 号加速度 ×100 步/s²（默认 50；越大阶跃越陡）")
    ap.add_argument("--torque-limit", type=int, default=500,
                    help="课 6：48 号扭矩限制（默认 500 = 50%% 堵转，台架保险值）")
    ap.add_argument("--hold", type=float, default=2.0, help="课 6：每段保持秒数")
    ap.add_argument("--pre", type=float, default=0.5, help="课 6：阶跃前静置秒数")
    ap.add_argument("--csv", help="课 6：CSV 路径（默认 hl2915_step_id<id>_kp<kp>_kd<kd>.csv）")
    ap.add_argument("--plot", action="store_true", help="课 6：顺手出 PNG 曲线（要 matplotlib）")
    ap.add_argument("--keep", action="store_true",
                    help="课 6：保留新写入的 21/22（默认测完还原原值）")
    ap.add_argument("--new-id", type=int)
    ap.add_argument("--new-baud", type=int)
    ap.add_argument("--set-zero-here", action="store_true")
    ap.add_argument("--rezero-2048", action="store_true")
    ap.add_argument("--volt-max", type=float)
    args = ap.parse_args()

    if args.cmd == "list":
        find_ports()
        return

    port = args.port
    if not port:
        ports = find_ports()
        port = ports[0] if len(ports) == 1 else sys.exit(
            "找到多个串口，用 --port 指定")
    bus = Bus(port, args.baud)
    try:
        if args.cmd == "1":
            lesson1(bus, args.id)
        elif args.cmd == "2":
            lesson2(bus, args.id, args.seconds)
        elif args.cmd == "3":
            lesson3(bus, args.id)
        elif args.cmd == "4":
            sys.exit(lesson4(bus, args.id, args.minutes))
        elif args.cmd == "5":
            lesson5(bus, args)
        elif args.cmd == "6":
            lesson6(bus, args.id, args)
        elif args.cmd == "set-id":
            cmd_set_id(bus, args.id, args)
        elif args.cmd == "set-baud":
            cmd_set_baud(bus, args.id, args)
        elif args.cmd == "cal":
            cmd_cal(bus, args.id, args)
        else:
            ap.print_help()
    finally:
        bus.close()


if __name__ == "__main__":
    main()
