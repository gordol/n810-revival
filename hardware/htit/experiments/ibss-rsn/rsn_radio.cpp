// Bounded native IBSS RSN interoperability lab. Not the deployable hub yet.
// Runtime-only PMK; no open-data fallback. Upstream owns RSN/rekey state.
#include <Arduino.h>
#include <esp_event.h>
#include <esp_wifi.h>
#include <esp_coexist.h>
#include "rsn-port/rsn_port.h"
#include "rx_observer.h"
#include "ccmp.h"
#include "tx_selector.h"
#include <mbedtls/sha256.h>
#include <freertos/queue.h>
#include "rsn_link.h"
#ifdef HTIT_RSN_INTEGRATED
// The full firmware owns USB KISS. This module must never write debug text to
// that byte stream; protocol diagnostics are confined to the lab build.
struct RsnSilentLog {
 template<class... A> int printf(const char*,A...){return 0;}
 template<class T> void print(T){}
 void println(){}
 template<class T> void println(T){}
};
static RsnSilentLog rsn_silent_log;
#define Serial rsn_silent_log
#endif
extern "C" void ic_set_bssid(uint8_t,const uint8_t*);
extern "C" void wDev_Insert_KeyEntry(uint8_t,uint8_t,uint8_t,uint8_t*,uint8_t,uint8_t*,size_t,bool,bool);
extern "C" int hal_crypto_is_key_valid(uint32_t);
extern "C" int pocket_wpa_wpa_debug_level;
static uint8_t own[6],peer[6],net[6]={2,0x4e,0x38,0x31,0x30,2};
static const uint8_t broadcast[6]={255,255,255,255,255,255};
static const char ssid[]="Pocket-RSN-Lab";
static pocket_rsn* rsn;
static HtitRsnEthernet ethernet_received=nullptr;
static CcmpEpoch ptk{},rxgtk[4]{},txgtk[4]{};
static bool pair_ready=false,rx_ready[4]{},tx_ready[4]{},active=false,attempted=false,authorized=false,peer_started=false;
static uint8_t command[44];static size_t command_used=0;static uint32_t end_at,beacon_at,status_at,group_at;
static unsigned channel,tx_group=0,auth_rx=0,eapol_rx=0,eapol_tx=0,key_changes=0,protected_rx=0,dropped=0;
struct PlainFrame {uint16_t length;uint8_t state;uint8_t frame[300];};
static QueueHandle_t plain_queue;static bool public_management=false;
static void public_rx(void* data,wifi_promiscuous_pkt_type_t type){
 if(type!=WIFI_PKT_DATA&&type!=WIFI_PKT_MGMT)return;
 auto* r=static_cast<wifi_promiscuous_pkt_t*>(data);const uint8_t* h=r->payload;
 unsigned n=r->rx_ctrl.sig_len;if(n<34||n>304||r->rx_ctrl.rx_state||h[1]&0x43||memcmp(h+4,own,6)||memcmp(h+10,peer,6)||memcmp(h+16,net,6))return;
 const uint8_t snap[]={0xaa,0xaa,3,0,0,0,0x88,0x8e};
 if(h[0]!=0xb0&&(h[0]!=8||n<40||memcmp(h+24,snap,8)))return;
 PlainFrame f;f.length=n-4;f.state=r->rx_ctrl.rx_state;memcpy(f.frame,h,f.length);xQueueSend(plain_queue,&f,0);
}
static void erase(void* p,size_t n){volatile uint8_t* q=(volatile uint8_t*)p;while(n--)*q++=0;}
static void header(uint8_t* p,uint8_t type,const uint8_t* dest){memset(p,0,24);p[0]=type;memcpy(p+4,dest,6);memcpy(p+10,own,6);memcpy(p+16,net,6);}
static int transmit(const uint8_t* p,size_t n){return esp_wifi_80211_tx(WIFI_IF_STA,p,n,true)==ESP_OK?0:-1;}
static void beacon(){
 uint8_t p[128];header(p,0x80,broadcast);uint64_t t=esp_timer_get_time();memcpy(p+24,&t,8);
 size_t n=32;p[n++]=100;p[n++]=0;p[n++]=0x32;p[n++]=0;
 p[n++]=0;p[n++]=sizeof(ssid)-1;memcpy(p+n,ssid,sizeof(ssid)-1);n+=sizeof(ssid)-1;
 const uint8_t ies[]={1,4,0x82,0x84,0x8b,0x96,3,1,0,6,2,0,0,
  48,20,1,0,0,15,172,4,1,0,0,15,172,4,1,0,0,15,172,2,0,0};
 memcpy(p+n,ies,sizeof(ies));p[n+8]=channel;n+=sizeof(ies);transmit(p,n);
}
static int data(const uint8_t* dest,uint16_t type,const uint8_t* body,size_t n,bool encrypted){
#ifdef HTIT_RSN_INTEGRATED
 constexpr size_t capacity=600;
#else
 constexpr size_t capacity=1350;
#endif
 if(n>capacity)return -1;
 uint8_t h[24],plain[capacity+8],frame[capacity+48];header(h,8,dest);
 const uint8_t snap[]={0xaa,0xaa,3,0,0,0};memcpy(plain,snap,6);plain[6]=type>>8;plain[7]=type;memcpy(plain+8,body,n);n+=8;
 if(!encrypted){if(type!=0x888e)return -1;memcpy(frame,h,24);memcpy(frame+24,plain,n);return transmit(frame,n+24);}
 bool group=dest[0]&1;CcmpEpoch* e=group?&txgtk[tx_group]:&ptk;
 if((group?!tx_ready[tx_group]:!pair_ready))return -1;
 memcpy(e->receiver,dest,6);int size=ccmp_seal(e,h,plain,n,frame,sizeof(frame));if(size<0)return -1;
 // The selected hardware key encrypts both unicast and group frames. Give
 // it plaintext, a fresh IV and tag space, never pre-encrypted ciphertext.
 memcpy(frame+32,plain,n);memset(frame+32+n,0,8);
 return transmit(frame,size);
}
static int send(void*,int kind,const uint8_t* dest,const uint8_t* p,size_t n,int encrypted){
 if(memcmp(dest,peer,6))return -1;
 if(kind==POCKET_RSN_AUTH){if(n!=30||p[0]!=0xb0||p[1]||memcmp(p+10,own,6)||memcmp(p+16,net,6))return -1;int r=transmit(p,n);Serial.printf("AUTH_TX result=%d\n",r);return r;}
 if(kind!=POCKET_RSN_EAPOL)return -1;
 ++eapol_tx;int r=data(dest,0x888e,p,n,encrypted);Serial.printf("EAPOL_TX length=%u encrypted=%u result=%d\n",unsigned(n),encrypted,r);return r;
}
static int key(void*,const uint8_t* addr,int alg,int index,int tx,const uint8_t* k,size_t n,const uint8_t* seq,size_t seq_len,int flags){
 if(index<0||index>3||seq_len>6)return -1;
 // Deletion revokes software authorization before any further dispatch.
 if(alg==0||!n){if(index==0)pair_ready=false;else if(flags&8)tx_ready[index]=false;else rx_ready[index]=false;return 0;}
 if(alg!=3||n!=16)return -1;
 bool group=index!=0,own_group=group&&(flags&8);
 CcmpEpoch* e=group?(own_group?&txgtk[index]:&rxgtk[index]):&ptk;
 bool installed=group?(own_group?tx_ready[index]:rx_ready[index]):pair_ready;
 bool same_key=e->key_valid&&!memcmp(e->key,k,16);
 uint64_t rx_floor=0;if(group&&!own_group)for(size_t i=0;i<seq_len;++i)rx_floor|=uint64_t(seq[i])<<(8*i);
 ccmp_install_key(e,k,rx_floor);e->key_id=index;memcpy(e->bssid,net,6);
 memcpy(e->transmitter,own_group||!group?own:peer,6);memcpy(e->receiver,own,6);
 if(installed&&same_key)return 0; // Preserve PN; only raise the authenticated RSC.
 if(!group){
  wDev_Insert_KeyEntry(3,0,0,peer,4,e->key,16,true,false);
  wDev_Insert_KeyEntry(3,0,0,peer,0,e->key,16,true,false);
  pair_ready=hal_crypto_is_key_valid(1u<<4)&&hal_crypto_is_key_valid(1);
  probe_tx_selector_key(0,0);if(!pair_ready)return -1;
 }else if(own_group){unsigned slot=5+index;wDev_Insert_KeyEntry(3,0,index,own,slot,e->key,16,true,false);tx_ready[index]=hal_crypto_is_key_valid(1u<<slot);if(!tx_ready[index])return -1;tx_group=index;probe_tx_selector_key(index,slot);}
 else {wDev_Insert_KeyEntry(3,0,index,peer,index,e->key,16,true,false);rx_ready[index]=hal_crypto_is_key_valid(1u<<index);if(!rx_ready[index])return -1;}
 ++key_changes;Serial.printf("KEY installed index=%d tx=%d flags=%d changes=%u\n",index,tx,flags,key_changes);return 0;
}
static int get_seqnum(void*,int index,uint8_t seq[8]){
 if(index<1||index>3||!tx_ready[index])return -1;
 memset(seq,0,8);uint64_t pn=txgtk[index].tx_pn;
 for(unsigned i=0;i<6;++i)seq[i]=uint8_t(pn>>(8*i));
 return 0;
}
static void ready(void*,int value){authorized=value;Serial.printf("RSN_AUTHORIZED %d\n",value);}
static unsigned be16(const uint8_t* p){return unsigned(p[0])*256+p[1];}
static uint16_t checksum(const uint8_t* p,size_t n){uint32_t sum=0;while(n>1){sum+=be16(p);p+=2;n-=2;}if(n)sum+=unsigned(*p)<<8;while(sum>>16)sum=(sum&65535)+(sum>>16);return ~sum;}
static void put16(uint8_t* p,uint16_t v){p[0]=v>>8;p[1]=v;}
static void process(const ProbeRawRx& r){
 const uint8_t* h=r.frame;if(r.state||r.length<24)return;
 if(h[0]==0xb0){if(r.sig_length!=34||r.length<30)return;if(!peer_started){if(pocket_rsn_start(rsn,peer))return;peer_started=true;}++auth_rx;pocket_rsn_receive(rsn,peer,POCKET_RSN_AUTH,h,30,0);return;}
 if(h[0]!=8||(h[1]&0x87)||(h[22]&15))return;
 const uint8_t* p;size_t n;bool encrypted=h[1]&0x40;
 if(encrypted){
  if(r.length<32||r.sig_length<44||h[26]||h[27]!=(0x20|((h[27]>>6)<<6))){++dropped;return;}
  unsigned id=h[27]>>6;bool group=h[4]&1;
  if((group?(!id||!rx_ready[id]):(id||!pair_ready))){++dropped;return;}
  CcmpEpoch* e=group?&rxgtk[id]:&ptk;n=r.sig_length-44;
  if(n>1358||r.length<32+n||r.dma_length!=((28+32+n+3)&~size_t(3))){++dropped;return;}
  uint64_t pn=h[24]|(uint64_t(h[25])<<8);for(unsigned i=0;i<4;++i)pn|=uint64_t(h[28+i])<<(16+8*i);
  if(!pn||pn<=e->rx_pn){++dropped;return;}e->rx_pn=pn;p=h+32;++protected_rx;
 }else {if(r.sig_length<36||r.length<r.sig_length-4)return;p=h+24;n=r.sig_length-28;}
 const uint8_t snap[]={0xaa,0xaa,3,0,0,0};if(n<8||memcmp(p,snap,6))return;
 unsigned type=be16(p+6);p+=8;n-=8;
 if(type==0x888e){if(!peer_started){if(pocket_rsn_start(rsn,peer))return;peer_started=true;}++eapol_rx;uint8_t digest[32];mbedtls_sha256_ret(p,n,digest,0);Serial.printf("EAPOL_RX_HASH length=%u hash=",unsigned(n));for(uint8_t b:digest)Serial.printf("%02x",b);Serial.println();
  // Wire ciphertext only, before upstream decrypts KDEs. Bounded lab evidence;
  // never dump decrypted keys, PMK, PTK or GTK. Removed from deployable builds.
  if(!encrypted&&n<=256){Serial.print("WIRE_EAPOL ");for(size_t i=0;i<n;++i)Serial.printf("%02x",p[i]);Serial.println();}
  int result=pocket_rsn_receive(rsn,peer,POCKET_RSN_EAPOL,p,n,encrypted);Serial.printf("EAPOL_RX length=%u encrypted=%u result=%d\n",unsigned(n),encrypted,result);return;}
 if(!encrypted||!authorized||!pocket_rsn_ready(rsn)){++dropped;return;}
 if(ethernet_received){ethernet_received(h+10,h+4,type,p,n);return;}
#ifndef HTIT_RSN_INTEGRATED
 // Secure ARP reachability gate; no IP/application plaintext is dispatched.
 const uint8_t ip[4]={10,81,0,1};
 if(type==0x806&&n>=28&&be16(p)==1&&be16(p+2)==0x800&&p[4]==6&&p[5]==4&&be16(p+6)==1&&!memcmp(p+24,ip,4)){
  uint8_t reply[28];memcpy(reply,p,28);reply[6]=0;reply[7]=2;memcpy(reply+8,own,6);memcpy(reply+14,ip,4);memcpy(reply+18,p+8,6);memcpy(reply+24,p+14,4);
  Serial.printf("SECURE_ARP reply=%d\n",data(peer,0x806,reply,28,true));
 }
 if(type==0x800&&n>=28&&(p[0]>>4)==4&&p[9]==1&&!memcmp(p+16,ip,4)){
  size_t ihl=(p[0]&15)*4,total=be16(p+2);
  if(ihl<20||ihl>60||total<ihl+8||total>n||total>1350||(be16(p+6)&0x3fff)||checksum(p,ihl)||p[ihl]!=8||p[ihl+1]||checksum(p+ihl,total-ihl))return;
  uint8_t reply[1350];memcpy(reply,p,total);memcpy(reply+16,p+12,4);memcpy(reply+12,ip,4);reply[8]=64;reply[10]=reply[11]=0;put16(reply+10,checksum(reply,ihl));reply[ihl]=0;reply[ihl+2]=reply[ihl+3]=0;put16(reply+ihl+2,checksum(reply+ihl,total-ihl));
  Serial.printf("SECURE_ICMP reply=%d\n",data(peer,0x800,reply,total,true));
 }
#endif
}
static void stop(){
 probe_rx_observer_stop();if(rsn)pocket_rsn_destroy(rsn);rsn=nullptr;esp_wifi_stop();esp_wifi_deinit();probe_tx_selector_stop();if(plain_queue){vQueueDelete(plain_queue);plain_queue=nullptr;}active=false;authorized=false;
 erase(&ptk,sizeof(ptk));erase(rxgtk,sizeof(rxgtk));erase(txgtk,sizeof(txgtk));erase(command,sizeof(command));Serial.println("STOP radios off");
}
static void start(unsigned rekey_override=0){
 attempted=true;if(memcmp(command,"PL01",4)||command[4]<1||command[4]>11||(command[5]&1)){Serial.println("REJECT config");erase(command,sizeof(command));return;}
 channel=command[4];public_management=command[43]&128;memcpy(peer,command+5,6);wifi_init_config_t config=WIFI_INIT_CONFIG_DEFAULT();config.nvs_enable=0;
#ifdef HTIT_RSN_INTEGRATED
 config.static_rx_buf_num=4;config.dynamic_rx_buf_num=8;config.tx_buf_type=1;config.static_tx_buf_num=0;config.dynamic_tx_buf_num=8;config.cache_tx_buf_num=0;config.mgmt_sbuf_num=6;config.ampdu_rx_enable=0;config.ampdu_tx_enable=0;config.rx_ba_win=4;
#endif
 esp_err_t event=esp_event_loop_create_default();
 if((event!=ESP_OK&&event!=ESP_ERR_INVALID_STATE)||esp_wifi_init(&config)!=ESP_OK||esp_wifi_set_storage(WIFI_STORAGE_RAM)!=ESP_OK||esp_wifi_set_mode(WIFI_MODE_STA)!=ESP_OK){Serial.println("FAIL init");erase(command,sizeof(command));return;}
#ifdef HTIT_RSN_INTEGRATED
 // SDK raw TX defaults to 1 Mbps. Shorten airtime so complete IBSS packets
 // can fit alongside Classic radio slots; 11 Mbps is advertised in our rates.
 if(esp_wifi_config_80211_tx_rate(WIFI_IF_STA,WIFI_PHY_RATE_11M_L)!=ESP_OK){esp_wifi_deinit();erase(command,sizeof(command));return;}
#endif
 if(esp_wifi_start()!=ESP_OK){esp_wifi_deinit();erase(command,sizeof(command));return;}
#ifdef HTIT_RSN_INTEGRATED
 // IDF 4.4 requires modem sleep for concurrent Classic Bluetooth/Wi-Fi.
 // The raw IBSS MAC remains awake while not associated to a stock Wi-Fi AP.
 const wifi_ps_type_t power_save=WIFI_PS_MIN_MODEM;
#else
 const wifi_ps_type_t power_save=WIFI_PS_NONE;
#endif
 active=true;if(esp_wifi_set_channel(channel,WIFI_SECOND_CHAN_NONE)!=ESP_OK||esp_wifi_set_ps(power_save)!=ESP_OK||esp_wifi_get_mac(WIFI_IF_STA,own)!=ESP_OK){stop();return;}
#ifdef HTIT_RSN_INTEGRATED
 // Raw IBSS never enters the SDK's associated-STA state. Request Wi-Fi RF
 // opportunity explicitly while retaining Classic Bluetooth coexistence.
 if(esp_coex_preference_set(ESP_COEX_PREFER_WIFI)!=ESP_OK){stop();return;}
#endif
 ic_set_bssid(0,net);probe_rx_observer_configure(own,peer,net);probe_tx_selector_configure(own,net);
#ifdef HTIT_RSN_INTEGRATED
 constexpr unsigned plain_frames=8;
#else
 constexpr unsigned plain_frames=16;
#endif
 plain_queue=xQueueCreate(plain_frames,sizeof(PlainFrame));wifi_promiscuous_filter_t filter{};filter.filter_mask=WIFI_PROMIS_FILTER_MASK_MGMT|WIFI_PROMIS_FILTER_MASK_DATA;
 if(!plain_queue||esp_wifi_set_promiscuous_filter(&filter)!=ESP_OK||esp_wifi_set_promiscuous_rx_cb(public_rx)!=ESP_OK||esp_wifi_set_promiscuous(true)!=ESP_OK){stop();return;}
 pocket_rsn_callbacks callbacks={send,key,ready,get_seqnum};unsigned rekey=rekey_override?rekey_override:(command[43]&127);rsn=pocket_rsn_create(own,net,command+11,rekey?rekey:30,&callbacks,nullptr);erase(command,sizeof(command));
 // Start the peer's retry budget only once it actually appears. Booting the
 // ESP before the Nokia must not exhaust the handshake before its first frame.
 if(!rsn){stop();return;}
 end_at=millis()+180000;beacon_at=status_at=0;Serial.println("START IBSS RSN channel configured; duration=180 seconds");
}
#ifndef HTIT_RSN_INTEGRATED
void setup(){Serial.begin(115200);pocket_wpa_wpa_debug_level=2;delay(200);Serial.println("IBSS RSN RADIO PROBE WIP; PL01 runtime command required; radios off");}
#endif
static void poll_radio(){
#ifndef HTIT_RSN_INTEGRATED
 if(!attempted){while(Serial.available()&&command_used<sizeof(command))command[command_used++]=Serial.read();if(command_used==sizeof(command))start();}
#endif
 if(active){if(end_at&&int32_t(millis()-end_at)>=0){stop();return;}if(int32_t(millis()-beacon_at)>=0){beacon();beacon_at=millis()+100;}
  ProbeRawRx r;unsigned budget=16;while(budget--&&probe_rx_observer_next(&r)){
   if(public_management&&!(r.frame[1]&0x40))continue;
   process(r);
  }
  PlainFrame plain;budget=16;while(budget--&&xQueueReceive(plain_queue,&plain,0)==pdTRUE){
   if(plain.frame[0]==8&&plain.length>=36){uint8_t digest[32];mbedtls_sha256_ret(plain.frame+32,plain.length-32,digest,0);Serial.print("PUBLIC_EAPOL_HASH ");for(uint8_t b:digest)Serial.printf("%02x",b);Serial.printf(" last=%u\n",plain.frame[plain.length-1]);}
   if(public_management){r={};r.state=plain.state;r.length=plain.length;r.sig_length=plain.length+4;memcpy(r.frame,plain.frame,plain.length);process(r);}
  }
  pocket_rsn_poll();
#ifdef HTIT_RSN_INTEGRATED
  extern void htit_rsn_diagnostics_poll();htit_rsn_diagnostics_poll();
#endif
  if(millis()-status_at>=5000){status_at=millis();auto s=probe_rx_observer_stats();
#ifdef HTIT_RSN_INTEGRATED
   unsigned mask=0;for(unsigned i=0;i<8;++i)if(hal_crypto_is_key_valid(1u<<i))mask|=1u<<i;
   printf("RSN_STATE ready=%u auth=%u eapol=%u/%u keys=%u protected=%u dropped=%u dma=%u overflow=%u hw_keys=%02x\n",authorized,auth_rx,eapol_rx,eapol_tx,key_changes,protected_rx,dropped,s.matching,s.overflow,mask);
#endif
   Serial.printf("STATUS ready=%u auth=%u eapol=%u/%u keys=%u protected=%u dropped=%u dma=%u overflow=%u stack_free=%u min_heap=%u tx_codes=%08x\n",authorized,auth_rx,eapol_rx,eapol_tx,key_changes,protected_rx,dropped,s.matching,s.overflow,unsigned(uxTaskGetStackHighWaterMark(nullptr)*sizeof(StackType_t)),ESP.getMinFreeHeap(),unsigned(probe_tx_selector_original_codes()));}
#ifndef HTIT_RSN_INTEGRATED
  if(authorized&&millis()-group_at>=5000){group_at=millis();const uint8_t marker[]="Pocket RSN group-data probe";Serial.printf("GROUP_PROBE index=%u result=%d\n",tx_group,data(broadcast,0x88b5,marker,sizeof(marker)-1,true));}
#endif
 }
}
#ifndef HTIT_RSN_INTEGRATED
void loop(){poll_radio();delay(1);}
#endif
bool htit_rsn_begin(const uint8_t pmk[32],const uint8_t selected_peer[6],HtitRsnEthernet callback){
 if(attempted||!pmk||!selected_peer||!callback)return false;
 uint8_t nonzero=0;for(unsigned i=0;i<32;++i)nonzero|=pmk[i];if(!nonzero)return false;
 memcpy(command,"PL01",4);command[4]=1;memcpy(command+5,selected_peer,6);memcpy(command+11,pmk,32);command[43]=128;
 extern void htit_rsn_diagnostics_begin();htit_rsn_diagnostics_begin();
 ethernet_received=callback;start(600);if(active)end_at=0;return active;
}
bool htit_rsn_ready(){return active&&authorized&&rsn&&pocket_rsn_ready(rsn);}
bool htit_rsn_send(const uint8_t dest[6],uint16_t type,const uint8_t* p,size_t n){return htit_rsn_ready()&&dest&&p&&data(dest,type,p,n,true)==0;}
void htit_rsn_tick(){poll_radio();}
