#pragma once
// ABI-2 argument boundary shared by native tests and embedded executors.
// No session, filesystem or scheduler ownership. Input spans borrow the request.
#include <MsgPack.h>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstddef>
#include <cstring>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>
#include <utility>

namespace pocket_rpc {
constexpr size_t limit=32768;
static_assert(sizeof(int)==4,"Pocket native ABI 2 requires 32-bit int");
using Callback=int(*)(const unsigned char*,size_t,unsigned char*,size_t);
extern "C" {
int pocket_rns_init(Callback,const char*); int pocket_rns_reset(); int pocket_rns_online(int);
int pocket_rns_incoming(const void*,size_t); int pocket_rns_identity(const void*,size_t,int);
int pocket_rns_key(int,int,void*,size_t); int pocket_rns_destination(int,int,const char*,const char*,void*);
int pocket_rns_handler(int,const char*,int,const void*,size_t); int pocket_rns_announce(int,const void*,size_t);
int pocket_rns_public(int,int); int pocket_rns_remove_destination(int); int pocket_rns_link(int,void*);
int pocket_rns_link_id(int,void*); int pocket_rns_remote(int); int pocket_rns_identify(int,int);
int pocket_rns_request(int,const char*,const void*,size_t,int,double);
int pocket_rns_reply(int,const void*,size_t,const void*,size_t); int pocket_rns_teardown(int);
int pocket_rns_resources(int,int); int pocket_rns_resource(int,const void*,size_t,int);
int pocket_rns_has_path(const void*); int pocket_rns_hops(const void*);
int pocket_rns_lxmf_init(int,const char*,void*); int pocket_rns_lxmf_public(int); int pocket_rns_lxmf_announce();
int pocket_rns_lxmf_remember(int); int pocket_rns_lxmf_send(int,const void*,size_t,int,int,void*);
int pocket_rns_appdata(const void*,void*,size_t); int pocket_rns_cancel_stamp(); const char* pocket_rns_error();
}
struct Value {
    enum Kind {nil,integer,boolean,number,binary} kind=nil;
    int64_t i=0; double d=0; const uint8_t* data=nullptr; size_t size=0;
};
struct Arguments {
    std::array<Value,6> values{}; size_t count=0;
    const Value& at(size_t n) const {if(n>=count)throw std::invalid_argument("Native argument index");return values[n];}
    void arity(size_t n) const {if(count!=n)throw std::invalid_argument("Native argument count");}
    int integer(size_t n) const {
        const auto& v=at(n);
        if((v.kind!=Value::integer&&v.kind!=Value::boolean)||v.i<std::numeric_limits<int32_t>::min()||v.i>std::numeric_limits<int32_t>::max())throw std::invalid_argument("Native integer argument");
        return static_cast<int>(v.i);
    }
    size_t size(size_t n,size_t multiplier=1) const {
        const auto& v=at(n);
        if(v.kind!=Value::integer||v.i<0||!multiplier||uint64_t(v.i)>limit/multiplier)throw std::invalid_argument("Native buffer capacity");
        return size_t(v.i)*multiplier;
    }
    const void* bytes(size_t n,size_t length) const {
        const auto& v=at(n);
        if(length>limit||v.kind!=Value::binary||v.size!=length)throw std::invalid_argument("Native input buffer length");
        return v.data;
    }
    void output(size_t n) const {if(at(n).kind!=Value::nil)throw std::invalid_argument("Native output placeholder");}
    std::string string(size_t n) const {
        const auto& v=at(n);
        if(v.kind!=Value::binary||v.size>limit||std::memchr(v.data,0,v.size))throw std::invalid_argument("Native string argument");
        return std::string(reinterpret_cast<const char*>(v.data),v.size);
    }
    double number(size_t n) const {
        const auto& v=at(n);
        double d=v.kind==Value::number?v.d:v.kind==Value::integer?double(v.i):std::numeric_limits<double>::quiet_NaN();
        if(!std::isfinite(d))throw std::invalid_argument("Native numeric argument");
        return d;
    }
};
// Only the ABI's flat array of scalars/binary is accepted. Bounds are checked
// before every read; no generic recursive MessagePack parser sees peer bytes.
class Cursor {
protected:
    const uint8_t* data; size_t length,pos=0;
    uint64_t take(size_t n) {
        if(n>length-pos)throw std::invalid_argument("Truncated native arguments");
        uint64_t value=0;while(n--)value=(value<<8)|data[pos++];return value;
    }
    Value value() {
        Value v;uint8_t tag=uint8_t(take(1));
        if(tag==0xc0)return v;
        if(tag==0xc2||tag==0xc3){v.kind=Value::boolean;v.i=tag==0xc3;return v;}
        if(tag==0xc4||tag==0xc5||tag==0xc6){
            size_t n=size_t(take(size_t(1)<<(tag-0xc4)));
            if(n>limit||n>length-pos)throw std::invalid_argument("Native binary length");
            v.kind=Value::binary;v.data=data+pos;v.size=n;pos+=n;return v;
        }
        if(tag==0xca||tag==0xcb){
            v.kind=Value::number;
            if(tag==0xca){uint32_t bits=uint32_t(take(4));float number;std::memcpy(&number,&bits,4);v.d=number;}
            else {uint64_t bits=take(8);std::memcpy(&v.d,&bits,8);}
            if(!std::isfinite(v.d))throw std::invalid_argument("Native numeric argument");
            return v;
        }
        v.kind=Value::integer;
        if(tag<=0x7f){v.i=tag;return v;}
        if(tag>=0xe0){v.i=int(tag)-256;return v;}
        bool signed_value=tag>=0xd0&&tag<=0xd3;
        if(!signed_value&&(tag<0xcc||tag>0xcf))throw std::invalid_argument("Unsupported native argument type");
        size_t bytes=size_t(1)<<(tag-(signed_value?0xd0:0xcc));uint64_t raw=take(bytes);
        if(signed_value&&(raw&(uint64_t(1)<<(bytes*8-1)))) {
            uint64_t magnitude=bytes==8?~raw+1:(uint64_t(1)<<(bytes*8))-raw;
            v.i=magnitude==(uint64_t(1)<<63)?std::numeric_limits<int64_t>::min():-int64_t(magnitude);
        }else {
            if(raw>uint64_t(std::numeric_limits<int64_t>::max()))throw std::invalid_argument("Native integer overflow");
            v.i=int64_t(raw);
        }
        return v;
    }
    Cursor(const uint8_t* raw,size_t n):data(raw),length(n){if(!raw||!n||n>limit)throw std::invalid_argument("Native argument frame size");}
    Arguments array() {
        uint8_t tag=uint8_t(take(1));size_t n;
        if((tag&0xf0)==0x90)n=tag&15;
        else if(tag==0xdc||tag==0xdd)n=size_t(take(tag==0xdc?2:4));
        else throw std::invalid_argument("Native arguments must be an array");
        Arguments args;if(n>args.values.size())throw std::invalid_argument("Native argument count");args.count=n;
        for(size_t i=0;i<n;++i)args.values[i]=value();
        return args;
    }
};
class Reader:private Cursor {
public:
    Reader(const uint8_t* raw,size_t n):Cursor(raw,n){}
    Arguments read(){auto args=array();if(pos!=length)throw std::invalid_argument("Trailing native arguments");return args;}
};
struct Context {Callback callback; const char* storage;};
struct Result {int result=-1; std::vector<std::vector<uint8_t>> outputs; std::string native_error;};
inline Result dispatch(const std::string& operation,const uint8_t* raw,size_t length,const Context& context) {
    Result r;
    try {
        if(operation.empty()||operation.size()>32)throw std::invalid_argument("Invalid native operation");
        const Arguments a=Reader(raw,length).read();std::vector<uint8_t> output;uint8_t empty_output=0;bool variable=false;
        auto buffer=[&](size_t index,size_t capacity)->void*{a.output(index);output.resize(capacity);return capacity?output.data():&empty_output;};
#define OP(name,n) if(operation==#name) {a.arity(n);
#define NEXT(name,n) } else OP(name,n)
        OP(init,2)
            a.output(0);a.string(1);
            if(!context.callback||!context.storage)throw std::invalid_argument("Executor init context required");
            r.result=pocket_rns_init(context.callback,context.storage);
        NEXT(reset,0) r.result=pocket_rns_reset();
        NEXT(online,1) r.result=pocket_rns_online(a.integer(0));
        NEXT(incoming,2) r.result=pocket_rns_incoming(a.bytes(0,a.size(1)),a.size(1));
        NEXT(identity,3) r.result=pocket_rns_identity(a.bytes(0,a.size(1)),a.size(1),a.integer(2));
        NEXT(key,4) r.result=pocket_rns_key(a.integer(0),a.integer(1),buffer(2,a.size(3)),a.size(3));variable=true;
        NEXT(destination,5) r.result=pocket_rns_destination(a.integer(0),a.integer(1),a.string(2).c_str(),a.string(3).c_str(),buffer(4,16));
        NEXT(handler,5)
            if(a.size(4)>16)throw std::invalid_argument("Native grant limit");
            r.result=pocket_rns_handler(a.integer(0),a.string(1).c_str(),a.integer(2),a.bytes(3,a.size(4,16)),a.size(4));
        NEXT(announce,3) r.result=pocket_rns_announce(a.integer(0),a.bytes(1,a.size(2)),a.size(2));
        NEXT(public,2) r.result=pocket_rns_public(a.integer(0),a.integer(1));
        NEXT(remove_destination,1) r.result=pocket_rns_remove_destination(a.integer(0));
        NEXT(link,2)
            a.bytes(1,16);std::array<uint8_t,16> scratch{};std::memcpy(scratch.data(),a.at(1).data,16);
            r.result=pocket_rns_link(a.integer(0),scratch.data());
        NEXT(link_id,2) r.result=pocket_rns_link_id(a.integer(0),buffer(1,16));
        NEXT(remote,1) r.result=pocket_rns_remote(a.integer(0));
        NEXT(identify,2) r.result=pocket_rns_identify(a.integer(0),a.integer(1));
        NEXT(request,6) r.result=pocket_rns_request(a.integer(0),a.string(1).c_str(),a.bytes(2,a.size(3)),a.size(3),a.integer(4),a.number(5));
        NEXT(reply,5) r.result=pocket_rns_reply(a.integer(0),a.bytes(1,a.size(2)),a.size(2),a.bytes(3,a.size(4)),a.size(4));
        NEXT(teardown,1) r.result=pocket_rns_teardown(a.integer(0));
        NEXT(resources,2) r.result=pocket_rns_resources(a.integer(0),a.integer(1));
        NEXT(resource,4) r.result=pocket_rns_resource(a.integer(0),a.bytes(1,a.size(2)),a.size(2),a.integer(3));
        NEXT(has_path,1) r.result=pocket_rns_has_path(a.bytes(0,16));
        NEXT(hops,1) r.result=pocket_rns_hops(a.bytes(0,16));
        NEXT(lxmf_init,3) r.result=pocket_rns_lxmf_init(a.integer(0),a.string(1).c_str(),buffer(2,16));
        NEXT(lxmf_public,1) r.result=pocket_rns_lxmf_public(a.integer(0));
        NEXT(lxmf_announce,0) r.result=pocket_rns_lxmf_announce();
        NEXT(lxmf_remember,1) r.result=pocket_rns_lxmf_remember(a.integer(0));
        NEXT(lxmf_send,6) r.result=pocket_rns_lxmf_send(a.integer(0),a.bytes(1,a.size(2)),a.size(2),a.integer(3),a.integer(4),buffer(5,limit));variable=true;
        NEXT(appdata,3) r.result=pocket_rns_appdata(a.bytes(0,16),buffer(1,a.size(2)),a.size(2));variable=true;
        NEXT(cancel_stamp,0) r.result=pocket_rns_cancel_stamp();
        } else throw std::invalid_argument("Unsupported native operation");
#undef OP
#undef NEXT
        if(r.result<0){const char* error=pocket_rns_error();if(error){size_t n=0;while(n<240&&error[n])++n;r.native_error.assign(error,n);}else r.native_error="Native operation failed";return r;}
        if(variable){if(size_t(r.result)>output.size())throw std::invalid_argument("Native output length");output.resize(size_t(r.result));}
        if(variable||!output.empty())r.outputs.push_back(std::move(output));
    }catch(const std::exception& error){r.result=-1;r.outputs.clear();r.native_error=std::string(error.what()).substr(0,240);}
    return r;
}
inline void pack_result(MsgPack::Packer& packer,const Result& result) {
    packer.packMapSize(result.result<0?4:3);packer.pack("version");packer.pack(1);
    packer.pack("result");packer.pack(result.result);packer.pack("outputs");packer.packArraySize(result.outputs.size());
    for(const auto& output:result.outputs)packer.packBinary(output.data(),output.size());
    if(result.result<0){packer.pack("native_error");packer.pack(result.native_error.c_str(),result.native_error.size());}
}
} // namespace pocket_rpc
