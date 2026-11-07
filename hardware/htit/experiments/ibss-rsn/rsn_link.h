#pragma once
#include <stddef.h>
#include <stdint.h>
// Callback receives Ethernet payload only after RSN authorization, hardware
// authentication and the per-key replay check. Single application-loop owner.
using HtitRsnEthernet = void (*)(const uint8_t source[6],const uint8_t dest[6],
                                uint16_t type,const uint8_t*,size_t);
bool htit_rsn_begin(const uint8_t pmk[32],const uint8_t peer[6],HtitRsnEthernet);
bool htit_rsn_send(const uint8_t dest[6],uint16_t,const uint8_t*,size_t);
bool htit_rsn_ready();
void htit_rsn_tick();
