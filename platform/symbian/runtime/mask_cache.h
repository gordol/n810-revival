/* SPDX-License-Identifier: MIT. Policy only: no GL calls or implicit sync. */
#pragma once
#include <array>
#include <algorithm>
#include <cstdint>
#include <limits>
#include <vector>
namespace mbx_mask {
struct source {
 uint64_t lifetime=0,generation=0;
 uint32_t name=0,width=0,height=0;
 std::array<int32_t,4> sampler{}; // min, mag, wrap S, wrap T
 std::array<int32_t,4> swizzle{};
 bool tracked=false,ever_render_target=false;
 bool operator==(const source& b)const{return lifetime==b.lifetime&&generation==b.generation&&name==b.name&&width==b.width&&height==b.height&&sampler==b.sampler&&swizzle==b.swizzle&&tracked==b.tracked&&ever_render_target==b.ever_render_target;}
};
struct key {
 uint64_t context=0;source image,mask;uint32_t flags=0;
 uint32_t x=0,y=0,width=0,height=0; // optional canonical source tile
 bool operator==(const key& b)const{return context==b.context&&image==b.image&&mask==b.mask&&flags==b.flags&&x==b.x&&y==b.y&&width==b.width&&height==b.height;}
};
/* Result lifetime is cache-owned only when insert succeeds. Hit handles are
 * borrowed until the next cache mutation; caller must issue its draw first.
 * Release callbacks must run with the owning GL context current, must not
 * throw, and must not reenter this cache. At most 256 metadata entries.
 * Construct keys from fresh authoritative metadata on every lookup. Lifetime
 * IDs must not be recycled; mutation generation must not wrap. Invalidate
 * before upload/subimage/copy/blit, before framebuffer attachment, before
 * destruction, and whenever tracked state becomes unknown. No API can detect
 * a stale caller-supplied key. A miss MUST retain existing synchronization.
 * Only insert after GPU completion and successful resident result creation. On false,
 * retain temporary ownership and delete after draw using the old path.
 * Allocation charge is supplied by the runtime; use verified allocation size
 * or a conservative upper bound, never width*height alone if layout is padded.
 * Close explicitly before GL context teardown. No work runs in destructor. */
class cache {
 struct entry {key k;uint32_t result;uint64_t bytes;};
 std::vector<entry> entries_;uint64_t context_,budget_,used_=0;size_t limit_;
 static bool eligible(const source& s){return s.tracked&&!s.ever_render_target&&s.lifetime&&s.generation&&s.name&&s.width&&s.height&&s.width<=1024&&s.height<=1024;}
 public:
 cache(uint64_t context,uint64_t bytes,size_t entries):context_(context),budget_(bytes),limit_(std::min<size_t>(entries,256)){entries_.reserve(limit_);}
 cache(const cache&)=delete;cache& operator=(const cache&)=delete;
 bool accepts(const key& k)const{return context_&&k.context==context_&&eligible(k.image)&&eligible(k.mask)&&k.image.width==k.mask.width&&k.image.height==k.mask.height&&(k.flags&~12U)==0&&
  ((!k.width&&!k.height&&!k.x&&!k.y)||(k.width&&k.height&&k.width<=128&&k.height<=128&&k.x<k.image.width&&k.y<k.image.height&&k.width<=k.image.width-k.x&&k.height<=k.image.height-k.y));}
 bool references(uint64_t lifetime)const{for(const auto& e:entries_)if(e.k.image.lifetime==lifetime||e.k.mask.lifetime==lifetime)return true;return false;}
 uint64_t bytes()const{return used_;}size_t size()const{return entries_.size();}
 uint32_t find(const key& k){if(!accepts(k))return 0;for(size_t i=0;i<entries_.size();++i)if(entries_[i].k==k){auto e=entries_[i];entries_.erase(entries_.begin()+i);entries_.push_back(e);return e.result;}return 0;}
 /* charge is actual retained allocation accounting, including padding/mips.
  * Unknown allocation size must bypass caching. Never charge less than RGBA8.
  * False leaves ownership with caller and does not evict anything. */
 template<class Release> bool insert(const key& k,uint32_t result,uint64_t charge,Release release){
  if(!accepts(k)||!result||result==k.image.name||result==k.mask.name||!limit_||charge< uint64_t(k.width?k.width:k.image.width)*(k.height?k.height:k.image.height)*4||charge>budget_)return false;
  for(const auto& e:entries_)if(e.result==result||e.k==k)return false;
  while(entries_.size()>=limit_||charge>budget_-used_){auto e=entries_.front();entries_.erase(entries_.begin());used_-=e.bytes;release(e.result);}
  entries_.push_back({k,result,charge});used_+=charge;return true;
 }
 /* Call before any mutation or destruction of this lifetime, and before it
  * first becomes a render target. Generation changes also make find miss. */
 template<class Release> void invalidate(uint64_t lifetime,Release release){
  for(size_t i=0;i<entries_.size();)if(entries_[i].k.image.lifetime==lifetime||entries_[i].k.mask.lifetime==lifetime){auto e=entries_[i];entries_.erase(entries_.begin()+i);used_-=e.bytes;release(e.result);}else ++i;
 }
 template<class Release> bool evict_oldest(Release release){if(entries_.empty())return false;auto e=entries_.front();entries_.erase(entries_.begin());used_-=e.bytes;release(e.result);return true;}
 template<class Release> void clear(Release release){for(const auto& e:entries_)release(e.result);entries_.clear();used_=0;}
 /* Teardown is explicit: GL deletes cannot safely run from a C++ destructor
  * after context destruction. This closes the policy permanently. */
 template<class Release> void close(Release release){clear(release);context_=0;}
};
}
