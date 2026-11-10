#pragma once
#include <sys/mman.h>
#include <cerrno>
#include <cstring>
#include <stdexcept>
#include <string>
#include <cstdint>
#ifndef MAP_FIXED_NOREPLACE
#define MAP_FIXED_NOREPLACE 0x100000
#endif
namespace eka2l1::arm {
inline constexpr uintptr_t native_trampoline_address=0xb0000000;
inline void *&native_trampoline_mapping(){static void *mapping=nullptr;return mapping;}
// Reserve before graphics libraries create heaps/threads. Never replace any
// pre-existing host mapping; guest executable addresses remain unchanged.
inline void reserve_native_trampoline(){
 auto &mapping=native_trampoline_mapping();if(mapping)return;
 void *p=mmap(reinterpret_cast<void*>(native_trampoline_address),4096,PROT_NONE,
              MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE,-1,0);
 if(p==MAP_FAILED)throw std::runtime_error(std::string("native trampoline reservation: ")+std::strerror(errno));
 if(p!=reinterpret_cast<void*>(native_trampoline_address)){
  munmap(p,4096);throw std::runtime_error("native trampoline reservation returned a different address");
 }
 mapping=p;
}
inline void release_native_trampoline(){
 auto &mapping=native_trampoline_mapping();if(mapping){munmap(mapping,4096);mapping=nullptr;}
}
}
