// Exercises the actual ESP crypto/timer provider, never transmits a test frame.
#include <Arduino.h>
#include <esp_wifi.h>
#include <esp_event.h>
#include "rsn-port/rsn_port.h"
struct Message {int from,kind,encrypted;size_t length;uint8_t data[1024];};
static Message queue[16];static unsigned rd,wr;
static pocket_rsn* nodes[2];
static const uint8_t mac[2][6]={{0x2c,0xbc,0xbb,0x9f,0xe0,0xe0},{0,2,0xee,0xc0,0xff,0xee}};
static const uint8_t bssid[6]={2,0x4e,0x38,0x31,0x30,2};
static uint8_t pairwise[2][16],groups[2][4][16];static unsigned pairs[2],group_tx[2],group_rx[2];
static bool failed=false,ran=false;
static int send(void* ctx,int kind,const uint8_t*,const uint8_t* p,size_t n,int encrypted){
 unsigned next=(wr+1)%16;if(next==rd||n>1024){failed=true;return -1;}
 Message& m=queue[wr];m.from=int(uintptr_t(ctx));m.kind=kind;m.encrypted=encrypted;m.length=n;memcpy(m.data,p,n);wr=next;return 0;
}
static int key(void* ctx,const uint8_t*,int,int index,int tx,const uint8_t* p,size_t n,const uint8_t*,size_t,int){
 unsigned i=uintptr_t(ctx);if(n==16){if(index==0){memcpy(pairwise[i],p,16);++pairs[i];}
 else {memcpy(groups[i][index],p,16);if(tx)++group_tx[i];else ++group_rx[i];}}return 0;
}
static void authorized(void*,int){}
static int sequence(void*,int,uint8_t seq[8]){memset(seq,0,8);return 0;}
static void run(){
 wifi_init_config_t config=WIFI_INIT_CONFIG_DEFAULT();config.nvs_enable=0;
 if(esp_event_loop_create_default()!=ESP_OK||esp_wifi_init(&config)!=ESP_OK||
 esp_wifi_set_storage(WIFI_STORAGE_RAM)!=ESP_OK||esp_wifi_set_mode(WIFI_MODE_STA)!=ESP_OK||esp_wifi_start()!=ESP_OK){Serial.println("SELFTEST init FAIL");return;}
 uint8_t pmk[32];esp_fill_random(pmk,sizeof(pmk));
 pocket_rsn_callbacks callbacks={send,key,authorized,sequence};
 for(unsigned i=0;i<2;++i)nodes[i]=pocket_rsn_create(mac[i],bssid,pmk,2,&callbacks,reinterpret_cast<void*>(i));
 memset(pmk,0,sizeof(pmk));
 if(!nodes[0]||!nodes[1]){Serial.println("SELFTEST context FAIL");failed=true;}
 else for(unsigned i=0;i<2;++i)if(pocket_rsn_start(nodes[i],mac[1-i]))failed=true;
 uint32_t end=millis()+6500;
 while(!failed&&int32_t(end-millis())>0){
  pocket_rsn_poll();unsigned budget=64;
  while(rd!=wr&&budget--){Message m=queue[rd];rd=(rd+1)%16;pocket_rsn_receive(nodes[1-m.from],mac[m.from],m.kind,m.data,m.length,m.encrypted);}
  delay(1);
 }
 bool ready=nodes[0]&&nodes[1]&&pocket_rsn_ready(nodes[0])&&pocket_rsn_ready(nodes[1]);
 bool pass=!failed&&ready&&pairs[0]==1&&pairs[1]==1&&!memcmp(pairwise[0],pairwise[1],16)&&group_tx[0]>=2&&group_tx[1]>=2&&group_rx[0]>=2&&group_rx[1]>=2;
 Serial.printf("SELFTEST ESP_RSN ready=%u PTK=%u/%u GTK_TX=%u/%u GTK_RX=%u/%u result=%s\n",ready,pairs[0],pairs[1],group_tx[0],group_tx[1],group_rx[0],group_rx[1],pass?"PASS":"FAIL");
 for(auto node:nodes)if(node)pocket_rsn_destroy(node);
 memset(pairwise,0,sizeof(pairwise));memset(groups,0,sizeof(groups));memset(queue,0,sizeof(queue));
 esp_wifi_stop();esp_wifi_deinit();Serial.println("STOP radios off");
}
void setup(){Serial.begin(115200);delay(200);Serial.println("IBSS RSN RADIO PROBE WIP; selftest; send T to run");}
void loop(){if(!ran&&Serial.available()&&Serial.read()=='T'){ran=true;run();}delay(5);}
