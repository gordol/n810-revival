/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include <cstddef>
#include <cstdint>
namespace eka2l1::drivers::n810_commands {
struct opcodes {unsigned feature,blend_feature,formula,brush,bitmap;};
// Producer-side only. These three state writes carry no owned allocations.
// Unknown commands and synchronous/callback commands are hard barriers.
// Only the fixed-function bitmap renderer's preserved states cross a draw.
template<class Command>
std::size_t coalesce(Command *commands, std::size_t count, opcodes op) {
 Command pending[3], current[3];bool waiting[3]{},known[3]{};
 std::size_t order[3]{},out=0;
 auto equal=[](const Command &a,const Command &b,unsigned k){
  const unsigned words=k==0?1:k==1?3:2;
  for(unsigned i=0;i<words;++i)if(a.data_[i]!=b.data_[i])return false;
  return true;
 };
 auto flush=[&](){
  for(unsigned pass=0;pass<3;++pass){
   int k=-1;for(unsigned i=0;i<3;++i)if(waiting[i]&&(k<0||order[i]<order[k]))k=i;
   if(k<0)break;
   if(!known[k]||!equal(current[k],pending[k],k))commands[out++]=pending[k];
   current[k]=pending[k];known[k]=true;waiting[k]=false;
  }
 };
 for(std::size_t i=0;i<count;++i){
  Command c=commands[i];int k=-1;
  if(!c.status_&&!c.readback_completion_&&!c.readback_userdata_){
   if(c.opcode_==op.feature&&uint32_t(c.data_[0])==op.blend_feature&&(c.data_[0]>>32)<=1)k=0;
   else if(c.opcode_==op.formula && c.data_[0]==0 &&
           uint32_t(c.data_[1])<=3 && (c.data_[1]>>32)<=3 &&
           uint32_t(c.data_[2])<=3 && (c.data_[2]>>32)<=3)k=1;
   else if(c.opcode_==op.brush && uint32_t(c.data_[0])<=255 &&
           (c.data_[0]>>32)<=255 && uint32_t(c.data_[1])<=255 && (c.data_[1]>>32)<=255)k=2;
  }
  if(k>=0){pending[k]=c;waiting[k]=true;order[k]=i;continue;}
  flush();commands[out++]=c;
  if(c.opcode_!=op.bitmap||c.status_||c.readback_completion_||c.readback_userdata_)
   for(auto &v:known)v=false;
 }
 flush();return out;
}
}
