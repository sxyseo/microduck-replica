// feetech_slave.h — 飞特 SCS/HLS 协议从机（协议层，纯 C99，无硬件依赖）
//
// 换舵机路线（飞特 HL 系列）下总线统一飞特协议，本板不再说 Dynamixel V2：
// 主机侧走 rustypot 飞特模块（换舵机重训全流程.md §3），本板行为在协议上与 HL 舵机同构，
// 寄存器契约保持与 dxl_slave.h 完全一致 —— 换的只是线上帧格式（"双协议设计已备"）。
//
// 帧格式（与 rl-series/scripts/hl2915_bench.py 的 packet()/parse()/sync_read() 位级一致，
// 该脚本已对 HL-2915 真机验证）：
//   指令：FF FF [ID] [LEN] [INST] [PARAMS..] [~SUM]   LEN = INST+PARAMS+CHK 的字节数
//   应答：FF FF [ID] [LEN] [ERR] [PARAMS..] [~SUM]    同上，ERR 占 1 字节
//   ~SUM = (~(ID+LEN+ERR/INST+PARAMS 各字节)) & 0xFF，覆盖 ID..最后一个 PARAM
//
// 支持的指令（只读板，够总线联调用）：
//   PING      0x01  无参数 → ERR=0 空应答
//   READ      0x02  参数 [addr, len]（各 1 字节）→ 应答 len 字节寄存器
//   SYNC_READ 0x82  广播 0xFE，参数 [addr, len, ID 列表...]，列表含本板则独立应答
//
// 一律沉默的情形（总线安全优先，主机以超时判错）：
//   非本板帧 / 校验错 / 未知指令（含 WRITE —— 本板只读）/ 出界读 / 半包
#ifndef FEETECH_SLAVE_H
#define FEETECH_SLAVE_H
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>

#define FEETECH_INST_PING       0x01
#define FEETECH_INST_READ       0x02
#define FEETECH_INST_SYNC_READ  0x82
#define FEETECH_BROADCAST_ID    0xFE

// 寄存器契约与 dxl_slave.h 相同（主机读 124 取 12 字节：0..6 陀螺 i16 LE，6..12 SFLP 四元数 fp16）
#define FT_REG_MODEL        0    // u16 LE，自定 200
#define FT_REG_FIRMWARE     6
#define FT_REG_ID           7
#define FT_REG_BAUD_INDEX   8    // 只读，固定 0（飞特索引：0 = 1 Mbps）
#define FT_REG_IMU_BLOCK    124  // 本板自定义块起点
#define FT_IMU_BLOCK_SIZE   20   // 12B 有效 + 8B 自定诊断（主机只读前 12）
#define FT_REG_SIZE         160

typedef struct {
    uint8_t  id;
    uint8_t  reg[FT_REG_SIZE];
    // 平台钩子：把应答字节推上总线（UART 阻塞发送即可，18 字节 @1Mbps ≈ 180 µs）
    void (*send)(const uint8_t *bytes, uint16_t n);
} feetech_slave_t;

typedef enum {
    FT_RX_INCOMPLETE = 0,   // 帧未收完，继续喂
    FT_RX_IGNORED,          // 不是给本板的帧（其他从机或广播读），保持沉默
    FT_RX_REPLIED,          // 帧结束（是否真的应答由帧内容决定；校验错等沉默情形也返回此值）
} ft_rx_result_t;

void     feetech_slave_init(feetech_slave_t *s, uint8_t id,
                            void (*send)(const uint8_t *, uint16_t));
// 喂一个收到的字节；返回是否产生了应答。
ft_rx_result_t feetech_slave_feed(feetech_slave_t *s, uint8_t byte);
// 构造应答包到 out，返回总长（= 6 + n_params）。
uint16_t feetech_build_status(const feetech_slave_t *s,
                              uint8_t err, const uint8_t *params, uint16_t n_params,
                              uint8_t out[]);

#endif
