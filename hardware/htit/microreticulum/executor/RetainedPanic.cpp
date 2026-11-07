#if defined(HTIT_EXECUTOR) && defined(HTIT_RETAIN_PANIC)
#include <esp_attr.h>
#include <esp_system.h>
#include <esp_debug_helpers.h>
#include <soc/soc_memory_types.h>
#include <esp_private/panic_internal.h>
#include <xtensa/xtensa_context.h>
#include <MsgPack.h>
#include <stdint.h>
#include <esp_heap_caps.h>
#include <atomic>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

// Diagnostic image only: retain exception registers, bounded backtrace and abort
// text across a restart. This evidence is retrieved privately after normal boot.
// The panic path must never allocate, take locks, or read flash strings.
namespace {
constexpr uint32_t MAGIC = 0x48545034;
constexpr size_t TRACE_DEPTH = 12;
constexpr size_t REASON_SIZE = 160;
struct Record {
    uint32_t magic,core,exception,pc,a0,a1,cause,address,stage;
    uint32_t trace_count,trace[TRACE_DEPTH];
};
struct AbortRecord { uint32_t magic,caller; char reason[REASON_SIZE]; };
RTC_NOINIT_ATTR volatile AbortRecord abort_record;
AbortRecord previous_abort{};
struct EarlyRecord { uint32_t magic,core,pc,a0,a1,cause,address,count,trace[16]; uint32_t a2,a3,a4,a5,a6,a7; };
RTC_NOINIT_ATTR volatile EarlyRecord early[2];
EarlyRecord previous_early[2]{};
RTC_NOINIT_ATTR volatile EarlyRecord exceptions[2];
EarlyRecord previous_exceptions[2]{};
bool IRAM_ATTR internal_stack(const esp_backtrace_frame_t& bt) {
    return !(bt.sp & 15) && esp_ptr_in_dram(reinterpret_cast<const void*>(bt.sp))
        && esp_ptr_in_dram(reinterpret_cast<const void*>(bt.sp-16));
}
void IRAM_ATTR capture_frame(void* raw,volatile EarlyRecord& saved) {
    if(saved.magic==MAGIC)return; // Preserve the original fault across nested exceptions.
    saved.magic=0;saved.core=xPortGetCoreID();saved.count=0;
    const auto* frame=static_cast<const XtExcFrame*>(raw);
    if(frame) {
        saved.pc=frame->pc;saved.a0=frame->a0;saved.a1=frame->a1;
        saved.a2=frame->a2;saved.a3=frame->a3;saved.a4=frame->a4;
        saved.a5=frame->a5;saved.a6=frame->a6;saved.a7=frame->a7;
        saved.cause=frame->exccause;saved.address=frame->excvaddr;
        saved.trace[0]=frame->pc;saved.count=1;saved.magic=MAGIC;
        esp_backtrace_frame_t bt{uint32_t(frame->pc),uint32_t(frame->a1),uint32_t(frame->a0),frame};
        while(bt.next_pc && saved.count<16 && internal_stack(bt) && esp_backtrace_get_next_frame(&bt))
            saved.trace[saved.count++]=bt.pc;
    }
}
RTC_NOINIT_ATTR volatile Record retained;
Record previous{};
uint32_t reset_reason = 0;
struct AllocationFailure { uint32_t size,caps,count,trace[16]; };
AllocationFailure allocation_failure{};
std::atomic_flag failure_guard = ATOMIC_FLAG_INIT;
std::atomic<uint32_t> allocation_failures{0};
bool allocation_hook_ready = false;
void IRAM_ATTR allocation_failed(size_t size,uint32_t caps,const char*) {
    allocation_failures.fetch_add(1,std::memory_order_relaxed);
    // Never wait, allocate, print or take a heap lock inside the failure hook.
    if(failure_guard.test_and_set(std::memory_order_acquire))return;
    allocation_failure.size=size;allocation_failure.caps=caps;allocation_failure.count=0;
    esp_backtrace_frame_t bt{};
    esp_backtrace_get_start(&bt.pc,&bt.sp,&bt.next_pc);
    do {
        allocation_failure.trace[allocation_failure.count++]=bt.pc;
        if(!bt.next_pc || allocation_failure.count==16)break;
    } while(esp_backtrace_get_next_frame(&bt));
    failure_guard.clear(std::memory_order_release);
}

}
RTC_NOINIT_ATTR volatile uint32_t htit_retained_core_stage;

// Capture before the SDK tries to enable caches or coordinate the other CPU.
// An interrupt watchdog can otherwise reset before esp_panic_handler is reached.
extern "C" void __real_panicHandler(void*);
extern "C" void IRAM_ATTR __wrap_panicHandler(void* frame) {
    capture_frame(frame,early[xPortGetCoreID()]);
    __real_panicHandler(frame);
}

extern "C" void __real_xt_unhandled_exception(void*);
extern "C" void IRAM_ATTR __wrap_xt_unhandled_exception(void* frame) {
    capture_frame(frame,exceptions[xPortGetCoreID()]);
    __real_xt_unhandled_exception(frame);
}

extern "C" void __real_esp_system_abort(const char*) __attribute__((noreturn));
extern "C" void IRAM_ATTR __wrap_esp_system_abort(const char* details) {
    abort_record.magic = 0;
    abort_record.caller = uint32_t(__builtin_return_address(0));
    // Assertion text is normally formatted in internal DRAM. Never dereference
    // flash/PSRAM here: an abort may happen while its cache is disabled.
    size_t n = 0;
    while (n + 1 < REASON_SIZE && details && esp_ptr_in_dram(details + n)) {
        const char c = details[n];
        abort_record.reason[n++] = c;
        if (!c) break;
    }
    abort_record.reason[n] = 0;
    abort_record.magic = MAGIC;
    __real_esp_system_abort(details);
}

extern "C" void __real_esp_panic_handler(panic_info_t*) __attribute__((noreturn));
extern "C" void IRAM_ATTR __wrap_esp_panic_handler(panic_info_t* info) {
    retained.magic = 0;
    retained.core = info ? uint32_t(info->core) : UINT32_MAX;
    retained.exception = info ? uint32_t(info->exception) : UINT32_MAX;
    retained.stage = htit_retained_core_stage;
    const auto* frame = info ? static_cast<const XtExcFrame*>(info->frame) : nullptr;
    retained.pc = frame ? uint32_t(frame->pc) : 0;
    retained.a0 = frame ? uint32_t(frame->a0) : 0;
    retained.a1 = frame ? uint32_t(frame->a1) : 0;
    retained.cause = frame ? uint32_t(frame->exccause) : 0;
    retained.address = frame ? uint32_t(frame->excvaddr) : 0;
    retained.trace_count = 0;
    if (frame) {
        esp_backtrace_frame_t bt{uint32_t(frame->pc), uint32_t(frame->a1), uint32_t(frame->a0), frame};
        do {
            retained.trace[retained.trace_count++] = bt.pc;
            if (!bt.next_pc || retained.trace_count == TRACE_DEPTH) break;
        } while (internal_stack(bt) && esp_backtrace_get_next_frame(&bt));
    }
    retained.magic = MAGIC;
    __real_esp_panic_handler(info);
}
void htit_retained_panic_begin() {
    allocation_hook_ready=heap_caps_register_failed_alloc_callback(allocation_failed)==ESP_OK;
    reset_reason = esp_reset_reason();
    auto restore_frame=[](volatile EarlyRecord& in,EarlyRecord& out) {
        out.magic=in.magic;out.core=in.core;out.pc=in.pc;out.a0=in.a0;out.a1=in.a1;
        out.a2=in.a2;out.a3=in.a3;out.a4=in.a4;out.a5=in.a5;out.a6=in.a6;out.a7=in.a7;
        out.cause=in.cause;out.address=in.address;out.count=in.count<=16?in.count:0;
        for(size_t i=0;i<out.count;++i)out.trace[i]=in.trace[i];
        if(out.magic!=MAGIC)out={};in.magic=0;
    };
    for(size_t core=0;core<2;++core) {
        restore_frame(early[core],previous_early[core]);
        restore_frame(exceptions[core],previous_exceptions[core]);
    }
    previous.magic = retained.magic;
    previous.core = retained.core; previous.exception = retained.exception;
    previous.pc = retained.pc; previous.a0 = retained.a0; previous.a1 = retained.a1;
    previous.cause = retained.cause; previous.address = retained.address;
    previous.stage = retained.stage;
    previous.trace_count = retained.trace_count <= TRACE_DEPTH ? retained.trace_count : 0;
    for (size_t i=0; i<previous.trace_count; ++i) previous.trace[i] = retained.trace[i];
    previous_abort.magic = abort_record.magic;
    previous_abort.caller = abort_record.caller;
    for (size_t i=0; i<REASON_SIZE; ++i) previous_abort.reason[i] = abort_record.reason[i];
    previous_abort.reason[REASON_SIZE-1] = 0;
    if (previous_abort.magic != MAGIC) previous_abort = {};
    if (previous.magic != MAGIC) previous = {};
    retained.magic = 0; abort_record.magic = 0; htit_retained_core_stage = 0;
}
bool htit_retained_panic_has_fault() {
    return previous.magic == MAGIC || (reset_reason != ESP_RST_POWERON && reset_reason != ESP_RST_EXT);
}
void htit_retained_panic_metadata(MsgPack::Packer& p) {
    p.packMapSize(16);
    p.pack("reset_reason");p.pack(reset_reason);
    p.pack("panic_valid");p.pack(previous.magic == MAGIC);
    p.pack("core");p.pack(previous.core);p.pack("exception");p.pack(previous.exception);
    p.pack("pc");p.pack(previous.pc);p.pack("a0");p.pack(previous.a0);
    p.pack("a1");p.pack(previous.a1);p.pack("cause");p.pack(previous.cause);
    p.pack("abort_valid");p.pack(previous_abort.magic == MAGIC);
    p.pack("abort_caller");p.pack(previous_abort.caller);
    p.pack("abort_reason");p.pack(previous_abort.reason);
    p.pack("backtrace");p.packArraySize(previous.trace_count);
    for (size_t i=0; i<previous.trace_count; ++i) p.pack(previous.trace[i]);
    p.pack("address");p.pack(previous.address);p.pack("stage");p.pack(previous.stage);
    auto pack_frame=[&](const EarlyRecord& fault,const char* source) {
        p.packMapSize(15);p.pack("valid");p.pack(fault.magic==MAGIC);
        p.pack("core");p.pack(fault.core);p.pack("pc");p.pack(fault.pc);
        p.pack("a0");p.pack(fault.a0);p.pack("a1");p.pack(fault.a1);
        p.pack("a2");p.pack(fault.a2);p.pack("a3");p.pack(fault.a3);p.pack("a4");p.pack(fault.a4);
        p.pack("a5");p.pack(fault.a5);p.pack("a6");p.pack(fault.a6);p.pack("a7");p.pack(fault.a7);
        p.pack("cause");p.pack(fault.cause);p.pack("address");p.pack(fault.address);
        p.pack("backtrace");p.packArraySize(fault.count);
        for(size_t i=0;i<fault.count;++i)p.pack(fault.trace[i]);
        p.pack("source");p.pack(source);
    };
    p.pack("early_watchdogs");p.packArraySize(2);
    for(const auto& fault:previous_early)pack_frame(fault,"pre-cache-watchdog-handler");
    p.pack("early_exceptions");p.packArraySize(2);
    for(const auto& fault:previous_exceptions)pack_frame(fault,"pre-cache-exception-handler");
}
void htit_memory_diagnostics_metadata(MsgPack::Packer& p) {
    AllocationFailure failure{};
    if(!failure_guard.test_and_set(std::memory_order_acquire)) {
        failure=allocation_failure;
        failure_guard.clear(std::memory_order_release);
    }
    constexpr uint32_t internal=MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT;
    p.packMapSize(10);
    p.pack("hook_ready");p.pack(allocation_hook_ready);
    p.pack("internal_free");p.pack(heap_caps_get_free_size(internal));
    p.pack("internal_largest");p.pack(heap_caps_get_largest_free_block(internal));
    p.pack("internal_minimum");p.pack(heap_caps_get_minimum_free_size(internal));
    p.pack("psram_free");p.pack(heap_caps_get_free_size(MALLOC_CAP_SPIRAM));
    p.pack("psram_largest");p.pack(heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM));
    p.pack("failed_allocations");p.pack(allocation_failures.load(std::memory_order_relaxed));
    p.pack("failed_size");p.pack(failure.size);p.pack("failed_caps");p.pack(failure.caps);
    p.pack("failure_trace");p.packArraySize(failure.count);
    for(size_t i=0;i<failure.count;++i)p.pack(failure.trace[i]);
}
#endif
