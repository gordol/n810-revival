#include "ccmp.h"
#include <string.h>

extern "C" bool ccmp_valid_fcs(const uint8_t* p,size_t length) {
    if(!p || length<4)return false;
    uint32_t crc=0xffffffff;
    for(size_t i=0;i<length-4;++i){crc^=p[i];for(int j=0;j<8;++j)crc=(crc>>1)^(0xedb88320u&uint32_t(-int32_t(crc&1)));}
    crc=~crc;
    return p[length-4]==uint8_t(crc) && p[length-3]==uint8_t(crc>>8) &&
        p[length-2]==uint8_t(crc>>16) && p[length-1]==uint8_t(crc>>24);
}

namespace {
constexpr size_t MAX_PAYLOAD = 1400;
constexpr uint64_t MAX_PN = (uint64_t(1) << 48) - 1;

void clear(uint8_t* p, size_t n) {
    volatile uint8_t* q = p;
    while (n--) *q++ = 0;
}
bool header_ok(const CcmpEpoch& e, const uint8_t* h) {
    // Only non-QoS, unfragmented IBSS data, not AP/STA, WDS or management frames.
    return h[0] == 0x08 && !(h[1] & 0x87) && !(h[22] & 15) &&
        e.key_id <= 3 && !memcmp(h+4, e.receiver, 6) &&
        !memcmp(h+10, e.transmitter, 6) && !memcmp(h+16, e.bssid, 6);
}
void inputs(const uint8_t* h, uint64_t pn, uint8_t* nonce, uint8_t* aad) {
    nonce[0] = 0; // Priority zero for non-QoS data.
    memcpy(nonce+1, h+10, 6);
    for (int i=0; i<6; ++i) nonce[7+i] = uint8_t(pn >> (8*(5-i)));
    aad[0] = h[0] & 0x8f;
    aad[1] = (h[1] & 0xc7) | 0x40;
    memcpy(aad+2, h+4, 18);
    aad[20] = h[22] & 15;
    aad[21] = 0;
}
}

extern "C" int ccmp_seal(CcmpEpoch* e, const uint8_t* header,
                         const uint8_t* plain, size_t n, uint8_t* out, size_t cap) {
    if (!out) return -1;
    clear(out, cap);
    if (!e || !header || !plain || !n || n>MAX_PAYLOAD || cap<n+40 ||
        !header_ok(*e, header) || e->tx_pn>=MAX_PN) return -1;
    // Consume before crypto: a failed attempt must never reuse a nonce.
    uint64_t pn = ++e->tx_pn;
    memcpy(out, header, 24);
    out[1] |= 0x40;
    out[24] = uint8_t(pn); out[25] = uint8_t(pn>>8);
    out[26] = 0; out[27] = 0x20 | (e->key_id<<6);
    for (int i=0; i<4; ++i) out[28+i] = uint8_t(pn >> (16+8*i));
    uint8_t nonce[13], aad[22], tag[8];
    inputs(out, pn, nonce, aad);
    if (!ccmp_aes(true, e->key, nonce, aad, plain, n, out+32, tag)) {
        clear(out, cap); return -1;
    }
    memcpy(out+32+n, tag, 8);
    return int(n+40);
}

extern "C" int ccmp_open(CcmpEpoch* e, const uint8_t* frame, size_t n,
                         uint8_t* out, size_t cap) {
    if (!out) return -1;
    clear(out, cap);
    if (!e || !frame || n<=40 || n>MAX_PAYLOAD+40 || cap<n-40 ||
        !header_ok(*e, frame) || !(frame[1]&0x40) || frame[26] ||
        frame[27] != uint8_t(0x20 | (e->key_id<<6))) return -1;
    uint64_t pn = frame[24] | (uint64_t(frame[25])<<8);
    for (int i=0; i<4; ++i) pn |= uint64_t(frame[28+i]) << (16+8*i);
    if (!pn || pn<=e->rx_pn) return -1;
    uint8_t nonce[13], aad[22], tag[8];
    inputs(frame, pn, nonce, aad);
    memcpy(tag, frame+n-8, 8);
    if (!ccmp_aes(false, e->key, nonce, aad, frame+32, n-40, out, tag)) {
        clear(out, cap); return -1;
    }
    // Authenticate FIRST: forgery cannot advance the replay window.
    e->rx_pn = pn;
    return int(n-40);
}

extern "C" void ccmp_install_key(CcmpEpoch* e,const uint8_t key[16],uint64_t rx_floor) {
    if(!e||!key||rx_floor>0xffffffffffffULL)return;
    if(!e->key_valid||memcmp(e->key,key,16)) {
        *e={};memcpy(e->key,key,16);e->key_valid=true;
    }
    if(rx_floor>e->rx_pn)e->rx_pn=rx_floor;
}
