// WIP read-only tap before the SDK's receive processing, never a driver takeover.
// DMA layout reference: esp32-open-mac/main and its PR #24 hardware RX dumps.
#include <Arduino.h>
#include <freertos/FreeRTOS.h>
#include <freertos/portmacro.h>
#include <string.h>
#include "rx_observer.h"

extern "C" void pocket_vendor_process_rx(void*,uint32_t,uint32_t);
static portMUX_TYPE guard=portMUX_INITIALIZER_UNLOCKED;
static volatile bool enabled=false;
static uint8_t own[6],peer[6],net[6];
#ifndef HTIT_RSN_RX_RING
#define HTIT_RSN_RX_RING 32
#endif
static ProbeRawRx ring[HTIT_RSN_RX_RING];
static unsigned read_at=0,write_at=0;
static ProbeRxStats stats{};

static inline __attribute__((always_inline)) bool dram(uintptr_t p,size_t n) {
    return !(p&3) && p>=0x3ffae000u && p<0x40000000u && n<=0x40000000u-p;
}
static void IRAM_ATTR observe(void* descriptor,uint32_t count) {
    if(!enabled)return;
    ++stats.calls;
    if(count!=1)return;
    ++stats.single;
    uintptr_t address=reinterpret_cast<uintptr_t>(descriptor);
    if(!dram(address,12)){++stats.bounds;++stats.pointer_bad;return;}
    const volatile uint32_t* d=reinterpret_cast<const volatile uint32_t*>(address);
    uint32_t flags=d[0],buffer=d[1];
    stats.sample_flags=flags;
    unsigned capacity=flags&4095,used=(flags>>12)&4095;
    if(!(flags&(1u<<30)))++stats.no_data;
    // The vendor's allocation can exceed open-mac's 1600-byte custom buffer.
    // Called only at completed-frame processing; bound reads by actual DMA use.
    if(used>capacity || used>1600 || !dram(buffer,used)) {++stats.bounds;++stats.buffer_bad;return;}
    ProbeRawRx item;
    if(!probe_dma_decode(reinterpret_cast<const volatile uint8_t*>(buffer),used,flags,own,peer,net,&item))return;
    ++stats.matching;
    portENTER_CRITICAL_ISR(&guard);
    unsigned next=(write_at+1)%HTIT_RSN_RX_RING;
    if(next==read_at)++stats.overflow;
    else {
        // Volatile source prevents optimization into a flash-resident memcpy.
        volatile const uint8_t* src=reinterpret_cast<const uint8_t*>(&item);
        uint8_t* dest=reinterpret_cast<uint8_t*>(&ring[write_at]);
        for(size_t i=0;i<offsetof(ProbeRawRx,frame)+item.length;++i)dest[i]=src[i];
        write_at=next;++stats.queued;
    }
    portEXIT_CRITICAL_ISR(&guard);
}

extern "C" void IRAM_ATTR wDev_ProcessRxSucData(void* descriptor,uint32_t count,uint32_t argument) {
    observe(descriptor,count);
    // Always retain the vendor's buffer ownership, recycling and processing.
    pocket_vendor_process_rx(descriptor,count,argument);
}
void probe_rx_observer_configure(const uint8_t receiver[6],const uint8_t source[6],const uint8_t bssid[6]) {
    portENTER_CRITICAL(&guard);
    enabled=false;memcpy(own,receiver,6);memcpy(peer,source,6);memcpy(net,bssid,6);
    read_at=write_at=0;stats={};enabled=true;
    portEXIT_CRITICAL(&guard);
}
void probe_rx_observer_stop() {portENTER_CRITICAL(&guard);enabled=false;portEXIT_CRITICAL(&guard);}
bool probe_rx_observer_next(ProbeRawRx* out) {
    portENTER_CRITICAL(&guard);
    bool found=read_at!=write_at;
    if(found){*out=ring[read_at];read_at=(read_at+1)%HTIT_RSN_RX_RING;}
    portEXIT_CRITICAL(&guard);return found;
}
ProbeRxStats probe_rx_observer_stats() {
    portENTER_CRITICAL(&guard);ProbeRxStats result=stats;portEXIT_CRITICAL(&guard);return result;
}
