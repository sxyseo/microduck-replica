#include "crc16.h"

static uint16_t build_entry(uint16_t i) {
    uint16_t crc = (uint16_t)(i << 8);
    for (int j = 0; j < 8; j++)
        crc = (crc & 0x8000) ? (uint16_t)((crc << 1) ^ 0x1021) : (uint16_t)(crc << 1);
    return crc;
}

void dxl_crc_init_table(uint16_t table[256]) {
    for (uint16_t i = 0; i < 256; i++) table[i] = build_entry(i);
}

uint16_t dxl_crc_update(uint16_t table[256], uint16_t accum,
                        const uint8_t *data, size_t len) {
    for (size_t j = 0; j < len; j++) {
        uint16_t i = (uint16_t)(((accum >> 8) ^ data[j]) & 0xFF);
        accum = (uint16_t)((accum << 8) ^ table[i]);
    }
    return accum;
}
