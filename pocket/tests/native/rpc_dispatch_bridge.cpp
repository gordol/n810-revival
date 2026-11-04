#include "rpc_dispatch.h"
extern "C" int pocket_rpc_dispatch(const char* operation,const uint8_t* arguments,size_t length,
        pocket_rpc::Callback callback,const char* storage,uint8_t* output,size_t capacity) {
    if(!operation||!output)return -1;
    auto result=pocket_rpc::dispatch(std::string(operation),arguments,length,{callback,storage});
    MsgPack::Packer packer;pocket_rpc::pack_result(packer,result);
    if(packer.size()>capacity)return -1;
    std::memcpy(output,packer.data(),packer.size());return int(packer.size());
}
