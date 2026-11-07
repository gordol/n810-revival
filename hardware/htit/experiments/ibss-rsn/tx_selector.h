#pragma once
#include <stdint.h>
void probe_tx_selector_configure(const uint8_t own[6],const uint8_t bssid[6]);
void probe_tx_selector_key(unsigned key_id,int hardware_slot);
void probe_tx_selector_stop();
unsigned probe_tx_selector_count();
uint32_t probe_tx_selector_original_codes();
