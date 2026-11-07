#pragma once
#include <stddef.h>
#include <stdint.h>
#ifdef HTIT_RSN_FRAME_MAX
constexpr size_t PROBE_RX_MAX=HTIT_RSN_FRAME_MAX;
#elif defined(HTIT_RSN_LINK)
constexpr size_t PROBE_RX_MAX=1600;
#else
constexpr size_t PROBE_RX_MAX=260;
#endif

// Lab snapshot only; not a trusted/authenticated application packet.
struct ProbeRawRx {
    uint32_t dma_flags;
    uint16_t dma_length,sig_length,length;
    uint8_t state,filter;
    uint8_t frame[PROBE_RX_MAX];
};
struct ProbeRxStats {uint32_t calls,single,bounds,matching,queued,overflow,pointer_bad,buffer_bad,no_data,sample_flags;};

// Original ESP32 RX metadata is 28 bytes. Layout cross-checked against the pinned
// SDK and esp32-open-mac 20ce43d. Explicit byte access avoids host bitfield ABI.
static inline __attribute__((always_inline)) bool probe_dma_decode(
    const volatile uint8_t* packet,size_t available,uint32_t flags,
    const uint8_t receiver[6],const uint8_t source[6],const uint8_t bssid[6],ProbeRawRx* out) {
    if(!packet || !out || !receiver || !source || !bssid || available<52 || available>1600)return false;
    unsigned sig=packet[24]|((unsigned(packet[25])&15)<<8);
    if(sig<24 || sig>PROBE_RX_MAX)return false;
    const volatile uint8_t* f=packet+28;
    if(f[0]!=8
#ifdef HTIT_RSN_LINK
       && f[0]!=0xb0
#endif
       )return false;
    for(unsigned i=0;i<6;++i)
        if((f[4+i]!=receiver[i]
#ifdef HTIT_RSN_LINK
           && !(f[4]&1)
#endif
           ) || f[10+i]!=source[i] || f[16+i]!=bssid[i])return false;
    size_t n=available-28;if(n>sig)n=sig;
    out->dma_flags=flags;out->dma_length=available;out->sig_length=sig;out->length=n;
    out->state=packet[27];out->filter=(packet[3]>>4)&3;
    for(size_t i=0;i<n;++i)out->frame[i]=f[i];
    return true;
}

void probe_rx_observer_configure(const uint8_t receiver[6],const uint8_t source[6],const uint8_t bssid[6]);
void probe_rx_observer_stop();
bool probe_rx_observer_next(ProbeRawRx*);
ProbeRxStats probe_rx_observer_stats();
