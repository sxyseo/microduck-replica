// test_protocol.c — 协议层主机测试（不依赖任何硬件）
// 编译运行：
//   cd docs/imu_to_dxl-设计包/firmware
//   cc -Wall -Wextra -Isrc src/crc16.c src/dxl_slave.c test/test_protocol.c -o /tmp/dxl_test && /tmp/dxl_test
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../src/crc16.h"
#include "../src/dxl_slave.h"

static uint16_t T[256];
static uint8_t last_tx[64];
static uint16_t last_tx_n;

static void fake_send(const uint8_t *b, uint16_t n) {
    memcpy(last_tx, b, n);
    last_tx_n = n;
}

static void feed_frame(dxl_slave_t *s, const uint8_t *f, uint16_t n) {
    for (uint16_t i = 0; i < n; i++) dxl_slave_feed(s, f[i]);
}

// 构造主机指令帧（对齐 rustypot/主仓发出的格式）
static uint16_t build_cmd(uint8_t id, uint8_t inst,
                          const uint8_t *params, uint16_t n_params,
                          uint8_t out[64]) {
    uint16_t len = (uint16_t)(n_params + 1);
    uint16_t k = 0;
    out[k++] = 0xFF; out[k++] = 0xFF; out[k++] = 0xFD; out[k++] = 0x00;
    out[k++] = id;
    out[k++] = (uint8_t)(len & 0xFF); out[k++] = (uint8_t)(len >> 8);
    out[k++] = inst;
    memcpy(&out[k], params, n_params); k = (uint16_t)(k + n_params);
    // CRC 覆盖 ID..PARAMS：ID(1) + LEN(2) + INST+PARAMS(len)
    uint16_t crc = dxl_crc_update(T, 0, &out[4], (size_t)(1 + 2 + len));
    out[k++] = (uint8_t)(crc & 0xFF); out[k++] = (uint8_t)(crc >> 8);
    return k;
}

int main(void) {
    dxl_crc_init_table(T);
    dxl_slave_t s;
    dxl_slave_init(&s, 200, fake_send);

    // 预填 IMU 块
    for (int i = 0; i < 12; i++) s.reg[DXL_REG_IMU_BLOCK + i] = (uint8_t)(0xA0 + i);

    uint8_t f[64];

    // 1) PING → 应答 11 字节：FF FF FD 00 C8 02 00 55 00 CRC(2)
    uint16_t n = build_cmd(200, DXL_INST_PING, NULL, 0, f);
    last_tx_n = 0;
    feed_frame(&s, f, n);
    assert(last_tx_n == 11);
    assert(last_tx[4] == 200 && last_tx[7] == DXL_INST_STATUS && last_tx[8] == 0);
    printf("PING            OK (%u bytes)\n", last_tx_n);

    // 2) READ 124, 12 → 参数 12 字节等于预填块（状态包 11 + 12 = 23 字节）
    uint8_t rd[4] = { 124, 0, 12, 0 };
    n = build_cmd(200, DXL_INST_READ, rd, 4, f);
    last_tx_n = 0;
    feed_frame(&s, f, n);
    assert(last_tx_n == 11 + 12);
    assert(memcmp(&last_tx[9], &s.reg[124], 12) == 0);
    printf("READ 124/12     OK\n");

    // 3) SYNC_READ，id 列表里含 200（对齐 bus.rs：15 舵机 + IMU 一次读）
    uint8_t sr[4 + 3] = { 124, 0, 12, 0, 1, 200, 15 };
    n = build_cmd(0xFE, DXL_INST_SYNC_READ, sr, 7, f);
    last_tx_n = 0;
    feed_frame(&s, f, n);
    assert(last_tx_n == 11 + 12);
    printf("SYNC_READ       OK\n");

    // 4) 广播 sync_read 但列表不含 200 → 必须沉默（否则抢线）
    uint8_t sr2[4 + 2] = { 124, 0, 12, 0, 1, 15 };
    n = build_cmd(0xFE, DXL_INST_SYNC_READ, sr2, 6, f);
    last_tx_n = 0;
    feed_frame(&s, f, n);
    assert(last_tx_n == 0);
    printf("SYNC_READ 无我   OK（沉默）\n");

    // 5) CRC 错误 → 沉默
    n = build_cmd(200, DXL_INST_PING, NULL, 0, f);
    f[n - 1] ^= 0xFF;
    last_tx_n = 0;
    feed_frame(&s, f, n);
    assert(last_tx_n == 0);
    printf("CRC 错误沉默     OK\n");

    // 6) 应答 CRC 自校验：用状态包重建 CRC 应等于包内 CRC
    uint8_t rd2[4] = { 124, 0, 12, 0 };
    n = build_cmd(200, DXL_INST_READ, rd2, 4, f);
    last_tx_n = 0;
    feed_frame(&s, f, n);
    uint16_t crc_expect = dxl_crc_update(T, 0, &last_tx[4], (size_t)(last_tx_n - 6));
    assert(last_tx[last_tx_n - 2] == (uint8_t)(crc_expect & 0xFF));
    assert(last_tx[last_tx_n - 1] == (uint8_t)(crc_expect >> 8));
    printf("应答 CRC 自洽    OK\n");

    printf("\n全部通过 ✅\n");
    return 0;
}
