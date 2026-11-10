#include <cassert>
#include "native_address_layout.h"
static bool enabled=false;
extern "C" int native_runtime_enabled(void){return enabled;}
int main(){
 using namespace eka2l1::mem;
 assert(native_kernel_boundary(0xc9200000,false,false)==0xc9200000);
 assert(native_kernel_boundary(0xffff0000,true,false)==0xffff0000);
 enabled=true;
 assert(native_kernel_boundary(0xc9200000,false,false)==0xa1000000);
 assert(native_kernel_boundary(0xffff0000,true,false)==0xaf000000);
 assert(native_kernel_boundary(0x58000000,false,true)==0x58000000);
 assert(native_kernel_boundary(0x60000000,true,true)==0x60000000);
 assert(native_kernel_end-native_kernel_begin>=1024*1024);
}
