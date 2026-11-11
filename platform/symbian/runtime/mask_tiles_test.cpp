// SPDX-License-Identifier: MIT
#include "mask_tiles.h"
#include "mask_cache.h"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <vector>
int main(){
 unsigned cases=0;
 for(auto size:{std::pair<unsigned,unsigned>{7,11},{128,128},{129,2},{240,320},{257,131},{1024,1024}})
 for(bool reverse:{false,true})for(bool crop:{false,true}){
  sg_sprite original{};original.model[0]=original.model[5]=1;original.color[0]=.37f;
  float a=crop?.17f:0,b=crop?.91f:1,c=crop?.09f:0,d=crop?.87f:1;
  if(reverse){std::swap(a,b);std::swap(c,d);}
  float uv[]={0,1,a,d,1,0,b,c,0,0,a,c,1,1,b,d};std::copy(uv,uv+16,original.xyuv);
  std::vector<sg::mask_tile> tiles;sg::mask_tiles(original,size.first,size.second,[&](const auto&t){tiles.push_back(t);});assert(!tiles.empty()&&tiles.size()<=64);
  for(auto&t:tiles){assert(!std::memcmp(t.sprite.model,original.model,sizeof original.model));assert(!std::memcmp(t.sprite.color,original.color,sizeof original.color));}
  for(auto&t:tiles)for(unsigned i=0;i<4;i++){
   assert(t.sprite.xyuv[4*i+2]>=0&&t.sprite.xyuv[4*i+2]<=float(t.width)/128);
   assert(t.sprite.xyuv[4*i+3]>=0&&t.sprite.xyuv[4*i+3]<=float(t.height)/128);
  }
  for(unsigned iy=0;iy<29;iy++)for(unsigned ix=0;ix<31;ix++){
   double x=(ix+.5)/31,y=(iy+.5)/29;unsigned hits=0;
   for(auto&t:tiles){const float*v=t.sprite.xyuv;double x0=v[8],x1=v[4],y0=v[9],y1=v[1];if(x<x0||x>=x1||y<y0||y>=y1)continue;
    ++hits;double u=v[10]+(v[6]-v[10])*(x-x0)/(x1-x0),w=v[11]+(v[3]-v[11])*(y-y0)/(y1-y0);
    assert(std::abs((t.x+u*128)/size.first-(a+(b-a)*x))<4e-7);
    assert(std::abs((t.y+w*128)/size.second-(c+(d-c)*y))<4e-7);
   }
   assert(hits==1);
  }++cases;
 }
 // Fractional source crops expose the float destination round-trip error.
 for(unsigned i=1;i<=20000;i++){
  unsigned w=129+(i*47)%896,h=129+(i*71)%896;
  float a=float((i*13)%997)/1000,b=float(998-(i*17)%997)/1000;
  float c=float((i*19)%991)/1000,d=float(994-(i*23)%991)/1000;
  if(a==b||c==d)continue;
  sg_sprite sprite{};float uv[]={0,1,a,d,1,0,b,c,0,0,a,c,1,1,b,d};std::copy(uv,uv+16,sprite.xyuv);
  sg::mask_tiles(sprite,w,h,[&](const auto&t){for(unsigned v=0;v<4;v++){
   assert(t.sprite.xyuv[v*4+2]>=0&&t.sprite.xyuv[v*4+2]<=float(t.width)/128);
   assert(t.sprite.xyuv[v*4+3]>=0&&t.sprite.xyuv[v*4+3]<=float(t.height)/128);
  }});
 }
 sg_sprite invalid{};unsigned emitted=0;try{sg::mask_tiles(invalid,2048,1,[&](auto){++emitted;});assert(false);}catch(const std::runtime_error&){}assert(!emitted);
 mbx_mask::source src;src.tracked=true;src.lifetime=1;src.generation=1;src.name=1;src.width=src.height=8;
 mbx_mask::key k;k.context=1;k.image=k.mask=src;mbx_mask::cache cache(1,4096,3);std::vector<unsigned> released;
 for(unsigned i=0;i<3;i++){k.image.generation=i+1;assert(cache.insert(k,100+i,1024,[&](unsigned n){released.push_back(n);}));}
 assert(cache.references(1));assert(cache.evict_oldest([&](unsigned n){released.push_back(n);}));assert(released[0]==100&&cache.size()==2);
 mbx_mask::key tile=k;tile.image.width=tile.image.height=tile.mask.width=tile.mask.height=1024;
 tile.x=tile.y=896;tile.width=tile.height=128;assert(cache.accepts(tile));
 tile.x=897;assert(!cache.accepts(tile));tile.x=896;tile.height=0;assert(!cache.accepts(tile));
 mbx_mask::cache atlas_cache(1,65536,1);tile.height=128;assert(atlas_cache.insert(tile,900,65536,[](unsigned){}));
 auto adjacent=tile;adjacent.x=768;assert(!atlas_cache.find(adjacent)&&atlas_cache.find(tile)==900);atlas_cache.close([](unsigned){});
 cache.close([&](unsigned n){released.push_back(n);});assert(cache.bytes()==0&&released.size()==3);
 std::printf("%u tile/crop/reversal cases: unique coverage, original UV mapping and attributes preserved; pre-miss eviction passed\n",cases);
}
