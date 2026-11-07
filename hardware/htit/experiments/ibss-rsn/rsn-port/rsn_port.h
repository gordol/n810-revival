#pragma once
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

// Transport-independent adapter for upstream IBSS RSN. No password/key logging.
// One explicitly selected peer per context. Key material is runtime-only.
enum { POCKET_RSN_AUTH=1, POCKET_RSN_EAPOL=2 };
struct pocket_rsn_callbacks {
    int (*send)(void*,int,const uint8_t dest[6],const uint8_t*,size_t,int encrypted);
    int (*key)(void*,const uint8_t* addr,int alg,int index,int transmit,
               const uint8_t*,size_t,const uint8_t* seq,size_t,int flags);
    void (*authorized)(void*,int);
    // Current transmitter packet number, little endian, padded to eight bytes.
    int (*get_seqnum)(void*,int index,uint8_t seq[8]);
};
struct pocket_rsn;
struct pocket_rsn* pocket_rsn_create(const uint8_t own[6],const uint8_t bssid[6],
    const uint8_t pmk[32],unsigned group_rekey_seconds,
    const struct pocket_rsn_callbacks*,void*);
int pocket_rsn_start(struct pocket_rsn*,const uint8_t peer[6]);
int pocket_rsn_receive(struct pocket_rsn*,const uint8_t peer[6],int kind,
    const uint8_t*,size_t,int encrypted);
int pocket_rsn_ready(struct pocket_rsn*);
void pocket_rsn_poll(void);
void pocket_rsn_destroy(struct pocket_rsn*);

#ifdef __cplusplus
}
#endif
