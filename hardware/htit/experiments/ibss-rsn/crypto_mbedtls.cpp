#include "ccmp.h"
#include <mbedtls/ccm.h>

bool ccmp_aes(bool encrypt, const uint8_t key[16], const uint8_t nonce[13],
              const uint8_t aad[22], const uint8_t* in, size_t n,
              uint8_t* out, uint8_t tag[8]) {
    mbedtls_ccm_context ctx;
    mbedtls_ccm_init(&ctx);
    int error = mbedtls_ccm_setkey(&ctx, MBEDTLS_CIPHER_ID_AES, key, 128);
    if (!error) error = encrypt ?
        mbedtls_ccm_encrypt_and_tag(&ctx, n, nonce, 13, aad, 22, in, out, tag, 8) :
        mbedtls_ccm_auth_decrypt(&ctx, n, nonce, 13, aad, 22, in, out, tag, 8);
    mbedtls_ccm_free(&ctx);
    return !error;
}
