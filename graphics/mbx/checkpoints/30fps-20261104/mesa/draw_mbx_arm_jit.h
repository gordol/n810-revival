/* SPDX-License-Identifier: MIT
 * ARMv6/VFPv2 native execution of the bounded SSA vertex program.
 * No fused arithmetic, reassociation, reduced precision or executable writes.
 * Unsupported instructions call the exact existing evaluator.
 */
#if defined(__arm__) && defined(__VFP_FP__) && !defined(__ARMEB__)
#include <stddef.h>
#include <sys/mman.h>
struct mf_emitter { uint32_t *words; size_t count,capacity; int bank; bool failed; int slots[16]; unsigned ages[16],tick,dirty; bool deferred; unsigned current; uint16_t last_use[MF_WORDS]; };
static void mf_emit(struct mf_emitter *e,uint32_t word)
{
 if(e->count==e->capacity){e->failed=true;return;}
 e->words[e->count++]=word;
}
static void mf_patch_skip(struct mf_emitter *e,size_t skip)
{
 if(skip>=e->capacity||e->count<skip+2){e->failed=true;return;}
 e->words[skip]=0x0a000000u|((uint32_t)(e->count-skip-2)&0x00ffffffu);
}
static void mf_literal(struct mf_emitter *e,unsigned reg,uint32_t value)
{
 mf_emit(e,0xe59f0000u|(reg<<12)); /* ldr reg,[pc] */
 mf_emit(e,0xea000000u);          /* branch over literal */
 mf_emit(e,value);
}
static void mf_bank(struct mf_emitter *e,unsigned slot)
{
 unsigned bank=slot/256;
 if(bank>=MF_WORDS/256){e->failed=true;return;}
 if(e->bank==(int)bank)return;
 /* Rotated immediate: ROR(bank,22) == bank*1024, bank in [0,8]. */
 mf_emit(e,0xe2851b00u|bank); /* add r1,r5,#bank*1024 */
 e->bank=bank;
}
static void mf_vmem(struct mf_emitter *e,bool store,unsigned reg,unsigned slot)
{
 mf_bank(e,slot);
 mf_emit(e,(store?0xed810a00u:0xed910a00u)|((reg&1)<<22)|((reg>>1)<<12)|(slot%256));
}
/* All sixteen registers are caller-clobbered under AAPCS. Values are also
 * Normally mirrored in SSA memory. Optional deferred stores spill on eviction,
 * callbacks, control-flow boundaries and return; arithmetic is unchanged. */
static void mf_reg_flush(struct mf_emitter *e,unsigned reg)
{
 if(e->dirty&(1u<<reg)){
  if(e->last_use[e->slots[reg]]>=e->current)mf_vmem(e,true,reg,e->slots[reg]);
  e->dirty&=~(1u<<reg);
 }
}
static void mf_regs_reset(struct mf_emitter *e)
{
 for(unsigned i=0;i<16;++i){mf_reg_flush(e,i);e->slots[i]=-1;e->ages[i]=0;}
 e->tick=0;
}
static unsigned mf_reg(struct mf_emitter *e,unsigned slot,unsigned locked,bool load)
{
 for(unsigned i=0;i<16;++i)if(e->slots[i]==(int)slot){e->ages[i]=++e->tick;return i;}
 unsigned best=16;
 for(unsigned i=0;i<16;++i)if(!(locked&(1u<<i))&&(best==16||e->ages[i]<e->ages[best]))best=i;
 if(best==16){e->failed=true;return 0;}
 mf_reg_flush(e,best);
 e->slots[best]=slot;e->ages[best]=++e->tick;
 if(load)mf_vmem(e,false,best,slot);
 return best;
}
static void mf_binary(struct mf_emitter *e,uint32_t base,unsigned d,unsigned n,unsigned m)
{ mf_emit(e,base|((d&1)<<22)|((d>>1)<<12)|((n&1)<<7)|((n>>1)<<16)|((m&1)<<5)|(m>>1)); }
static void mf_scalar_native(struct mf_emitter *e,const struct mf_op *o)
{
 unsigned source[3][4]={{0}},locked=0;
 unsigned ns=o->opcode==TGSI_OPCODE_MOV?1:o->opcode==TGSI_OPCODE_MAD?3:2;
 /* Lock all sources before allocating results: later channels can read an
  * earlier channel's input, and SSA register references can be swizzled. */
 for(unsigned n=0;n<ns;++n)for(unsigned c=0;c<4;++c)if(o->mask&(1<<c)){
  unsigned r=mf_reg(e,o->src[n][c],locked,true);source[n][c]=r;locked|=1u<<r;
 }
 for(unsigned c=0;c<4;++c)if(o->mask&(1<<c)){
  unsigned d=mf_reg(e,o->dst+c,locked,false);
  if(o->opcode==TGSI_OPCODE_MOV)
   mf_emit(e,0xeeb00a40u|((d&1)<<22)|((d>>1)<<12)|((source[0][c]&1)<<5)|(source[0][c]>>1));
  else{
   mf_binary(e,o->opcode==TGSI_OPCODE_ADD?0xee300a00u:0xee200a00u,d,source[0][c],source[1][c]);
   if(o->opcode==TGSI_OPCODE_MAD)mf_binary(e,0xee300a00u,d,d,source[2][c]);
  }
  if(e->deferred)e->dirty|=1u<<d;else mf_vmem(e,true,d,o->dst+c);
 }
}
static void mf_patch_branch(struct mf_emitter *e,size_t at,uint32_t condition)
{
 if(at>=e->capacity||e->count<at+2){e->failed=true;return;}
 e->words[at]=condition|((uint32_t)(e->count-at-2)&0x00ffffffu);
}
static void mf_callback(struct mf_emitter *e,const struct mf_op *o)
{
 mf_regs_reset(e);
 mf_emit(e,0xe1a00004);mf_literal(e,1,(uintptr_t)o);
 mf_literal(e,12,(uintptr_t)mf_execute);mf_emit(e,0xe12fff3c);
 e->bank=-1;mf_regs_reset(e);
}
static void mf_special_native(struct mf_emitter *e,const struct mf_op *o)
{
 size_t fallback[8],nf=0;mf_regs_reset(e);
 if(o->opcode==TGSI_OPCODE_RSQ||o->opcode==TGSI_OPCODE_RCP){
  mf_vmem(e,false,0,o->src[0][0]);
  if(o->opcode==TGSI_OPCODE_RSQ){
   mf_emit(e,0xeeb50a40); /* vcmp s0,#0 */
   mf_emit(e,0xeef1fa10); /* vmrs APSR_nzcv,fpscr */
   fallback[nf++]=e->count;mf_emit(e,0xba000000); /* negative or unordered */
   mf_emit(e,0xeeb10ac0); /* vsqrt s0,s0 */
  }
  mf_literal(e,12,0x3f800000);mf_emit(e,0xee00ca90); /* s1=1.0 */
  mf_emit(e,0xee800a80); /* vdiv s0,s1,s0 */
  for(unsigned c=0;c<4;++c)if(o->mask&(1<<c))mf_vmem(e,true,0,o->dst+c);
 }else for(unsigned c=0;c<4;++c)if(o->mask&(1<<c)){
  mf_vmem(e,false,0,o->src[0][c]);mf_vmem(e,false,1,o->src[1][c]);
  mf_emit(e,0xeeb40a60);mf_emit(e,0xeef1fa10); /* compare s0,s1 */
  if(o->opcode==TGSI_OPCODE_SLT){
   mf_literal(e,12,0x3f800000);mf_emit(e,0xe3a02000);mf_emit(e,0xee012a10);
   mf_emit(e,0x3e01ca10); /* ordered less only: unordered sets C=1 */
  }else{
   fallback[nf++]=e->count;mf_emit(e,0x6a000000); /* unordered: exact C path */
   fallback[nf++]=e->count;mf_emit(e,0x0a000000); /* equality preserves C signed-zero selection */
   mf_emit(e,0xeeb01a60); /* vmov s2,s1 */
   mf_emit(e,o->opcode==TGSI_OPCODE_MAX?0xaeb01a40:0xdeb01a40); /* GE/LE */
  }
  mf_vmem(e,true,2,o->dst+c);
 }
 if(nf){
  size_t done=e->count;mf_emit(e,0xea000000);
  for(unsigned i=0;i<nf;++i){
   if(fallback[i]>=e->capacity)e->failed=true;
   else mf_patch_branch(e,fallback[i],e->words[fallback[i]]&0xff000000u);
  }
  /* Runtime can branch before any current address bank has been set. */
  mf_callback(e,o);mf_patch_branch(e,done,0xea000000);
 }
 e->bank=-1;mf_regs_reset(e);
}

static void mf_compile_native(struct mf_program *p)
{
 const char *enable=getenv("N810_MBX_ARM_JIT");
 if(!enable||strcmp(enable,"1"))return;
 size_t bytes=65536;
 uint32_t *code=mmap(NULL,bytes,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
 if(code==MAP_FAILED)return;
 struct mf_emitter e={.words=code,.capacity=bytes/4,.bank=-1};unsigned native=0,callbacks=0;
 e.deferred=(!p->reuse_inputs||(getenv("N810_MBX_DEFER_REUSE")&&!strcmp(getenv("N810_MBX_DEFER_REUSE"),"1")))&&getenv("N810_MBX_DEFER_VERTEX_STORES")&&!strcmp(getenv("N810_MBX_DEFER_VERTEX_STORES"),"1");
 /* Track the last consumer of each SSA word. Values consumed outside this
  * compiled partition (uniform/vertex split) and declared outputs stay live. */
 for(unsigned i=0;i<MF_WORDS;++i)e.last_use[i]=UINT16_MAX;
 if(e.deferred){
  uint16_t order[256];for(unsigned i=0;i<256;++i)order[i]=UINT16_MAX;
  for(unsigned k=0;k<p->vertex_count;++k){
   unsigned i=p->vertex_ops[k];order[i]=k;
   for(unsigned c=0;c<4;++c)if(p->ops[i].mask&(1u<<c))e.last_use[p->ops[i].dst+c]=0;
  }
  for(unsigned i=0;i<p->count;++i){
   const struct mf_op *o=&p->ops[i];
   unsigned ns=o->opcode==TGSI_OPCODE_MOV||o->opcode==TGSI_OPCODE_RSQ||o->opcode==TGSI_OPCODE_RCP?1:o->opcode==TGSI_OPCODE_MAD?3:2;
   unsigned mask=o->opcode==TGSI_OPCODE_DP3?7:o->opcode==TGSI_OPCODE_DP4?15:o->opcode==TGSI_OPCODE_RSQ||o->opcode==TGSI_OPCODE_RCP?1:o->mask;
   for(unsigned n=0;n<ns;++n)for(unsigned c=0;c<4;++c)if(mask&(1u<<c)){
    unsigned ref=o->src[n][c];if(e.last_use[ref]<order[i])e.last_use[ref]=order[i];
   }
  }
  /* A skipped dependency group may be needed by a later vertex. Its
   * results must survive in SSA memory across conditional native blocks. */
  if(p->reuse_inputs)for(unsigned k=0;k<p->vertex_count;++k){
   unsigned i=p->vertex_ops[k];uint32_t deps=p->dependencies[i];
   if(deps&&!(deps&~p->reuse_mask))for(unsigned c=0;c<4;++c)
    if(p->ops[i].mask&(1u<<c))e.last_use[p->ops[i].dst+c]=UINT16_MAX;
  }
  for(unsigned i=0;i<p->outputs;++i)for(unsigned c=0;c<4;++c)e.last_use[p->output[i][c]]=UINT16_MAX;
 }
 mf_regs_reset(&e);
 mf_emit(&e,0xe92d4070); /* push {r4,r5,r6,lr}: AAPCS 8-byte aligned */
 mf_emit(&e,0xe1a04000); /* mov r4,r0: program pointer */
 if(p->reuse_inputs){
  mf_literal(&e,6,offsetof(struct mf_program,dirty_inputs));
  mf_emit(&e,0xe7946006u); /* ldr r6,[r4,r6], callee-preserved dirty mask */
 }
 mf_literal(&e,5,offsetof(struct mf_program,r));
 mf_emit(&e,0xe0845005); /* add r5,r4,r5: SSA values */
 size_t skip=0;uint32_t group=0;
 for(unsigned k=0;k<p->vertex_count;++k){
  e.current=k;
  unsigned index=p->vertex_ops[k];
  const struct mf_op *o=&p->ops[index];
  if(p->reuse_inputs&&(k==0||group!=p->dependencies[index])){
   bool previous_guard=skip!=0;
   if(skip){mf_regs_reset(&e);e.bank=-1;mf_patch_skip(&e,skip);}
   skip=0;group=p->dependencies[index];
   bool guard=group && !(group&~p->reuse_mask);
   if(previous_guard||guard){mf_regs_reset(&e);e.bank=-1;}
   if(guard){
    mf_literal(&e,12,group);
    mf_emit(&e,0xe116000cu); /* tst r6,ip */
    skip=e.count;mf_emit(&e,0x0a000000u);
   }
  }
  bool scalar=o->opcode==TGSI_OPCODE_MOV||o->opcode==TGSI_OPCODE_ADD||
              o->opcode==TGSI_OPCODE_MUL||o->opcode==TGSI_OPCODE_MAD;
  bool dot=o->opcode==TGSI_OPCODE_DP3||o->opcode==TGSI_OPCODE_DP4;
  bool special=o->opcode==TGSI_OPCODE_RSQ||o->opcode==TGSI_OPCODE_RCP||
               o->opcode==TGSI_OPCODE_MAX||o->opcode==TGSI_OPCODE_MIN||o->opcode==TGSI_OPCODE_SLT;
  if(special&&!o->abs&&!o->neg&&!o->saturate){++native;mf_special_native(&e,o);}
  else if((scalar||dot)&&!o->abs&&!o->neg&&!o->saturate){
   ++native;
   if(dot){
    /* Keep common matrix/vector sources live across dot products. Reserve
     * s14/s15 for the accumulator/product; all cached values have SSA stores. */
    mf_reg_flush(&e,14);mf_reg_flush(&e,15);
    e.slots[14]=e.slots[15]=-1;
    unsigned n=o->opcode==TGSI_OPCODE_DP3?3:4;
    unsigned source[2][4],locked=(1u<<14)|(1u<<15);
    for(unsigned c=0;c<n;++c)for(unsigned j=0;j<2;++j){
     unsigned r=mf_reg(&e,o->src[j][c],locked,true);
     source[j][c]=r;locked|=1u<<r;
    }
    mf_binary(&e,0xee200a00u,14,source[0][0],source[1][0]);
    for(unsigned c=1;c<n;++c){
     mf_binary(&e,0xee200a00u,15,source[0][c],source[1][c]);
     mf_binary(&e,0xee300a00u,14,15,14);
    }
    for(unsigned c=0;c<4;++c)if(o->mask&(1<<c))mf_vmem(&e,true,14,o->dst+c);
   }else mf_scalar_native(&e,o);
  }else{
   ++callbacks;
   mf_regs_reset(&e);
   mf_emit(&e,0xe1a00004); /* mov r0,r4 */
   mf_literal(&e,1,(uintptr_t)o);
   mf_literal(&e,12,(uintptr_t)mf_execute);
   mf_emit(&e,0xe12fff3c); /* blx ip (honors ARM/Thumb function pointer) */
   e.bank=-1;mf_regs_reset(&e); /* Caller-clobbered scalar and VFP registers. */
  }
 }
 if(skip){mf_regs_reset(&e);e.bank=-1;mf_patch_skip(&e,skip);}
 e.current=p->vertex_count;mf_regs_reset(&e);
 mf_emit(&e,0xe8bd8070); /* pop {r4,r5,r6,pc} */
 if(e.failed||!native){munmap(code,bytes);return;}
 __builtin___clear_cache((char *)code,(char *)(code+e.count));
 if(mprotect(code,bytes,PROT_READ|PROT_EXEC)){munmap(code,bytes);return;}
 p->native_code=code;p->native_bytes=bytes;p->native_run=(void (*)(struct mf_program *))code;
 fprintf(stderr,"N810_MBX_ARM_JIT bytes=%zu native_ops=%u callbacks=%u wx=0\n",e.count*4,native,callbacks);
}
static void mf_destroy(struct mf_program *p)
{ if(p&&p->native_code)munmap(p->native_code,p->native_bytes);if(p&&p->native_uniform_code)munmap(p->native_uniform_code,p->native_uniform_bytes);if(p)free(p->cached_vertices);free(p); }
#else
static void mf_compile_native(struct mf_program *p){(void)p;}
static void mf_destroy(struct mf_program *p){if(p)free(p->cached_vertices);free(p);}
#endif
