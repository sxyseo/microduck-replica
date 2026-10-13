#!/usr/bin/env python3
# 总线信号完整性诊断：空闲电平 / 完整响应捕获 / 多次重试
import serial, time, sys

port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyS2"
ser = serial.Serial(port, 1000000, timeout=0.05)

def frame(pid, inst, params=b""):
    body = bytes([pid, len(params) + 2, inst, *params])
    return b"\xff\xff" + body + bytes([(~sum(body)) & 0xFF])

def capture(ms):
    ser.reset_input_buffer()
    buf = b""
    end = time.time() + ms / 1000
    while time.time() < end:
        n = ser.in_waiting
        if n:
            buf += ser.read(n)
        else:
            time.sleep(0.002)
    return buf

print("== 1. 空闲电平（不发任何东西，收 300ms）==")
idle = capture(300)
print(f"   {len(idle)} bytes: {idle[:24].hex()}")

print("== 2. PING 后完整捕获 300ms ==")
for i in range(3):
    ser.reset_input_buffer()
    ser.write(frame(1, 1))
    ser.flush()
    cap = capture(300)
    print(f"   #{i}: {len(cap)} bytes: {cap[:32].hex()}")

print("== 3. 读电压(62) 完整捕获 300ms ==")
for i in range(2):
    ser.reset_input_buffer()
    ser.write(frame(1, 2, bytes([62, 1])))
    ser.flush()
    cap = capture(300)
    print(f"   #{i}: {len(cap)} bytes: {cap[:32].hex()}")

ser.close()
