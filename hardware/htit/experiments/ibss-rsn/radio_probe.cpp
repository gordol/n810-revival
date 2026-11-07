// WIP protected-data radio-path experiment. NOT an authenticated RSN network.
// Radios stay off until one explicit USB command; no application/boot writes.
// Framework/PHY startup can alter NVS: back it up and restore it after a trial.
#include <Arduino.h>
#include <esp_event.h>
#include <esp_wifi.h>
#include <esp_system.h>
#include <freertos/queue.h>
#include <string.h>
#include "ccmp.h"
#ifdef HTIT_RX_OBSERVER
#include "rx_observer.h"
#include "hw_ccmp.h"
#include <mbedtls/sha256.h>
#endif
#ifdef HTIT_TX_SELECTOR
#include "tx_selector.h"
#endif

// Pinned IDF 4.4.7 private ABI used by Espressif's wpa_install_key.
// LAB ONLY: diagnostic fresh temporal key installation, not RSN pairing.
extern "C" int esp_wifi_set_sta_key_internal(int,uint8_t*,int,int,uint8_t*,size_t,uint8_t*,size_t,int);
// Reverse-inspected ABI in this pinned SDK: interface index, key-slot mask.
extern "C" void hal_crypto_disable(uint8_t,uint8_t);
extern "C" void ic_set_bssid(uint8_t,const uint8_t*);
extern "C" void wDev_Insert_KeyEntry(uint8_t,uint8_t,uint8_t,uint8_t*,uint8_t,uint8_t*,size_t,bool,bool);
extern "C" int hal_crypto_is_key_valid(uint32_t);

static bool started=false;
static uint8_t command[40];
static size_t used=0;
static uint32_t last_byte=0;
struct Received {uint16_t length;uint8_t state,fcs_ok;uint8_t frame[256];};
static QueueHandle_t incoming;
static StaticQueue_t queue_control;
static uint8_t queue_storage[16*sizeof(Received)];
static uint8_t expected_source[6],expected_receiver[6],expected_bssid[6];
static volatile uint32_t rx_total=0,rx_peer=0;

static void receive(void* data,wifi_promiscuous_pkt_type_t type) {
    if(type!=WIFI_PKT_DATA)return;
    auto* packet=static_cast<wifi_promiscuous_pkt_t*>(data);
    ++rx_total;
    if(packet->rx_ctrl.sig_len<28 || packet->rx_ctrl.sig_len>260)return;
    const uint8_t* f=packet->payload;
    if(memcmp(f+4,expected_receiver,6) || memcmp(f+10,expected_source,6))return;
    ++rx_peer;
    Received item;item.length=packet->rx_ctrl.sig_len-4;item.state=packet->rx_ctrl.rx_state;
    item.fcs_ok=ccmp_valid_fcs(f,packet->rx_ctrl.sig_len);
    memcpy(item.frame,f,item.length);xQueueSend(incoming,&item,0);
}

static void run_probe() {
    // PC01 | channel | receiver[6] | BSSID[6] | fresh key[16] | reserved[7].
    // Exactly 16 transmissions, then driver stop; no autonomous retry or beacon.
    if (memcmp(command,"PC01",4) || command[4]<1 || command[4]>11 ||
        (command[5]&1) || (command[11]&1)) {Serial.println("REJECT command");return;}
    if(command[33]>1){Serial.println("REJECT alias mode");return;}
    if(command[34]>1){Serial.println("REJECT FCS diagnostic mode");return;}
    if(command[35]>6){Serial.println("REJECT crypto diagnostic mode");return;}
#ifndef HTIT_TX_SELECTOR
    if(command[35]==6){Serial.println("REJECT selected-key mode requires TX selector target");return;}
#endif
#ifndef HTIT_RX_OBSERVER
    if(command[35]==5){Serial.println("REJECT hardware mode requires DMA observer target");return;}
#endif
    if(command[36]>1){Serial.println("REJECT BSSID diagnostic mode");return;}
    if(command[37]>1 || (command[37] && command[35]!=5)){Serial.println("REJECT wrong-key diagnostic mode");return;}
    for (size_t i=38;i<40;++i)if(command[i]){Serial.println("REJECT reserved");return;}
    wifi_init_config_t cfg=WIFI_INIT_CONFIG_DEFAULT();cfg.nvs_enable=0;
    esp_err_t error=esp_event_loop_create_default();
    if(error!=ESP_OK && error!=ESP_ERR_INVALID_STATE){Serial.printf("ERROR event %d\n",error);return;}
    error=esp_wifi_init(&cfg);
    if(error!=ESP_OK){Serial.printf("ERROR init %d\n",error);return;}
    started=true;
    uint8_t header[24]={8,0};CcmpEpoch epoch{};
    memcpy(header+4,command+5,6);memcpy(header+16,command+11,6);
    memcpy(epoch.receiver,command+5,6);memcpy(epoch.bssid,command+11,6);
    memcpy(epoch.key,command+17,16);
    error=esp_wifi_set_storage(WIFI_STORAGE_RAM);
    if(error==ESP_OK)error=esp_wifi_set_mode(WIFI_MODE_STA);
    if(error==ESP_OK)error=esp_wifi_start();
    if(error==ESP_OK)error=esp_wifi_set_channel(command[4],WIFI_SECOND_CHAN_NONE);
    if(error==ESP_OK)error=esp_wifi_set_ps(WIFI_PS_NONE);
    if(error==ESP_OK)error=esp_wifi_get_mac(WIFI_IF_STA,header+10);
    memcpy(epoch.transmitter,header+10,6);
    CcmpEpoch receiver=epoch;
    memcpy(receiver.receiver,epoch.transmitter,6);memcpy(receiver.transmitter,epoch.receiver,6);
    if(command[33])receiver.receiver[0]^=2; // Separate software-MAC alias for RX filtering diagnosis.
    memcpy(expected_source,receiver.transmitter,6);memcpy(expected_receiver,receiver.receiver,6);
    memcpy(expected_bssid,receiver.bssid,6);
#ifdef HTIT_TX_SELECTOR
    probe_tx_selector_configure(header+10,expected_bssid);
#endif
#ifdef HTIT_RX_OBSERVER
    probe_rx_observer_configure(expected_receiver,expected_source,expected_bssid);
    CcmpEpoch raw_receiver=receiver;
    CcmpEpoch hw_receiver=receiver;bool hardware_rx_ready=false;
#endif
    incoming=xQueueCreateStatic(16,sizeof(Received),queue_storage,&queue_control);
    wifi_promiscuous_filter_t filter{};filter.filter_mask=WIFI_PROMIS_FILTER_MASK_DATA;
    if(command[34])filter.filter_mask|=WIFI_PROMIS_FILTER_MASK_FCSFAIL|WIFI_PROMIS_FILTER_MASK_MISC;
    if(error==ESP_OK)error=esp_wifi_set_promiscuous_filter(&filter);
    if(error==ESP_OK)error=esp_wifi_set_promiscuous_rx_cb(receive);
    if(error==ESP_OK)error=esp_wifi_set_promiscuous(true);
    if(error==ESP_OK && command[35]==1) {
        uint8_t seq[6]={0};
        int installed=esp_wifi_set_sta_key_internal(3,expected_source,0,1,seq,6,epoch.key,16,44);
        Serial.printf("HARDWARE_KEY result=%d\n",installed);
        if(installed)error=ESP_FAIL;
    }
    if(error==ESP_OK && command[35]==2) {
        // Ciphertext is constructed and authenticated by ccmp.cpp. Disable the
        // station hardware crypto engine to test its pre-callback filtering.
        // No plaintext fallback or application dispatch exists in this probe.
        hal_crypto_disable(0,255);Serial.println("SOFTWARE_CRYPTO diagnostic enabled");
    }
    if(error==ESP_OK && command[36]) {
        ic_set_bssid(0,expected_bssid);Serial.println("BSSID_FILTER diagnostic configured");
    }
    if(error==ESP_OK && command[35]>=3) {
        uint8_t slot=command[35]==3?0:4;
        if(command[35]==5)wDev_Insert_KeyEntry(3,0,0,expected_source,0,epoch.key,16,true,false);
        uint8_t receive_key[16];memcpy(receive_key,epoch.key,16);
        if(command[37])receive_key[0]^=0x80;
        wDev_Insert_KeyEntry(3,0,0,expected_source,slot,receive_key,16,true,false);
        volatile uint8_t* erase=receive_key;for(unsigned i=0;i<16;++i)erase[i]=0;
        if(command[37])Serial.println("WRONG_RX_KEY negative control enabled");
        Serial.printf("DIRECT_KEY diagnostic configured slot=%u; API has no success result\n",slot);
#ifdef HTIT_RX_OBSERVER
        hardware_rx_ready=slot==4 && hal_crypto_is_key_valid(1u<<4);
        if(command[35]==5 && !hal_crypto_is_key_valid(1))hardware_rx_ready=false;
        Serial.printf("HARDWARE_RX_READY %u\n",hardware_rx_ready);
        if(command[35]>=5 && !hardware_rx_ready)error=ESP_FAIL;
#ifdef HTIT_TX_SELECTOR
        if(hardware_rx_ready)probe_tx_selector_key(0,4);
#endif
#endif
    }
    if(error==ESP_OK) {
        Serial.printf("START channel=%u source=%02x:%02x:%02x:%02x:%02x:%02x\n",command[4],
            header[10],header[11],header[12],header[13],header[14],header[15]);
        uint8_t payload[64]={0xaa,0xaa,3,0,0,0,0x88,0xb5}; // Experimental Ethernet type, standard CCMP wrapper.
        memcpy(payload+8,"Pocket CCMP radio-path probe",28);
        for(unsigned i=0;i<16;++i) {
            payload[36]=i;esp_fill_random(payload+37,sizeof(payload)-37);
            uint8_t frame[104];int length=ccmp_seal(&epoch,header,payload,sizeof(payload),frame,sizeof(frame));
            if(length==104 && command[35]>=5) {
                // Public test data only. The raw TX descriptor uses the low
                // hardware slot; give it plaintext plus the standard IV/padding.
                memcpy(frame+32,payload,64);memset(frame+96,0,8);
            }
            esp_err_t sent=length>0?esp_wifi_80211_tx(WIFI_IF_STA,frame,length,true):ESP_FAIL;
            Serial.printf("TX seq=%u pn=%u result=%d\n",i,unsigned(epoch.tx_pn),sent);
            delay(200);
        }
        if(command[35]==1 || command[35]>=3) {
            // Public lab marker only: trigger the reply test even if enabling
            // hardware crypto interferes with pre-encrypted raw TX. No app data.
            uint8_t trigger[60];memcpy(trigger,header,24);trigger[1]=0;
            memcpy(trigger+24,payload,36);
            Serial.printf("PUBLIC_TRIGGER result=%d\n",esp_wifi_80211_tx(WIFI_IF_STA,trigger,sizeof(trigger),true));
        }
        unsigned accepted=0,rejected=0;
#ifdef HTIT_RX_OBSERVER
        unsigned raw_accepted=0,raw_rejected=0;
        unsigned hw_accepted=0,hw_rejected=0;
#endif
        uint32_t end=millis()+10000;
        while(int32_t(end-millis())>0) {
#ifdef HTIT_RX_OBSERVER
            ProbeRawRx raw;
            while(probe_rx_observer_next(&raw)) {
                uint8_t plaintext[64];
                if(hardware_rx_ready) {
                    int h=ccmp_open_hardware(&hw_receiver,raw,true,plaintext,sizeof(plaintext));
                    if(h==64 && !memcmp(plaintext+8,"Pocket CCMP radio-path probe",28) &&
                        plaintext[36]<16 && plaintext[36]+1==hw_receiver.rx_pn) {
                        ++hw_accepted;uint8_t digest[32];
                        mbedtls_sha256_ret(plaintext,64,digest,0);
                        Serial.printf("HW_RX seq=%u pn=%u hash=",plaintext[36],unsigned(hw_receiver.rx_pn));
                        for(uint8_t byte:digest){Serial.printf("%02x",byte);}Serial.println();
                    } else ++hw_rejected;
                }
                int n=raw.length>=4?ccmp_open(&raw_receiver,raw.frame,raw.length-4,plaintext,sizeof(plaintext)):-1;
                if(n<0)n=ccmp_open(&raw_receiver,raw.frame,raw.length,plaintext,sizeof(plaintext));
                if(n==64 && !memcmp(plaintext+8,"Pocket CCMP radio-path probe",28) &&
                    plaintext[36]<16 && plaintext[36]+1==raw_receiver.rx_pn) {
                    ++raw_accepted;Serial.printf("RAW_RX seq=%u pn=%u authenticated state=%u filter=%u dma=%u sig=%u copy=%u\n",
                        plaintext[36],unsigned(raw_receiver.rx_pn),raw.state,raw.filter,raw.dma_length,raw.sig_length,raw.length);
                } else if(++raw_rejected<=4) {
                    Serial.printf("RAW_REJECT fc=%02x%02x state=%u filter=%u dma=%u sig=%u copy=%u flags=%08x body32=%02x%02x%02x%02x\n",
                        raw.frame[0],raw.frame[1],raw.state,raw.filter,raw.dma_length,raw.sig_length,raw.length,unsigned(raw.dma_flags),
                        raw.length>35?raw.frame[32]:0,raw.length>35?raw.frame[33]:0,raw.length>35?raw.frame[34]:0,raw.length>35?raw.frame[35]:0);
                }
            }
#endif
            Received item;uint8_t plain[64];
            if(xQueueReceive(incoming,&item,pdMS_TO_TICKS(10))==pdTRUE) {
                // FCS bytes are diagnostic: the SDK may omit/alter them. Never
                // deliver any payload without independent CCMP authentication.
                int length=ccmp_open(&receiver,item.frame,item.length,plain,sizeof(plain));
                if(length==64 && !memcmp(plain+8,"Pocket CCMP radio-path probe",28) &&
                    plain[36]<16 && plain[36]+1==receiver.rx_pn) {
                    ++accepted;Serial.printf("RX seq=%u pn=%u authenticated state=%u fcs=%u\n",plain[36],unsigned(receiver.rx_pn),item.state,item.fcs_ok);
                } else {++rejected;if(rejected<4)Serial.printf("RX_REJECT len=%u fc=%02x%02x state=%u fcs=%u bssid=%02x%02x%02x%02x%02x%02x\n",item.length,item.frame[0],item.frame[1],item.state,item.fcs_ok,item.frame[16],item.frame[17],item.frame[18],item.frame[19],item.frame[20],item.frame[21]);}
            }
        }
        Serial.printf("RX_DONE authenticated=%u rejected=%u data_seen=%u peer_seen=%u\n",accepted,rejected,unsigned(rx_total),unsigned(rx_peer));
#ifdef HTIT_RX_OBSERVER
        Serial.printf("RAW_DONE authenticated=%u rejected=%u\n",raw_accepted,raw_rejected);
        Serial.printf("HW_DONE authenticated=%u rejected=%u\n",hw_accepted,hw_rejected);
#endif
    } else Serial.printf("ERROR radio %d\n",error);
#ifdef HTIT_RX_OBSERVER
    probe_rx_observer_stop();
#endif
    esp_wifi_set_promiscuous(false);esp_wifi_stop();esp_wifi_deinit();
#ifdef HTIT_TX_SELECTOR
    Serial.printf("TX_SELECTOR matched=%u\n",probe_tx_selector_count());probe_tx_selector_stop();
#endif
#ifdef HTIT_RX_OBSERVER
    ProbeRxStats observed=probe_rx_observer_stats();
    Serial.printf("RAW_STATS calls=%u single=%u bounds=%u peer=%u queued=%u overflow=%u pointer_bad=%u buffer_bad=%u no_data=%u sample_flags=%08x\n",unsigned(observed.calls),unsigned(observed.single),unsigned(observed.bounds),unsigned(observed.matching),unsigned(observed.queued),unsigned(observed.overflow),unsigned(observed.pointer_bad),unsigned(observed.buffer_bad),unsigned(observed.no_data),unsigned(observed.sample_flags));
#endif
    volatile uint8_t* key=epoch.key;for(size_t i=0;i<16;++i)key[i]=0;
    key=receiver.key;for(size_t i=0;i<16;++i)key[i]=0;
#ifdef HTIT_RX_OBSERVER
    key=raw_receiver.key;for(size_t i=0;i<16;++i)key[i]=0;
    key=hw_receiver.key;for(size_t i=0;i<16;++i)key[i]=0;
#endif
    memset(command,0,sizeof(command));
    Serial.println("STOP radios off; power-cycle/reset required for another fresh-key probe");
}

void setup() {Serial.begin(115200);Serial.println("CCMP RADIO PROBE WIP; USB command required; RSN handshake absent; radios off");}
void loop() {
    if(started){delay(100);return;}
    if(used && millis()-last_byte>1000){memset(command,0,sizeof(command));used=0;}
    while(Serial.available() && used<sizeof(command)){command[used++]=Serial.read();last_byte=millis();}
    if(used==sizeof(command)){run_probe();memset(command,0,sizeof(command));used=0;}
    delay(1);
}
