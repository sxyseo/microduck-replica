#include "feetech_slave.h"
#include <string.h>

// 接收状态机：FF FF | ID | LEN | INST + PARAMS + CHK（共 LEN 字节，LEN 含 CHK）
// 校验覆盖 ID + LEN + INST + PARAMS（不含包头、不含 CHK 本身）—— 飞特 SCS 定义，
// 与 hl2915_bench.py packet() 的构造方向一致。
typedef enum { ST_H1, ST_H2, ST_ID, ST_LEN, ST_PAYLOAD } st_t;
static st_t s_state = ST_H1;
static uint8_t s_id, s_len;
static uint8_t s_payload[256];
static uint8_t s_payload_n;

static void reset(void) { s_state = ST_H1; }

static void reply_with_block(feetech_slave_t *s, uint8_t err,
                             const uint8_t *params, uint16_t n) {
    uint8_t pkt[FT_IMU_BLOCK_SIZE + 16];
    uint16_t len = feetech_build_status(s, err, params, n, pkt);
    s->send(pkt, len);
}

static void handle_frame(feetech_slave_t *s) {
    if (s_len < 2) { reset(); return; }   // LEN<2 连 INST+CHK 都放不下，n_params 会下溢

    // CHK = ~SUM(ID + LEN + INST + PARAMS)；s_payload 存 INST+PARAMS+CHK 共 LEN 字节
    uint16_t sum = (uint16_t)s_id + s_len;
    for (uint8_t i = 0; i < (uint8_t)(s_len - 1); i++) sum += s_payload[i];
    if (((~sum) & 0xFF) != s_payload[s_len - 1]) { reset(); return; }  // 校验错：沉默

    if (s_id != s->id && s_id != FEETECH_BROADCAST_ID) { reset(); return; }

    uint8_t inst = s_payload[0];
    const uint8_t *params = &s_payload[1];
    uint8_t n_params = (uint8_t)(s_len - 2);   // LEN = INST(1) + PARAMS(n) + CHK(1)

    switch (inst) {
    case FEETECH_INST_PING:
        if (n_params == 0) reply_with_block(s, 0, NULL, 0);
        break;
    case FEETECH_INST_READ: {                  // params: addr(1) + len(1)
        if (n_params != 2) break;
        uint16_t addr = params[0];
        uint16_t rlen = params[1];
        if (rlen == 0 || addr + rlen > FT_REG_SIZE) break;   // 出界读：沉默
        reply_with_block(s, 0, &s->reg[addr], rlen);
        break;
    }
    case FEETECH_INST_SYNC_READ: {             // params: addr(1) + len(1) + ID 列表[...]
        if (n_params < 3) break;
        uint16_t addr = params[0];
        uint16_t rlen = params[1];
        bool mine = false;
        for (uint8_t i = 2; i < n_params; i++)
            if (params[i] == s->id) { mine = true; break; }
        if (!mine) break;                      // 广播列表不含本板：沉默（否则抢线）
        if (rlen == 0 || addr + rlen > FT_REG_SIZE) break;
        reply_with_block(s, 0, &s->reg[addr], rlen);
        break;
    }
    default:
        break;                                 // 只读板：WRITE 等一律沉默
    }
    reset();
}

void feetech_slave_init(feetech_slave_t *s, uint8_t id,
                        void (*send)(const uint8_t *, uint16_t)) {
    memset(s, 0, sizeof(*s));
    s->id = id;
    s->send = send;
    s->reg[FT_REG_MODEL] = 0xC8; s->reg[FT_REG_MODEL + 1] = 0x00;  // 自定型号 200
    s->reg[FT_REG_FIRMWARE] = 1;
    s->reg[FT_REG_ID] = id;
    s->reg[FT_REG_BAUD_INDEX] = 0;     // 飞特索引 0 = 1 Mbps
}

ft_rx_result_t feetech_slave_feed(feetech_slave_t *s, uint8_t byte) {
    switch (s_state) {
    case ST_H1: if (byte == 0xFF) s_state = ST_H2; break;
    case ST_H2: s_state = (byte == 0xFF) ? ST_ID : ST_H1; break;
    case ST_ID:
        s_id = byte;
        s_state = ST_LEN;
        break;
    case ST_LEN:
        s_len = byte;
        s_payload_n = 0;
        s_state = (s_len >= 2) ? ST_PAYLOAD : ST_H1;   // LEN<2 的帧直接丢弃重扫
        break;
    case ST_PAYLOAD:
        s_payload[s_payload_n++] = byte;
        if (s_payload_n >= s_len) { handle_frame(s); return FT_RX_REPLIED; }
        break;
    }
    return FT_RX_INCOMPLETE;
}

uint16_t feetech_build_status(const feetech_slave_t *s,
                              uint8_t err, const uint8_t *params, uint16_t n_params,
                              uint8_t out[]) {
    uint16_t len = (uint16_t)(n_params + 2);   // ERR(1) + PARAMS(n) + CHK(1)
    uint16_t k = 0;
    out[k++] = 0xFF; out[k++] = 0xFF;
    out[k++] = s->id;
    out[k++] = (uint8_t)len;
    out[k++] = err;
    uint16_t sum = (uint16_t)s->id + len + err;
    if (n_params) {
        memcpy(&out[k], params, n_params);
        for (uint16_t i = 0; i < n_params; i++) sum += params[i];
        k = (uint16_t)(k + n_params);
    }
    out[k++] = (uint8_t)((~sum) & 0xFF);
    return k;
}
