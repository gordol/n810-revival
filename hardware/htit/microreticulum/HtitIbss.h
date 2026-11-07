#ifdef HTIT_EXECUTOR
#include "executor/Transport.h"
#endif
#pragma once
// Experimental IBSS IPv4/UDP bearer. Called only from the application loop.
#include <Arduino.h>
#include <esp_event.h>
#include <esp_bt.h>
#include <esp_heap_caps.h>
#include <esp_wifi.h>
#include <esp_timer.h>
#include <freertos/queue.h>
#include <atomic>
#ifdef HTIT_IBSS_RSN
#include "HTITPrivate.h"
#include "../../experiments/ibss-rsn/rsn_link.h"
#ifndef HTIT_RSN_PMK
#error "Secure IBSS requires a generated private HTIT_RSN_PMK; no default key exists"
#endif
#endif

namespace HtitIbss {
static void (*udp_in)(const uint8_t*,size_t);
static uint32_t udp_rx,udp_tx,udp_seen,udp_bad,ip_bad,wrong_ip;
static bool busy,ready;
static StaticQueue_t queue_control, management_control;
static constexpr size_t DATA_FRAMES=32, MANAGEMENT_FRAMES=4;
static std::atomic<uint32_t> data_drops{0},management_drops{0},peer_beacons_rx{0},data_high_water{0};
#ifdef HTIT_IBSS_RSN
static constexpr char ssid[] = "Pocket-RSN-Lab";
static constexpr uint8_t channel = 1;
static const uint8_t bssid[6] = {0x02,0x4e,0x38,0x31,0x30,0x02};
#else
static constexpr char ssid[] = "Pocket-IBSS-Lab";
static constexpr uint8_t channel = 6;
static const uint8_t bssid[6] = {0x02,0x4e,0x38,0x31,0x30,0x01};
#endif
static const uint8_t ip[4] = {10,81,0,1};
static uint8_t mac[6];
#ifdef HTIT_IBSS_RSN
static constexpr size_t frame_capacity=640;
#else
static constexpr size_t frame_capacity=1600;
#endif
struct Frame { uint16_t len; int8_t rssi; uint8_t data[frame_capacity]; };
static QueueHandle_t frames,management_frames;
static uint32_t beacons, probes, arp_requests, echo_requests, tx_errors;
static esp_err_t last_tx_error=ESP_OK;
static uint32_t last_activity;

static uint16_t be16(const uint8_t *p) { return uint16_t(p[0])<<8 | p[1]; }
static void put16(uint8_t *p,uint16_t v) { p[0]=v>>8;p[1]=v; }
static uint16_t checksum(const uint8_t *p,size_t n) {
  uint32_t sum=0;while(n>1){sum+=be16(p);p+=2;n-=2;}if(n)sum+=uint16_t(*p)<<8;
  while(sum>>16)sum=(sum&65535)+(sum>>16);return ~sum;
}
static bool transmit(uint8_t *data,size_t len) {
  esp_err_t err=esp_wifi_80211_tx(WIFI_IF_STA,data,len,true);
  if(err!=ESP_OK){++tx_errors;if(err!=last_tx_error){last_tx_error=err;ERRORF("IBSS raw TX failed: %s (0x%x)",esp_err_to_name(err),unsigned(err));}return false;}
  return true;
}
static size_t header(uint8_t *p,uint8_t type,const uint8_t *dest) {
  memset(p,0,24);p[0]=type;memcpy(p+4,dest,6);memcpy(p+10,mac,6);memcpy(p+16,bssid,6);return 24;
}
static void beacon(bool probe,const uint8_t *dest) {
  uint8_t p[160];size_t n=header(p,probe?0x50:0x80,dest);
  uint64_t tsf=esp_timer_get_time();memcpy(p+n,&tsf,8);n+=8;
  p[n++]=100;p[n++]=0; // 100 TU beacon interval
  p[n++]=0x22;p[n++]=0; // IBSS + short preamble; ESS/privacy off
  p[n++]=0;p[n++]=sizeof(ssid)-1;memcpy(p+n,ssid,sizeof(ssid)-1);n+=sizeof(ssid)-1;
  const uint8_t rates[]={1,4,0x82,0x84,0x8b,0x96};memcpy(p+n,rates,sizeof(rates));n+=sizeof(rates);
  p[n++]=3;p[n++]=1;p[n++]=channel;
  p[n++]=6;p[n++]=2;p[n++]=0;p[n++]=0; // IBSS parameter: ATIM window zero
  if(transmit(p,n)){if(probe)++probes;else ++beacons;}
}
static bool ethernet(const uint8_t *dest,uint16_t type,const uint8_t *payload,size_t len) {
#ifdef HTIT_IBSS_RSN
  bool ok=htit_rsn_send(dest,type,payload,len);if(!ok)++tx_errors;else last_activity=millis();return ok;
#else
  if(len>1500)return false;
  uint8_t p[1532];size_t n=header(p,0x08,dest);
  const uint8_t snap[]={0xaa,0xaa,3,0,0,0};memcpy(p+n,snap,6);n+=6;
  put16(p+n,type);n+=2;memcpy(p+n,payload,len);n+=len;bool ok=transmit(p,n);last_activity=millis();return ok;
#endif
}
static void receive(void *buf,wifi_promiscuous_pkt_type_t type) {
  if(type!=WIFI_PKT_MGMT && type!=WIFI_PKT_DATA)return;
  auto *packet=static_cast<wifi_promiscuous_pkt_t*>(buf);
  if(packet->rx_ctrl.sig_len<28 || packet->rx_ctrl.sig_len>1604)return;
  const uint8_t* raw=packet->payload;
  if(raw[0]!=0x40 && memcmp(raw+16,bssid,6))return;
  // Beacons do not require core processing and must never evict packets
  // while crypto/filesystem work occupies the cooperative core loop.
  if(raw[0]==0x80){if(memcmp(raw+10,mac,6))++peer_beacons_rx;return;}
  bool management=raw[0]==0x40;
  if(!management && ((raw[0]&0xfc)!=0x08 || (raw[1]&0x43)))return;
  const uint8_t broadcast[6]={255,255,255,255,255,255};
  if(!management && memcmp(raw+4,mac,6) && memcmp(raw+4,broadcast,6))return;
  Frame f;f.len=packet->rx_ctrl.sig_len-4;f.rssi=packet->rx_ctrl.rssi;
  memcpy(f.data,packet->payload,f.len);
  auto queue=management?management_frames:frames;
  if(xQueueSend(queue,&f,0)!=pdTRUE){if(management)++management_drops;else ++data_drops;}
  else if(!management){uint32_t used=uxQueueMessagesWaiting(frames),old=data_high_water.load();while(used>old&&!data_high_water.compare_exchange_weak(old,used)){} }
}
static void process(const Frame &f) {
  const uint8_t *p=f.data;const size_t n=f.len;
  if(n<24 || !memcmp(p+10,mac,6))return;
  if(p[0]==0x40){ // Probe request: wildcard or matching SSID
    for(size_t i=24;i+2<=n;){size_t len=p[i+1];if(i+2+len>n)break;
      if(p[i]==0 && (len==0 || (len==sizeof(ssid)-1 && !memcmp(p+i+2,ssid,len)))){beacon(true,p+10);return;}i+=2+len;}
    return;
  }
  if(memcmp(p+16,bssid,6))return;
  if(p[0]==0x80)return;
  if((p[0]&0xfc)!=0x08 || (p[1]&0x43) || n<32)return; // non-QoS, unencrypted, no DS
  const uint8_t snap[]={0xaa,0xaa,3,0,0,0};if(memcmp(p+24,snap,6))return;
  const uint16_t type=be16(p+30);const uint8_t *body=p+32;size_t len=n-32;
  if(type==0x0806 && len>=28 && be16(body)==1 && be16(body+2)==0x0800 && body[4]==6 && body[5]==4 && be16(body+6)==1 && !memcmp(body+24,ip,4)) {
    ++arp_requests;uint8_t reply[28];memcpy(reply,body,28);put16(reply+6,2);
    memcpy(reply+8,mac,6);memcpy(reply+14,ip,4);memcpy(reply+18,body+8,6);memcpy(reply+24,body+14,4);
    ethernet(p+10,0x0806,reply,28);return;
  }
  if(type!=0x0800 || len<28 || (body[0]>>4)!=4)return;
  const uint8_t subnet_broadcast[]={10,81,0,255},all_broadcast[]={255,255,255,255};
  if(body[9]==17)++udp_seen;
  if(memcmp(body+16,ip,4) && memcmp(body+16,subnet_broadcast,4) && memcmp(body+16,all_broadcast,4)){++wrong_ip;return;}
  if(!memcmp(body+12,ip,4))return;
  size_t ihl=(body[0]&15)*4,total=be16(body+2);
  if(ihl<20 || ihl>60 || total<ihl+8 || total>len || total>1500 || (be16(body+6)&0x3fff))return;
  if(checksum(body,ihl)!=0){++ip_bad;return;}
  if(body[9]==17){
    if(total<ihl+8)return;
    const uint8_t *u=body+ihl;size_t ul=be16(u+4);
    if(be16(u+2)!=4242 || ul<8 || ul!=total-ihl || ul-8>500){++udp_bad;INFOF("IBSS UDP header reject dst=%u len=%u total=%u ihl=%u",be16(u+2),ul,total,ihl);return;}
    if(be16(u+6)) { // Validate optional UDP checksum with IPv4 pseudoheader.
      uint32_t sum=17+ul;
      for(size_t i=12;i<20;i+=2)sum+=be16(body+i);
      for(size_t i=0;i+1<ul;i+=2)sum+=be16(u+i);
      if(ul&1)sum+=uint32_t(u[ul-1])*256u;
      while(sum>>16)sum=(sum&0xffff)+(sum>>16);
      if(sum!=0xffff){++udp_bad;INFOF("IBSS UDP checksum reject field=%04x residual=%04x len=%u tail=%02x",be16(u+6),uint16_t(~sum),ul,u[ul-1]);return;}
    }
    if(ul>8 && udp_in){
#ifdef HTIT_EXECUTOR
      HtitCoreStage stage(4);
#endif
      ++udp_rx;udp_in(u+8,ul-8);
    }return;
  }
  if(body[9]!=1)return;
  if(body[ihl]!=8 || body[ihl+1]!=0 || checksum(body+ihl,total-ihl)!=0)return;
  ++echo_requests;uint8_t reply[frame_capacity];memcpy(reply,body,total);
  memcpy(reply+16,body+12,4);memcpy(reply+12,ip,4);reply[8]=64;
  reply[10]=reply[11]=0;put16(reply+10,checksum(reply,ihl));
  reply[ihl]=0;reply[ihl+2]=reply[ihl+3]=0;put16(reply+ihl+2,checksum(reply+ihl,total-ihl));
  ethernet(p+10,0x0800,reply,total);
}
static bool send_udp(const uint8_t *data,size_t len) {
  if(!ready || !len || len>500)return false;
  uint8_t packet[528]={};packet[0]=0x45;put16(packet+2,28+len);
  packet[8]=1;packet[9]=17;memcpy(packet+12,ip,4);
  const uint8_t dest_ip[]={10,81,0,255};memcpy(packet+16,dest_ip,4);
  put16(packet+10,checksum(packet,20));put16(packet+20,4242);put16(packet+22,4242);
  put16(packet+24,8+len);memcpy(packet+28,data,len); // UDP checksum zero is valid for IPv4.
  const uint8_t broadcast[]={255,255,255,255,255,255};
  bool ok=ethernet(broadcast,0x0800,packet,28+len);if(ok)++udp_tx;return ok;
}
static bool begin() {
#ifdef HTIT_IBSS_RSN
  static const uint8_t pmk[32]=HTIT_RSN_PMK;
  static const uint8_t peer[6]={0,2,0xee,0xc0,0xff,0xee};
  ready=htit_rsn_begin(pmk,peer,[](const uint8_t* source,const uint8_t* dest,uint16_t type,const uint8_t* payload,size_t len){
    if(len>600)return;
    // Normalize an authenticated Ethernet payload for the existing IPv4/UDP
    // parser. No raw-radio callback can enter this path in the secure target.
    Frame frame{};frame.len=32+len;frame.data[0]=8;
    memcpy(frame.data+4,dest,6);memcpy(frame.data+10,source,6);memcpy(frame.data+16,bssid,6);
    const uint8_t snap[]={0xaa,0xaa,3,0,0,0};memcpy(frame.data+24,snap,6);put16(frame.data+30,type);memcpy(frame.data+32,payload,len);
    process(frame);
  });
  if(ready&&esp_wifi_get_mac(WIFI_IF_STA,mac)!=ESP_OK)ready=false;
  if(ready)INFOF("HTIT RSN IBSS UDP/4242: SSID=%s channel=%u IP=10.81.0.1 CCMP; peer authorization required",ssid,channel);
  return ready;
#else
  auto storage=static_cast<uint8_t*>(heap_caps_malloc(DATA_FRAMES*sizeof(Frame),MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));
  auto management_storage=static_cast<uint8_t*>(heap_caps_malloc(MANAGEMENT_FRAMES*sizeof(Frame),MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));
  if(!storage||!management_storage){heap_caps_free(storage);heap_caps_free(management_storage);return false;}
  frames=xQueueCreateStatic(DATA_FRAMES,sizeof(Frame),storage,&queue_control);
  management_frames=xQueueCreateStatic(MANAGEMENT_FRAMES,sizeof(Frame),management_storage,&management_control);
  if(!frames||!management_frames){if(frames)vQueueDelete(frames);if(management_frames)vQueueDelete(management_frames);heap_caps_free(storage);heap_caps_free(management_storage);return false;}
  esp_err_t event=esp_event_loop_create_default();
  if(event!=ESP_OK && event!=ESP_ERR_INVALID_STATE)return false;
  wifi_init_config_t cfg=WIFI_INIT_CONFIG_DEFAULT();
  cfg.static_rx_buf_num=4;cfg.dynamic_rx_buf_num=8;
  cfg.tx_buf_type=1;cfg.static_tx_buf_num=0;cfg.dynamic_tx_buf_num=8;
  cfg.cache_tx_buf_num=0;cfg.mgmt_sbuf_num=6;
  cfg.ampdu_rx_enable=0;cfg.ampdu_tx_enable=0;cfg.rx_ba_win=4;
  esp_err_t init=esp_wifi_init(&cfg);
  if(init!=ESP_OK){ERRORF("IBSS Wi-Fi init failed: %s",esp_err_to_name(init));return false;}
  ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
  ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
  ESP_ERROR_CHECK(esp_wifi_start());
  ESP_ERROR_CHECK(esp_wifi_set_ps(WIFI_PS_MIN_MODEM));
  ESP_ERROR_CHECK(esp_wifi_set_protocol(WIFI_IF_STA,WIFI_PROTOCOL_11B|WIFI_PROTOCOL_11G));
  ESP_ERROR_CHECK(esp_wifi_get_mac(WIFI_IF_STA,mac));
  ESP_ERROR_CHECK(esp_wifi_set_channel(channel,WIFI_SECOND_CHAN_NONE));
  wifi_promiscuous_filter_t filter={};filter.filter_mask=WIFI_PROMIS_FILTER_MASK_MGMT|WIFI_PROMIS_FILTER_MASK_DATA;
  ESP_ERROR_CHECK(esp_wifi_set_promiscuous_filter(&filter));
  ESP_ERROR_CHECK(esp_wifi_set_promiscuous_rx_cb(receive));
  ESP_ERROR_CHECK(esp_wifi_set_promiscuous(true));
  ready=true;
  INFOF("IBSS experimental UDP/4242: SSID=%s channel=%u IP=10.81.0.1 OPEN",ssid,channel);
  return true;
#endif
}
static void tick() {
  if(!ready || busy)return;busy=true;
  struct Guard {~Guard(){busy=false;}} guard;
#ifdef HTIT_IBSS_RSN
  htit_rsn_tick();
  static uint32_t last_secure_report;if(millis()-last_secure_report>=10000){last_secure_report=millis();INFOF("RSN_IP arp=%u icmp=%u udp_rx=%u udp_tx=%u tx_err=%u udp_seen=%u udp_bad=%u ip_bad=%u wrong_ip=%u",arp_requests,echo_requests,udp_rx,udp_tx,tx_errors,udp_seen,udp_bad,ip_bad,wrong_ip);}
  return;
#else
  static uint32_t last_beacon,last_report;uint32_t now=millis();

  const uint8_t broadcast[6]={255,255,255,255,255,255};
  if(now-last_beacon>=102){last_beacon=now;beacon(false,broadcast);}
  Frame f;for(int i=0;i<2 && xQueueReceive(management_frames,&f,0)==pdTRUE;++i)process(f);
  for(int i=0;i<6 && xQueueReceive(frames,&f,0)==pdTRUE;++i)process(f);
  if(now-last_report>=5000){last_report=now;INFOF("IBSS beacon=%u peer=%u arp=%u icmp=%u udp_rx=%u udp_tx=%u tx_err=%u drops=%u seen=%u udp_bad=%u ip_bad=%u wrong_ip=%u heap=%u data_drop=%u mgmt_drop=%u data_high=%u internal_largest=%u psram_free=%u tx_code=%u",beacons,peer_beacons_rx.load(),arp_requests,echo_requests,udp_rx,udp_tx,tx_errors,data_drops.load()+management_drops.load(),udp_seen,udp_bad,ip_bad,wrong_ip,ESP.getFreeHeap(),data_drops.load(),management_drops.load(),data_high_water.load(),heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT),heap_caps_get_free_size(MALLOC_CAP_SPIRAM),unsigned(last_tx_error));}
  busy=false;
#endif
}

} // namespace HtitIbss
class HtitIbssInterface : public RNS::InterfaceImpl {
public:
  HtitIbssInterface():RNS::InterfaceImpl("HTIT IBSS UDP") {
    _IN=true;_OUT=true;_HW_MTU=500;_bitrate=1000000;active=this;
  }
protected:
  bool start() override {
    HtitIbss::udp_in=[](const uint8_t* data,size_t len){
      if(active && active->_online)active->handle_incoming(RNS::Bytes(data,len));
    };
    _online=HtitIbss::begin();return _online;
  }
  bool send_outgoing(const RNS::Bytes& data) override {
#ifdef HTIT_EXECUTOR
    if(!htit_executor_generation_live(htit_executor_packet_generation(data.data(),data.size()),20))return false;
#endif
    if(!_online || !HtitIbss::send_udp(data.data(),data.size()))return false;
    handle_outgoing(data);return true;
  }
  void loop() override {HtitIbss::tick();}
private:
  static HtitIbssInterface* active;
};
HtitIbssInterface* HtitIbssInterface::active=nullptr;
