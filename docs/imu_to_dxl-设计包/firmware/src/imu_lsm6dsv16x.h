// imu_lsm6dsv16x.h — IMU 采样与打包（STM32 侧骨架）
//
// 数据格式必须逐字节对齐主机解码器 duck-control/src/imu.rs：
//   陀螺  = i16 LE 原始计数，量程必须配 ±500 dps（主机按 17.5 mdps/LSB 换算，imu.rs L47–48）
//   四元数 = SFLP game-rotation 的 x/y/z，IEEE fp16 LE；w 由主机自己算（imu.rs L13, L124）
#ifndef LSM6DSV16X_H
#define LSM6DSV16X_H
#include <stdint.h>
#include <stdbool.h>

#define LSM_I2C_ADDR        0x6A    // SA0 接 GND；接 VDDIO 则 0x6B
#define LSM_WHO_AM_I_REG    0x5F
#define LSM_WHO_AM_I_VAL    0x70    // 【待核对】上电读一次，不符即报警
#define LSM_OUTX_L_G        0x22    // 陀螺 6 字节突发读（LSM6 家族通用）
#define LSM_OUTX_L_A        0x28    // 加计 6 字节突发读
#define LSM_SFLP_GAME_GRX_L 0x17    // SFLP game rotation x/y/z fp16 ×3
                                    // 【待核对】地址以数据手册为准（ST 驱动
                                    // lsm6dsv16x_reg.c 同名寄存器可对照）

// 平台钩子：I2C 突发读（HAL_I2C_Mem_Read 封装），返回 false = 总线异常
bool lsm_i2c_read(uint8_t reg, uint8_t *buf, uint16_t n);

// 初始化：返回 false = WHO_AM_I 不符
// 【待核对】各 CTRL 寄存器地址/位域以数据手册核对后填入 lsm6dsv16x.c
bool lsm_init(void);

// 采样一次并写入 20 字节寄存器块（DXL_REG_IMU_BLOCK 布局）
void lsm_sample_into(uint8_t reg_block[20]);

// f32 → IEEE binary16 位模式（M0+ 无 FPU，纯整数位操作）
uint16_t fp16_from_f32(float v);

#endif
