#include "rpc_dispatch.h"
#include "request_decode.h"
#include <algorithm>
#include <cstdlib>
using pocket_rpc::Callback;
namespace {int calls=0,last_count=0,last_byte=0,override_result=-999;std::string storage;
int result(const char*,int normal=0){++calls;return override_result==-999?normal:override_result;}
void fill(void* p,size_t n,uint8_t c){if(n)std::memset(p,c,n);}
}
extern "C" {
int pocket_rns_init(Callback,const char* path){storage=path;return result("init");}
int pocket_rns_reset(){return result("reset");}
int pocket_rns_online(int){return result("online");}
int pocket_rns_incoming(const void*,size_t n){last_count=int(n);return result("incoming");}
int pocket_rns_identity(const void*,size_t n,int){last_count=int(n);return result("identity",7);}
int pocket_rns_key(int,int,void* p,size_t n){fill(p,n,'k');return result("key",int(n));}
int pocket_rns_destination(int,int,const char*,const char*,void* p){fill(p,16,'d');return result("destination",7);}
int pocket_rns_handler(int,const char*,int,const void* p,size_t n){last_count=int(n);if(n)last_byte=static_cast<const uint8_t*>(p)[n*16-1];return result("handler");}
int pocket_rns_announce(int,const void*,size_t n){last_count=int(n);return result("announce");}
int pocket_rns_public(int,int){return result("public");}
int pocket_rns_remove_destination(int){return result("remove_destination");}
int pocket_rns_link(int,void* p){fill(p,16,'l');return result("link",8);}
int pocket_rns_link_id(int,void* p){fill(p,16,'i');return result("link_id",16);}
int pocket_rns_remote(int){return result("remote",7);}
int pocket_rns_identify(int,int){return result("identify");}
int pocket_rns_request(int,const char*,const void*,size_t n,int,double){last_count=int(n);return result("request",1);}
int pocket_rns_reply(int,const void*,size_t,const void*,size_t n){last_count=int(n);return result("reply",1);}
int pocket_rns_teardown(int){return result("teardown");}
int pocket_rns_resources(int,int){return result("resources");}
int pocket_rns_resource(int,const void*,size_t n,int){last_count=int(n);return result("resource");}
int pocket_rns_has_path(const void*){return result("has_path",1);}
int pocket_rns_hops(const void*){return result("hops",2);}
int pocket_rns_lxmf_init(int,const char*,void* p){fill(p,16,'m');return result("lxmf_init");}
int pocket_rns_lxmf_public(int){return result("lxmf_public");}
int pocket_rns_lxmf_announce(){return result("lxmf_announce");}
int pocket_rns_lxmf_remember(int){return result("lxmf_remember");}
int pocket_rns_lxmf_send(int,const void*,size_t n,int,int,void* p){last_count=int(n);fill(p,36,'s');return result("lxmf_send",36);}
int pocket_rns_appdata(const void*,void* p,size_t n){size_t count=std::min(n,size_t(3));fill(p,count,'a');return result("appdata",int(count));}
int pocket_rns_cancel_stamp(){return result("cancel_stamp");}
const char* pocket_rns_error(){return "injected native error";}
int pocket_rpc_calls(){return calls;}
int pocket_rpc_count(){return last_count;}
int pocket_rpc_last_byte(){return last_byte;}
const char* pocket_rpc_storage(){return storage.c_str();}
void pocket_rpc_override(int n){override_result=n;}
int pocket_rpc_callback(const unsigned char*,size_t,unsigned char*,size_t){return 0;}
int pocket_rpc_request(const uint8_t* raw,size_t n,uint8_t* output,size_t capacity){
    MsgPack::Packer p;
    try {
        const auto r=pocket_rpc::decode_request(raw,n);
        p.packMapSize(10);p.pack("unix_ms");p.pack(r.unix_ms);p.pack("channel");p.pack(r.channel);p.pack("action");p.pack(r.action);p.pack("session");p.pack(r.session);
        p.pack("identity");p.pack(r.identity);p.pack("abi");p.pack(r.abi);p.pack("operation");p.pack(r.operation);p.pack("token");p.pack(r.token);
        p.pack("arguments");p.packBinary(r.arguments.data,r.arguments.size);p.pack("data");p.packBinary(r.data.data,r.data.size);
    }catch(const std::exception& error){p.packMapSize(1);p.pack("error");p.pack(std::string(error.what()));}
    if(p.size()>capacity)return -1;std::memcpy(output,p.data(),p.size());return int(p.size());
}
int pocket_rpc_test(const char* operation,const uint8_t* raw,size_t n,uint8_t* output,size_t capacity){
    auto r=pocket_rpc::dispatch(std::string(operation),raw,n,{pocket_rpc_callback,"/node/private"});
    MsgPack::Packer p;pocket_rpc::pack_result(p,r);
    if(p.size()>capacity)return -1;
    std::memcpy(output,p.data(),p.size());return int(p.size());
}
}
#ifdef POCKET_RPC_SANITIZER_MAIN
int main(){
    MsgPack::Packer request;request.packMapSize(6);
    request.pack("version");request.pack(1);request.pack("channel");request.pack(1);request.pack("action");request.pack("native_call");
    request.pack("session");request.pack(std::string(32,'a'));request.pack("operation");request.pack("online");request.pack("arguments");request.packArraySize(1);request.pack(true);
    const std::vector<uint8_t> reference(request.data(),request.data()+request.size());
    uint32_t seed=1;const char* names[]={"init","reset","identity","key","handler","request","lxmf_send","link","appdata"};
    for(unsigned i=0;i<100000;++i){
        std::array<uint8_t,80> data{};size_t n=i%data.size();
        for(size_t j=0;j<n;++j){seed=1664525*seed+1013904223;data[j]=uint8_t(seed>>24);}
        if(n>1){data[0]=uint8_t(0x90+(i%7));data[1]=uint8_t(i);}
        auto r=pocket_rpc::dispatch(names[i%9],data.data(),n,{pocket_rpc_callback,"/node"});
        MsgPack::Packer packer;pocket_rpc::pack_result(packer,r);
        auto mutated=reference;
        for(size_t j=0;j<1+i%3;++j){seed=1664525*seed+1013904223;mutated[seed%mutated.size()]=uint8_t(seed>>16);}
        size_t length=i%2?mutated.size():i%mutated.size();
        try{pocket_rpc::decode_request(mutated.data(),length);}catch(const std::exception&) {}
    }
    const uint8_t empty[]={0x90};
    auto bad=pocket_rpc::dispatch(std::string("reset\0suffix",12),empty,1,{nullptr,nullptr});
    return bad.result<0?0:1;
}
#endif
