#include "utils/includes.h"
#include "utils/common.h"
#include "common/ieee802_11_defs.h"
#include "common/wpa_common.h"
#include "wpa_supplicant_i.h"
#include "driver_i.h"
#include "ibss_rsn.h"
#include "l2_packet/l2_packet.h"
#include "rsn_port.h"

struct pocket_rsn {
    struct wpa_supplicant wpa;
    struct ibss_rsn* rsn;
    struct pocket_rsn_callbacks callbacks;
    void* context;
    u8 peer[6];
    int bound,pairwise_installed,reported,key_error,port_authorized;
};
static struct pocket_rsn* contexts[4];
void pocket_eloop_poll(void);

static struct pocket_rsn* port(struct wpa_supplicant* wpa) {return wpa->port;}

int wpa_drv_send_mlme(struct wpa_supplicant* wpa,const u8* data,size_t len,int noack,unsigned freq,int no_cck) {
    (void)noack;(void)freq;(void)no_cck;
    struct pocket_rsn* p=port(wpa);
    if(!p->bound || len!=30 || memcmp(data+4,p->peer,6))return -1;
    return p->callbacks.send(p->context,POCKET_RSN_AUTH,p->peer,data,len,0);
}
int wpa_drv_tx_control_port(struct wpa_supplicant* wpa,const u8* dest,u16 proto,const u8* data,size_t len,int no_encrypt) {
    struct pocket_rsn* p=port(wpa);
    if(!p->bound || proto!=ETH_P_EAPOL || len>1024 || memcmp(dest,p->peer,6))return -1;
    return p->callbacks.send(p->context,POCKET_RSN_EAPOL,dest,data,len,!no_encrypt);
}
int wpa_drv_set_key(struct wpa_supplicant* wpa,int link_id,enum wpa_alg alg,const u8* addr,int index,int transmit,
    const u8* seq,size_t seq_len,const u8* key,size_t key_len,enum key_flag flags) {
    (void)link_id;
    struct pocket_rsn* p=port(wpa);
    if(index<0 || index>3 || (alg!=WPA_ALG_NONE && alg!=WPA_ALG_CCMP) ||
        (key_len!=0 && key_len!=16) || seq_len>6)return -1;
    if(addr && p->bound && memcmp(addr,p->peer,6) && !is_broadcast_ether_addr(addr))return -1;
    int result=p->callbacks.key(p->context,addr,alg,index,transmit,key,key_len,seq,seq_len,flags);
    // Fail closed for the entire session, including failed GTK installation.
    // Upstream's completion bits alone do not represent driver success.
    if(result && alg==WPA_ALG_CCMP)p->key_error=1;
    if(!result && index==0)p->pairwise_installed=alg==WPA_ALG_CCMP && key_len==16;
    return result;
}
int pocket_rsn_get_seqnum(struct wpa_supplicant* wpa,int index,u8* seq) {
    struct pocket_rsn* p=port(wpa);
    if(!seq || index<1 || index>3 || !p->callbacks.get_seqnum)return -1;
    os_memset(seq,0,8);
    return p->callbacks.get_seqnum(p->context,index,seq);
}
int wpa_drv_sta_deauth(struct wpa_supplicant* wpa,const u8* addr,u16 reason) {
    (void)addr;(void)reason;
    struct pocket_rsn* p=port(wpa);p->pairwise_installed=0;p->port_authorized=0;
    return 0;
}
int wpa_drv_sta_set_flags(struct wpa_supplicant* wpa,const u8* addr,unsigned total,unsigned set,unsigned mask) {
    (void)set;(void)mask;
    struct pocket_rsn* p=port(wpa);
    if(!p->bound || memcmp(addr,p->peer,6))return -1;
    p->port_authorized=(total&WPA_STA_AUTHORIZED)!=0;
    return 0; // Also require BOTH roles, installed PTK and no driver key errors.
}
// The adapter always uses CONTROL_PORT; no OS Ethernet socket is exposed.
int l2_packet_send(struct l2_packet_data* socket,const u8* dest,u16 proto,const u8* data,size_t len) {
    (void)socket;(void)dest;(void)proto;(void)data;(void)len;return -1;
}

struct pocket_rsn* pocket_rsn_create(const uint8_t own[6],const uint8_t bssid[6],
    const uint8_t pmk[32],unsigned rekey,const struct pocket_rsn_callbacks* cb,void* ctx) {
    if(!own || !bssid || !pmk || !cb || !cb->send || !cb->key || own[0]&1 || bssid[0]&1)return NULL;
    unsigned slot=0;while(slot<4 && contexts[slot])++slot;if(slot==4)return NULL;
    struct pocket_rsn* p=os_zalloc(sizeof(*p));if(!p)return NULL;
    p->callbacks=*cb;p->context=ctx;p->wpa.port=p;
    memcpy(p->wpa.own_addr,own,6);memcpy(p->wpa.bssid,bssid,6);
    p->wpa.drv_flags=WPA_DRIVER_FLAGS_CONTROL_PORT;p->wpa.ssid.group_rekey=rekey;
    p->rsn=ibss_rsn_init(&p->wpa,&p->wpa.ssid);
    if(!p->rsn){os_free(p);return NULL;}
    ibss_rsn_set_psk(p->rsn,pmk);contexts[slot]=p;return p;
}
int pocket_rsn_start(struct pocket_rsn* p,const uint8_t peer[6]) {
    if(!p || !peer || peer[0]&1 || !memcmp(peer,p->wpa.own_addr,6))return -1;
    if(p->bound && memcmp(p->peer,peer,6))return -1;
    memcpy(p->peer,peer,6);p->bound=1;return ibss_rsn_start(p->rsn,peer);
}
int pocket_rsn_receive(struct pocket_rsn* p,const uint8_t peer[6],int kind,const uint8_t* data,size_t len,int encrypted) {
    if(!p || !data || !peer || !p->bound || memcmp(peer,p->peer,6) || len>1024)return -1;
    if(kind==POCKET_RSN_AUTH) {
        if(encrypted)return -1;
        if(len!=30 || data[0]!=0xb0 || data[1] || memcmp(data+4,p->wpa.own_addr,6) ||
            memcmp(data+10,peer,6) || memcmp(data+16,p->wpa.bssid,6))return -1;
        ibss_rsn_handle_auth(p->rsn,data,len);return 0;
    }
    if(kind!=POCKET_RSN_EAPOL || len<4 || (encrypted!=0 && encrypted!=1))return -1;
    return ibss_rsn_rx_eapol(p->rsn,peer,data,len,encrypted?FRAME_ENCRYPTED:FRAME_NOT_ENCRYPTED);
}
int pocket_rsn_ready(struct pocket_rsn* p) {
    return p && !p->key_error && p->port_authorized && p->pairwise_installed && p->rsn->peers &&
        (p->rsn->peers->authentication_status&IBSS_RSN_REPORTED_PTK)!=0;
}
void pocket_rsn_poll(void) {
    pocket_eloop_poll();
    for(unsigned i=0;i<4;++i)if(contexts[i]) {
        struct pocket_rsn* p=contexts[i];int ready=pocket_rsn_ready(p);
        if(ready!=p->reported){p->reported=ready;if(p->callbacks.authorized)p->callbacks.authorized(p->context,ready);}
    }
}
void pocket_rsn_destroy(struct pocket_rsn* p) {
    if(!p)return;
    for(unsigned i=0;i<4;++i)if(contexts[i]==p)contexts[i]=NULL;
    forced_memzero(p->rsn->psk,sizeof(p->rsn->psk));
    ibss_rsn_deinit(p->rsn);
    forced_memzero(p,sizeof(*p));os_free(p);
}
