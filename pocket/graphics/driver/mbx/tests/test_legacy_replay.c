/* SPDX-License-Identifier: MIT. Legacy API compatibility and exact commands. */
#define main prepared_fixture_main
#include "test_prepared.c"
#undef main
int main(void){
 for(unsigned texture=0;texture<2;texture++){
  unsigned bytes=make_frame(texture),written,count;
  struct mbx_vgp_wire_replay_cache cache={.snapshot=(void*)snapshot,.snapshot_capacity=sizeof snapshot};
  assert(!mbx_vgp_wire_encode_replay(wire,bytes,command,65536,&written,0,&cache));
  assert(cache.bytes==bytes&&cache.draws==1&&cache.written==written&&cache.owner==command);
  assert(!memcmp(snapshot,wire,bytes));
  assert(!mbx_vgp_wire_encode(wire,bytes,reference,65536,&count)&&count==written&&!memcmp(command,reference,count*sizeof *command));
  struct mbx_vgp_wire_draw *draw=(void*)((unsigned char*)wire+48+(texture?8192:0));
  unsigned *uniform=(void*)((unsigned char*)(draw+1)+8*draw->instructions);
  for(unsigned step=0;step<64;step++){
   draw->viewport[0]=0x43000000+step*0x10000;uniform[16]=0x3e800000+step*0x1000;
   assert(mbx_template_update(snapshot,bytes,wire,bytes,7,update,sizeof update,&written)==1&&written==136);
   memcpy(before,command,count*sizeof *command);unsigned unchanged=37;
   assert(mbx_vgp_wire_apply_update(update,written,8,command,65536,&unchanged,&cache)==-22);
   assert(unchanged==37&&!memcmp(before,command,count*sizeof *command));
   assert(mbx_vgp_wire_apply_update(update,written,7,reference,65536,&unchanged,&cache)==-22);
   assert(!mbx_vgp_wire_apply_update(update,written,7,command,65536,&written,&cache));
   assert(!mbx_vgp_wire_encode(wire,bytes,reference,65536,&count));
   assert(written==count&&!memcmp(command,reference,count*sizeof *command));
  }
  /* Replacement failures and missing storage cannot leave an old identity. */
  unsigned old=((struct mbx_vgp_wire_frame*)wire)->magic;
  ((struct mbx_vgp_wire_frame*)wire)->magic=0;
  assert(mbx_vgp_wire_encode_replay(wire,bytes,command,65536,&written,0,&cache)==-22&&!cache.bytes&&!cache.owner);
  ((struct mbx_vgp_wire_frame*)wire)->magic=old;
  cache.snapshot_capacity=bytes-1;
  assert(!mbx_vgp_wire_encode_replay(wire,bytes,command,65536,&written,0,&cache)&&!cache.bytes&&!cache.owner);
  cache.snapshot_capacity=sizeof snapshot;cache.snapshot=NULL;
  assert(!mbx_vgp_wire_encode_replay(wire,bytes,command,65536,&written,0,&cache)&&!cache.bytes&&!cache.owner);
 }
 /* New retained-image frame versions stay outside implicit legacy capture. */
 unsigned bytes=make_frame(0),written;((struct mbx_vgp_wire_frame*)wire)->version=9;
 memmove((unsigned char*)wire+64,(unsigned char*)wire+48,bytes-48);memset((unsigned char*)wire+48,0,16);
 bytes+=16;((struct mbx_vgp_wire_frame*)wire)->bytes=bytes;
 struct mbx_vgp_wire_replay_cache cache={.snapshot=(void*)snapshot,.snapshot_capacity=sizeof snapshot};
 assert(!mbx_vgp_wire_encode_replay(wire,bytes,command,65536,&written,0,&cache)&&!cache.bytes&&!cache.owner);
 puts("legacy replay:plain/textured capture and128 compact updates match full commands exactly; stale generation/wrong command owner rejected before writes; failed/oversize/storage-less/newer frames invalidate legacy identity");
}
