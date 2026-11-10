#pragma once
#include "direct_core.h"
#include <kernel/thread.h>
#include <mem/mem.h>
#include <cstdlib>
#include <cstring>
#include <stdexcept>
#include <cstdio>
// Called only after the independent RM-320 ROM fingerprints have passed.
// Patch loaded private mappings, never the supplied ROM or application file.
inline void apply_native_fast_exec(eka2l1::memory_system *memory,eka2l1::arm::core *cpu){
 const char *enabled=std::getenv("N810_SYMBIAN_FAST_TLS");if(!enabled||std::strcmp(enabled,"1"))return;
 auto *native=dynamic_cast<eka2l1::arm::direct_core*>(cpu);if(!native)throw std::runtime_error("Native fast TLS requires direct ARM backend");
 static_assert(offsetof(eka2l1::kernel::thread_local_data,heap)==0);
 static_assert(offsetof(eka2l1::kernel::thread_local_data,trap_handler)==8);
 struct patch {uint32_t va,svc,target;};const patch patches[]={{0x803a0350,0xef800001,0xb0000040},{0x803a0388,0xef800008,0xb0000050}};
 for(auto &p:patches){auto *words=(uint32_t*)memory->get_real_pointer(p.va);if(!words||words[0]!=p.svc||words[1]!=0xe12fff1e)throw std::runtime_error("Native fast executive fingerprint mismatch");}
 native->enable_fast_localdata(sizeof(eka2l1::kernel::thread_local_data));
 for(auto &p:patches){uint32_t jump[]={0xe51ff004,p.target};std::memcpy(memory->get_real_pointer(p.va),jump,sizeof jump);cpu->imb_range(p.va,sizeof jump);}
 std::printf("native_fast_exec=heap,trap_handler original_files_unchanged=1\n");
}
