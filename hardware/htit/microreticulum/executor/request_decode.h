#pragma once
#include "rpc_dispatch.h"
// The transport validates PS02/KISS lengths first. This decoder owns strings;
// binary/argument spans borrow that immutable body through operation completion.
namespace pocket_rpc {
struct Span {const uint8_t* data=nullptr;size_t size=0;};
struct Request {
    int channel=0,abi=0;
    int64_t unix_ms=0; // Optional native_open clock; zero means absent.
    std::string action,session,identity,operation,token;
    Span arguments,data;
};
class RequestReader:private Cursor {
    std::string string(size_t maximum) {
        uint8_t tag=uint8_t(take(1));size_t n;
        if((tag&0xe0)==0xa0)n=tag&31;
        else if(tag>=0xd9&&tag<=0xdb)n=size_t(take(size_t(1)<<(tag-0xd9)));
        else throw std::invalid_argument("Native request string required");
        if(!n||n>maximum||n>length-pos)throw std::invalid_argument("Native request string length");
        const char* start=reinterpret_cast<const char*>(data+pos);
        if(std::memchr(start,0,n))throw std::invalid_argument("Native request contains NUL");
        pos+=n;return std::string(start,n);
    }
    int integer() {
        Value v=value();
        if(v.kind!=Value::integer||v.i<0||v.i>std::numeric_limits<int32_t>::max())throw std::invalid_argument("Native request integer required");
        return int(v.i);
    }
    void hex_identity(const std::string& s) {
        if(s.size()!=32)throw std::invalid_argument("Native request identity length");
        for(char c:s)if(!((c>='0'&&c<='9')||(c>='a'&&c<='f')))throw std::invalid_argument("Native request identity encoding");
    }
public:
    RequestReader(const uint8_t* body,size_t n):Cursor(body,n){}
    Request read() {
        uint8_t tag=uint8_t(take(1));size_t count;
        if((tag&0xf0)==0x80)count=tag&15;
        else if(tag==0xde||tag==0xdf)count=size_t(take(tag==0xde?2:4));
        else throw std::invalid_argument("Native request must be a map");
        if(count>16)throw std::invalid_argument("Native request field limit");
        enum {version=1,channel=2,action=4,session=8,identity=16,abi=32,operation=64,arguments=128,token=256,binary=512,clock=1024};
        unsigned seen=0;Request r;
        for(size_t i=0;i<count;++i) {
            const auto key=string(16);unsigned field=0;
            if(key=="version")field=version;else if(key=="channel")field=channel;else if(key=="action")field=action;
            else if(key=="session")field=session;else if(key=="identity")field=identity;else if(key=="abi")field=abi;
            else if(key=="operation")field=operation;else if(key=="arguments")field=arguments;else if(key=="token")field=token;else if(key=="data")field=binary;
            else if(key=="unix_ms")field=clock;
            else throw std::invalid_argument("Unknown native request field");
            if(seen&field)throw std::invalid_argument("Duplicate native request field");seen|=field;
            switch(field) {
                case version:if(integer()!=1)throw std::invalid_argument("Native request version");break;
                case channel:r.channel=integer();if(!r.channel)throw std::invalid_argument("Native request channel");break;
                case action:r.action=string(32);break;
                case session:r.session=string(32);hex_identity(r.session);break;
                case identity:r.identity=string(32);hex_identity(r.identity);break;
                case abi:r.abi=integer();break;
                case clock:{Value v=value();if(v.kind!=Value::integer||v.i<=0)throw std::invalid_argument("Native request Unix milliseconds required");r.unix_ms=v.i;break;}
                case operation:r.operation=string(32);break;
                case token:r.token=string(64);break;
                case arguments:{size_t start=pos;array();r.arguments={data+start,pos-start};break;}
                case binary:{Value v=value();if(v.kind!=Value::binary)throw std::invalid_argument("Native request data must be binary");r.data={v.data,v.size};break;}
            }
        }
        if(pos!=length)throw std::invalid_argument("Trailing native request data");
        unsigned expected=version|channel|action|session;
        if(r.action=="native_open")expected|=identity|abi|(seen&clock);
        else if(r.action=="native_call")expected|=operation|arguments;
        else if(r.action=="native_callback")expected|=token|binary;
        else if(r.action!="native_renew"&&r.action!="native_cancel"&&r.action!="subscribe")throw std::invalid_argument("Unsupported native request action");
        if(seen!=expected)throw std::invalid_argument("Native request fields do not match action");
        return r;
    }
};
inline Request decode_request(const uint8_t* body,size_t length){return RequestReader(body,length).read();}
} // namespace pocket_rpc
