#!/usr/bin/env python3
# 原始字节级 PING 诊断 —— 区分"零字节（无电/断线）"与"乱码（冲突/电平）"
import serial, time, sys

port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyS2"
ser = serial.Serial(port, 1000000, timeout=0.05)

def frame(pid, inst, params=b""):
    body = bytes([pid, len(params) + 2, inst, *params])
    return b"\xff\xff" + body + bytes([(~sum(body)) & 0xFF])

for attempt in range(3):
    ser.reset_input_buffer()
    ser.write(frame(1, 1))
    ser.flush()
    time.sleep(0.03)
    n = ser.in_waiting
    raw = ser.read(n) if n else b""
    print(f"PING id1 #{attempt}: {n} bytes: {raw.hex() if raw else '(zero bytes)'}")
    time.sleep(0.05)

ser.reset_input_buffer()
ser.write(frame(254, 1))
ser.flush()
time.sleep(0.05)
n = ser.in_waiting
raw = ser.read(n) if n else b""
print(f"broadcast 254: {n} bytes: {raw.hex() if raw else '(zero bytes)'}")

# 顺带读一次电压寄存器（地址 62，1 字节）——若有应答，看总线电压
ser.reset_input_buffer()
ser.write(frame(1, 2, bytes([62, 1])))
ser.flush()
time.sleep(0.03)
n = ser.in_waiting
raw = ser.read(n) if n else b""
print(f"read 62 @id1: {n} bytes: {raw.hex() if raw else '(zero bytes)'}")
ser.close()
