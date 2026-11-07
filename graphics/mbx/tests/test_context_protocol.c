/* SPDX-License-Identifier: MIT */
#include "../common/mbx_context.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
struct event {unsigned kind,a,b;};
struct fake {struct event events[16];unsigned count,fail;};
static int record(struct fake *f,unsigned kind,unsigned a,unsigned b)
{
 unsigned n=f->count++;assert(n<16);f->events[n]=(struct event){kind,a,b};
 return f->count==f->fail ? -110 : 0;
}
static int write_reg(void *p,unsigned r,unsigned v){return record(p,1,r,v);}
static int fresh(void *p,unsigned m){return record(p,2,m,0);}
static int wait_event(void *p,unsigned m){return record(p,3,m,0);}
static void settle(void *p){assert(!record(p,4,0,0));}
int main(void)
{
 struct fake f={0};struct mbx_context_io io={&f,write_reg,fresh,wait_event,settle};
 /* Pin the reference's retirement->reload ordering and distinct event
  * boundaries; a context-load event cannot stand in for a TA transition. */
 const struct event init[]={{1,0x834,1},{4,0,0},{1,0x134,0xc0},{2,0x100,0},
  {1,0x864,0x94000},{1,0x820,0x92000},{1,0x814,1},{3,0x100,0}};
 const struct event finish[]={{2,0x10,0},{1,0x80c,0x60005},{1,0x808,1},{3,0x10,0}};
 unsigned i;
 const struct event seeded[]={{1,0x834,1},{4,0,0},{1,0x134,0xc0}};
 assert(!mbx_context_retire_loaded(&io));
 assert(f.count==3 && !memcmp(seeded,f.events,sizeof(seeded)));
 memset(&f,0,sizeof(f));
 assert(!mbx_context_retire_then_reload(&io,0x92000,0x94000));
 assert(f.count==8 && !memcmp(init,f.events,sizeof(init)));
 memset(&f,0,sizeof(f));assert(!mbx_context_finish(&io,0x60005));
 assert(f.count==4 && !memcmp(finish,f.events,sizeof(finish)));
 /* Every failing write/readback boundary stops the protocol immediately. */
 for(i=1;i<=8;++i){if(i==2)continue;memset(&f,0,sizeof(f));f.fail=i;
  assert(mbx_context_retire_then_reload(&io,0x92000,0x94000)==-110 && f.count==i);}
 for(i=1;i<=4;++i){memset(&f,0,sizeof(f));f.fail=i;
  assert(mbx_context_finish(&io,0)==-110 && f.count==i);}
 memset(&f,0,sizeof(f));assert(mbx_context_retire_then_reload(&io,0x92001,0x94000)==-22 && !f.count);
 assert(mbx_context_finish(&io,0x80000000)==-22 && !f.count);
 puts("MBX context protocol: retirement/reload ordering, fresh transition event and all11 error boundaries PASS");
}
