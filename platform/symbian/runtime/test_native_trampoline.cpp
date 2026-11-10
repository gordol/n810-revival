#include "native_trampoline.h"
#include <cassert>
#include <sys/wait.h>
#include <unistd.h>
#include <cstdio>
int main(){
 using namespace eka2l1::arm;
 reserve_native_trampoline();assert(native_trampoline_mapping()==reinterpret_cast<void*>(native_trampoline_address));
 reserve_native_trampoline();assert(!mprotect(native_trampoline_mapping(),4096,PROT_READ|PROT_WRITE));
 auto *p=static_cast<unsigned*>(native_trampoline_mapping());*p=0x12345678;reserve_native_trampoline();assert(*p==0x12345678);
 release_native_trampoline();assert(!native_trampoline_mapping());
 void *other=mmap(reinterpret_cast<void*>(native_trampoline_address),4096,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE,-1,0);assert(other==reinterpret_cast<void*>(native_trampoline_address));
 *static_cast<unsigned*>(other)=0xabcdef12;bool rejected=false;try{reserve_native_trampoline();}catch(const std::runtime_error&){rejected=true;}
 assert(rejected&&!native_trampoline_mapping()&&*static_cast<unsigned*>(other)==0xabcdef12);
 munmap(other,4096);puts("PASS early reservation, idempotence, release and non-destructive collision rejection");
}
