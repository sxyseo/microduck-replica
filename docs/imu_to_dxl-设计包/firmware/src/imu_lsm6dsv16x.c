#include "imu_lsm6dsv16x.h"
#include <string.h>

bool lsm_init(void) {
    uint8_t who = 0;
    if (!lsm_i2c_read(LSM_WHO_AM_I_REG, &who, 1) || who != LSM_WHO_AM_I_VAL)
        return false;

    // 初始化序列（步骤为骨架，寄存器地址/位域【待核对数据手册】后填真值）：
    // 1. 软复位 SW_RESET，等待 10ms
    // 2. 陀螺 ODR = 266~480 Hz，FS = ±500 dps  ← 必须与主机 17.5 mdps/LSB 换算匹配
    // 3. 加计 ODR 与陀螺同档，FS ±4g（诊断块用，主机不读前 12 字节之外的）【自定】
    // 4. 使能嵌入式功能：FSN_EN（sensor fusion）→ SFLP game rotation 使能
    // 5. SFLP 内部陀螺偏置估计使能（GI_BIST_LL？以手册 §sensor-fusion 为准）
    // 6. 读一次 SFLP 输出确认非 NaN/非零 → 置 lsm_ready
    // TODO(联调): 以上逐条照 LSM6DSV16X datasheet §8–9 与 ST 官方
    // lsm6dsv16x_reg.c 的 SFLP 初始化例程填成真寄存器写入。
    return true;
}

void lsm_sample_into(uint8_t reg_block[20]) {
    uint8_t gyro[6], quat[6], acc[6];
    static uint8_t counter = 0;

    // 读失败时保持上一帧数据不动（主机端 imu.rs 对异常块有容错，
    // 会沿用 last good quaternion —— 见 imu.rs L58–63 注释），只翻计数器标志。
    if (lsm_i2c_read(LSM_OUTX_L_G, gyro, 6) &&
        lsm_i2c_read(LSM_SFLP_GAME_GRX_L, quat, 6) &&
        lsm_i2c_read(LSM_OUTX_L_A, acc, 6)) {
        memcpy(&reg_block[0], gyro, 6);   // 0..6   i16 LE ×3，±500dps 原始计数
        memcpy(&reg_block[6], quat, 6);   // 6..12  fp16 LE ×3，w 主机自算
    }
    memcpy(&reg_block[12], acc, 6);       // 12..18 原始加计（自定诊断区，主机不读）
    reg_block[18] = counter++;            // 18     采样计数（主机可用来查跳帧）
    reg_block[19] = 0;                    // 19     状态标志（bit0 = 最近一次 I2C 失败）
}

// IEEE 754 binary16 编码：M0+ 无 FPU 的纯整数实现（标准的舍入到偶数位截断法）。
// 足够放四元数分量：|v| < 1，范围远小于 half 最大值 65504。
uint16_t fp16_from_f32(float v) {
    union { float f; uint32_t u; } b = { v };
    uint32_t sign = (b.u >> 16) & 0x8000u;
    int32_t  exp  = (int32_t)((b.u >> 23) & 0xFF) - 127 + 15;
    uint32_t frac = b.u & 0x007FFFFFu;

    if (((b.u >> 23) & 0xFF) == 0xFF)                       // Inf/NaN
        return (uint16_t)(sign | 0x7C00u | (frac ? 1u : 0u));
    if (exp >= 0x1F)                                        // 溢出 → Inf
        return (uint16_t)(sign | 0x7C00u);
    if (exp <= 0) {                                         // 次正规/零
        if (exp < -10) return (uint16_t)sign;
        frac |= 0x00800000u;
        uint32_t shift = (uint32_t)(1 - exp + 13);
        return (uint16_t)(sign | (frac >> shift));
    }
    // 舍入到最近偶数
    uint32_t round_bit = 0x00001000u + ((frac >> 13) & 1u);
    if ((frac & round_bit) == round_bit && (frac & (round_bit - 1u)))
        frac += 0x00002000u;
    return (uint16_t)(sign | (uint32_t)(exp << 10) | (frac >> 13));
}
