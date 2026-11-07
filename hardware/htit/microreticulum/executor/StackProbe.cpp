#include "StackProbe.h"

#ifdef HTIT_STACK_PROBE

#include <Arduino.h>
#include <LXMF/LXMessage.h>
#include <Log.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

#ifndef HTIT_STACK_PROBE_DEPTH
#define HTIT_STACK_PROBE_DEPTH 64
#endif

namespace {

constexpr size_t kProbeStackBytes = 16384;
constexpr size_t kSupervisorStackBytes = 4096;
constexpr uint32_t kProbeIterations = 32;
static_assert(HTIT_STACK_PROBE_DEPTH > 0, "probe depth must be positive");
static_assert(HTIT_STACK_PROBE_DEPTH <= 512, "probe is intentionally bounded");

StaticTask_t probe_control;
StackType_t probe_stack[kProbeStackBytes / sizeof(StackType_t)];
TaskHandle_t probe_task = nullptr;
StaticTask_t supervisor_control;
StackType_t supervisor_stack[kSupervisorStackBytes / sizeof(StackType_t)];
TaskHandle_t supervisor_task = nullptr;
volatile uint32_t probe_started = 0;
volatile uint32_t probe_returned = 0;
volatile uint32_t probe_destroyed = 0;

RNS::Bytes make_nested_lxmf() {
    RNS::Bytes wire;
    uint8_t fixed[96] = {};
    wire.append(fixed, sizeof(fixed));

    // [timestamp, empty title, empty content, {1: nested value}]
    const uint8_t prefix[] = {
        0x94, 0xcb, 0, 0, 0, 0, 0, 0, 0, 0,
        0xc4, 0, 0xc4, 0, 0x81, 1,
    };
    wire.append(prefix, sizeof(prefix));
    for (size_t i = 0; i < HTIT_STACK_PROBE_DEPTH; ++i) wire.append(0x91);
    wire.append(0xc0);
    return wire;
}

void run_probe(void*) {
    const UBaseType_t before = uxTaskGetStackHighWaterMark(nullptr);
    RNS::Bytes wire = make_nested_lxmf();
    INFOF("STACK_PROBE begin depth=%u bytes=%u high_water=%u",
          unsigned(HTIT_STACK_PROBE_DEPTH), unsigned(wire.size()), unsigned(before));

    for (uint32_t i = 0; i < kProbeIterations; ++i) {
        probe_started = i + 1;
        {
            LXMF::LXMessage message = LXMF::LXMessage::unpack_from_bytes(
                wire, LXMF::Type::Message::DIRECT, true);
            probe_returned = i + 1;
        }
        probe_destroyed = i + 1;
        vTaskDelay(1);
    }

    const UBaseType_t after = uxTaskGetStackHighWaterMark(nullptr);
    INFOF("STACK_PROBE end started=%u returned=%u destroyed=%u high_water=%u consumed=%u",
          unsigned(probe_started), unsigned(probe_returned), unsigned(probe_destroyed),
          unsigned(after), unsigned(before - after));
    vTaskDelay(pdMS_TO_TICKS(500));
    probe_task = nullptr;
    vTaskDelete(nullptr);
}

void supervise_probe(void*) {
    for (uint32_t sample = 1; sample <= 6; ++sample) {
        vTaskDelay(pdMS_TO_TICKS(2000));
        TaskHandle_t task = probe_task;
        const unsigned state = task ? unsigned(eTaskGetState(task)) : 0xff;
        const unsigned high_water = task ? unsigned(uxTaskGetStackHighWaterMark(task)) : 0;
        INFOF("STACK_PROBE supervisor sample=%u started=%u returned=%u destroyed=%u state=%u high_water=%u",
              unsigned(sample), unsigned(probe_started), unsigned(probe_returned),
              unsigned(probe_destroyed), state, high_water);
    }
    supervisor_task = nullptr;
    vTaskDelete(nullptr);
}

}  // namespace

bool htit_stack_probe_start() {
    if (probe_task) return false;
    probe_task = xTaskCreateStaticPinnedToCore(
        run_probe,
        "lxmf-stack-probe",
        sizeof(probe_stack),
        nullptr,
        1,
        probe_stack,
        &probe_control,
        xPortGetCoreID());
    if (!probe_task) return false;
    supervisor_task = xTaskCreateStaticPinnedToCore(
        supervise_probe,
        "lxmf-stack-watch",
        sizeof(supervisor_stack),
        nullptr,
        1,
        supervisor_stack,
        &supervisor_control,
        xPortGetCoreID());
    return supervisor_task != nullptr;
}

#endif
