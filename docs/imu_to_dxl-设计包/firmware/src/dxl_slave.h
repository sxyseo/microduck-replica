// dxl_slave.h — Dynamixel Protocol 2.0 从机（协议层，纯 C99，无硬件依赖）
//
// 目标行为对齐上游主机 duck-control/src/bus.rs 的真实预期：
//   - 总线 ID 200（model.rs L78 IMU_DXL_ID），1 Mbps 8N1 半双工 TTL（L80）
//   - 主机每 tick 一次 sync_read，覆盖 15 个舵机 + 本板（bus.rs L3, L115）
//   - 读地址 124、长度 12（bus.rs L27–28 READ_ADDR/READ_LEN）
//   - 主机整体超时 30 ms（bus.rs L49 READ_TIMEOUT）
//   - 应答字节块：0..6 陀螺 i16 LE（±500 dps 原始计数），6..12 SFLP 四元数 fp16（imu.rs L8–13）
#ifndef DXL_SLAVE_H
#define DXL_SLAVE_H
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>

#define DXL_INST_PING       0x01
#define DXL_INST_READ       0x02
#define DXL_INST_SYNC_READ  0x82
#define DXL_INST_STATUS     0x55
#define DXL_ERR_INSTRUCTION 0x40

#define DXL_REG_MODEL       0    // u16 LE，自定 200
#define DXL_REG_FIRMWARE    6
#define DXL_REG_ID          7
#define DXL_REG_BAUD_INDEX  8    // 只读，固定 3（= 1 Mbps，X 系索引）
#define DXL_REG_RETURN_DELAY 9   // 单位 2 µs，默认 125 → 250 µs
#define DXL_REG_STATUS_LEVEL 20
#define DXL_REG_IMU_BLOCK   124  // 本板自定义块起点
#define DXL_IMU_BLOCK_SIZE  20   // 12B 有效 + 8B 自定诊断（主机只读前 12）
#define DXL_REG_SIZE        160

typedef struct {
    uint8_t  id;
    uint8_t  reg[DXL_REG_SIZE];
    // 平台钩子：把应答字节推上总线（UART 阻塞发送即可，22 字节 @1Mbps ≈ 220 µs）
    void (*send)(const uint8_t *bytes, uint16_t n);
} dxl_slave_t;

typedef enum {
    DXL_RX_INCOMPLETE = 0,   // 帧未收完，继续喂
    DXL_RX_IGNORED,          // 不是给本板的帧（其他从机或广播读），保持沉默
    DXL_RX_REPLIED,          // 已产生应答（经 send 钩子发出）
} dxl_rx_result_t;

void     dxl_slave_init(dxl_slave_t *s, uint8_t id,
                        void (*send)(const uint8_t *, uint16_t));
// 喂一个收到的字节；返回是否产生了应答。
dxl_rx_result_t dxl_slave_feed(dxl_slave_t *s, uint8_t byte);
// 构造状态包到 out，返回总长（= 10 + n_params）。
uint16_t dxl_build_status(dxl_slave_t *s, uint16_t crc_table[256],
                          uint8_t err, const uint8_t *params, uint16_t n_params,
                          uint8_t out[]);

#endif
