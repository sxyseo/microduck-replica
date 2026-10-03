// test_feetech.c — 飞特协议层主机测试（不依赖任何硬件）
// 编译运行：
//   cd docs/imu_to_dxl-设计包/firmware
//   cc -Wall -Wextra -Isrc src/feetech_slave.c test/test_feetech.c -o /tmp/ft_test && /tmp/ft_test
//
// 帧构造与断言对齐 hl2915_bench.py 的 packet()/parse()（已对 HL-2915 真机验证），
// 以及换舵机后主机侧 rustypot 飞特模块的读法（READ 0x02 [addr, len]）。
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../src/feetech_slave.h"

static uint8_t last_tx[64];
static uint16_t last_tx_n;

static void fake_send(const uint8_t *b, uint16_t n) {
    memcpy(last_tx, b, n);
    last_tx_n = n;
}

static void feed_frame(feetech_slave_t *s, const uint8_t *f, uint16_t n) {
    for (uint16_t i = 0; i < n; i++) feetech_slave_feed(s, f[i]);
}

// 构造飞特指令帧：FF FF [ID] [LEN] [INST] [PARAMS..] [~SUM]
static uint16_t build_cmd(uint8_t id, uint8_t inst,
                          const uint8_t *params, uint16_t n_params,
                          uint8_t out[64]) {
    uint8_t len = (uint8_t)(n_params + 2);     // INST + PARAMS + CHK
    uint16_t k = 0;
    out[k++] = 0xFF; out[k++] = 0xFF; out[k++] = id; out[k++] = len; out[k++] = inst;
    memcpy(&out[k], params, n_params); k = (uint16_t)(k + n_params);
    uint16_t sum = (uint16_t)id + len + inst;
    for (uint16_t i = 0; i < n_params; i++) sum += params[i];
    out[k++] = (uint8_t)((~sum) & 0xFF);
    return k;
}

// 应答包自校验：用 FF FF ID LEN ERR PARAMS 重建 ~SUM 应等于包内 CHK
static void assert_status_chk(void) {
    uint16_t sum = (uint16_t)last_tx[2] + last_tx[3] + last_tx[4];
    for (uint16_t i = 5; i < (uint16_t)(last_tx_n - 1); i++) sum += last_tx[i];
    assert(last_tx[last_tx_n - 1] == (uint8_t)((~sum) & 0xFF));
}

int main(void) {
    feetech_slave_t s;
    feetech_slave_init(&s, 200, fake_send);

    // 预填 IMU 块
    for (int i = 0; i < 12; i++) s.reg[FT_REG_IMU_BLOCK + i] = (uint8_t)(0xA0 + i);

    uint8_t f[64];

    // 1) PING → 6 字节：FF FF C8 02 00 CHK
    uint16_t n = build_cmd(200, FEETECH_INST_PING, NULL, 0, f);
    last_tx_n = 0;
    feed_frame(&s, f, n);
    assert(last_tx_n == 6);
    assert(last_tx[2] == 200 && last_tx[3] == 2 && last_tx[4] == 0);
    assert_status_chk();
    printf("PING            OK (%u 字节)\n", last_tx_n);

    // 2) READ 124, 12 → 18 字节：FF FF C8 0E 00 + 12B + CHK（rustypot 读 IMU 块的路径）
    uint8_t rd[2] = { FT_REG_IMU_BLOCK, 12 };
    n = build_cmd(200, FEETECH_INST_READ, rd, 2, f);
    last_tx_n = 0;
    feed_frame(&s, f, n);
    assert(last_tx_n == 6 + 12);
    assert(memcmp(&last_tx[5], &s.reg[FT_REG_IMU_BLOCK], 12) == 0);
    assert_status_chk();
    printf("READ 124/12     OK\n");

    // 3) 广播 SYNC_READ(0x82)，ID 列表含 200（总线 15 舵机 + 本板一次问）
    uint8_t sr[2 + 3] = { FT_REG_IMU_BLOCK, 12, 1, 200, 15 };
    n = build_cmd(FEETECH_BROADCAST_ID, FEETECH_INST_SYNC_READ, sr, 5, f);
    last_tx_n = 0;
    feed_frame(&s, f, n);
    assert(last_tx_n == 6 + 12);
    assert(memcmp(&last_tx[5], &s.reg[FT_REG_IMU_BLOCK], 12) == 0);
    printf("SYNC_READ       OK\n");

    // 4) 广播 SYNC_READ 但列表不含 200 → 沉默（否则抢线）
    uint8_t sr2[2 + 2] = { FT_REG_IMU_BLOCK, 12, 1, 15 };
    n = build_cmd(FEETECH_BROADCAST_ID, FEETECH_INST_SYNC_READ, sr2, 4, f);
    last_tx_n = 0;
    feed_frame(&s, f, n);
    assert(last_tx_n == 0);
    printf("SYNC_READ 无我   OK（沉默）\n");

    // 5) 校验错 → 沉默；随后同帧重发必须恢复正常（状态机正确复位）
    n = build_cmd(200, FEETECH_INST_PING, NULL, 0, f);
    f[n - 1] ^= 0xFF;
    last_tx_n = 0;
    feed_frame(&s, f, n);
    assert(last_tx_n == 0);
    n = build_cmd(200, FEETECH_INST_PING, NULL, 0, f);
    feed_frame(&s, f, n);
    assert(last_tx_n == 6);
    printf("校验错沉默+复位  OK\n");

    // 6) WRITE(0x03) 等未知指令 → 沉默（本板只读）
    uint8_t wr[3] = { 42, 0x10, 0x00 };
    n = build_cmd(200, 0x03, wr, 3, f);
    last_tx_n = 0;
    feed_frame(&s, f, n);
    assert(last_tx_n == 0);
    printf("WRITE 沉默       OK\n");

    // 7) 非本板 ID → 沉默
    n = build_cmd(15, FEETECH_INST_PING, NULL, 0, f);
    last_tx_n = 0;
    feed_frame(&s, f, n);
    assert(last_tx_n == 0);
    printf("非本板 ID 沉默   OK\n");

    // 8) 出界读（addr+len > 160）→ 沉默，且状态机仍能处理后续帧
    uint8_t bad[2] = { 150, 20 };
    n = build_cmd(200, FEETECH_INST_READ, bad, 2, f);
    last_tx_n = 0;
    feed_frame(&s, f, n);
    assert(last_tx_n == 0);
    n = build_cmd(200, FEETECH_INST_PING, NULL, 0, f);
    feed_frame(&s, f, n);
    assert(last_tx_n == 6);
    printf("出界读沉默+复位  OK\n");

    // 9) 参数含 0xFF 字节不破坏成帧（LEN 计数推进，不靠扫描包头）
    uint8_t sr3[2 + 3] = { FT_REG_IMU_BLOCK, 12, 0xFF, 200, 0xFF };
    n = build_cmd(FEETECH_BROADCAST_ID, FEETECH_INST_SYNC_READ, sr3, 5, f);
    last_tx_n = 0;
    feed_frame(&s, f, n);
    assert(last_tx_n == 6 + 12);
    printf("参数含 FF 成帧   OK\n");

    // 10) 半包：前半帧悬着，再喂完整帧 → 正常应答（字节流里半包是常态）
    uint8_t rd2[2] = { FT_REG_IMU_BLOCK, 12 };
    n = build_cmd(200, FEETECH_INST_READ, rd2, 2, f);
    last_tx_n = 0;
    for (uint16_t i = 0; i < n / 2; i++) feetech_slave_feed(&s, f[i]);
    assert(last_tx_n == 0);
    for (uint16_t i = n / 2; i < n; i++) feetech_slave_feed(&s, f[i]);
    assert(last_tx_n == 6 + 12);
    printf("半包续收        OK\n");

    printf("\n全部通过 ✅\n");
    return 0;
}
