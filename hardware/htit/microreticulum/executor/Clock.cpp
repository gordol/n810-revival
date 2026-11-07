#ifdef HTIT_EXECUTOR
#include "Clock.h"
#include <microReticulum.h>
#include <esp_timer.h>
#include <mutex>
#include <stdexcept>
namespace {
std::mutex clock_guard;
int64_t epoch_ms=0,anchor_us=0;
double announce_floor=0;
double wall_locked(){return epoch_ms>0 ? double(epoch_ms)/1000.0+double(esp_timer_get_time()-anchor_us)/1000000.0 : RNS::Utilities::OS::time();}
}
void htit_executor_set_epoch_ms(int64_t value){if(value<=0)throw std::invalid_argument("Controller Unix clock required");std::lock_guard<std::mutex> lock(clock_guard);epoch_ms=value;anchor_us=esp_timer_get_time();}
double htit_executor_wall_time(){std::lock_guard<std::mutex> lock(clock_guard);return wall_locked();}
double htit_executor_announce_time(){std::lock_guard<std::mutex> lock(clock_guard);double now=wall_locked();if(now>announce_floor)announce_floor=now;return announce_floor;}
bool htit_executor_clock_synced(){std::lock_guard<std::mutex> lock(clock_guard);return epoch_ms>0;}
#endif
