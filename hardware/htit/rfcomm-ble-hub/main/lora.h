#pragma once
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
/* Explicit configuration only; this module never restores or auto-enables RF. */
typedef struct { uint32_t frequency, bandwidth; uint8_t sf, cr, power; } lora_config;
typedef void (*lora_receive)(const uint8_t *, size_t, int16_t, int8_t);
typedef void (*lora_complete)(bool);
bool lora_init(void);
bool lora_configure(const lora_config *);
bool lora_enable(bool);
bool lora_send(const uint8_t *, size_t);
void lora_poll(lora_receive, lora_complete);
bool lora_online(void);
bool lora_busy(void);
