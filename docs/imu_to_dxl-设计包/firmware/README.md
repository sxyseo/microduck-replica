# firmware/ — `imu_to_dxl` 固件

> **协议层已完成并通过主机测试**（纯 C99，无硬件依赖）；
> STM32 外设层（I2C/UART 初始化）与 IMU 寄存器序列为骨架，标注了 TODO/待核对。
>
> **双协议设计（2026-10-04）**：换舵机路线（飞特 HL 系列）下总线统一飞特协议，
> `main.c` 以 `IMU_PROTO` 编译开关切换 DXL / 飞特从机 —— 两种模式共用同一寄存器契约
> （ID 200 / 124 号块 12 字节），只换线上帧格式。飞特帧格式与
> `rl-series/scripts/hl2915_bench.py` 的 `packet()/parse()/sync_read()` 位级一致（已对 HL-2915 真机验证）。

## 文件

| 文件 | 状态 | 说明 |
|---|---|---|
| `src/crc16.c/.h` | ✅ 完成并测试 | Dynamixel V2 CRC-16，与 dynamixel_sdk 位级一致 |
| `src/dxl_slave.c/.h` | ✅ 完成并测试 | Dynamixel 从机状态机：PING / READ / SYNC_READ；CRC 错与非本板帧正确沉默 |
| `src/feetech_slave.c/.h` | ✅ 完成并测试 | 飞特 SCS/HLS 从机状态机：PING(0x01) / READ(0x02) / SYNC_READ(0x82)；校验错、非本板帧、未知指令（含 WRITE，只读板）、出界读一律沉默 |
| `test/test_protocol.c` | ✅ 6/6 通过 | DXL 主机可跑：`cc -Wall -Isrc src/crc16.c src/dxl_slave.c test/test_protocol.c -o t && ./t` |
| `test/test_feetech.c` | ✅ 10/10 通过 | 飞特主机可跑：`cc -Wall -Isrc src/feetech_slave.c test/test_feetech.c -o t && ./t`（含校验错复位、半包续收、参数含 0xFF 成帧） |
| `src/imu_lsm6dsv16x.c/.h` | 🔶 骨架 | I2C 读 + fp16 编码已写；SFLP/CTRL 初始化序列待对照数据手册填 |
| `src/main.c` | 🔶 骨架 | 主循环结构完整；HAL 外设初始化留 TODO；`IMU_PROTO` 编译开关选 DXL（默认）/ 飞特 |

## 行为对齐（全部有源码出处，见 ../设计规格.md 第二节）

- ID 200 / 1Mbps 8N1 / 读 124 取 12 字节 / 主机超时 30ms
- 陀螺 i16 LE（±500 dps 原始计数）、四元数 fp16 LE（w 主机自算）
- DXL 模式：状态包 23 字节（12 数据时），CRC 覆盖 ID..PARAMS
- 飞特模式：应答 `FF FF ID LEN ERR PARAMS ~SUM`（READ 124/12 时 18 字节），
  与 HL 舵机同构，主机统一用飞特协议栈访问（rustypot 飞特模块）

## 上板步骤（打样回来后）

1. STM32CubeIDE 建 G031 工程（或 platformio `ststm32`），把 `src/` 拷进工程
2. 补 `main.c` 的 HAL 初始化 TODO（I2C1 400k、USART1 1M、RX 中断）
3. 照 datasheet 补 `lsm6dsv16x.c` 初始化 TODO（重点：陀螺 FS ±500 dps 别配错）
4. **按总线协议选 `IMU_PROTO`**：官方 DXL 舵机总线用默认；飞特 HL 总线编译时 `-DIMU_PROTO=1`
5. SWD 烧录 → USB-TTL 单板自测 PING → 上总线联调（验收清单见规格文档第七节）
