// WPA primitives provided by the SDK's mbedTLS, not a new cipher implementation.
#include "utils/includes.h"
#include "utils/common.h"
#include "crypto/crypto.h"
#include <mbedtls/md.h>
#include <mbedtls/aes.h>

static int digest(mbedtls_md_type_t type,size_t count,const u8* data[],const size_t lengths[],u8* out) {
    mbedtls_md_context_t c;mbedtls_md_init(&c);
    const mbedtls_md_info_t* info=mbedtls_md_info_from_type(type);
    int r=info?mbedtls_md_setup(&c,info,0):-1;
    if(!r)r=mbedtls_md_starts(&c);
    for(size_t i=0;!r&&i<count;++i)r=mbedtls_md_update(&c,data[i],lengths[i]);
    if(!r)r=mbedtls_md_finish(&c,out);mbedtls_md_free(&c);return r;
}
static int hmac(mbedtls_md_type_t type,const u8* key,size_t keylen,size_t count,const u8* data[],const size_t lengths[],u8* out) {
    mbedtls_md_context_t c;mbedtls_md_init(&c);
    const mbedtls_md_info_t* info=mbedtls_md_info_from_type(type);
    int r=info?mbedtls_md_setup(&c,info,1):-1;
    if(!r)r=mbedtls_md_hmac_starts(&c,key,keylen);
    for(size_t i=0;!r&&i<count;++i)r=mbedtls_md_hmac_update(&c,data[i],lengths[i]);
    if(!r)r=mbedtls_md_hmac_finish(&c,out);mbedtls_md_free(&c);return r;
}
#define VECTOR(name,type) int name##_vector(size_t n,const u8* p[],const size_t l[],u8* out){return digest(type,n,p,l,out);}
#define HMAC(name,type) int hmac_##name##_vector(const u8* k,size_t z,size_t n,const u8* p[],const size_t l[],u8* o){return hmac(type,k,z,n,p,l,o);} \
int hmac_##name(const u8* k,size_t z,const u8* p,size_t l,u8* o){return hmac(type,k,z,1,&p,&l,o);}
VECTOR(md5,MBEDTLS_MD_MD5)
VECTOR(sha1,MBEDTLS_MD_SHA1)
VECTOR(sha256,MBEDTLS_MD_SHA256)
HMAC(md5,MBEDTLS_MD_MD5)
HMAC(sha1,MBEDTLS_MD_SHA1)
HMAC(sha256,MBEDTLS_MD_SHA256)
static void* aes_init(const u8* key,size_t n,int decrypt) {
    if(n!=16 && n!=24 && n!=32)return NULL;
    mbedtls_aes_context* c=os_malloc(sizeof(*c));if(!c)return NULL;mbedtls_aes_init(c);
    int r=decrypt?mbedtls_aes_setkey_dec(c,key,n*8):mbedtls_aes_setkey_enc(c,key,n*8);
    if(r){mbedtls_aes_free(c);os_free(c);return NULL;}return c;
}
void* aes_encrypt_init(const u8* k,size_t n){return aes_init(k,n,0);}
void* aes_decrypt_init(const u8* k,size_t n){return aes_init(k,n,1);}
int aes_encrypt(void* c,const u8* in,u8* out){return mbedtls_aes_crypt_ecb(c,MBEDTLS_AES_ENCRYPT,in,out);}
int aes_decrypt(void* c,const u8* in,u8* out){return mbedtls_aes_crypt_ecb(c,MBEDTLS_AES_DECRYPT,in,out);}
void aes_encrypt_deinit(void* c){if(c){mbedtls_aes_free(c);os_free(c);}}
void aes_decrypt_deinit(void* c){aes_encrypt_deinit(c);}
