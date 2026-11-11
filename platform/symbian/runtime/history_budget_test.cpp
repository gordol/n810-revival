// SPDX-License-Identifier: MIT
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <memory>
#include <vector>
#include <cstdio>
namespace common {static uint64_t now=5000000;uint64_t get_current_utc_time_in_microseconds_since_epoch(){return now;}}
enum kind{gdi_store_command_segment_non_redraw,gdi_store_command_segment_redraw};
struct gdi_store_command_segment{kind type_=gdi_store_command_segment_non_redraw;uint64_t creation_date_=0;std::vector<unsigned> commands_;};
struct gdi_store_command_collection{
 using segment_flattener=std::function<std::unique_ptr<gdi_store_command_segment>(const std::unique_ptr<gdi_store_command_segment>*,size_t)>;
 static constexpr int KEEP_NON_REDRAW_SEGMENTS=12,LIMIT_NON_REDRAW_SEGMENTS=20;static constexpr uint64_t AGE_LIMIT_NONREDRAW_US=1000000;
 std::vector<std::unique_ptr<gdi_store_command_segment>> segments_;gdi_store_command_segment *current_segment_=nullptr;
 bool clean_old_nonredraw_segments(const segment_flattener &flatten={});
};
#include "history_cleanup.inc"
int main(){unsigned cases=0;
 for(unsigned enabled=0;enabled<2;enabled++)for(unsigned n=1;n<=28;n++)for(unsigned commands=0;commands<=100;commands++){
  setenv("N810_SYMBIAN_BOUNDED_HISTORY",enabled?"1":"0",1);gdi_store_command_collection c;
  for(unsigned i=0;i<n;i++){auto s=std::make_unique<gdi_store_command_segment>();s->commands_.resize(i?0:commands);for(unsigned j=0;j<s->commands_.size();j++)s->commands_[j]=j;c.current_segment_=s.get();c.segments_.push_back(std::move(s));}
  unsigned calls=0;c.clean_old_nonredraw_segments([&](const auto *segments,size_t count){++calls;auto merged=std::make_unique<gdi_store_command_segment>();merged->type_=gdi_store_command_segment_redraw;for(size_t i=0;i<count;i++)merged->commands_.insert(merged->commands_.end(),segments[i]->commands_.begin(),segments[i]->commands_.end());return merged;});
  bool expected=n>20||(!(enabled&&commands<=64)&&n>1);assert(bool(calls)==expected);
  std::vector<unsigned> all;for(auto &s:c.segments_)all.insert(all.end(),s->commands_.begin(),s->commands_.end());assert(all.size()==commands);for(unsigned j=0;j<commands;j++)assert(all[j]==j);++cases;
 }
 puts("5656 history cases: bounded small replay, large/count-limit compaction, exact command order preserved");assert(cases==5656);
}
