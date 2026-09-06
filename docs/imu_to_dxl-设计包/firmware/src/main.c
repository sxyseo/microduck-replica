// main.c — STM32G031F8P6 固件主骨架（HAL 风格，外设初始化为 TODO 骨架）
//
// 职责（全部来自已验证的主机侧预期，见 设计规格.md）：
//   I2C1 400kHz 读 LSM6DSV16X → 填 124 号块（20B）
//   USART1 1Mbps 半双工 → dxl_slave_feed() → 应答
// 目标循环节奏：IMU 采样 ≥200Hz；UART 字节级中断喂协议层。
#include "stm32g0xx_hal.h"
#include "dxl_slave.h"
#include "imu_lsm6dsv16x.h"

static dxl_slave_t g_slave;
static uint16_t g_crc_table[256];   // dxl_slave 内部表为主；此处仅示意

// ---- 平台钩子：应答上总线 -------------------------------------------------
// 半双工方向：若采用 SN74LVC1G126 缓冲方案，先拉高 OE（PA8）再发送，发完拉低。
// 若用 STM32 原生 HDSEL 单线模式，则无需方向控制。
static void bus_send(const uint8_t *bytes, uint16_t n) {
    // TODO(HAL): HAL_UART_Transmit(&huart1, bytes, n, 5);  // 22B@1Mbps≈0.25ms，超时给 5ms 冗余
    (void)bytes; (void)n;
}

// ---- UART RX：字节到一个喂一个 -------------------------------------------
void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart) {
    static uint8_t b;
    (void)huart;
    dxl_slave_feed(&g_slave, b);
    // TODO(HAL): HAL_UART_Receive_IT(&huart1, &b, 1);  // 重新挂接收中断
}

int main(void) {
    // TODO(HAL): HAL_Init(); SystemClock_Config();      // HSI16 默认即可
    //            MX_I2C1_Init();                        // 400kHz
    //            MX_USART1_UART_Init();                 // 1_000_000 8N1，TX=PA9 RX=PA10
    //            HAL_UART_Receive_IT(&huart1, &rx_byte, 1);

    dxl_slave_init(&g_slave, 200, bus_send);           // ID 200 = model.rs L78

    if (!lsm_init()) {
        // WHO_AM_I 不符：慢闪 LED 报错，且 124 块全零（主机端会拒绝异常四元数）
        // TODO(HAL): while(1) { LED 异常闪烁 }
    }

    uint32_t next_sample = 0;
    for (;;) {
        uint32_t now = HAL_GetTick();
        if ((int32_t)(now - next_sample) >= 0) {       // 5ms → 200Hz
            next_sample = now + 5;
            lsm_sample_into(&g_slave.reg[DXL_REG_IMU_BLOCK]);
        }
    }
}
