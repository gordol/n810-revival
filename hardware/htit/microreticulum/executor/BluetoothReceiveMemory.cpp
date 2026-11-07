// Internal storage for IDF 4.4.7 HCI receive and ACL reassembly only.
#ifdef HTIT_EXECUTOR
#include <atomic>
#include <cstddef>
#include <cstring>
#include <esp_heap_caps.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
namespace { std::atomic<uint32_t> allocations{0}, failures{0};std::atomic<TaskHandle_t> receiving_task{nullptr}; }
extern "C" uint32_t htit_bt_internal_allocations(){return allocations.load();}
extern "C" uint32_t htit_bt_internal_failures(){return failures.load();}
extern "C" void htit_bt_receive_scope(bool active){receiving_task.store(active?xTaskGetCurrentTaskHandle():nullptr);}
#ifdef HTIT_BT_RX_INTERNAL
namespace {
bool internal_required(){
 if(xPortInIsrContext()||xTaskGetSchedulerState()!=taskSCHEDULER_RUNNING)return false;
 if(receiving_task.load()==xTaskGetCurrentTaskHandle())return true;
 const char* name=pcTaskGetName(nullptr);
// IDF 4.4.7 hci_layer.c reassembles ACL fragments on this task.
 return name&&!strcmp(name,"hciT");
}
void* counted(void* pointer){++allocations;if(!pointer)++failures;return pointer;}
}
extern "C" void* __real_malloc(size_t);
extern "C" void* __real_calloc(size_t,size_t);
extern "C" void* __real_realloc(void*,size_t);
extern "C" void* __wrap_malloc(size_t size){
 if(internal_required())return counted(heap_caps_malloc(size,MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT));
 return __real_malloc(size);
}
extern "C" void* __wrap_calloc(size_t count,size_t size){
 if(internal_required())return counted(heap_caps_calloc(count,size,MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT));
 return __real_calloc(count,size);
}
extern "C" void* __wrap_realloc(void* pointer,size_t size){
 if(internal_required())return counted(heap_caps_realloc(pointer,size,MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT));
 return __real_realloc(pointer,size);
}
#endif
#endif
