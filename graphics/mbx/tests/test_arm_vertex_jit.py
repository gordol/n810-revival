"""Run emitted ARMv6/VFPv2 code under qemu-arm against the C evaluator.
Uses production evaluator/emitter, randomized SSA, all arithmetic, masks,
modifiers, saturation, callbacks, signed zero, infinities and NaNs.
Run in n810-builder with the owned mesa directory as argv[1].
"""
from pathlib import Path
import subprocess,sys
src=Path(sys.argv[1]);out=Path('/tmp/mbx-jit-test');out.mkdir(exist_ok=True)
header=(src/'draw_mbx_fast_vs.h').read_text().split('static struct mf_program *mf_create')[0]
prefix=r'''
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <math.h>
#include <assert.h>
#define SATURATE(x) fminf(fmaxf((x),0.0f),1.0f)
enum { TGSI_OPCODE_MOV, TGSI_OPCODE_ADD,TGSI_OPCODE_MUL,TGSI_OPCODE_MAD,
TGSI_OPCODE_DP3,TGSI_OPCODE_DP4,TGSI_OPCODE_RSQ,TGSI_OPCODE_RCP,TGSI_OPCODE_MAX,
TGSI_OPCODE_MIN,TGSI_OPCODE_SLT };
'''
main=r'''
static uint32_t rng=0x98101234;
static uint32_t random32(void){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;}
int main(void){
 setenv("N810_MBX_ARM_JIT","1",1);
 /* Exhaustion and branch patching cannot write beyond the code capacity. */
 uint32_t limited[5]={0};struct mf_emitter small={.words=limited,.capacity=4};
 for(unsigned i=0;i<5;++i)mf_emit(&small,0x12345678);
 assert(small.failed&&small.count==4&&limited[4]==0);
 mf_patch_skip(&small,4);mf_patch_branch(&small,4,0xea000000);
 assert(limited[4]==0);
 unsigned long values=0,nan_payloads=0;
 for(unsigned trial=0;trial<128;++trial){
  struct mf_program *p=calloc(1,sizeof(*p)),*reference=calloc(1,sizeof(*p));assert(p&&reference);
  p->count=256;
  for(unsigned k=0;k<p->count;++k){
   struct mf_op *o=&p->ops[k];o->dst=MF_RESULT+4*k;
   o->opcode=k%11;o->mask=1+(random32()%15);
   if(k%5==0){o->abs=random32()%8;o->neg=random32()%8;o->saturate=k%2;}
   /* Previous result slots are initialized too, so partial masks are covered. */
   for(unsigned s=0;s<3;++s)for(unsigned c=0;c<4;++c)o->src[s][c]=random32()%o->dst;
   p->vertex_ops[p->vertex_count++]=k;
  }
  mf_compile_native(p);assert(p->native_run);
  for(unsigned iteration=0;iteration<64;++iteration){
   for(unsigned i=0;i<MF_WORDS;++i){
    uint32_t bits=random32();
    if(iteration<32)bits=(bits&0x807fffff)|((110+random32()%30)<<23);
    memcpy(&p->r[i],&bits,4);
   }
   memcpy(reference->r,p->r,sizeof(p->r));
   for(unsigned k=0;k<p->count;++k)mf_execute(reference,&p->ops[k]);
   p->native_run(p);
   for(unsigned i=0;i<MF_WORDS;++i){
    if(memcmp(&p->r[i],&reference->r[i],4)&&isnan(p->r[i])&&isnan(reference->r[i])){++nan_payloads;continue;}
    if(memcmp(&p->r[i],&reference->r[i],4)){
     fprintf(stderr,"FAIL trial=%u iteration=%u slot=%u native=%a C=%a\n",trial,iteration,i,p->r[i],reference->r[i]);
     if(i>=MF_RESULT){struct mf_op *op=&p->ops[(i-MF_RESULT)/4];unsigned ch=i%4;fprintf(stderr,"opcode=%u abs=%u neg=%u sat=%u a=%a b=%a refs=%u,%u\n",op->opcode,op->abs,op->neg,op->saturate,reference->r[op->src[0][ch]],reference->r[op->src[1][ch]],op->src[0][ch],op->src[1][ch]);}return 1;
    }
    ++values;
   }
  }
  mf_destroy(p);free(reference);
 }
 printf("PASS ARM1136 VFP native/C: %lu bit-exact values; %lu equivalent NaNs with different payload/sign; 128 programs, 2097152 operations\n",values,nan_payloads);
 return 0;
}
'''
c=out/'test.c';c.write_text(prefix+header+main)
subprocess.run(['arm-linux-gnueabi-gcc','-O3','-mcpu=arm1136jf-s','-marm','-mfpu=vfp','-mfloat-abi=softfp','-ffp-contract=off','-I'+str(src),str(c),'-lm','-o',str(out/'test')],check=True)
subprocess.run(['qemu-arm','-cpu','arm1136','-L','/usr/arm-linux-gnueabi',str(out/'test')],check=True)
