#ifdef HTIT_EXECUTOR
#include <Arduino.h>
#include <EspIdfUartIram.h>
#include <esp_timer.h>
#include <soc/soc_memory_types.h>
#include <microReticulum.h>
#include <atomic>
#include <mutex>
#include <deque>
#include <algorithm>
#include <set>
#include "request_decode.h"
#include "Transport.h"
#include "Clock.h"
extern "C" bool htit_executor_router_online();
extern "C" bool htit_executor_fw_hash_matches(const uint8_t*,size_t);
extern "C" int htit_executor_available(int);
extern "C" int htit_executor_read(int);
extern "C" uint32_t htit_executor_bt_rx_overruns();
extern "C" uint32_t htit_bt_internal_allocations();
extern "C" uint32_t htit_bt_internal_failures();
#ifdef HTIT_RADIO_DIAGNOSTICS
extern "C" void htit_executor_radio_diagnostics(uint32_t*);
#endif
extern "C" bool htit_executor_connected(int);
extern "C" size_t htit_executor_write(int,const uint8_t*,size_t);
extern "C" void htit_executor_legacy(uint8_t);
extern "C" const char* htit_executor_identity();
extern "C" int pocket_rns_poll();
extern "C" uint32_t htit_executor_lora_margin();
extern bool htit_executor_owns_incoming(const uint8_t*,size_t);
extern bool htit_executor_owns_packet(const uint8_t*,size_t);
extern "C" int pocket_rns_stamp_result(void*,size_t);
#ifdef HTIT_RETAIN_PANIC
extern volatile uint32_t htit_retained_core_stage;
extern void htit_retained_panic_begin();
extern void htit_retained_panic_metadata(MsgPack::Packer&);
extern void htit_memory_diagnostics_metadata(MsgPack::Packer&);
extern bool htit_retained_panic_has_fault();
#endif
namespace {
using Buffer=std::vector<uint8_t,RNS::Utilities::Memory::ContainerAllocator<uint8_t>>;
constexpr size_t MAX_FRAME=32768,MAX_QUEUE=8;
constexpr uint32_t LEASE_MS=5000;
struct Frame {int port;Buffer body;int command=0x88;uint32_t id=0;size_t offset=0;int lane=0;int channel=0;};
std::mutex guard,txguard,diagguard;
std::array<std::array<int,32>,4> diag_channels{};
std::array<uint32_t,4> diag_counts{};
std::atomic<uint32_t> uart_errors[6]{};
std::atomic<uint32_t> protocol_errors{0},rejected_legacy{0};
std::atomic<unsigned> core_stage{0};
std::atomic<uint64_t> core_entered_us{0};
void diagnostic(int stage,int channel){if(!channel)return;std::lock_guard<std::mutex> lock(diagguard);diag_channels[stage][diag_counts[stage]++%32]=channel;}
std::deque<Frame> pending,legacy,tx;
uint32_t tx_counter=0;size_t tx_count[4]={0,0,0,0};
#ifdef HTIT_SPP_RX_TRACE
constexpr size_t TX_LIMITS[4]={16,8,8,128};
#else
constexpr size_t TX_LIMITS[4]={16,8,8,4};
#endif
std::set<int> active_channels;
std::atomic<bool> started{false};
std::string session;int owner=-1,subscription=0;uint32_t deadline=0,generation=0;
bool initialized=false,reset_due=false;
bool stamp_pending=false;int stamp_port=0,stamp_channel=0;uint32_t stamp_generation=0;
bool native_scope=false;
int legacy_port=0;
struct Tag {uint16_t start;uint32_t gen;};
std::vector<Tag> lora_tags;
Buffer legacy_tx;
std::string callback_token;int callback_answer=-1;
uint32_t callback_counter=0;
bool live_locked(){return owner>=0 && int32_t(deadline-millis())>0 && htit_executor_connected(owner);}
void expire_locked(){if(owner>=0&&!live_locked()){owner=-1;session.clear();subscription=0;reset_due=true;++generation;pocket_rpc::pocket_rns_cancel_stamp();callback_answer=0;}}
void packstr(MsgPack::Packer& p,const std::string& s){p.pack(s.c_str(),s.size());}
Buffer kiss(uint8_t command,const uint8_t* body,size_t n){
 Buffer wire;wire.reserve(2*n+3);wire.push_back(0xc0);wire.push_back(command);
 for(size_t i=0;i<n;++i){uint8_t b=body[i];if(b==0xc0){wire.push_back(0xdb);b=0xdc;}else if(b==0xdb){wire.push_back(0xdb);b=0xdd;}wire.push_back(b);}wire.push_back(0xc0);return wire;
}
bool queue_tx(Frame&& frame,bool reliable){
 const int lane=frame.lane;
 for(;;){
  {std::lock_guard<std::mutex> lock(txguard);
   if(tx_count[lane]<TX_LIMITS[lane]){frame.id=++tx_counter;if(!frame.id)frame.id=++tx_counter;tx.push_back(std::move(frame));++tx_count[lane];return true;}}
  if(!reliable||!htit_executor_connected(frame.port))return false;
  // Writer runs independently; a full event lane cannot consume reply/control
  // credits. An admitted result waits for space instead of disappearing.
  vTaskDelay(pdMS_TO_TICKS(2));
 }
}
bool enqueue(int port,uint8_t command,const uint8_t* body,size_t n,int lane=0,int channel=0){
 if(n>MAX_FRAME)return false;Frame f{port,{body,body+n}};f.command=command;f.lane=lane;f.channel=channel;
 return queue_tx(std::move(f),lane!=3);
}
#ifdef HTIT_SPP_RX_TRACE
void trace_frame(uint8_t command,const uint8_t* data,size_t length){
 if(!started||length>4096)return;
 static std::atomic<uint32_t> sequence{0};uint32_t hash=2166136261u;
 for(size_t i=0;i<length;++i)hash=(hash^data[i])*16777619u;
 uint32_t id=++sequence;
 Frame f{0,{uint8_t(id>>24),uint8_t(id>>16),uint8_t(id>>8),uint8_t(id),uint8_t(hash>>24),uint8_t(hash>>16),uint8_t(hash>>8),uint8_t(hash)}};
 f.body.insert(f.body.end(),data,data+length);f.command=command;f.lane=3;
 queue_tx(std::move(f),false);
}
#endif

void reply(int port,int channel,MsgPack::Packer& p,int lane=0){
 // Packer contains the complete response map, including its channel.
 Buffer wire{'P','S',2,uint8_t(p.size()>>24),uint8_t(p.size()>>16),uint8_t(p.size()>>8),uint8_t(p.size())};
 wire.insert(wire.end(),p.data(),p.data()+p.size());enqueue(port,0x88,wire.data(),wire.size(),lane,channel);
}
void ack(int port,int channel){MsgPack::Packer p;p.packMapSize(3);p.pack("version");p.pack(1);p.pack("channel");p.pack(channel);p.pack("core");p.packMapSize(5);p.pack("stage");p.pack(core_stage.load());p.pack("elapsed_ms");p.pack(uint64_t((esp_timer_get_time()-core_entered_us.load())/1000));p.pack("pending");p.pack(pending.size());p.pack("active");p.pack(active_channels.size());p.pack("tx");{std::lock_guard<std::mutex> lock(txguard);p.packArraySize(4);for(auto count:tx_count)p.pack(count);}reply(port,channel,p);}
void error(int port,int channel,const char* message){MsgPack::Packer p;p.packMapSize(4);p.pack("owner_online");p.pack(true);p.pack("version");p.pack(1);p.pack("channel");p.pack(channel);p.pack("error");p.pack(message);reply(port,channel,p);}
void result_reply(int port,int channel,const pocket_rpc::Result& result){
 MsgPack::Packer body;pocket_rpc::pack_result(body,result);
 MsgPack::Packer out;out.packMapSize((result.result<0?4:3)+1);out.pack("channel");out.pack(channel);
 Buffer response(out.data(),out.data()+out.size());response.insert(response.end(),body.data()+1,body.data()+body.size());
 Buffer wire{'P','S',2,uint8_t(response.size()>>24),uint8_t(response.size()>>16),uint8_t(response.size()>>8),uint8_t(response.size())};wire.insert(wire.end(),response.begin(),response.end());diagnostic(2,channel);enqueue(port,0x88,wire.data(),wire.size(),1,channel);
}
void info(int port,int channel){
 // Lifecycle and responsive cancellation were accepted on the actual board.
 MsgPack::Packer p;p.packMapSize(8);p.pack("version");p.pack(1);p.pack("channel");p.pack(channel);p.pack("protocol");p.pack(1);p.pack("abi");p.pack(2);p.pack("identity");p.pack(htit_executor_identity());p.pack("lease_seconds");p.pack(5);p.pack("online");p.pack(htit_executor_router_online());p.pack("features");p.packArraySize(4);p.pack("links");p.pack("endpoints");p.pack("resources");p.pack("lxmf");reply(port,channel,p);
}
void protocol_error(int port,const char* message){
 ++protocol_errors;
 {std::lock_guard<std::mutex> lock(guard);if(owner==port){owner=-1;session.clear();subscription=0;reset_due=true;++generation;pocket_rpc::pocket_rns_cancel_stamp();callback_answer=0;}}
 error(port,0,message);
}
bool safe_legacy(const Frame& f){
 if(f.body.empty())return false;uint8_t command=f.body[0];
 if(command==0x86){
  // Provisioning writes/configuration are not an executor transport service.
  return f.body.size()>=3&&f.body[1]==0x93&&f.body[2]>=1&&f.body[2]<=4;
 }
 if(command==0x58){
  return f.port==0&&owner<0&&!reset_due&&f.body.size()==33&&htit_executor_fw_hash_matches(f.body.data()+1,32);
 }
 if(f.body.size()!=2)return false;
 uint8_t value=f.body[1];
 switch(command){
  case 0x08:return value==0x73;
  case 0x47:case 0x48:case 0x49:case 0x50:return value==0;
  case 0x56:return value==1;
  case 0x60:return value>=1&&value<=4;
  case 0x51:case 0x6d:return value==0||value==0xff;
  default:return false;
 }
}
void legacy_frame(Frame&& f){
 bool accepted;
 {std::lock_guard<std::mutex> lock(guard);accepted=safe_legacy(f)&&legacy.size()<MAX_QUEUE;if(accepted)legacy.push_back(std::move(f));}
 if(!accepted){++rejected_legacy;protocol_error(f.port,"Unsupported or malformed executor KISS command");}
}
void control(Frame&& f){
 int channel=0;
 try{
  const auto& b=f.body;if(b.size()<8||b.size()>MAX_FRAME||b[0]!='P'||b[1]!='S'||b[2]!=2)throw std::invalid_argument("Invalid PS02 envelope");
  size_t n=(size_t(b[3])<<24)|(size_t(b[4])<<16)|(size_t(b[5])<<8)|b[6];if(n!=b.size()-7)throw std::invalid_argument("Invalid PS02 length");
  auto r=pocket_rpc::decode_request(b.data()+7,n);channel=r.channel;
  std::lock_guard<std::mutex> lock(guard);expire_locked();
  if(r.action=="native_open"){
   if(owner>=0||reset_due)throw std::invalid_argument("Node context busy");
   if(r.abi!=2||r.identity!=htit_executor_identity())throw std::invalid_argument("Wrong node identity or ABI");
   htit_executor_set_epoch_ms(r.unix_ms);owner=f.port;session=r.session;deadline=millis()+LEASE_MS;++generation;info(f.port,r.channel);return;
  }
  if(!live_locked()||owner!=f.port||session!=r.session)throw std::invalid_argument("Node lease expired");
  if(r.action=="native_renew"){deadline=millis()+LEASE_MS;ack(f.port,r.channel);}
  else if(r.action=="native_cancel"){pocket_rpc::pocket_rns_cancel_stamp();MsgPack::Packer p;p.packMapSize(4);p.pack("version");p.pack(1);p.pack("channel");p.pack(r.channel);p.pack("result");p.pack(0);p.pack("outputs");p.packArraySize(0);reply(f.port,r.channel,p);}
  else if(r.action=="native_callback"){
   if(r.token!=callback_token||r.data.size!=1)throw std::invalid_argument("Unknown callback or invalid result");callback_answer=r.data.data[0]?1:0;ack(f.port,r.channel);
  }else if(r.action=="subscribe"){
   subscription=r.channel;MsgPack::Packer p;p.packMapSize(4);p.pack("version");p.pack(1);p.pack("channel");p.pack(r.channel);p.pack("session");packstr(p,session);p.pack("ready");p.pack(true);reply(f.port,r.channel,p);
  }else{
   if(active_channels.size()>=MAX_QUEUE)throw std::invalid_argument("Native operation queue full");
   if(active_channels.count(r.channel))throw std::invalid_argument("Duplicate native channel");
   for(const auto& queued:pending){auto other=pocket_rpc::decode_request(queued.body.data()+7,queued.body.size()-7);if(other.channel==r.channel)throw std::invalid_argument("Duplicate native channel");}
   diagnostic(0,r.channel);active_channels.insert(r.channel);pending.push_back(std::move(f));
  }
 }catch(const std::exception& e){if(!channel)protocol_error(f.port,e.what());else error(f.port,channel,e.what());}
}
struct Assembly {int port;uint32_t id,updated;size_t total;Buffer bytes;};
std::vector<Assembly> assemblies;
void fragment(int port,const Buffer& raw){
 uint32_t now=millis();assemblies.erase(std::remove_if(assemblies.begin(),assemblies.end(),[&](const Assembly& a){return now-a.updated>10000||!htit_executor_connected(a.port);}),assemblies.end());
 if(raw.size()<10||raw.size()>1033){char reason[96];snprintf(reason,sizeof(reason),"Invalid owner fragment size: %u (expected 10..1033)",unsigned(raw.size()));protocol_error(port,reason);return;} // command + header + 1..1024 data
 uint32_t id=(uint32_t(raw[1])<<24)|(uint32_t(raw[2])<<16)|(uint32_t(raw[3])<<8)|raw[4];
 size_t offset=(size_t(raw[5])<<8)|raw[6],total=(size_t(raw[7])<<8)|raw[8],n=raw.size()-9;
 auto it=std::find_if(assemblies.begin(),assemblies.end(),[&](const Assembly& a){return a.port==port&&a.id==id;});
 if(!id||!total||total>MAX_FRAME||offset+n>total){if(it!=assemblies.end())assemblies.erase(it);protocol_error(port,"Invalid owner fragment range");return;}
 if(it==assemblies.end()){if(offset||assemblies.size()>=8){protocol_error(port,"Owner fragment assembly unavailable");return;}assemblies.push_back({port,id,now,total,{}});it=assemblies.end()-1;it->bytes.reserve(total);}
 if(it->total!=total||it->bytes.size()!=offset){assemblies.erase(it);protocol_error(port,"Out-of-order owner fragment");return;}
 it->updated=now;it->bytes.insert(it->bytes.end(),raw.begin()+9,raw.end());
 if(it->bytes.size()==total){Frame complete{port,std::move(it->bytes)};assemblies.erase(it);control(std::move(complete));}
}
struct Parser {
 Buffer bytes;bool escaping=false,overflow=false,active=false;
 void clear(){bytes.clear();escaping=false;overflow=false;}
 void feed(int port,uint8_t byte){
  if(byte==0xc0){
   if(active&&(overflow||escaping))protocol_error(port,"Malformed or oversized KISS frame");
   else if(active&&!bytes.empty()){
#ifdef HTIT_SPP_RX_TRACE
    if(port==1)trace_frame(0x8b,bytes.data(),bytes.size());
#endif
    uint8_t command=bytes[0];if(command==0x89)fragment(port,bytes);
    else {Frame f{port,{bytes.begin()+1,bytes.end()}};if(command==0x88)control(std::move(f));else {f.body.insert(f.body.begin(),command);legacy_frame(std::move(f));}}
   }
   clear();active=true;return;
  }
  if(!active||overflow)return;
  if(escaping){if(byte==0xdc)byte=0xc0;else if(byte==0xdd)byte=0xdb;else{overflow=true;return;}escaping=false;}
  else if(byte==0xdb){escaping=true;return;}
  if(bytes.size()>=MAX_FRAME+1){overflow=true;bytes.clear();return;}bytes.push_back(byte);
 }
};
void reader(void*){Parser parsers[2];for(;;){for(int port=0;port<2;++port){if(!htit_executor_connected(port)){parsers[port].clear();parsers[port].active=false;continue;}int count=0;
#ifdef HTIT_SPP_RX_TRACE
 uint8_t captured[256];size_t captured_size=0;
#endif
 while(count++<256&&htit_executor_available(port)>0){uint8_t byte=uint8_t(htit_executor_read(port));
#ifdef HTIT_SPP_RX_TRACE
 if(port==1)captured[captured_size++]=byte;
#endif
 parsers[port].feed(port,byte);}
#ifdef HTIT_SPP_RX_TRACE
 if(captured_size)trace_frame(0x8e,captured,captured_size);
#endif
 }{std::lock_guard<std::mutex> lock(guard);expire_locked();}vTaskDelay(pdMS_TO_TICKS(2));}}
void writer(void*){
 Frame bulk;bool have_bulk=false;
 for(;;){
  Frame f;bool have=false;
  {std::lock_guard<std::mutex> lock(txguard);
   auto it=std::find_if(tx.begin(),tx.end(),[](const Frame& a){return a.lane==0;});
   if(it==tx.end())it=std::find_if(tx.begin(),tx.end(),[](const Frame& a){return a.lane==1&&a.body.size()<=1024;});
   if(it!=tx.end()){f=std::move(*it);tx.erase(it);have=true;}
   else if(have_bulk){f=std::move(bulk);have_bulk=false;have=true;}
   else if(!tx.empty()){
    it=std::min_element(tx.begin(),tx.end(),[](const Frame& a,const Frame& b){return a.lane<b.lane;});f=std::move(*it);tx.erase(it);have=true;
   }
  }
  if(!have){vTaskDelay(pdMS_TO_TICKS(2));continue;}
  Buffer wire;bool more=false;
  if(f.command<0)wire=f.body;
  else if(f.command==0x88&&f.body.size()>1024){
   size_t n=std::min(size_t(1024),f.body.size()-f.offset);
   Buffer part{uint8_t(f.id>>24),uint8_t(f.id>>16),uint8_t(f.id>>8),uint8_t(f.id),uint8_t(f.offset>>8),uint8_t(f.offset),uint8_t(f.body.size()>>8),uint8_t(f.body.size())};
   part.insert(part.end(),f.body.begin()+f.offset,f.body.begin()+f.offset+n);wire=kiss(0x89,part.data(),part.size());f.offset+=n;more=f.offset<f.body.size();
  }else wire=kiss(f.command,f.body.data(),f.body.size());
  size_t sent=0;while(sent<wire.size()&&htit_executor_connected(f.port)){
   size_t n=htit_executor_write(f.port,wire.data()+sent,std::min(size_t(128),wire.size()-sent));sent+=n;if(!n)vTaskDelay(pdMS_TO_TICKS(2));
  }
  if(more&&sent==wire.size()){bulk=std::move(f);have_bulk=true;}
  else {if(f.lane==1&&sent==wire.size())diagnostic(3,f.channel);std::lock_guard<std::mutex> lock(txguard);--tx_count[f.lane];}
 }
}
int event(const unsigned char* raw,size_t n,unsigned char* output,size_t capacity){
 HtitCoreStage stage(9);
 int port,channel;uint32_t gen;std::string sess,token;
 // Only resource advertisements require a synchronous decision. Event payload
 // uses a map whose first key is event; parse that name without copying secrets.
 // Engine event() emits event as its first field, encoded as fixed strings.
 const char prefix[]="\xa5" "event" "\xb3" "resource_advertised";
 bool decision=n>=sizeof(prefix) && (raw[0]&0xf0)==0x80 &&
     !memcmp(raw+1,prefix,sizeof(prefix)-1);
 {std::lock_guard<std::mutex> lock(guard);expire_locked();if(!live_locked()||!subscription)return 0;port=owner;channel=subscription;gen=generation;sess=session;if(decision){char t[32];snprintf(t,sizeof(t),"%08lx%08lx",(unsigned long)generation,(unsigned long)++callback_counter);token=t;callback_token=token;callback_answer=-1;}}
 MsgPack::Packer p;p.packMapSize(5);p.pack("version");p.pack(1);p.pack("channel");p.pack(channel);p.pack("session");packstr(p,sess);p.pack("native_event");p.packBinary(raw,n);p.pack("callback");if(decision)packstr(p,token);else p.pack(nullptr);reply(port,channel,p,decision?0:2);
 if(!decision||!capacity)return 0;
 uint32_t until=millis()+4000;for(;;){{std::lock_guard<std::mutex> lock(guard);expire_locked();if(gen!=generation||!live_locked()){callback_token.clear();return 0;}if(callback_answer>=0){output[0]=uint8_t(callback_answer);callback_token.clear();return 1;}}if(int32_t(until-millis())<=0)return 0;vTaskDelay(pdMS_TO_TICKS(2));}
}
}
HtitCoreStage::HtitCoreStage(unsigned stage):previous(core_stage.load()),started(core_entered_us.load()){core_entered_us=esp_timer_get_time();core_stage=stage;
#if defined(HTIT_RETAIN_PANIC) && defined(HTIT_RADIO_DIAGNOSTICS)
htit_retained_core_stage=stage;
#endif
}
#ifdef HTIT_SPP_RX_TRACE
extern "C" void htit_executor_bt_trace(const uint8_t* data,size_t length,const void* queue){
 static bool reported=false;if(!reported){uint8_t external=esp_ptr_external_ram(queue)?1:0;trace_frame(0x8f,&external,1);reported=true;}
 trace_frame(esp_ptr_external_ram(data)?0x8c:0x8a,data,length);
}
#ifdef HTIT_HCI_RX_TRACE
extern "C" void htit_executor_hci_trace(const uint8_t* data,size_t length){
 trace_frame(0x8d,data,length);
}
#endif
#endif
HtitCoreStage::~HtitCoreStage(){core_stage=previous;core_entered_us=started;
#if defined(HTIT_RETAIN_PANIC) && defined(HTIT_RADIO_DIAGNOSTICS)
htit_retained_core_stage=previous;
#endif
}
void htit_executor_pack_metadata(MsgPack::Packer& p){
 std::lock_guard<std::mutex> lock(guard);expire_locked();
 size_t fields=18;
#ifdef HTIT_RETAIN_PANIC
 bool report_reset=htit_retained_panic_has_fault();
#ifdef HTIT_RADIO_DIAGNOSTICS
 report_reset=true;
#endif
#endif
#ifdef HTIT_RADIO_DIAGNOSTICS
 ++fields;
#endif
#ifdef HTIT_RETAIN_PANIC
 ++fields;
 if(report_reset)++fields;
#endif
 p.packMapSize(fields);
#ifdef HTIT_RETAIN_PANIC
 p.pack("memory_diagnostics");htit_memory_diagnostics_metadata(p);
 if(report_reset){p.pack("reset_diagnostics");htit_retained_panic_metadata(p);}
#endif
#ifdef HTIT_RADIO_DIAGNOSTICS
 p.pack("radio_diagnostics");
 uint32_t values[12]{};htit_executor_radio_diagnostics(values);
 const char* names[]={"rx_irq_edges","rx_irq_coalesced","rx_irq_handled","max_rx_irq_delay_us","dispatch_without_rx_done","received_packets","rx_queue_drops","rx_alloc_failures","tx_packets","queued_bytes","queued_packets","airtime_locked"};
 p.packMapSize(12);for(unsigned i=0;i<12;++i){p.pack(names[i]);p.pack(values[i]);}
#endif
 p.pack("resource_limit");p.pack(30000);p.pack("protocol");p.pack(1);p.pack("abi");p.pack(2);p.pack("identity");p.pack(htit_executor_identity());p.pack("lease_seconds");p.pack(5);
 p.pack("online");p.pack(htit_executor_router_online());p.pack("features");p.packArraySize(4);p.pack("links");p.pack("endpoints");p.pack("resources");p.pack("lxmf");
 p.pack("available");p.pack(!reset_due&&(owner<0||owner==legacy_port));
 p.pack("framing");p.pack("kiss-fragment-v1");p.pack("fragment_size");p.pack(1024);
 p.pack("development");p.pack(true);
 p.pack("uptime_ms");p.pack(uint64_t(esp_timer_get_time()/1000));
 p.pack("clock");p.pack("unix-ms-v1");p.pack("clock_synced");p.pack(htit_executor_clock_synced());
 p.pack("text_limit");p.pack(240);p.pack("lxmf_receive_limit");p.pack(15000);
 p.pack("rx_diagnostics");p.packMapSize(6);p.pack("bt_internal_allocations");p.pack(htit_bt_internal_allocations());p.pack("bt_internal_failures");p.pack(htit_bt_internal_failures());p.pack("bluetooth_overruns");p.pack(htit_executor_bt_rx_overruns());p.pack("uart_errors");p.packArraySize(6);for(unsigned i=0;i<6;++i)p.pack(uart_errors[i].load());p.pack("protocol_errors");p.pack(protocol_errors.load());p.pack("rejected_legacy");p.pack(rejected_legacy.load());

 p.pack("debug");p.packMapSize(4);
 {std::lock_guard<std::mutex> diagnostic_lock(diagguard);const char* names[]={"accepted","completed","replied","written"};
 for(size_t stage=0;stage<4;++stage){p.pack(names[stage]);size_t count=std::min(size_t(diag_counts[stage]),size_t(32));p.packArraySize(count);size_t first=diag_counts[stage]-count;for(size_t i=0;i<count;++i)p.pack(diag_channels[stage][(first+i)%32]);}}

}
int htit_executor_ingress_enter(const uint8_t* raw,size_t length){
 if(!started||!htit_executor_owns_incoming(raw,length))return 0;
 std::lock_guard<std::mutex> lock(guard);if(!live_locked())return -1;int token=native_scope?2:1;native_scope=true;return token;
}
void htit_executor_ingress_exit(int token){if(token>0)native_scope=token==2;}
uint32_t htit_executor_packet_generation(const uint8_t* raw,size_t length){
 if(!started||(!native_scope&&!htit_executor_owns_packet(raw,length)))return 0;
 std::lock_guard<std::mutex> lock(guard);return live_locked()?generation:UINT32_MAX;
}
bool htit_executor_generation_live(uint32_t gen,uint32_t margin_ms){
 if(!gen)return true;std::lock_guard<std::mutex> lock(guard);
 return gen==generation&&live_locked()&&uint32_t(deadline-millis())>margin_ms;
}
bool htit_executor_lora_tag(uint16_t start,uint32_t gen){
 if(!htit_executor_generation_live(gen,htit_executor_lora_margin()))return false;
 for(const auto& tag:lora_tags)if(tag.start==start)return false;
 if(lora_tags.size()>=64)return false;lora_tags.push_back({start,gen});return true;
}
bool htit_executor_lora_permit(uint16_t start){
 for(auto it=lora_tags.begin();it!=lora_tags.end();++it)if(it->start==start){uint32_t gen=it->gen;lora_tags.erase(it);return htit_executor_generation_live(gen,htit_executor_lora_margin());}return true;
}
void htit_executor_uart_error(unsigned kind){if(kind<6)++uart_errors[kind];}
#ifdef HTIT_RADIO_RX_TASK
extern "C" bool htit_executor_start_radio_rx();
#endif
bool htit_executor_begin(){htit_uart_iram_driver_link_anchor();if(started)return true;
#ifdef HTIT_RETAIN_PANIC
htit_retained_panic_begin();
#endif
TaskHandle_t w=nullptr,r=nullptr;if(xTaskCreate(writer,"executor-tx",4096,nullptr,1,&w)!=pdPASS)return false;if(xTaskCreate(reader,"executor-io",8192,nullptr,2,&r)!=pdPASS){vTaskDelete(w);return false;}
#ifdef HTIT_RADIO_RX_TASK
if(!htit_executor_start_radio_rx()){vTaskDelete(r);vTaskDelete(w);return false;}
#endif
started=true;return true;}
bool htit_executor_serial_byte(uint8_t b){
 if(!started)return false;
 if(b==0xc0){
  if(!legacy_tx.empty()){Frame f{legacy_port,std::move(legacy_tx)};f.command=-1;f.lane=0;f.body.push_back(0xc0);queue_tx(std::move(f),true);legacy_tx.clear();}
  else legacy_tx.push_back(0xc0);
 }else if(legacy_tx.size()<4096)legacy_tx.push_back(b);
 return true;
}
bool htit_executor_log(const char* s,size_t n){if(!started)return false;enqueue(0,0x80,reinterpret_cast<const uint8_t*>(s),std::min(n,size_t(512)),3);return true;}

void htit_executor_tick(){
 if(!started)return;Frame call,old;bool have=false,oldhave=false,reset=false;uint32_t gen=0;
 {std::lock_guard<std::mutex> lock(guard);expire_locked();if(reset_due){reset=true;pending.clear();active_channels.clear();}else if(!pending.empty()){call=std::move(pending.front());pending.pop_front();have=true;gen=generation;}if(!legacy.empty()){old=std::move(legacy.front());legacy.pop_front();oldhave=true;}}
 if(reset){native_scope=true;pocket_rpc::pocket_rns_reset();native_scope=false;initialized=false;stamp_pending=false;std::lock_guard<std::mutex> lock(guard);reset_due=false;}
 if(oldhave){bool safe;{std::lock_guard<std::mutex> lock(guard);safe=safe_legacy(old);}if(!safe){protocol_error(old.port,"Legacy maintenance is unavailable while leased");oldhave=false;}}
 if(oldhave){legacy_port=old.port;htit_executor_legacy(0xc0);for(uint8_t b:old.body){if(b==0xc0){htit_executor_legacy(0xdb);b=0xdc;}else if(b==0xdb){htit_executor_legacy(0xdb);b=0xdd;}htit_executor_legacy(b);}htit_executor_legacy(0xc0);}
 if(have){auto r=pocket_rpc::decode_request(call.body.data()+7,call.body.size()-7);bool valid;{std::lock_guard<std::mutex> lock(guard);expire_locked();valid=live_locked()&&gen==generation&&owner==call.port&&session==r.session;}
  if(valid){HtitCoreStage stage(5);native_scope=true;auto result=pocket_rpc::dispatch(r.operation,r.arguments.data,r.arguments.size,{event,"/executor"});native_scope=false;diagnostic(1,r.channel);
   if(r.operation=="lxmf_send"&&result.result==-2){stamp_pending=true;stamp_port=call.port;stamp_channel=r.channel;stamp_generation=gen;}
   else {bool valid_now;{std::lock_guard<std::mutex> lock(guard);valid_now=gen==generation&&live_locked();active_channels.erase(r.channel);}if(valid_now)result_reply(call.port,r.channel,result);else error(call.port,r.channel,"Node lease expired during operation");}
   if(r.operation=="init"&&result.result>=0)initialized=true;
   if(r.operation=="reset"&&result.result>=0){initialized=false;stamp_pending=false;std::lock_guard<std::mutex> lock(guard);owner=-1;session.clear();subscription=0;++generation;pending.clear();active_channels.clear();}

  }else {error(call.port,r.channel,"Node lease expired");std::lock_guard<std::mutex> lock(guard);active_channels.erase(r.channel);}
 }
 if(stamp_pending){
  bool active;{std::lock_guard<std::mutex> lock(guard);expire_locked();active=live_locked()&&stamp_generation==generation;}
  if(!active){pocket_rpc::pocket_rns_cancel_stamp();stamp_pending=false;}
  else {std::vector<uint8_t> output(MAX_FRAME);native_scope=true;int n=pocket_rns_stamp_result(output.data(),output.size());native_scope=false;if(n!=-2){pocket_rpc::Result result;result.result=n;if(n<0)result.native_error=pocket_rpc::pocket_rns_error();else{output.resize(n);result.outputs.push_back(std::move(output));}result_reply(stamp_port,stamp_channel,result);stamp_pending=false;std::lock_guard<std::mutex> lock(guard);active_channels.erase(stamp_channel);}}
 }
 if(initialized){bool active;{std::lock_guard<std::mutex> lock(guard);active=live_locked();}if(active){native_scope=true;pocket_rns_poll();native_scope=false;}}
}
#endif
