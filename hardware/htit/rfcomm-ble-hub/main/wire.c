#include "wire.h"
#include <string.h>
uint16_t hub_crc(const uint8_t *p, size_t n) {
    uint16_t crc = 0xffff;
    while (n--) {
        crc ^= (uint16_t)*p++ << 8;
        for (int i = 0; i < 8; i++)
            crc = (crc & 0x8000) ? (crc << 1) ^ 0x1021 : crc << 1;
    }
    return crc;
}
static uint16_t get16(const uint8_t *p) { return p[0] | ((uint16_t)p[1] << 8); }
static void put16(uint8_t *p, uint16_t v) {
    p[0] = v;
    p[1] = v >> 8;
}
size_t hub_encode(const hub_frame *f, uint8_t *out, size_t cap) {
    if (f->len > HUB_PAYLOAD || cap < 2)
        return 0;
    uint8_t raw[HUB_RAW];
    raw[0] = 1;
    raw[1] = f->service;
    raw[2] = f->op;
    put16(raw + 3, f->id);
    put16(raw + 5, f->len);
    memcpy(raw + 7, f->data, f->len);
    put16(raw + 7 + f->len, hub_crc(raw, 7 + f->len));
    size_t used = 0;
    out[used++] = 0x7e;
    for (size_t i = 0; i < 9 + f->len; i++) {
        uint8_t b = raw[i];
        size_t need = (b == 0x7e || b == 0x7d) ? 2 : 1;
        if (used + need + 1 > cap)
            return 0;
        if (need == 2) {
            out[used++] = 0x7d;
            b ^= 0x20;
        }
        out[used++] = b;
    }
    out[used++] = 0x7e;
    return used;
}
void hub_feed(hub_parser *p, const uint8_t *buf, size_t len, hub_frame_cb cb, void *ctx) {
    while (len--) {
        uint8_t b = *buf++;
        if (b == 0x7e) {
            if (p->active && !p->bad && !p->escaped && p->used >= 9 && p->bytes[0] == 1) {
                uint16_t n = get16(p->bytes + 5);
                if (n <= HUB_PAYLOAD && p->used == (size_t)n + 9 &&
                    hub_crc(p->bytes, n + 7) == get16(p->bytes + n + 7)) {
                    hub_frame f = {.service = p->bytes[1],
                                   .op = p->bytes[2],
                                   .id = get16(p->bytes + 3),
                                   .len = n};
                    memcpy(f.data, p->bytes + 7, n);
                    cb(&f, ctx);
                }
            }
            p->used = 0;
            p->escaped = false;
            p->bad = false;
            p->active = true;
            continue;
        }
        if (!p->active || p->bad)
            continue;
        if (p->escaped) {
            b ^= 0x20;
            p->escaped = false;
        } else if (b == 0x7d) {
            p->escaped = true;
            continue;
        }
        if (p->used == HUB_RAW) {
            p->bad = true;
            continue;
        }
        p->bytes[p->used++] = b;
    }
}
