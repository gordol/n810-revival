// WIP coexistence diagnostics: no policy overrides, no keys or packet contents.
#include <Arduino.h>
#include <esp_heap_caps.h>
#include <esp_timer.h>
extern "C" int ets_printf(const char*,...);
static volatile unsigned alarms_created,alarms_freed,alloc_failed_size,alloc_failed_caps;
static volatile int timer_error;
extern "C" void* __real_osi_alarm_new(const char*,esp_timer_cb_t,void*,uint64_t);
extern "C" void __real_osi_alarm_free(void*);
extern "C" esp_err_t __real_esp_timer_create(const esp_timer_create_args_t*,esp_timer_handle_t*);
static void allocation_failed(size_t size,uint32_t caps,const char*){
 alloc_failed_size=size;alloc_failed_caps=caps;
}
extern "C" void* __wrap_osi_alarm_new(const char* name,esp_timer_cb_t cb,void* data,uint64_t period){
 void* p=__real_osi_alarm_new(name,cb,data,period);
 if(p)++alarms_created;
 else ets_printf("BT_ALARM_FAILED created=%u freed=%u timer_error=%d alloc_size=%u caps=%08x internal_free=%u largest=%u\n",alarms_created,alarms_freed,timer_error,alloc_failed_size,alloc_failed_caps,unsigned(heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT)),unsigned(heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT)));
 return p;
}
extern "C" void __wrap_osi_alarm_free(void* p){if(p)++alarms_freed;__real_osi_alarm_free(p);}
extern "C" esp_err_t __wrap_esp_timer_create(const esp_timer_create_args_t* args,esp_timer_handle_t* result){
 esp_err_t err=__real_esp_timer_create(args,result);if(err!=ESP_OK)timer_error=err;return err;
}
void htit_rsn_diagnostics_begin(){heap_caps_register_failed_alloc_callback(allocation_failed);}

void htit_rsn_diagnostics_poll(){
 static uint32_t last;if(millis()-last<10000)return;last=millis();
 TaskHandle_t btc=xTaskGetHandle("BTC_TASK"),btu=xTaskGetHandle("BTU_TASK");
 printf("RSN_MEMORY internal_free=%u largest=%u loop_free=%u btc_free=%u btu_free=%u\n",unsigned(heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT)),unsigned(heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT)),unsigned(uxTaskGetStackHighWaterMark(nullptr)*sizeof(StackType_t)),btc?unsigned(uxTaskGetStackHighWaterMark(btc)*sizeof(StackType_t)):0,btu?unsigned(uxTaskGetStackHighWaterMark(btu)*sizeof(StackType_t)):0);
}
