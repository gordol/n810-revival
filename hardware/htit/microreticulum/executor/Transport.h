#pragma once
#include <stdint.h>
#include <stddef.h>
#ifdef HTIT_EXECUTOR
uint32_t htit_executor_packet_generation(const uint8_t*,size_t);
bool htit_executor_generation_live(uint32_t,uint32_t margin_ms=0);
bool htit_executor_lora_tag(uint16_t,uint32_t);
bool htit_executor_lora_permit(uint16_t);
void htit_executor_uart_error(unsigned);
struct HtitCoreStage {
  unsigned previous;uint64_t started;
  explicit HtitCoreStage(unsigned stage);
  ~HtitCoreStage();
};
bool htit_executor_begin();
void htit_executor_tick();
bool htit_executor_serial_byte(uint8_t);
bool htit_executor_log(const char*,size_t);
#endif
