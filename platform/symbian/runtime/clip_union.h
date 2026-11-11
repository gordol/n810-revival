/* SPDX-License-Identifier: MIT */
#pragma once
#include <vector>
#include <algorithm>
#include <stdexcept>
namespace sg {
struct box { int x0,y0,x1,y1; };
inline bool valid(box a){return a.x0<a.x1&&a.y0<a.y1;}
inline box intersection(box a,box b){return {std::max(a.x0,b.x0),std::max(a.y0,b.y0),std::min(a.x1,b.x1),std::min(a.y1,b.y1)};}
/* Exact half-open rectangle union, no pixel processing. Disjoint output avoids
 * applying blend twice in overlap. Bound fragmentation before publication. */
inline std::vector<box> disjoint_union(const std::vector<box>& input){
 if(input.size()>512)throw std::runtime_error("clip input capacity");
 std::vector<box> out;
 for(auto a:input){
  if(!valid(a))continue;
  std::vector<box> pending{a};
  for(auto b:out){
   std::vector<box> next;
   for(auto p:pending){auto i=intersection(p,b);
    if(!valid(i)){next.push_back(p);continue;}
    for(auto q:{box{p.x0,p.y0,p.x1,i.y0},box{p.x0,i.y1,p.x1,p.y1},box{p.x0,i.y0,i.x0,i.y1},box{i.x1,i.y0,p.x1,i.y1}})
     if(valid(q))next.push_back(q);
   }
   if(next.size()>512)throw std::runtime_error("clip fragmentation capacity");
   pending.swap(next);
  }
  if(out.size()+pending.size()>512)throw std::runtime_error("clip union capacity");
  out.insert(out.end(),pending.begin(),pending.end());
 }
 return out;
}
}
