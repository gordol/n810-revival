#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#define HUB_PAYLOAD 512
#define HUB_RAW (7 + HUB_PAYLOAD + 2)
#define HUB_ENCODED (2 * HUB_RAW + 2)
typedef struct {
    uint8_t service, op;
    uint16_t id, len;
    uint8_t data[HUB_PAYLOAD];
} hub_frame;
typedef struct {
    uint8_t bytes[HUB_RAW];
    size_t used;
    bool active, escaped, bad;
} hub_parser;
typedef void (*hub_frame_cb)(const hub_frame *, void *);
uint16_t hub_crc(const uint8_t *, size_t);
size_t hub_encode(const hub_frame *, uint8_t *, size_t);
void hub_feed(hub_parser *, const uint8_t *, size_t, hub_frame_cb, void *);
