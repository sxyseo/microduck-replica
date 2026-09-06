// crc16.h — Dynamixel Protocol 2.0 CRC-16
// 与 ROBOTIS dynamixel_sdk protocol2_packet_handler.c 的 dxl_crc 逐位一致：
// 多项式 0x1021、初值 0、无反射、无异或输出。
#ifndef DXL_CRC16_H
#define DXL_CRC16_H
#include <stdint.h>
#include <stddef.h>

void dxl_crc_init_table(uint16_t table[256]);
uint16_t dxl_crc_update(uint16_t table[256], uint16_t accum,
                        const uint8_t *data, size_t len);

#endif
