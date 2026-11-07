#pragma once
#include <stddef.h>
#include <stdint.h>

// Stage-one data-plane experiment. No radio or RSN key-management implementation.
// One object is one direction and one authenticated, FRESH temporal key epoch.
// Never reset counters or recreate an epoch with the same key and transmitter.
struct CcmpEpoch {
    uint8_t key[16], transmitter[6], receiver[6], bssid[6];
    uint64_t tx_pn, rx_pn;
    uint8_t key_id;
    bool key_valid;
};

// No in-place input/output. On failure output is cleared and no plaintext exposed.
// Return protected MPDU length / decrypted payload length, or -1 on rejection.
extern "C" int ccmp_seal(CcmpEpoch*, const uint8_t header[24], const uint8_t*,
                         size_t, uint8_t*, size_t);
extern "C" int ccmp_open(CcmpEpoch*, const uint8_t*, size_t, uint8_t*, size_t);
extern "C" bool ccmp_valid_fcs(const uint8_t*,size_t);

// Implemented by mbedTLS on ESP32 and OpenSSL in the native test harness.
bool ccmp_aes(bool encrypt, const uint8_t key[16], const uint8_t nonce[13],
              const uint8_t aad[22], const uint8_t* input, size_t length,
              uint8_t* output, uint8_t tag[8]);

// Rebinding an existing key must preserve counters, even after driver deletion.
// An authenticated RSC may only raise the receive replay floor.
extern "C" void ccmp_install_key(CcmpEpoch*,const uint8_t key[16],uint64_t rx_floor);
