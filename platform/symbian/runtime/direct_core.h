#pragma once
#include <cpu/arm_interface.h>
#include <atomic>
#include <map>
#include <memory>
#include <thread>
#include <mutex>
#include <set>
extern "C" {
#include "native_memory.h"
}
namespace eka2l1::arm {
// Experimental native process backend. No instruction translation is performed.
// Memory must come from the supplied shared arena; unsupported backing fails.
class direct_core final : public core {
 struct worker;
 native_arena *arena_;
 std::map<uint32_t,std::unique_ptr<worker>> workers_;
 std::map<uint32_t,uint64_t> generations_;
 uint64_t mappings_=0,syscalls_=0,remote_calls_=0,worker_creations_=0;
 uint32_t asid_=0,ticks_=0,localdata_bias_=0,schedule_hz_=400000000;
 thread_context context_{};
 std::atomic<bool> stopped_{false};
 std::thread::id runner_;
 bool demand_=false, revoke_all_=false, flush_code_=false;
 std::mutex invalidation_lock_;
 std::set<address> revoke_;
 void service_invalidations();
 void publish_workers();
 worker &current();
 void capture(worker &w);
 void install(worker &w);
 uint32_t remote(worker &w,uint32_t number,const std::array<uint32_t,6>&args);
public:
 explicit direct_core(native_arena *arena);
 ~direct_core() override;
 void enable_fast_localdata(uint32_t bias);
 void set_native_address_space(uint32_t id,uint64_t generation);
 void set_schedule_frequency(uint32_t hz);
 void run(uint32_t budget) override;
 void stop() override {stopped_=true;}
 void step() override;
 uint32_t get_reg(size_t i) override {return context_.cpu_registers.at(i);}
 void set_reg(size_t i,uint32_t v) override {context_.cpu_registers.at(i)=v;}
 uint32_t get_sp() override{return get_reg(13);}
 uint32_t get_pc() override{return get_reg(15);}
 uint32_t get_lr() override{return get_reg(14);}
 void set_sp(uint32_t v) override{set_reg(13,v);}
 void set_pc(uint32_t v) override{set_reg(15,v);}
 void set_lr(uint32_t v) override{set_reg(14,v);}
 uint32_t get_cpsr() override{return context_.cpsr;}
 void set_cpsr(uint32_t v) override{context_.cpsr=v;}
 uint32_t get_fpscr() override{return context_.fpscr;}
 void set_fpscr(uint32_t v) override{context_.fpscr=v;}
 uint32_t get_vfp(size_t i) override{return context_.fpu_registers.at(i);}
 void set_vfp(size_t i,uint32_t v) override{context_.fpu_registers.at(i)=v;}
 void save_context(thread_context &c) override{c=context_;}
 void load_context(const thread_context &c) override{context_=c;}
 bool is_thumb_mode() override{return context_.cpsr&0x20;}
 void set_asid(uint32_t id) override{asid_=id;}
 void set_tlb_page(address address,uint8_t *host,prot permission) override;
 void dirty_tlb_page(address address) override;
 void flush_tlb() override;
 void clear_instruction_cache() override;
 void imb_range(address address,size_t size) override;
 bool should_clear_old_memory_map() const override{return false;}
 // Scheduler quantum accounting, NOT a measured native instruction count.
 uint32_t get_num_instruction_executed() override{return ticks_;}
};
}
