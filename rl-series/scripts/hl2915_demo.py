#!/usr/bin/env python3
"""HL-2915/HL-1910 慢速摆动演示——肉眼看轴到底转不转。

用法:先看一眼输出轴(建议装上摇臂或在轴上做个标记),然后:
    ftbench-venv/bin/python hl2915_demo.py          # 默认 ID 1
    ftbench-venv/bin/python hl2915_demo.py --id 2
它会:读电压 → 扭矩开 → 以慢速在 ±90°(±1024 步)间摆动 3 个来回 → 扭矩关。
全程打印目标与实际位置;结束时告诉你"轴动了 / 轴没动"的判读方法。
"""
import argparse
import serial
import time

REG_GOAL, REG_TORQUE, REG_POS, REG_VOLT = 42, 40, 56, 62

def packet(sid, instr, params=b""):
    body = bytes([sid, len(params) + 2, instr]) + params
    return b"\xff\xff" + body + bytes([(~sum(body)) & 0xFF])

class Bus:
    def __init__(self, port, baud=1000000):
        self.s = serial.Serial(port, baud, bytesize=8, parity="N", stopbits=1, timeout=0.1)
    def read(self, addr, length, sid=1):
        self.s.reset_input_buffer()
        self.s.write(packet(sid, 0x02, bytes([addr, length])))
        time.sleep(0.05)
        rx = self.s.read(64); i = 0
        while i + 6 <= len(rx):
            if rx[i] == 0xFF and rx[i+1] == 0xFF:
                ln = rx[i+3]; tot = 4 + ln
                if i + tot > len(rx): return None
                if ((~sum(rx[i+2:i+tot-1])) & 0xFF) == rx[i+tot-1]:
                    return rx[i+5:i+tot-1]
            i += 1
        return None
    def write(self, addr, data, sid=1):
        self.s.reset_input_buffer()
        self.s.write(packet(sid, 0x03, bytes([addr]) + bytes(data)))
        time.sleep(0.05); self.s.read(32)
    def pos(self, sid=1):
        d = self.read(REG_POS, 2)
        return (d[0] | (d[1] << 8)) if d and len(d) == 2 else None

def find_port():
    import glob
    ports = sorted(glob.glob("/dev/tty.usb*"))
    if not ports:
        raise SystemExit("没找到 USB 串口——URT2 插好了吗?")
    print(f"串口:{ports[0]}")
    return ports[0]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", type=int, default=1)
    ap.add_argument("--port")
    a = ap.parse_args()
    bus = Bus(a.port or find_port())
    v = bus.read(REG_VOLT, 1)
    volt = v[0] / 10 if v else None
    print(f"供电电压:{volt}V" if volt is not None else "读电压失败")
    if volt is not None and volt < 9 and volt > 4:
        print("⚠ 电压 <9V:HL-2915 需 9–14V(HL-1910 需 4–8.4V)。电压不足时电机不会真正转动,只有计数变化!")
    start = bus.pos(a.id)
    print(f"起始位置:{start}")
    print("\n>>> 现在盯着输出轴!3 秒后开始慢速摆动 ±90°,共 3 个来回 <<<\n")
    time.sleep(3)
    bus.write(REG_TORQUE, [1], a.id)
    targets = [start + 1024, start, start - 1024, start, start + 1024, start]
    for tgt in targets:
        print(f"目标 {tgt}({(tgt-start)*0.088:+.0f}°):", end=" ", flush=True)
        bus.write(REG_GOAL, [tgt & 0xFF, (tgt >> 8) & 0xFF], a.id)
        for _ in range(8):
            time.sleep(0.35)
            print(bus.pos(a.id), end=" ", flush=True)
        print()
    bus.write(REG_TORQUE, [0], a.id)
    print("\n扭矩已关。判读:")
    print("- 亲眼看到轴来回摆 ±90° → 舵机正常,之前只是动作小/快没看清")
    print("- 轴完全没动,但屏幕上的位置在跟 → 编码器在转、输出轴没转 = 磁环/输出耦合脱开(坏件)")
    print("- 位置也不跟 → 驱动/通信问题,把本输出截图发回")
    bus.s.close()

if __name__ == "__main__":
    main()
