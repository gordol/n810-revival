#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include "../common/mbx_texture_resident.h"
static unsigned make(unsigned char *p,unsigned count,const unsigned *ids){
 unsigned span=32*18*4,prefix=64+16*count,bytes=prefix+count*span+count*64;
 unsigned h[12]={0x3156474d,9,bytes,count,400,256,0,0,0,0,0,5},t[4]={count,count*span,0,0};
 memset(p,0,bytes);memcpy(p,h,48);memcpy(p+48,t,16);
 for(unsigned i=0;i<count;i++){
  struct mbx_wire_resource d={8,span,i*span,(16<<16)|16};memcpy(p+64+i*16,&d,16);
  memset(p+prefix+i*span,ids[i]+1,span);
  unsigned draw[16]={64};draw[15]=4|128|65536|mbx_resource_index_flags(i);memcpy(p+prefix+count*span+i*64,draw,64);
 }return bytes;
}
int main(void){
 unsigned char *f=malloc(1048576),*o=malloc(1048608),*copy=malloc(1048608),*saved=malloc(1048576);
 struct mbx_texture_resident s={.data=malloc(MBX_WIRE_LINEAR_PAYLOAD),.session=17};struct mbx_wire_resources r;
 unsigned ids[4]={0,1,2,3},n=make(f,4,ids),written,expanded;
 assert(!mbx_wire_resources_parse(f,n,&r));assert(!mbx_texture_resident_commit(&s,f,&r));
 for(unsigned mask=0;mask<16;mask++)for(unsigned reverse=0;reverse<2;reverse++){
  unsigned count=0;for(unsigned i=0;i<4;i++){unsigned j=reverse?3-i:i;if(mask&(1U<<j))ids[count++]=j;}
  n=make(f,count,ids);memcpy(saved,f,n);
  assert(!mbx_texture_ref_pack_subset(&s,f,n,o,1048608,&written));assert(!memcmp(saved,f,n));
  memcpy(copy,o,written);assert(!mbx_texture_ref_expand(&s,copy,written,1048576,&expanded));
  assert(!mbx_wire_resources_parse(copy,expanded,&r));assert(r.count==4);
  for(unsigned i=0;i<count;i++){
   unsigned flags;memcpy(&flags,copy+r.draw_offset+i*64+60,4);
   assert(mbx_resource_index_decode(flags)==ids[i]);assert((flags&~mbx_resource_index_flags(63))==(4|128|65536));
   assert(!memcmp(copy+r.data_offset+r.item[ids[i]].offset,f+64+16*count+i*32*18*4,32*18*4));
  }
 }
 ids[0]=2;n=make(f,1,ids);memset(o,0x55,1048608);f[80]^=1;
 assert(mbx_texture_ref_pack_subset(&s,f,n,o,1048608,&written));assert(o[0]==0x55);
 f[80]^=1;unsigned bad=63;memcpy(f+n-4,&bad,4);assert(mbx_texture_ref_pack_subset(&s,f,n,o,1048608,&written));
 n=make(f,1,ids);assert(mbx_texture_ref_pack_subset(&s,f,n,o,10,&written));
 for(unsigned i=0;i<n;i++)assert(mbx_texture_ref_pack_subset(&s,f,i,o,1048608,&written));
 /* Mixed uploaded textures and rendered-image tokens retain token identity.
  * A newly rendered generation must miss, even if its slot is unchanged. */
 n=make(f,1,ids);unsigned resource_index;
 struct mbx_window_token token={17,71,3};
 assert(!mbx_wire_resource_append_window(f,1048576,token,&resource_index));
 memcpy(&n,f+8,4);assert(!mbx_wire_resources_parse(f,n,&r));
 assert(mbx_texture_resident_eligible(&r));assert(!mbx_texture_resident_commit(&s,f,&r));
 n=make(f,0,ids);assert(!mbx_wire_resource_append_window(f,1048576,token,&resource_index));memcpy(&n,f+8,4);
 assert(!mbx_texture_ref_pack_subset(&s,f,n,o,1048608,&written));
 memcpy(copy,o,written);assert(!mbx_texture_ref_expand(&s,copy,written,1048576,&expanded));
 assert(!mbx_wire_resources_parse(copy,expanded,&r));assert(r.item[1].version==13&&r.item[1].bytes==71&&r.item[1].offset==3);
 ((struct mbx_wire_resource *)(f+64))->bytes=72;
 assert(mbx_texture_ref_pack_subset(&s,f,n,o,1048608,&written));
 s.valid=0;assert(mbx_texture_ref_pack_subset(&s,f,n,o,1048608,&written));
 free(f);free(o);free(copy);free(saved);free(s.data);
 puts("texture subset: 32 empty/subset/reorder cases exact; mutation/truncation/stale/capacity rejected");
}
