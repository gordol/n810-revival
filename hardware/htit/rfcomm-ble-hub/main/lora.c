/* SX1276 packet engine for HTIT-WB. RNode on-air framing: high nibble sequence,
 * bit0 split, up to two 254-byte payload fragments. No radio use at boot. */
#include "lora.h"
#include "driver/spi_master.h"
#include "driver/gpio.h"
#include "esp_timer.h"
#include "esp_random.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <string.h>
static spi_device_handle_t dev;
static bool present, configured, online;
static uint8_t tx[508], rx[508], tx_header;
static size_t tx_len, tx_offset, rx_len;
static int rx_sequence=-1;
static int64_t rx_until, deadline, next_poll, backoff;
static enum {IDLE, WAIT, CAD, TX} phase;
static uint8_t reg_read(uint8_t a) {
    spi_transaction_t t={.flags=SPI_TRANS_USE_TXDATA|SPI_TRANS_USE_RXDATA,.length=16};
    t.tx_data[0]=a&0x7f;
    ESP_ERROR_CHECK(spi_device_polling_transmit(dev,&t));
    return t.rx_data[1];
}
static void reg_write(uint8_t a,uint8_t v) {
    spi_transaction_t t={.flags=SPI_TRANS_USE_TXDATA,.length=16};
    t.tx_data[0]=a|0x80;t.tx_data[1]=v;
    ESP_ERROR_CHECK(spi_device_polling_transmit(dev,&t));
}
static void fifo(uint8_t *data,size_t n,bool write) {
    /* ESP32 without DMA has a 64-byte SPI FIFO, including the address.
       The SX1276 FIFO pointer persists across chip-select boundaries. */
    while(n) {
        size_t count=n>63?63:n;
        uint8_t out[64]={0},in[64]={0};out[0]=write?0x80:0;
        if(write)memcpy(out+1,data,count);
        spi_transaction_t t={.length=(count+1)*8,.tx_buffer=out,.rx_buffer=in};
        ESP_ERROR_CHECK(spi_device_polling_transmit(dev,&t));
        if(!write)memcpy(data,in+1,count);
        data+=count;n-=count;
    }
}
static void receive_mode(void) { reg_write(0x12,0xff);reg_write(0x01,0x85); }
bool lora_init(void) {
    if(dev)return present;
    spi_bus_config_t bus={.mosi_io_num=27,.miso_io_num=19,.sclk_io_num=5,
        .quadwp_io_num=-1,.quadhd_io_num=-1,.max_transfer_sz=64};
    if(spi_bus_initialize(SPI2_HOST,&bus,SPI_DMA_DISABLED)!=ESP_OK)return false;
    spi_device_interface_config_t device={.clock_speed_hz=4000000,.mode=0,.spics_io_num=18,.queue_size=1};
    if(spi_bus_add_device(SPI2_HOST,&device,&dev)!=ESP_OK)return false;
    gpio_set_direction(GPIO_NUM_14,GPIO_MODE_OUTPUT);gpio_set_level(GPIO_NUM_14,0);
    vTaskDelay(pdMS_TO_TICKS(10));gpio_set_level(GPIO_NUM_14,1);vTaskDelay(pdMS_TO_TICKS(10));
    present=reg_read(0x42)==0x12;
    if(present)reg_write(0x01,0x80);
    return present;
}
bool lora_configure(const lora_config *c) {
    /* PA_BOOST supports 2..17 dBm here; never silently clamp a host profile. */
    if(online||phase!=IDLE||c->frequency<850000000||c->frequency>950000000||
       c->sf<7||c->sf>12||c->cr<5||c->cr>8||c->power<2||c->power>17)return false;
    int bw=c->bandwidth==125000?7:c->bandwidth==250000?8:c->bandwidth==500000?9:-1;
    if(bw<0||!lora_init())return false;
    reg_write(0x01,0x80);
    uint32_t f=((uint64_t)c->frequency<<19)/32000000;
    reg_write(0x06,f>>16);reg_write(0x07,f>>8);reg_write(0x08,f);
    reg_write(0x0e,0);reg_write(0x0f,0);reg_write(0x0c,0x23);
    reg_write(0x1d,(bw<<4)|((c->cr-4)<<1)); /* explicit header */
    reg_write(0x1e,(c->sf<<4)|0x04); /* packet CRC */
    reg_write(0x26,0x04|(((uint64_t)(1<<c->sf)*1000>16ULL*c->bandwidth)?8:0));
    reg_write(0x31,0xc3);reg_write(0x37,0x0a);reg_write(0x39,0x12);
    reg_write(0x33,0x27);reg_write(0x3b,0x1d); /* normal IQ */
    unsigned preamble=(24*c->bandwidth+1000*(1<<c->sf)-1)/(1000*(1<<c->sf));
    if(preamble<18)preamble=18;
    reg_write(0x20,preamble>>8);reg_write(0x21,preamble);
    reg_write(0x4d,0x84);reg_write(0x0b,0x2b);reg_write(0x09,0x80|(c->power-2));
    /* SX1276 errata 500kHz sensitivity optimization, HF band. */
    reg_write(0x36,bw==9?0x02:0x03);if(bw==9)reg_write(0x3a,0x64);
    uint32_t read_f=((uint32_t)reg_read(0x06)<<16)|((uint32_t)reg_read(0x07)<<8)|reg_read(0x08);
    if(read_f!=f||reg_read(0x1d)!=((bw<<4)|((c->cr-4)<<1))||
       reg_read(0x1e)!=((c->sf<<4)|4)||reg_read(0x09)!=(0x80|(c->power-2)))return false;
    configured=true;return true;
}
bool lora_enable(bool enabled) {
    if(enabled&&(!present||!configured))return false;
    phase=IDLE;tx_len=rx_len=0;rx_sequence=-1;online=enabled;
    if(dev&&present){if(enabled)receive_mode();else reg_write(0x01,0x80);}
    return true;
}
bool lora_online(void){return online;}
bool lora_busy(void){return phase!=IDLE;}
bool lora_send(const uint8_t *data,size_t n) {
    if(!online||phase!=IDLE||!n||n>508)return false;
    memcpy(tx,data,n);tx_len=n;tx_offset=0;
    tx_header=(esp_random()&0xf0)|(n>254?1:0);
    phase=WAIT;deadline=esp_timer_get_time()+60000000;backoff=0;return true;
}
static void transmit_fragment(void) {
    uint8_t packet[255];size_t n=tx_len-tx_offset;if(n>254)n=254;
    packet[0]=tx_header;memcpy(packet+1,tx+tx_offset,n);tx_offset+=n;
    reg_write(0x01,0x81);reg_write(0x0d,0);fifo(packet,n+1,true);
    reg_write(0x22,n+1);reg_write(0x12,0xff);reg_write(0x01,0x83);phase=TX;
}
void lora_poll(lora_receive received,lora_complete completed) {
    int64_t now=esp_timer_get_time();if(!online||now<next_poll)return;next_poll=now+5000;
    if(rx_sequence>=0&&now>rx_until){rx_sequence=-1;rx_len=0;}
    if(phase!=IDLE&&now>deadline){phase=IDLE;receive_mode();completed(false);return;}
    uint8_t flags=reg_read(0x12);
    if(phase==TX) {
        if(flags&8){reg_write(0x12,8);if(tx_offset<tx_len)transmit_fragment();
            else {phase=IDLE;receive_mode();completed(true);}}
        return;
    }
    if(phase==CAD) {
        if(flags&4){reg_write(0x12,0xff);
            if(flags&1){receive_mode();phase=WAIT;backoff=now+50000+(esp_random()%200000);}
            else transmit_fragment();}
        return;
    }
    if(flags&0x40) {
        uint8_t packet[255];size_t n=reg_read(0x13);
        if(!(flags&0x20)&&n>1) {
            reg_write(0x0d,reg_read(0x10));fifo(packet,n,false);
            int8_t snr=(int8_t)reg_read(0x19);int16_t rssi=(int)reg_read(0x1a)-157;
            if(snr<0)rssi+=snr/4;
            int seq=packet[0]>>4;bool split=packet[0]&1;
            if(!split){rx_sequence=-1;rx_len=0;received(packet+1,n-1,rssi,snr);}
            else if(rx_sequence==seq){
                if(rx_len+n-1<=sizeof(rx)){memcpy(rx+rx_len,packet+1,n-1);received(rx,rx_len+n-1,rssi,snr);}
                rx_sequence=-1;rx_len=0;
            }else{memcpy(rx,packet+1,n-1);rx_len=n-1;rx_sequence=seq;rx_until=now+30000000;}
        }
        reg_write(0x12,flags);
    }
    if(phase==WAIT&&now>=backoff){reg_write(0x01,0x81);reg_write(0x12,0xff);reg_write(0x01,0x87);phase=CAD;}
}
