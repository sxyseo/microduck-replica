#include "dxl_slave.h"
#include "crc16.h"
#include <string.h>

// 协议层为纯 C99：CRC 表是 256×2 字节，静态放这里（G031 有 8KB RAM，无压力）。
static uint16_t s_crc_table[256];
static bool s_table_ready = false;

// 接收状态机：FF FF FD 00 | ID | LEN_L LEN_H | INST + PARAMS(LEN 字节) | CRC_L CRC_H
// CRC 覆盖范围 = ID..最后一个 PARAM（不含包头、不含 CRC 本身）—— ROBOTIS e-Manual 定义。
typedef enum { ST_H1, ST_H2, ST_H3, ST_H4, ST_ID, ST_LEN_L, ST_LEN_H, ST_PAYLOAD, ST_CRC_L, ST_CRC_H } st_t;
static st_t s_state = ST_H1;
static uint8_t s_id, s_len_l, s_len_h;
static uint8_t s_payload[256];
static uint16_t s_payload_n, s_crc_in;

static void reset(void) { s_state = ST_H1; }

static void reply_with_block(dxl_slave_t *s, uint8_t err,
                             const uint8_t *params, uint16_t n) {
    uint8_t pkt[DXL_IMU_BLOCK_SIZE + 16];
    uint16_t len = dxl_build_status(s, s_crc_table, err, params, n, pkt);
    s->send(pkt, len);
}

static void handle_frame(dxl_slave_t *s) {
    uint16_t len = (uint16_t)(s_len_l | (s_len_h << 8));
    uint16_t crc_calc = dxl_crc_update(s_crc_table, 0, &s_id, 1);
    uint8_t lenb[2] = { s_len_l, s_len_h };
    crc_calc = dxl_crc_update(s_crc_table, crc_calc, lenb, 2);
    // CRC 覆盖 INST + PARAMS 共 LEN 字节（s_payload 里正好存了 LEN 字节）
    crc_calc = dxl_crc_update(s_crc_table, crc_calc, s_payload, (size_t)len);
    if (crc_calc != s_crc_in) { reset(); return; }        // CRC 错：从机按协议保持沉默

    uint8_t inst = s_payload[0];
    const uint8_t *params = &s_payload[1];
    uint16_t n_params = (uint16_t)(len > 1 ? len - 1 : 0);

    if (s_id != s->id && s_id != 0xFE) { reset(); return; } // 不是给本板的

    switch (inst) {
    case DXL_INST_PING:
        reply_with_block(s, 0, NULL, 0);
        break;
    case DXL_INST_READ: {                       // params: addr(2 LE) + len(2 LE)
        if (n_params < 4) { reply_with_block(s, DXL_ERR_INSTRUCTION, NULL, 0); break; }
        uint16_t addr = (uint16_t)(params[0] | (params[1] << 8));
        uint16_t rlen = (uint16_t)(params[2] | (params[3] << 8));
        if (addr + rlen > DXL_REG_SIZE) { reply_with_block(s, DXL_ERR_INSTRUCTION, NULL, 0); break; }
        reply_with_block(s, 0, &s->reg[addr], rlen);
        break;
    }
    case DXL_INST_SYNC_READ: {                  // params: addr(2) + len(2) + ids[...]
        if (n_params < 5) { reset(); break; }
        uint16_t addr = (uint16_t)(params[0] | (params[1] << 8));
        uint16_t rlen = (uint16_t)(params[2] | (params[3] << 8));
        bool mine = false;
        for (uint16_t i = 4; i < n_params; i++)
            if (params[i] == s->id) { mine = true; break; }
        if (!mine) { reset(); break; }          // 广播 sync_read 不含本板：沉默
        if (addr + rlen > DXL_REG_SIZE) { reply_with_block(s, DXL_ERR_INSTRUCTION, NULL, 0); break; }
        // TODO(时序)：这里按 return_delay(×2µs) 再发送更贴近舵机行为；
        // 骨架先立即应答，联调时如发现与低 ID 舵机抢线再加延迟钩子。
        reply_with_block(s, 0, &s->reg[addr], rlen);
        break;
    }
    default:
        reply_with_block(s, DXL_ERR_INSTRUCTION, NULL, 0);
        break;
    }
    reset();
}

void dxl_slave_init(dxl_slave_t *s, uint8_t id, void (*send)(const uint8_t *, uint16_t)) {
    memset(s, 0, sizeof(*s));
    s->id = id;
    s->send = send;
    s->reg[DXL_REG_MODEL] = 0xC8; s->reg[DXL_REG_MODEL + 1] = 0x00;  // 自定型号 200
    s->reg[DXL_REG_FIRMWARE] = 1;
    s->reg[DXL_REG_ID] = id;
    s->reg[DXL_REG_BAUD_INDEX] = 3;      // 1 Mbps
    s->reg[DXL_REG_RETURN_DELAY] = 125;  // 250 µs，与 XL330 默认一致
    if (!s_table_ready) { dxl_crc_init_table(s_crc_table); s_table_ready = true; }
}

dxl_rx_result_t dxl_slave_feed(dxl_slave_t *s, uint8_t byte) {
    switch (s_state) {
    case ST_H1: if (byte == 0xFF) s_state = ST_H2; break;
    case ST_H2: s_state = (byte == 0xFF) ? ST_H3 : ST_H1; break;
    case ST_H3: s_state = (byte == 0xFD) ? ST_H4 : ST_H1; break;
    case ST_H4: s_state = (byte == 0x00) ? ST_ID : ST_H1; break;
    case ST_ID: s_id = byte; s_state = ST_LEN_L; break;
    case ST_LEN_L: s_len_l = byte; s_state = ST_LEN_H; break;
    case ST_LEN_H: s_len_h = byte; s_payload_n = 0; s_state = ST_PAYLOAD; break;
    case ST_PAYLOAD: {
        uint16_t len = (uint16_t)(s_len_l | (s_len_h << 8));
        s_payload[s_payload_n++] = byte;
        if (s_payload_n >= len) s_state = ST_CRC_L;
        break;
    }
    case ST_CRC_L: s_crc_in = byte; s_state = ST_CRC_H; break;
    case ST_CRC_H:
        s_crc_in |= (uint16_t)(byte << 8);
        handle_frame(s);
        return DXL_RX_REPLIED;   // 帧结束（是否真的应答由帧内容决定）
    }
    return DXL_RX_INCOMPLETE;
}

uint16_t dxl_build_status(dxl_slave_t *s, uint16_t crc_table[256],
                          uint8_t err, const uint8_t *params, uint16_t n_params,
                          uint8_t out[]) {
    static const uint8_t hdr[4] = { 0xFF, 0xFF, 0xFD, 0x00 };
    uint16_t len = (uint16_t)(n_params + 2);   // INST(0x55) + ERR + params
    uint16_t k = 0;
    memcpy(out, hdr, 4); k = 4;
    out[k++] = s->id;
    out[k++] = (uint8_t)(len & 0xFF);
    out[k++] = (uint8_t)(len >> 8);
    out[k++] = DXL_INST_STATUS;
    out[k++] = err;
    // CRC 覆盖 ID + LEN + INST + ERR + PARAMS
    uint16_t crc = dxl_crc_update(crc_table, 0, &out[4], 3);   // ID + LEN
    crc = dxl_crc_update(crc_table, crc, &out[7], 2);          // INST + ERR
    if (n_params) {
        memcpy(&out[k], params, n_params);
        crc = dxl_crc_update(crc_table, crc, params, n_params);
        k = (uint16_t)(k + n_params);
    }
    out[k++] = (uint8_t)(crc & 0xFF);
    out[k++] = (uint8_t)(crc >> 8);
    return k;
}
