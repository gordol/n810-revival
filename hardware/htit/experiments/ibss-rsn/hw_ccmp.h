#pragma once
#include "ccmp.h"
#include "rx_observer.h"

// LAB hardware RX adapter, NOT a parser for untrusted socket/serial metadata.
// Only call with snapshots from the pinned DMA tap after installing the fresh
// expected PTK in the VIF-0 unicast key slot. The hardware authenticates/removes
// the MIC before DMA; this function checks the descriptor contract and replay.
// Native tests validate these checks, not the silicon's MIC verification.
static inline int ccmp_open_hardware(CcmpEpoch* e,const ProbeRawRx& r,bool key_ready,
                                     uint8_t* out,size_t capacity) {
    if(!out)return -1;
    for(size_t i=0;i<capacity;++i)out[i]=0;
    if(!e || !key_ready || r.state || r.filter!=1 || r.sig_length<=44 || r.sig_length>260)return -1;
    size_t length=r.sig_length-44; // MAC24 + CCMP8 + MIC8 + FCS4 on air.
    size_t used=28+32+length;
    if(length>1400 || length>capacity || 32+length>sizeof(r.frame) ||
       r.length>sizeof(r.frame) || r.length<32+length ||
       r.dma_length!=((used+3)&~size_t(3)) || e->key_id>3)return -1;
    const uint8_t* h=r.frame;
    if(h[0]!=8 || !(h[1]&0x40) || (h[1]&0x87) || (h[22]&15) || (h[4]&1) || h[26] ||
       h[27]!=uint8_t(0x20|(e->key_id<<6)))return -1;
    for(unsigned i=0;i<6;++i)
        if(h[4+i]!=e->receiver[i] || h[10+i]!=e->transmitter[i] || h[16+i]!=e->bssid[i])return -1;
    uint64_t pn=h[24]|(uint64_t(h[25])<<8);
    for(unsigned i=0;i<4;++i)pn|=uint64_t(h[28+i])<<(16+8*i);
    if(!pn || pn<=e->rx_pn)return -1;
    for(size_t i=0;i<length;++i)out[i]=h[32+i];
    e->rx_pn=pn;return length;
}
