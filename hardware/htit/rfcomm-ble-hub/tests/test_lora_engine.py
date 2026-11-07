"""Exercise actual C radio engine with register/FIFO simulation; no RF."""
from pathlib import Path
import subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]
class EngineTests(unittest.TestCase):
 def test_configuration_fragmentation_receive_and_timeout(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)
   for sub in ('driver','freertos'):(p/sub).mkdir()
   stub='''#pragma once
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <stdbool.h>
#define ESP_OK 0
#define ESP_ERROR_CHECK(x) do {if((x)!=0)abort();} while(0)
#define SPI_TRANS_USE_TXDATA 1
#define SPI_TRANS_USE_RXDATA 2
#define SPI2_HOST 2
#define SPI_DMA_DISABLED 0
#define GPIO_NUM_14 14
#define GPIO_MODE_OUTPUT 1
#define pdMS_TO_TICKS(x) (x)
typedef void *spi_device_handle_t;
typedef struct {int flags;size_t length;uint8_t tx_data[4],rx_data[4];const void *tx_buffer;void *rx_buffer;} spi_transaction_t;
typedef struct {int mosi_io_num,miso_io_num,sclk_io_num,quadwp_io_num,quadhd_io_num,max_transfer_sz;} spi_bus_config_t;
typedef struct {int clock_speed_hz,mode,spics_io_num,queue_size;} spi_device_interface_config_t;
int spi_device_polling_transmit(spi_device_handle_t,spi_transaction_t *);
int spi_bus_initialize(int,spi_bus_config_t *,int);
int spi_bus_add_device(int,spi_device_interface_config_t *,spi_device_handle_t *);
int gpio_set_direction(int,int);int gpio_set_level(int,int);
void vTaskDelay(int);int64_t esp_timer_get_time(void);uint32_t esp_random(void);
'''
   (p/'stub.h').write_text(stub)
   for name in ('driver/spi_master.h','driver/gpio.h','esp_timer.h','esp_random.h','freertos/FreeRTOS.h','freertos/task.h'):(p/name).write_text('#include "stub.h"\n')
   harness=r'''
#include "stub.h"
#include "lora.h"
#include <assert.h>
#include <string.h>
static uint8_t regs[128],input[255],sent[2][255],received[508];
static size_t sizes[2],received_len;static int packets,done;static int64_t clock_us;
int spi_bus_initialize(int a,spi_bus_config_t*b,int c){assert(b->sclk_io_num==5&&b->mosi_io_num==27&&b->miso_io_num==19);return 0;}
int spi_bus_add_device(int a,spi_device_interface_config_t*b,spi_device_handle_t*c){assert(b->spics_io_num==18);*c=(void*)1;return 0;}
int gpio_set_direction(int a,int b){return 0;}int gpio_set_level(int a,int b){return 0;}
void vTaskDelay(int n){clock_us+=n*1000;}int64_t esp_timer_get_time(void){return clock_us;}uint32_t esp_random(void){return 0xa0;}
int spi_device_polling_transmit(spi_device_handle_t d,spi_transaction_t*t){
 assert(t->length<=64*8);
 if(t->flags&SPI_TRANS_USE_TXDATA){int a=t->tx_data[0]&127;
  if(t->tx_data[0]&128){if(a==0x12)regs[a]&=~t->tx_data[1];else {regs[a]=t->tx_data[1];if(a==1&&t->tx_data[1]==0x83){sizes[packets]=regs[0x22];packets++;}}}
  else t->rx_data[1]=regs[a];
 }else{const uint8_t *out=t->tx_buffer;uint8_t *in=t->rx_buffer;size_t n=t->length/8-1;
  if(out[0]&128){assert(packets<2);memcpy(sent[packets]+regs[0x0d],out+1,n);regs[0x0d]+=n;}
  else {memcpy(in+1,input+regs[0x0d],n);regs[0x0d]+=n;}
 }return 0;
}
void rx(const uint8_t*d,size_t n,int16_t r,int8_t s){memcpy(received,d,n);received_len=n;assert(r==-100&&s==-4);}
void complete(bool ok){done=ok?1:-1;}
void poll(void){clock_us+=10000;lora_poll(rx,complete);}
int main(void){
 regs[0x42]=0x12;lora_config c={912345000,500000,7,5,2};
 assert(!lora_online());assert(!lora_enable(true));assert(lora_configure(&c));assert(!lora_online());
 c.power=0;assert(!lora_configure(&c));c.power=2;assert(lora_enable(true));assert(!lora_configure(&c));
 uint8_t data[508];for(int i=0;i<508;i++)data[i]=i;
 assert(lora_send(data,508));assert(!lora_send(data,1));poll();assert(regs[1]==0x87);
 regs[0x12]=4;poll();assert(packets==1&&sizes[0]==255&&sent[0][0]==0xa1);
 regs[0x12]=8;poll();assert(packets==2&&sizes[1]==255&&sent[1][0]==0xa1);
 assert(!memcmp(sent[0]+1,data,254));assert(!memcmp(sent[1]+1,data+254,254));
 regs[0x12]=8;poll();assert(done==1&&!lora_busy());
 regs[0x19]=0xfc;regs[0x1a]=58;
 for(int i=0;i<2;i++){memcpy(input,sent[i],255);regs[0x13]=255;regs[0x12]=0x40;poll();}
 assert(received_len==508&&!memcmp(received,data,508));
 received_len=0;regs[0x13]=255;regs[0x12]=0x60;poll();assert(received_len==0);
 assert(lora_send(data,1));clock_us+=61000000;poll();assert(done==-1&&!lora_busy());
 assert(lora_enable(false));assert(!lora_online()&&!lora_send(data,1));return 0;
}
'''
   (p/'test.c').write_text(harness)
   subprocess.run(['cc','-std=c11','-I'+d,'-I'+str(ROOT/'main'),str(ROOT/'main/lora.c'),str(p/'test.c'),'-o',str(p/'test')],check=True)
   subprocess.run([str(p/'test')],check=True)
if __name__=='__main__':unittest.main()
