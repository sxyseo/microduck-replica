#!/usr/bin/env python3
# REBOOT 清锁 + PING 判定 —— 零响应≠坏，先清锁再下结论（仓库自己的流程）
import serial, time, sys

port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyS2"
ids = [int(x) for x in (sys.argv[2].split(",") if len(sys.argv) > 2 else ["13", "22"])]
ser = serial.Serial(port, 1000000, timeout=0.05)

def frame(pid, inst, params=b""):
    body = bytes([pid, len(params) + 2, inst, *params])
    return b"\xff\xff" + body + bytes([(~sum(body)) & 0xFF])

def ping(pid):
    ser.reset_input_buffer()
    ser.write(frame(pid, 1))
    ser.flush()
    time.sleep(0.03)
    n = ser.in_waiting
    return ser.read(n) if n else b""

for pid in ids:
    ser.reset_input_buffer()
    ser.write(frame(pid, 8))  # REBOOT (0x08) —— 清锁，不写任何寄存器
    ser.flush()
    print(f"REBOOT -> {pid}，等待重启…")
    time.sleep(0.5)
    for i in range(4):
        r = ping(pid)
        ok = bytes([0xFF, 0xFF, pid]) in r
        print(f"  PING#{i}: {len(r)}B {r.hex()[:24]} {'✓应答' if ok else ''}")
        if ok:
            break
        time.sleep(0.2)
ser.close()
