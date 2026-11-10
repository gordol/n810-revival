#include "direct_core.h"
#include "native_trampoline.h"
#include <sys/ptrace.h>
#include <sys/mman.h>
#include <sys/wait.h>
#include <sys/prctl.h>
#include <sys/time.h>
#include <sys/resource.h>
#include <signal.h>
#include <unistd.h>
#include <cstdio>
#include <cstring>
#include <cerrno>
#include <stdexcept>
#include <vector>
#include <fstream>
#include <sys/syscall.h>
#include <sstream>
#include <time.h>
#include <algorithm>
#include <fcntl.h>
#include <cstdlib>
namespace eka2l1::arm {
namespace {
constexpr uintptr_t stub=native_trampoline_address;
constexpr long set_syscall=23,ptrace_get_vfp=27,ptrace_set_vfp=28;
constexpr uint32_t nr_mmap2=192,nr_munmap=91,nr_cacheflush=0xf0002;
void require(bool ok,const char *what){if(!ok)throw std::runtime_error(what);}
void trace(long request,pid_t pid,void *data=nullptr){if(ptrace(static_cast<__ptrace_request>(request),pid,nullptr,data)<0)throw std::runtime_error(std::string("native ptrace: ")+strerror(errno));}
int wait_stop(pid_t pid){int status;pid_t r;do{r=waitpid(pid,&status,0);}while(r<0&&errno==EINTR);require(r==pid&&WIFSTOPPED(status),"native worker exited");return WSTOPSIG(status);}
// ARM ptrace temporarily substitutes r12 with an entry/exit marker. Reach a
// plain breakpoint before reading or restoring the real register context.
void leave_syscall_stop(pid_t pid){unsigned long r[18];trace(PTRACE_GETREGS,pid,r);r[15]=stub+4;r[16]=0x10;trace(PTRACE_SETREGS,pid,r);
 for(;;){trace(PTRACE_CONT,pid);int sig=wait_stop(pid);if(sig==SIGVTALRM)continue;if(sig!=SIGILL)throw std::runtime_error("native syscall return signal "+std::to_string(sig));unsigned long stopped[18];trace(PTRACE_GETREGS,pid,stopped);require(stopped[15]==stub+4,"native return trap PC");break;}}
uint64_t cpu_time(clockid_t clock){timespec t{};require(clock_gettime(clock,&t)==0,"native CPU clock");return uint64_t(t.tv_sec)*1000000000+t.tv_nsec;}
struct vfp_state{uint32_t words[64];uint32_t fpscr;};
}
struct direct_core::worker {
 pid_t pid=-1;uint32_t localdata=0;clockid_t clock;
 std::map<uint32_t,std::pair<uint64_t,int>> pages;
 ~worker(){if(pid>0){kill(pid,SIGKILL);while(waitpid(pid,nullptr,0)<0&&errno==EINTR){}}}
};
direct_core::direct_core(native_arena *arena):arena_(arena){require(arena_!=nullptr,"native arena missing");
 reserve_native_trampoline();void *p=native_trampoline_mapping();
 require(!mprotect(p,4096,PROT_READ|PROT_WRITE),"native trampoline activation");uint32_t instructions[]={0xef000000,0xe7f000f0};memcpy(p,instructions,sizeof instructions);
 // Native getters preserve flags and every register other than the return r0.
 uint32_t heap[]={0xe59f0fb4,0xe5900000,0xe12fff1e};
 uint32_t trap[]={0xe59f0fa4,0xe5900008,0xe12fff1e};
 memcpy((char*)p+0x40,heap,sizeof heap);memcpy((char*)p+0x50,trap,sizeof trap);
 __builtin___clear_cache((char*)p,(char*)p+4096);require(!mprotect(p,4096,PROT_READ|PROT_EXEC),"native trampoline RX");
 context_.cpsr=0x10;publish_workers();
}
direct_core::~direct_core(){std::printf("native_backend_totals guest_syscalls=%llu mappings=%llu host_mapping_calls=%llu worker_creations=%llu\n",(unsigned long long)syscalls_,(unsigned long long)mappings_,(unsigned long long)remote_calls_,(unsigned long long)worker_creations_);workers_.clear();
 if(const char *prefix=std::getenv("N810_SYMBIAN_WORKER_PREFIX")){std::string path=std::string(prefix)+"-"+std::to_string(getpid());unlink(path.c_str());}
 release_native_trampoline();}
void direct_core::publish_workers(){
 const char *prefix=std::getenv("N810_SYMBIAN_WORKER_PREFIX");if(!prefix)return;
 const std::string path=std::string(prefix)+"-"+std::to_string(getpid()),temporary=path+".next";
 int fd=open(temporary.c_str(),O_WRONLY|O_CREAT|O_TRUNC|O_CLOEXEC,0600);require(fd>=0,"native worker manifest open");
 bool ok=true;for(auto&[id,w]:workers_){(void)id;if(dprintf(fd,"%d\n",w->pid)<0)ok=false;}
 if(close(fd))ok=false;
 require(ok&&rename(temporary.c_str(),path.c_str())==0,"native worker manifest publish");
}
uint32_t direct_core::remote(worker&w,uint32_t number,const std::array<uint32_t,6>&args){
 ++remote_calls_;unsigned long saved[18],r[18];trace(PTRACE_GETREGS,w.pid,saved);memcpy(r,saved,sizeof r);
 for(unsigned i=0;i<6;++i){r[i]=args[i];}r[7]=number;r[15]=stub;r[16]=0x10;trace(PTRACE_SETREGS,w.pid,r);
 // Only this host-controlled injection may execute a Linux syscall.
 for(int phase=0;phase<2;){trace(PTRACE_SYSCALL,w.pid);int sig=wait_stop(w.pid);if(sig==SIGVTALRM)continue;require(sig==(SIGTRAP|0x80),"native injected syscall signal");
  if(!phase){trace(PTRACE_GETREGS,w.pid,r);require(r[15]==stub+4&&r[7]==number,"native injected syscall origin");}++phase;}
 trace(PTRACE_GETREGS,w.pid,r);uint32_t result=r[0];leave_syscall_stop(w.pid);trace(PTRACE_SETREGS,w.pid,saved);return result;
}
direct_core::worker &direct_core::current(){
 auto it=workers_.find(asid_);if(it!=workers_.end())return *it->second;
 auto w=std::make_unique<worker>();
 // The N810 ARM kernel reserves the upper 16 MiB below PAGE_OFFSET.
 // Clear whole guest/user intervals in the child, avoiding a race with host
 // threads creating mappings between an inventory and fork.
 constexpr uint32_t task_end=0xbf000000;
 w->pid=fork();require(w->pid>=0,"native fork");if(w->pid==0){
  unsigned arena_fd=(unsigned)native_arena_fd(arena_);
  if((arena_fd>3 && syscall(SYS_close_range,3u,arena_fd-1,0u)) || syscall(SYS_close_range,arena_fd+1,~0u,0u))_exit(123);
  rlimit limit{300,300};setrlimit(RLIMIT_CPU,&limit);limit={0,0};setrlimit(RLIMIT_CORE,&limit);
  if(prctl(PR_SET_NO_NEW_PRIVS,1,0,0,0)||ptrace(PTRACE_TRACEME,0,nullptr,nullptr))_exit(120);
  itimerval timer{{0,2000},{0,2000}};if(setitimer(ITIMER_VIRTUAL,&timer,nullptr))_exit(121);raise(SIGSTOP);_exit(122);
 }
 require(wait_stop(w->pid)==SIGSTOP,"native initial stop");trace(PTRACE_SETOPTIONS,w->pid,(void*)(uintptr_t)(PTRACE_O_TRACESYSGOOD|PTRACE_O_EXITKILL));
 require(remote(*w,nr_munmap,{0x10000,stub-0x10000,0,0,0,0})==0,"native clear child lower range");
 require(remote(*w,nr_munmap,{stub+4096,task_end-stub-4096,0,0,0,0})==0,"native clear child upper range");
 require(clock_getcpuclockid(w->pid,&w->clock)==0,"native worker CPU clock");++worker_creations_;auto &out=*w;workers_[asid_]=std::move(w);publish_workers();return out;
}
void direct_core::set_native_address_space(uint32_t id,uint64_t generation){
 require(runner_==std::thread::id{}||runner_==std::this_thread::get_id(),"native address-space owner thread changed");
 auto old=generations_.find(id);if(workers_.count(id)&&(old==generations_.end()||old->second!=generation)){workers_.erase(id);publish_workers();}
 generations_[id]=generation;asid_=id;
}
void direct_core::capture(worker&w){unsigned long r[18];trace(PTRACE_GETREGS,w.pid,r);for(unsigned i=0;i<16;++i)context_.cpu_registers[i]=r[i];context_.cpsr=r[16];vfp_state f{};trace(ptrace_get_vfp,w.pid,&f);memcpy(context_.fpu_registers.data(),f.words,sizeof f.words);context_.fpscr=f.fpscr;}
void direct_core::set_schedule_frequency(uint32_t hz){require(hz>0&&hz<=1000000000,"native scheduler frequency");schedule_hz_=hz;}
void direct_core::enable_fast_localdata(uint32_t bias){require(bias>0&&bias<4096,"native TLS layout bias");localdata_bias_=bias;}
void direct_core::install(worker&w){
 if(localdata_bias_){require(context_.uprw>=localdata_bias_,"native TLS pointer missing");uint32_t local=context_.uprw-localdata_bias_;
  if(local!=w.localdata){require(ptrace(PTRACE_POKEDATA,w.pid,(void*)(stub+4092),(void*)(uintptr_t)local)==0,"native TLS slot update");w.localdata=local;}}

 unsigned long r[18]{};for(unsigned i=0;i<16;++i)r[i]=context_.cpu_registers[i];r[16]=(context_.cpsr&0xf80f0020)|0x10;trace(PTRACE_SETREGS,w.pid,r);
 vfp_state f{};memcpy(f.words,context_.fpu_registers.data(),sizeof f.words);f.fpscr=context_.fpscr;trace(ptrace_set_vfp,w.pid,&f);
}
void direct_core::set_tlb_page(address va,uint8_t*host,prot permission){
 if(!demand_ || std::this_thread::get_id()!=runner_)return;
 va&=~4095u;uint64_t offset;require(native_arena_resolve(arena_,host,4096,&offset)==0&&!(offset&4095),"native page not shared-backed");
 if(!(va>=0x10000&&va<stub)){char message[128];std::snprintf(message,sizeof message,"native guest address outside user range va=%08x pc=%08x",va,context_.cpu_registers[15]);throw std::runtime_error(message);}auto&w=current();int flags=int(permission)&7;
 auto found=w.pages.find(va);if(found!=w.pages.end()&&found->second==std::make_pair(offset,flags))return;
 if(found!=w.pages.end()){require(remote(w,nr_munmap,{va,4096,0,0,0,0})==0,"native unmap old page");w.pages.erase(found);}
 uint32_t result=remote(w,nr_mmap2,{va,4096,(uint32_t)flags,MAP_SHARED|MAP_FIXED_NOREPLACE|MAP_POPULATE,(uint32_t)native_arena_fd(arena_),(uint32_t)(offset>>12)});
 require(result==va,"native mmap page failed");w.pages[va]={offset,flags};++mappings_;
 if(flags&PROT_EXEC){__builtin___clear_cache((char*)host,(char*)host+4096);uint32_t flushed=remote(w,nr_cacheflush,{va,va+4096,0,0,0,0});if(flushed!=0)throw std::runtime_error("native code cache flush result="+std::to_string((int32_t)flushed));}
}
void direct_core::dirty_tlb_page(address va){std::lock_guard<std::mutex> lock(invalidation_lock_);revoke_.insert(va&~4095u);}
void direct_core::flush_tlb(){std::lock_guard<std::mutex> lock(invalidation_lock_);revoke_all_=true;}
void direct_core::clear_instruction_cache(){std::lock_guard<std::mutex> lock(invalidation_lock_);flush_code_=true;}
void direct_core::imb_range(address va,size_t size){require(size<=UINT32_MAX-va,"native instruction range overflow");clear_instruction_cache();}
void direct_core::service_invalidations(){
 std::set<address> revoke;bool all,code;{std::lock_guard<std::mutex> lock(invalidation_lock_);revoke.swap(revoke_);all=revoke_all_;code=flush_code_;revoke_all_=flush_code_=false;}
 // The snapshot is empty in normal dispatch. Do not walk every guest page.
 // Invalidations queued after the snapshot remain pending for the next run.
 if(!all&&!code&&revoke.empty())return;
 for(auto&[id,w]:workers_){(void)id;
  for(auto it=w->pages.begin();it!=w->pages.end();){uint32_t va=it->first;
   if(all||revoke.count(va)){require(remote(*w,nr_munmap,{va,4096,0,0,0,0})==0,"native revoke mapping");it=w->pages.erase(it);}
   else {if(code&&(it->second.second&PROT_EXEC))require(remote(*w,nr_cacheflush,{va,va+4096,0,0,0,0})==0,"native invalidate code");++it;}
  }
 }
}
void direct_core::step(){throw std::runtime_error("native single step not implemented; no interpreter fallback");}
void direct_core::run(uint32_t budget){
 ticks_=0;stopped_=false;const uint64_t parent_start=cpu_time(CLOCK_THREAD_CPUTIME_ID);
 require(runner_==std::thread::id{}||runner_==std::this_thread::get_id(),"native CPU runner thread changed");runner_=std::this_thread::get_id();
 service_invalidations();auto&w=current();const uint64_t child_start=cpu_time(w.clock);
 // Charge actual host service and native-worker CPU time to the guest quantum.
 // One SVC is not one instruction: treating it that way starves ready peers.
 auto account=[&]{uint64_t elapsed=cpu_time(CLOCK_THREAD_CPUTIME_ID)-parent_start+cpu_time(w.clock)-child_start;
  const uint64_t quantum_ns=(uint64_t(budget)*1000000000+schedule_hz_-1)/schedule_hz_;
  ticks_=elapsed>=quantum_ns?budget:(uint32_t)std::max<uint64_t>(1,elapsed*schedule_hz_/1000000000);};
 install(w);
 for(unsigned faults=0;faults<4096&&!stopped_;++faults){trace(PTRACE_SYSCALL,w.pid);int sig=wait_stop(w.pid);capture(w);
  if(sig==SIGVTALRM){account();return;}
  if(sig==(SIGTRAP|0x80)){
   // Save arguments, suppress the Linux syscall, and reach its exit stop.
   ++syscalls_;auto call=context_;trace(set_syscall,w.pid,(void*)-1L);
   for(;;){trace(PTRACE_SYSCALL,w.pid);int s=wait_stop(w.pid);if(s==SIGVTALRM)continue;require(s==(SIGTRAP|0x80),"native syscall exit");break;}
   leave_syscall_stop(w.pid);unsigned long restored[18];trace(PTRACE_GETREGS,w.pid,restored);
   context_=call;context_.cpu_registers[12]=restored[12];uint32_t ordinal=0;uint32_t pc=context_.cpu_registers[15];
   if(is_thumb_mode()){uint16_t op;require(read_16bit(pc-2,&op)&&(op&0xff00)==0xdf00,"native Thumb SVC decode");ordinal=op&255;}
   else {uint32_t op;require(read_code(pc-4,&op)&&(op&0x0f000000)==0x0f000000,"native ARM SVC decode");ordinal=op&0xffffff;}
   require(bool(system_call_handler),"native syscall handler missing");system_call_handler(ordinal);account();return;
  }
  if(sig==SIGILL && !is_thumb_mode()){
   // ARM1136 lacks this user thread-ID register. Trap only these exact OS
   // register accesses; arithmetic, loads, branches and VFP execute natively.
   uint32_t op;require(read_code(get_pc(),&op),"native undefined instruction fetch");uint32_t form=op&0x0fff0fff;unsigned rd=(op>>12)&15;
   if(rd<15 && (form==0x0e1d0f50 || form==0x0e0d0f50)){
    if(form==0x0e1d0f50)set_reg(rd,context_.uprw);else context_.uprw=get_reg(rd);
    set_pc(get_pc()+4);install(w);account();if(ticks_>=budget)return;continue;
   }
  }
  if(sig==SIGSEGV || sig==SIGBUS){siginfo_t info{};trace(PTRACE_GETSIGINFO,w.pid,&info);uint32_t va=(uintptr_t)info.si_addr;
   auto before=w.pages.find(va&~4095u);require(before==w.pages.end(),"native permission or repeated memory fault");uint8_t ignored;
   demand_=true;bool mapped=read_8bit&&read_8bit(va,&ignored);demand_=false;require(mapped,"native unmapped guest address");require(w.pages.count(va&~4095u)!=0,"native read did not map backing");install(w);account();if(ticks_>=budget)return;continue;
  }
  throw std::runtime_error("native guest signal "+std::to_string(sig)+" at "+std::to_string(get_pc()));
 }
 require(stopped_,"native mapping fault budget exhausted");account();
}
}
