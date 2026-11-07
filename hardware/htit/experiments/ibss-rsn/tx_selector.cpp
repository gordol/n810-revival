// Pinned SDK adapter: select an explicitly installed key on our protected frames.
// Retains vendor queue/register ownership; unrelated packets are passed through.
#include <Arduino.h>
#include <string.h>
#include "tx_selector.h"
extern "C" int pocket_vendor_tx_plcp1(void*);
static uint8_t own[6],net[6];
static volatile int slots[4]={-1,-1,-1,-1};
static volatile bool enabled=false;
static volatile unsigned selected=0;
static volatile uint32_t original_codes=0;
static inline bool range(uintptr_t p,size_t n){return !(p&3)&&p>=0x3ffae000u&&p<0x40000000u&&n<=0x40000000u-p;}
extern "C" int mac_tx_set_plcp1(void* queue) {
    if(enabled && range(uintptr_t(queue),8)) {
        uintptr_t esf=*static_cast<uint32_t*>(queue);
        if(range(esf,48)) {
            uintptr_t dma=*reinterpret_cast<uint32_t*>(esf+4),meta=*reinterpret_cast<uint32_t*>(esf+44);
            if(range(dma,12)&&range(meta,20)) {
                uintptr_t data=*reinterpret_cast<uint32_t*>(dma+4);
                unsigned n=*reinterpret_cast<uint16_t*>(esf+20)+*reinterpret_cast<uint16_t*>(esf+22);
                if(n>=40 && n<=1500 && range(data,n)) {
                    uint8_t* h=reinterpret_cast<uint8_t*>(data);
                    if(h[0]==8 && (h[1]&0x40) && !memcmp(h+10,own,6)&&!memcmp(h+16,net,6)) {
                        unsigned id=h[27]>>6;int slot=slots[id];
                        // Sending protected data without an installed mapping is
                        // a programming fault. Stop before handing it to the PHY.
                        if(slot<0 || slot>24)abort();
                        auto* code=reinterpret_cast<uint8_t*>(meta+16);
                        original_codes|=1u<<(*code&31);
                        *code=slot;++selected;
                    }
                }
            }
        }
    }
    return pocket_vendor_tx_plcp1(queue);
}
void probe_tx_selector_configure(const uint8_t a[6],const uint8_t b[6]) {
    enabled=false;memcpy(own,a,6);memcpy(net,b,6);selected=0;original_codes=0;
    for(unsigned i=0;i<4;++i)slots[i]=-1;
    enabled=true;
}
void probe_tx_selector_key(unsigned id,int slot){if(id<4)slots[id]=slot;}
void probe_tx_selector_stop(){enabled=false;}
unsigned probe_tx_selector_count(){return selected;}
uint32_t probe_tx_selector_original_codes(){return original_codes;}
