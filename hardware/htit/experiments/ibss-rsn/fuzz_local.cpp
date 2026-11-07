// Bounded local malformed-frame checks, suitable for ASan + UBSan. No radio I/O.
#include "ccmp.h"
#include <assert.h>
#include <random>
#include <string.h>

int main() {
    std::mt19937 rng(4913);
    CcmpEpoch tx{},rx{};
    for (auto& b:tx.key) b=uint8_t(rng());
    const uint8_t header[24]={8,0,0,0,2,0,0,0,0,1,2,0,0,0,0,2,2,0,0,0,0,3,0,0};
    memcpy(tx.receiver,header+4,6);memcpy(tx.transmitter,header+10,6);memcpy(tx.bssid,header+16,6);
    rx=tx;
    uint8_t plain[1401],wire[1441],out[1401];
    for (unsigned i=0;i<20000;++i) {
        for (auto& b:plain)b=uint8_t(rng());
        size_t n=1+rng()%1400;
        int count=ccmp_seal(&tx,header,plain,n,wire,sizeof(wire));
        assert(count==int(n+40));
        assert(ccmp_open(&rx,wire,count,out,sizeof(out))==int(n));
        assert(!memcmp(plain,out,n));
        assert(ccmp_open(&rx,wire,count,out,sizeof(out))==-1);
        for (auto b:out)assert(b==0);
        // Each forged frame has a fresh replay state, so authentication is exercised.
        CcmpEpoch fresh=tx;fresh.rx_pn=0;
        wire[32+rng()%(n+8)]^=1u<<(rng()%8);
        assert(ccmp_open(&fresh,wire,count,out,sizeof(out))==-1);
        assert(fresh.rx_pn==0);
        for (auto b:out)assert(b==0);
        // Arbitrary input, including malformed lengths and headers.
        for (auto& b:wire)b=uint8_t(rng());
        assert(ccmp_open(&fresh,wire,rng()%sizeof(wire),out,sizeof(out))==-1);
    }
    return 0;
}
