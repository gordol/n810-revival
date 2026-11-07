#pragma once
#include <stdint.h>
void htit_executor_set_epoch_ms(int64_t);
double htit_executor_wall_time();
double htit_executor_announce_time();
bool htit_executor_clock_synced();
