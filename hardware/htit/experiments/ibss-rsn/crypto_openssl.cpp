#include "ccmp.h"
#include <openssl/evp.h>

bool ccmp_aes(bool encrypt, const uint8_t key[16], const uint8_t nonce[13],
              const uint8_t aad[22], const uint8_t* in, size_t n,
              uint8_t* out, uint8_t tag[8]) {
    EVP_CIPHER_CTX* ctx = EVP_CIPHER_CTX_new();
    if (!ctx) return false;
    int count=0;
    bool ok = EVP_CipherInit_ex(ctx, EVP_aes_128_ccm(), nullptr, nullptr, nullptr, encrypt)==1 &&
        EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_CCM_SET_IVLEN, 13, nullptr)==1 &&
        EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_CCM_SET_TAG, 8, encrypt ? nullptr : tag)==1 &&
        EVP_CipherInit_ex(ctx, nullptr, nullptr, key, nonce, encrypt)==1 &&
        EVP_CipherUpdate(ctx, nullptr, &count, nullptr, int(n))==1 &&
        EVP_CipherUpdate(ctx, nullptr, &count, aad, 22)==1 &&
        EVP_CipherUpdate(ctx, out, &count, in, int(n))==1;
    if (ok && encrypt) ok = EVP_CipherFinal_ex(ctx, out+count, &count)==1 &&
        EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_CCM_GET_TAG, 8, tag)==1;
    EVP_CIPHER_CTX_free(ctx);
    return ok;
}
