// Pocket's bounded C ABI over the pinned, stock-compatible microReticulum core.
// Service policies remain in service_bridge.py; no alternative crypto or wire format.
#include <microReticulum.h>
#include <LXMF/LXMRouter.h>
#include <LXMF/LXStamper.h>
#include <atomic>
#include <microStore/FileSystem.h>
#include <microStore/Adapters/UniversalFileSystem.h>
#include <MsgPack.h>
#include <mutex>
#include <map>
#include <vector>
#include <stdexcept>
#include <cstring>
#include <cstdio>
#include <cstdlib>
using namespace RNS;
namespace {
constexpr size_t LIMIT=32768;
using Callback=int(*)(const unsigned char*,size_t,unsigned char*,size_t);
Callback callback=nullptr;
std::recursive_mutex mutex;
thread_local std::string engine_error;
Reticulum stack({Type::NONE});
std::unique_ptr<LXMF::LXMRouter> messaging;
std::map<Bytes,int> message_tokens;
bool message_public=false;
std::atomic<bool> stamp_cancel{false};
std::map<int,Identity> identities;
std::map<int,Destination> destinations;
std::map<int,Link> links;
std::set<int> public_destinations;
std::map<Bytes,int> link_ids,requests,resources,incoming_resources;
struct RetainedResource {Resource resource;int link;};
std::map<Bytes,RetainedResource> retained_resources;
int counter=0;
int trace_count=0;
int next(){if(counter>=2147483646)throw std::runtime_error("Native handle limit reached");return ++counter;}
Bytes bytes(const void* p,size_t n){if(n>LIMIT||(!p&&n))throw std::runtime_error("Native buffer limit exceeded");return Bytes((const uint8_t*)p,n);}
void binary(MsgPack::Packer& p,const Bytes& b){p.packBinary(b.data(),b.size());}
MsgPack::Packer event(const char* name,int handle,size_t extra=0){MsgPack::Packer p;p.packMapSize(2+extra);p.pack("event");p.pack(name);p.pack("handle");p.pack(handle);return p;}
Bytes emit(MsgPack::Packer& p){
    if(!callback)return {Bytes::NONE};
    std::vector<unsigned char> result(LIMIT);
    int n=callback(p.data(),p.size(),result.data(),result.size());
    if(n<0||size_t(n)>result.size())throw std::runtime_error("Invalid native callback result");
    return Bytes(result.data(),n);
}
Bytes bin_decode(const Bytes& encoded){MsgPack::Unpacker u;u.feed(encoded.data(),encoded.size());if(!u.isBin())throw std::runtime_error("Expected binary RNS payload");MsgPack::bin_t<uint8_t> b;u.deserialize(b);if(b.size()>LIMIT)throw std::runtime_error("RNS response exceeds service limit");return Bytes(b.data(),b.size());}
Bytes bin_encode(const Bytes& b){MsgPack::Packer p;binary(p,b);return Bytes(p.data(),p.size());}
int remember_identity(const Identity& identity){if(!identity)return 0;for(auto& entry:identities)if(entry.second.get_public_key()==identity.get_public_key())return entry.first;if(identities.size()>=256)throw std::runtime_error("Identity limit reached");int id=next();identities.emplace(id,identity);return id;}
int remember_link(const Link& link){auto it=link_ids.find(link.link_id());if(it!=link_ids.end())return it->second;if(links.size()>=64)throw std::runtime_error("Link limit reached");int id=next();links.emplace(id,link);link_ids.emplace(link.link_id(),id);return id;}
void closed(Link& link){int id=remember_link(link);auto p=event("closed",id);emit(p);link_ids.erase(link.link_id());links.erase(id);}
void resource_received(const Resource& resource){auto found=incoming_resources.find(resource.hash());if(found==incoming_resources.end())return;int handle=found->second;incoming_resources.erase(found);auto p=event("resource",handle,3);p.pack("status");p.pack((int)resource.status());p.pack("data");binary(p,resource.data());p.pack("resource");binary(p,resource.hash());emit(p);}
void resource_advertised(const ResourceAdvertisement& ad){
    if(ad.get_data_size()>LIMIT||ad.get_transfer_size()>LIMIT+1024)throw std::runtime_error("Resource exceeds service limit");
    int handle=remember_link(ad.get_link());auto p=event("resource_advertised",handle,1);p.pack("size");p.pack(ad.get_data_size());auto answer=emit(p);
    if(answer.size()!=1||!answer.data()[0])throw std::runtime_error("Resource not authorized");
    incoming_resources[ad.get_hash()]=handle;
}
void established(Link& link){int id=remember_link(link);link.set_link_closed_callback(closed);auto p=event("established",id,2);p.pack("destination");binary(p,link.destination().hash());p.pack("remote");p.pack(remember_identity(link.get_remote_identity()));emit(p);}
void response(const RequestReceipt& receipt){auto it=requests.find(receipt.get_request_id());if(it==requests.end())return;auto p=event("response",it->second,1);p.pack("data");auto value=receipt.get_response();if(value.size() && value.data()[0]>=0xc4 && value.data()[0]<=0xc6)value=bin_decode(value);binary(p,value);requests.erase(it);emit(p);}
void failed(const RequestReceipt& receipt){auto it=requests.find(receipt.get_request_id());if(it==requests.end())return;auto p=event("failed",it->second);requests.erase(it);emit(p);}
void delivered(const Resource& resource){if(getenv("POCKET_RNS_TRACE"))fprintf(stderr,"native resource delivered status=%d known=%zu\n",int(resource.status()),resources.count(resource.hash()));auto it=resources.find(resource.hash());if(it==resources.end())return;auto p=event("delivered",it->second,1);p.pack("status");p.pack((int)resource.status());resources.erase(it);emit(p);}
Bytes respond(const Bytes& path,const Bytes& data,const Bytes& request,const Bytes& link,const Identity& remote,double at){
    if(!remote)return {Bytes::NONE};auto p=event("request",link_ids.at(link),6);
    p.pack("path");binary(p,path);p.pack("data");binary(p,bin_decode(data));p.pack("request");binary(p,request);
    p.pack("link");binary(p,link);p.pack("remote");p.pack(remember_identity(remote));p.pack("at");p.pack(at);
    auto result=emit(p);return result?bin_encode(result):Bytes(Bytes::NONE);
}
void message_event(LXMF::LXMessage& message,bool incoming){
    if(getenv("POCKET_RNS_TRACE"))fprintf(stderr,"native lxmf event incoming=%d state=%d bytes=%zu\n",incoming,int(message.state()),message.content().size());
    int token=incoming?0:(message_tokens.count(message.hash())?message_tokens.at(message.hash()):0);
    auto identity=incoming?Identity::recall(message.source_hash()):Identity(Type::NONE);
    int remote=identity?remember_identity(identity):0;
    auto p=event("lxmf",token,11);
    p.pack("incoming");p.pack(incoming);p.pack("state");p.pack((int)message.state());
    p.pack("hash");binary(p,message.hash());p.pack("source");binary(p,message.source_hash());
    p.pack("destination");binary(p,message.destination_hash());p.pack("content");binary(p,message.content());
    p.pack("signature");p.pack(message.signature_validated());p.pack("reason");p.pack((int)message.unverified_reason());
    p.pack("remote");p.pack(remote);p.pack("timestamp");p.pack(message.timestamp());p.pack("packed");binary(p,message.packed());
    emit(p);
    if(!incoming&&(message.state()==LXMF::Type::Message::DELIVERED||message.state()==LXMF::Type::Message::FAILED||message.state()==LXMF::Type::Message::REJECTED))message_tokens.erase(message.hash());
}
class Radio:public InterfaceImpl {
public:Radio():InterfaceImpl("Pocket radio"){_IN=true;_OUT=true;_online=false;_bitrate=1000;_HW_MTU=508;}
    bool send_outgoing(const Bytes& data) override {if(getenv("POCKET_RNS_TRACE") && trace_count++<128){Packet packet(data);packet.unpack();fprintf(stderr,"native TX type=%d context=%d bytes=%zu dest=%s\n",int(packet.packet_type()),int(packet.context()),packet.data().size(),packet.destination_hash().toHex().c_str());}auto p=event("outgoing",0,1);p.pack("data");binary(p,data);auto result=emit(p);return result.size()==1&&result.data()[0];}
    void incoming(const Bytes& data){handle_incoming(data);}
    void online(bool value){_online=value;}
};
class Announces:public AnnounceHandler {
public:Announces():AnnounceHandler(nullptr){}
    void received_announce(const Bytes& destination,const Identity& identity,const Bytes& data) override {
        if(identities.size()>=128){bool known=false;for(auto& entry:identities)if(entry.second.get_public_key()==identity.get_public_key()){known=true;break;}if(!known)return;}
        auto p=event("announce",remember_identity(identity),2);p.pack("destination");binary(p,destination);p.pack("data");binary(p,data);emit(p);
    }
};
HAnnounceHandler observer(new Announces());
Radio* radio=nullptr;
Interface radio_interface({Type::NONE});
}
#define API_BEGIN std::lock_guard<std::recursive_mutex> guard(mutex);try {
#define API_END }catch(const std::exception& e){engine_error=e.what();return -1;}catch(...){engine_error="Native Reticulum failure";return -1;}
extern "C" {
int pocket_rns_abi(){return 2;}
int pocket_rns_cancel_stamp(){stamp_cancel.store(true);return 0;}
const char* pocket_rns_error(){return engine_error.c_str();}
int pocket_rns_init(Callback cb,const char* storage){API_BEGIN
    if(callback)throw std::runtime_error("One native stack per process");callback=cb;stamp_cancel.store(false);
    if(radio)return 0;
    static microStore::FileSystem filesystem{microStore::Adapters::UniversalFileSystem()};filesystem.init();Utilities::OS::register_filesystem(filesystem);
    Reticulum::storagepath(storage);RNS::loglevel(RNS::LOG_NONE);
    radio=new Radio();radio_interface=radio;Transport::register_interface(radio_interface);
    stack=Reticulum();stack.transport_enabled(false);stack.start();Transport::register_announce_handler(observer);return 0;API_END}
int pocket_rns_reset(){API_BEGIN
    if(radio)radio->online(false);
    if(messaging){
        std::vector<Link> all;for(auto& link:Transport::active_links())all.push_back(link);for(auto& link:Transport::pending_links())all.push_back(link);
        for(auto& link:all)link.teardown();
        Transport::deregister_destination(messaging->delivery_destination());messaging.reset();
    }
    message_tokens.clear();message_public=false;
    while(!links.empty()){int id=links.begin()->first;Link link=links.begin()->second;link.teardown();link_ids.erase(link.link_id());links.erase(id);}
    for(auto& entry:destinations)Transport::deregister_destination(entry.second);
    for(auto& entry:retained_resources)entry.second.resource.cancel();
    destinations.clear();public_destinations.clear();identities.clear();link_ids.clear();requests.clear();resources.clear();incoming_resources.clear();retained_resources.clear();
    callback=nullptr;return 0;API_END}
int pocket_rns_poll(){API_BEGIN
    stack.loop();
    if(messaging){messaging->process_outbound();messaging->process_inbound();}
    std::vector<Bytes> finished;
    for(auto& entry:retained_resources){auto& resource=entry.second.resource;auto link=links.find(entry.second.link);
        if(link==links.end()||link->second.status()==Type::Link::CLOSED){resource.cancel();finished.push_back(entry.first);}
        else if(resource.status()>=Type::Resource::COMPLETE)finished.push_back(entry.first);
        else if(resource.status()==Type::Resource::QUEUED && link->second.ready_for_new_resource())resource.advertise_job();
    }
    for(auto& key:finished)retained_resources.erase(key);
    return 0;API_END}
int pocket_rns_online(int online){API_BEGIN radio->online(online!=0);return 0;API_END}
int pocket_rns_incoming(const void* data,size_t n){API_BEGIN
    auto raw=bytes(data,n);Packet packet(raw);if(!packet.unpack())return 0;
    if(getenv("POCKET_RNS_TRACE")&&packet.packet_type()==Type::Packet::PROOF&&packet.context()==Type::Packet::CONTEXT_NONE)fprintf(stderr,"native packet proof receipts=%zu size=%zu active_links=%zu\n",Transport::receipts().size(),packet.data().size(),Transport::active_links().size());
    if(getenv("POCKET_RNS_TRACE") && trace_count++<128)fprintf(stderr,"native RX type=%d desttype=%d context=%d bytes=%zu dest=%s\n",int(packet.packet_type()),int(packet.destination_type()),int(packet.context()),packet.data().size(),packet.destination_hash().toHex().c_str());
    bool accepted=false;
    if(packet.packet_type()==Type::Packet::ANNOUNCE) {
        accepted=true;
    }else if(packet.destination_type()==Type::Destination::LINK){radio->incoming(raw);return 1;}
    else if(packet.destination_type()==Type::Destination::PLAIN){
        auto data=packet.data();if(data.size()>=16){auto target=data.left(16);
            for(int id:public_destinations)if(destinations.at(id).hash()==target)accepted=true;
            if(messaging&&message_public&&messaging->delivery_destination().hash()==target)accepted=true;
        }
    }
    else if(messaging&&messaging->delivery_destination().hash()==packet.destination_hash())accepted=true;
    else for(auto& entry:destinations)if(entry.second.direction()==Type::Destination::IN && entry.second.hash()==packet.destination_hash()){accepted=true;break;}
    if(accepted)radio->incoming(raw);return accepted?1:0;API_END}
int pocket_rns_identity(const void* data,size_t n,int private_key){API_BEGIN
    Identity identity(n==0);if(n){if(private_key){if(n!=64||!identity.load_private_key(bytes(data,n)))throw std::runtime_error("Invalid private identity");}else{if(n!=64)throw std::runtime_error("Invalid public identity");identity.load_public_key(bytes(data,n));}}
    return remember_identity(identity);API_END}
int pocket_rns_key(int id,int private_key,void* output,size_t capacity){API_BEGIN auto b=private_key?identities.at(id).get_private_key():identities.at(id).get_public_key();if(b.size()>capacity)throw std::runtime_error("Key buffer too small");memcpy(output,b.data(),b.size());return b.size();API_END}
int pocket_rns_destination(int identity,int direction,const char* app,const char* aspects,void* output){API_BEGIN
    if(destinations.size()>=128)throw std::runtime_error("Destination limit reached");int id=next();Destination destination(identities.at(identity),(Type::Destination::directions)direction,Type::Destination::SINGLE,app,aspects);destination.set_link_established_callback(established);memcpy(output,destination.hash().data(),16);destinations.emplace(id,destination);return id;API_END}
int pocket_rns_handler(int destination,const char* path,int policy,const void* allowed,size_t count){API_BEGIN
    if(count>16)throw std::runtime_error("Grant limit reached");std::set<Bytes> keys;for(size_t i=0;i<count;++i)keys.emplace((const uint8_t*)allowed+i*16,16);
    destinations.at(destination).register_request_handler(Bytes(path),respond,(Type::Destination::request_policies)policy,keys,false);return 0;API_END}
int pocket_rns_public(int destination,int enabled){API_BEGIN
    if(enabled)public_destinations.insert(destination);else public_destinations.erase(destination);return 0;API_END}
int pocket_rns_remove_destination(int destination){API_BEGIN
    auto it=destinations.find(destination);if(it!=destinations.end()){Transport::deregister_destination(it->second);destinations.erase(it);}public_destinations.erase(destination);return 0;API_END}
int pocket_rns_announce(int destination,const void* data,size_t n){API_BEGIN destinations.at(destination).announce(bytes(data,n));return 0;API_END}
int pocket_rns_link(int destination,void* output){API_BEGIN
    Link link(destinations.at(destination),established,closed);int id=remember_link(link);memcpy(output,link.link_id().data(),16);return id;API_END}
int pocket_rns_link_id(int id,void* output){API_BEGIN memcpy(output,links.at(id).link_id().data(),16);return 16;API_END}
int pocket_rns_remote(int id){API_BEGIN auto& link=links.at(id);auto remote=link.get_remote_identity();if(!remote&&link.initiator())remote=link.destination().identity();return remember_identity(remote);API_END}
int pocket_rns_identify(int id,int identity){API_BEGIN links.at(id).identify(identities.at(identity));return 0;API_END}
int pocket_rns_request(int id,const char* path,const void* data,size_t n,int token,double timeout){API_BEGIN
    auto receipt=links.at(id).request(Bytes(path),bin_encode(bytes(data,n)),response,failed,nullptr,timeout);if(!receipt)return 0;requests.emplace(receipt.get_request_id(),token);return 1;API_END}
int pocket_rns_reply(int id,const void* request,size_t request_size,const void* data,size_t n){API_BEGIN
    auto it=links.find(id);if(it==links.end()||it->second.status()!=Type::Link::ACTIVE)return 0;
    MsgPack::Packer p;p.packArraySize(2);binary(p,bytes(request,request_size));binary(p,bytes(data,n));Bytes packed(p.data(),p.size());
    if(packed.size()<=it->second.get_mdu())Packet(it->second,packed).context(Type::Packet::RESPONSE).send();
    else {
        if(retained_resources.size()>=128)throw std::runtime_error("Native resource limit reached");
        auto resource=Resource(packed,it->second).auto_compress(false).request_id(bytes(request,request_size)).is_response(true).start();
        retained_resources.emplace(resource.hash(),RetainedResource{resource,id});
    }
    return 1;API_END}
int pocket_rns_teardown(int id){API_BEGIN auto it=links.find(id);if(it!=links.end()){Link link=it->second;link.teardown();}return 0;API_END}
int pocket_rns_resources(int id,int strategy){API_BEGIN auto& link=links.at(id);link.set_resource_strategy((Type::Link::resource_strategy)strategy);link.set_resource_callback(resource_advertised);link.set_resource_concluded_callback(resource_received);return 0;API_END}
int pocket_rns_resource(int id,const void* data,size_t n,int token){API_BEGIN
    if(retained_resources.size()>=128)throw std::runtime_error("Native resource limit reached");
    auto resource=Resource(bytes(data,n),links.at(id)).auto_compress(false).set_concluded_callback(delivered).start();resources.emplace(resource.hash(),token);retained_resources.emplace(resource.hash(),RetainedResource{resource,id});if(getenv("POCKET_RNS_TRACE"))fprintf(stderr,"native resource started token=%d bytes=%zu hash=%s\n",token,n,resource.hash().toHex().c_str());return 0;API_END}
int pocket_rns_lxmf_init(int identity,const char* name,void* output){API_BEGIN
    if(messaging)throw std::runtime_error("Messaging already initialized");
    messaging.reset(new LXMF::LXMRouter(identities.at(identity),"",false));
    messaging->set_display_name(name);messaging->set_announce_interval(0);
    messaging->register_delivery_callback([](LXMF::LXMessage& m){message_event(m,true);});
    messaging->register_delivered_callback([](LXMF::LXMessage& m){message_event(m,false);});
    messaging->register_failed_callback([](LXMF::LXMessage& m){message_event(m,false);});
    memcpy(output,messaging->delivery_destination().hash().data(),16);return 0;API_END}
int pocket_rns_appdata(const void* destination,void* output,size_t capacity){API_BEGIN
    auto data=Identity::recall_app_data(bytes(destination,16));
    if(data.size()>capacity)throw std::runtime_error("Announce metadata exceeds limit");
    if(data.size())memcpy(output,data.data(),data.size());return data.size();API_END}
int pocket_rns_lxmf_remember(int id){API_BEGIN
    auto& identity=identities.at(id);auto target=Destination::hash_from_name_and_identity("lxmf.delivery",identity);
    Identity::remember(Identity::full_hash(identity.get_public_key()),target,identity.get_public_key(),Identity::recall_app_data(target));return 0;API_END}
int pocket_rns_lxmf_public(int enabled){API_BEGIN message_public=enabled!=0;return 0;API_END}
int pocket_rns_lxmf_announce(){API_BEGIN if(!messaging||!message_public)return 0;messaging->announce();return 0;API_END}
int pocket_rns_lxmf_send(int destination,const void* content,size_t n,int token,int stamp_cost,void* output){API_BEGIN
    if(stamp_cancel.load())throw std::runtime_error("Owner is closing; message was not queued");
    if(stamp_cost<0||stamp_cost>255)throw std::runtime_error("Invalid LXMF stamp cost");
    if(!messaging||message_tokens.size()>=8)throw std::runtime_error("Messaging is unavailable or busy");
    if(n>240)throw std::runtime_error("Message exceeds text limit");
    auto& target=destinations.at(destination);auto identity=target.identity();
    Identity::remember(Identity::full_hash(identity.get_public_key()),target.hash(),identity.get_public_key(),Identity::recall_app_data(target.hash()));
    LXMF::LXMessage message(target,messaging->delivery_destination(),bytes(content,n),Bytes(),LXMF::Type::Message::DIRECT);
    message.pack();
    if(stamp_cost){
        auto result=LXMF::LXStamper::generate_stamp(message.hash(),stamp_cost,LXMF::LXStamper::WORKBLOCK_EXPAND_ROUNDS,&stamp_cancel);
        if(result.first.size()!=LXMF::LXStamper::STAMP_SIZE)throw std::runtime_error("Message stamp cancelled; message was not queued");
        message.stamp(result.first);message.content(bytes(content,n));message.pack();
    }
    if(stamp_cancel.load())throw std::runtime_error("Owner is closing; message was not queued");
    message_tokens.emplace(message.hash(),token);memcpy(output,message.hash().data(),32);memcpy((unsigned char*)output+32,message.packed().data(),message.packed().size());messaging->handle_outbound(message);return 32+message.packed().size();API_END}
int pocket_rns_hops(const void* data){API_BEGIN return Transport::hops_to(bytes(data,16));API_END}
int pocket_rns_has_path(const void* data){API_BEGIN return Transport::has_path(bytes(data,16));API_END}
}
