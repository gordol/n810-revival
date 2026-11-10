// N810 ARMv6 regression: multi-register transfers across unmapped/cached pages.
#include <cpu/12l1r/arm_12l1r.h>
#include <cpu/12l1r/exclusive_monitor.h>
#include <common/log.h>
#include "fault_capture.h"
#include <array>
#include <sys/mman.h>
#include <common/armemitter.h>
#include <common/cpudetect.h>
#include <cstring>
#include <cstdio>
int main() {
 n810_fault::install();std::setvbuf(stdout,nullptr,_IOLBF,0);eka2l1::log::setup_log(nullptr);
 {
  using namespace eka2l1::common::armgen;
  auto *memory=static_cast<unsigned char *>(mmap(nullptr,65536,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0));
  if(memory==MAP_FAILED)return 2;
  eka2l1::common::cpu_info info;info.detect();if(info.bARMv7)return 3;
  armx_emitter emitter(memory,info);std::array<unsigned,1004> output{},expected{};
  for(unsigned i=0;i<1000;++i) {
   expected[i]=0x12345678u ^ (i*0x9e3779b9u);
   emitter.MOVI2R(eka2l1::common::armgen::R1,expected[i]);emitter.STR(eka2l1::common::armgen::R1,eka2l1::common::armgen::R0,i*4);
  }
  emitter.MOV(eka2l1::common::armgen::R2,7);emitter.CMP(eka2l1::common::armgen::R2,7);
  emitter.set_cc(eka2l1::common::CC_NEQ);emitter.MOVI2R(eka2l1::common::armgen::R2,0xdeadbeef);
  emitter.set_cc(eka2l1::common::CC_AL);emitter.STR(eka2l1::common::armgen::R2,eka2l1::common::armgen::R0,4000);emitter.MRS(eka2l1::common::armgen::R3);emitter.STR(eka2l1::common::armgen::R3,eka2l1::common::armgen::R0,4004);
  emitter.set_cc(eka2l1::common::CC_EQ);emitter.MOVI2R(eka2l1::common::armgen::R2,0xcafebabe);
  emitter.set_cc(eka2l1::common::CC_AL);emitter.STR(eka2l1::common::armgen::R2,eka2l1::common::armgen::R0,4008);emitter.MRS(eka2l1::common::armgen::R3);emitter.STR(eka2l1::common::armgen::R3,eka2l1::common::armgen::R0,4012);
  emitter.B(eka2l1::common::armgen::R14);emitter.flush_lit_pool();emitter.flush_icache();
  if(mprotect(memory,65536,PROT_READ|PROT_EXEC))return 4;
  reinterpret_cast<void(*)(unsigned*)>(memory)(output.data());
  bool good=std::memcmp(output.data(),expected.data(),4000)==0 && output[1000]==7 && output[1002]==0xcafebabe && (output[1001]&0xf0000000)==0x60000000 && (output[1003]&0xf0000000)==0x60000000;
  std::printf("armv6_literal_stress constants=1000 conditional_cases=2 flags_preserved=%d pass=%d\n",(output[1001]&0xf0000000)==(output[1003]&0xf0000000),good);
  munmap(memory,65536);if(!good)return 5;
 }
 for (int mode=0;mode<3;++mode) {
  eka2l1::arm::r12l1::exclusive_monitor monitor(1);
  eka2l1::arm::r12l1_core cpu(&monitor,12);n810_fault::cpu=&cpu;
  std::array<unsigned char,0x5000> memory{};
  constexpr unsigned source=0x1ff8,target=0x3ff8,bytes=48;
  for(unsigned i=0;i<bytes;++i) memory[source+i]=static_cast<unsigned char>(i*17+3);
  const unsigned code[]={0xe8b45fcf,0xe8a55fcf,0xef012345};
  cpu.read_code=[&](unsigned a,unsigned *v){if(a<0x10000 || a+4>0x10000+sizeof(code))return false;std::memcpy(v,reinterpret_cast<const unsigned char*>(code)+a-0x10000,4);return true;};
  unsigned reads=0,writes=0;
  cpu.read_32bit=[&](unsigned a,unsigned *v){if(a+4>memory.size())return false;std::memcpy(v,memory.data()+a,4);++reads;if(mode==1)cpu.set_tlb_page(a,memory.data()+a,prot_read_write);return true;};
  cpu.write_32bit=[&](unsigned a,unsigned *v){if(a+4>memory.size())return false;std::memcpy(memory.data()+a,v,4);++writes;if(mode==1)cpu.set_tlb_page(a,memory.data()+a,prot_read_write);return true;};
  if(mode==2)for(unsigned a=0x1000;a<0x5000;a+=0x1000)cpu.set_tlb_page(a,memory.data()+a,prot_read_write);
  bool stopped=false;cpu.system_call_handler=[&](unsigned svc){if(svc!=0x12345)std::abort();stopped=true;cpu.stop();};
  cpu.exception_handler=[](auto, unsigned){std::abort();return false;};
  for(unsigned i=0;i<16;++i)cpu.set_reg(i,0);
  cpu.set_cpsr(0x10);cpu.set_fpscr(0);cpu.set_pc(0x10000);cpu.set_reg(4,source);cpu.set_reg(5,target);
  std::printf("memory_chain_start mode=%d\n",mode);cpu.run(1000);
  bool good=stopped && cpu.get_reg(4)==source+bytes && cpu.get_reg(5)==target+bytes && !std::memcmp(memory.data()+source,memory.data()+target,bytes);
  std::printf("memory_chain_result mode=%d pass=%d reads=%u writes=%u\n",mode,good,reads,writes);
  if(!good)return 1;
 }
 {
  eka2l1::arm::r12l1::exclusive_monitor monitor(1);eka2l1::arm::r12l1_core cpu(&monitor,12);n810_fault::cpu=&cpu;
  unsigned code[]={0xe3a00001,0xef012345};unsigned code_reads=0;
  cpu.read_code=[&](unsigned a,unsigned *v){if(a<0x10000 || a+4>0x10008)return false;*v=code[(a-0x10000)/4];++code_reads;return true;};
  cpu.system_call_handler=[&](unsigned svc){if(svc!=0x12345)std::abort();cpu.stop();};
  cpu.exception_handler=[](auto,unsigned){std::abort();return false;};
  for(unsigned i=0;i<16;++i)cpu.set_reg(i,0);cpu.set_cpsr(0x10);cpu.set_fpscr(0);
  unsigned round=0;
  for(unsigned asid : {1u,2u,1u,3u,4u,5u,6u,1u,7u,8u,2u,1u}) {
   code[0]=0xe3a00000|asid;code_reads=0;cpu.set_asid(asid);cpu.set_pc(0x10000);cpu.run(100);
   const bool expected_hit=round==2 || round==7 || round==11;
   bool good=cpu.get_reg(0)==asid && ((code_reads==0)==expected_hit);
   std::printf("address_space_switch asid=%u result=%u code_reads=%u pass=%d\n",asid,cpu.get_reg(0),code_reads,good);
   if(!good)return 6;++round;
  }
  cpu.imb_range(0x10000,8);
  for(unsigned asid : {2u,1u}) {
   code[0]=0xe3a00000|(asid+10);cpu.set_asid(asid);cpu.set_pc(0x10000);cpu.run(100);
   bool good=cpu.get_reg(0)==asid+10;std::printf("inactive_cache_invalidate asid=%u pass=%d\n",asid,good);if(!good)return 8;
  }
 }
 {
  eka2l1::arm::r12l1::exclusive_monitor monitor(1);eka2l1::arm::r12l1_core cpu(&monitor,12);n810_fault::cpu=&cpu;
  unsigned code[]={0xea000000,0xef012345,0xe3a00001,0xef012345};
  cpu.read_code=[&](unsigned a,unsigned *v){if(a<0x10000 || a+4>0x10010)return false;*v=code[(a-0x10000)/4];return true;};
  cpu.system_call_handler=[&](unsigned svc){if(svc!=0x12345)std::abort();cpu.stop();};
  cpu.exception_handler=[](auto,unsigned){std::abort();return false;};
  for(unsigned i=0;i<16;++i)cpu.set_reg(i,0);cpu.set_cpsr(0x10);cpu.set_fpscr(0);
  cpu.set_pc(0x10008);cpu.run(100); // Compile destination before source link.
  cpu.set_pc(0x10000);cpu.run(100);
  for(unsigned value=2;value<10;++value) {
   code[2]=0xe3a00000|value;cpu.imb_range(0x10008,8);cpu.set_pc(0x10000);cpu.run(100);
   bool good=cpu.get_reg(0)==value;std::printf("linked_block_recompile expected=%u result=%u pass=%d\n",value,cpu.get_reg(0),good);
   if(!good)return 7;
  }
 }
 n810_fault::cpu=nullptr;return 0;
}
