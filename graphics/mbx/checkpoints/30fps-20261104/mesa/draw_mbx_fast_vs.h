/* SPDX-License-Identifier: MIT
 * Bounded straight-line TGSI vertex execution. SSA references remove repeated
 * register-file decoding; input-independent operations run once per draw.
 * Unsupported programs retain Mesa's original vertex interpreter.
 */
#include <stdint.h>
#include <time.h>
#include "mbx_trace.h"
#define MF_INPUT 0
#define MF_CONST 128
#define MF_IMM 1152
#define MF_RESULT 1280
#define MF_WORDS 2304
struct mf_op { uint16_t src[3][4]; uint16_t dst; uint8_t opcode,mask,abs,neg,saturate,uniform; };
struct mf_program {
 uint32_t dependencies[256],dirty_inputs,reuse_mask; bool reuse_inputs;
 struct mf_op ops[256]; unsigned count,constants,inputs,outputs,uniform_count;
 uint16_t uniform_ops[256],vertex_ops[256]; unsigned vertex_count;
 uint16_t output[32][4]; float r[MF_WORDS]; bool verify,profile; bool output_contiguous[32];
 unsigned verified,verify_limit;
 bool result_cache,uniform_cache,uniform_ready;
 uint32_t cached_clamp,cache_valid;
 float *cached_vertices;
 uint64_t cache_hits,cache_misses,trace_calls,uniform_reused;
 void (*native_uniform_run)(struct mf_program *); void *native_uniform_code; size_t native_uniform_bytes;
 void (*native_run)(struct mf_program *); void *native_code; size_t native_bytes;
};
/* Cold-path inventory only. Cache-line footprint is not a miss counter. */
static void mf_memory_inventory(const struct mf_program *p)
{
 if(!getenv("N810_MBX_PROFILE_MEMORY"))return;
 bool used[MF_WORDS]={0};
 for(unsigned i=0;i<p->inputs*4;++i)used[MF_INPUT+i]=true;
 for(unsigned i=0;i<p->constants*4;++i)used[MF_CONST+i]=true;
 for(unsigned n=0;n<p->count;++n){
  const struct mf_op *o=&p->ops[n];
  unsigned ns=o->opcode==TGSI_OPCODE_MAD?3:
   (o->opcode==TGSI_OPCODE_MOV||o->opcode==TGSI_OPCODE_RCP||o->opcode==TGSI_OPCODE_RSQ)?1:2;
  unsigned mask=o->opcode==TGSI_OPCODE_DP3?7:o->opcode==TGSI_OPCODE_DP4?15:
   (o->opcode==TGSI_OPCODE_RSQ||o->opcode==TGSI_OPCODE_RCP)?1:o->mask;
  for(unsigned j=0;j<ns;++j)for(unsigned k=0;k<4;++k)
   if(mask&(1u<<k))used[o->src[j][k]]=true;
  for(unsigned k=0;k<4;++k)if(o->mask&(1u<<k))used[o->dst+k]=true;
 }
 unsigned words=0,lines=0,first=MF_WORDS,last=0;uintptr_t previous=UINTPTR_MAX;
 for(unsigned i=0;i<MF_WORDS;++i)if(used[i]){
  uintptr_t line=(uintptr_t)(p->r+i)/32;
  ++words;if(line!=previous){++lines;previous=line;}
  if(first==MF_WORDS)first=i;last=i;
 }
 fprintf(stderr,"N810_MBX_WORKSET context=%p active_register_bytes=%u register_span_bytes=%u register_cache_lines32=%u struct_bytes=%zu native_mapping_bytes=%zu inputs=%u outputs=%u constants=%u\n",
  (const void *)p,words*4,words?(last-first+1)*4:0,lines,sizeof(*p),p->native_bytes+p->native_uniform_bytes,p->inputs,p->outputs,p->constants);
}
static float mf_source(const struct mf_program *p,const struct mf_op *o,unsigned s,unsigned c)
{
 float v=p->r[o->src[s][c]];
 if(o->abs&(1<<s))v=fabsf(v);
 if(o->neg&(1<<s))v=-v;
 return v;
}
static void mf_execute(struct mf_program *p,const struct mf_op *o)
{
 /* Common vector arithmetic has no per-channel opcode or modifier dispatch.
  * SSA destinations cannot alias any of this instruction's source values. */
 if(o->mask==15&&!o->abs&&!o->neg&&!o->saturate){
  float *r=p->r,*dst=r+o->dst;
  if(o->opcode==TGSI_OPCODE_MOV){
   for(unsigned i=0;i<4;++i)dst[i]=r[o->src[0][i]];
   return;
  }
  if(o->opcode==TGSI_OPCODE_ADD){
   for(unsigned i=0;i<4;++i)dst[i]=r[o->src[0][i]]+r[o->src[1][i]];
   return;
  }
  if(o->opcode==TGSI_OPCODE_MUL){
   for(unsigned i=0;i<4;++i)dst[i]=r[o->src[0][i]]*r[o->src[1][i]];
   return;
  }
  if(o->opcode==TGSI_OPCODE_MAD){
   for(unsigned i=0;i<4;++i)dst[i]=r[o->src[0][i]]*r[o->src[1][i]]+r[o->src[2][i]];
   return;
  }
 }
 float value[4]={0},a,b,c;
 if(o->opcode==TGSI_OPCODE_DP3||o->opcode==TGSI_OPCODE_DP4){
  unsigned n=o->opcode==TGSI_OPCODE_DP3?3:4;
  a=mf_source(p,o,0,0)*mf_source(p,o,1,0);
  for(unsigned i=1;i<n;++i)a=mf_source(p,o,0,i)*mf_source(p,o,1,i)+a;
  for(unsigned i=0;i<4;++i)value[i]=a;
 }else if(o->opcode==TGSI_OPCODE_RSQ||o->opcode==TGSI_OPCODE_RCP){
  a=mf_source(p,o,0,0);a=o->opcode==TGSI_OPCODE_RSQ?1.0f/sqrtf(a):1.0f/a;
  for(unsigned i=0;i<4;++i)value[i]=a;
 }else for(unsigned i=0;i<4;++i)if(o->mask&(1<<i)){
  a=mf_source(p,o,0,i);b=mf_source(p,o,1,i);c=mf_source(p,o,2,i);
  switch(o->opcode){
   case TGSI_OPCODE_MOV:value[i]=a;break;
   case TGSI_OPCODE_MUL:value[i]=a*b;break;
   case TGSI_OPCODE_ADD:value[i]=a+b;break;
   case TGSI_OPCODE_MAD:value[i]=a*b+c;break;
   case TGSI_OPCODE_MAX:value[i]=fmaxf(a,b);break;
   case TGSI_OPCODE_MIN:value[i]=fminf(a,b);break;
   case TGSI_OPCODE_SLT:value[i]=a<b?1.0f:0.0f;break;
  }
 }
 for(unsigned i=0;i<4;++i)if(o->mask&(1<<i))p->r[o->dst+i]=o->saturate?SATURATE(value[i]):value[i];
}
/* Instruction encodings are checked against the ARM cross assembler. */
#include "draw_mbx_arm_jit.h"
/* Compile per-draw constants through the same exact native evaluator. */
static void mf_compile_all_native(struct mf_program *p)
{
 mf_compile_native(p);
 if(!p->uniform_count)return;
 unsigned count=p->vertex_count;uint16_t ops[256];
 memcpy(ops,p->vertex_ops,sizeof(ops));
 void (*run)(struct mf_program *)=p->native_run;void *code=p->native_code;size_t bytes=p->native_bytes;
 bool reuse=p->reuse_inputs;p->reuse_inputs=false;
 p->vertex_count=p->uniform_count;memcpy(p->vertex_ops,p->uniform_ops,sizeof(p->vertex_ops));
 p->native_run=NULL;p->native_code=NULL;p->native_bytes=0;
 mf_compile_native(p);
 p->native_uniform_run=p->native_run;p->native_uniform_code=p->native_code;p->native_uniform_bytes=p->native_bytes;
 p->native_run=run;p->native_code=code;p->native_bytes=bytes;
 p->vertex_count=count;memcpy(p->vertex_ops,ops,sizeof(ops));p->reuse_inputs=reuse;
}
static struct mf_program *mf_create(struct draw_vertex_shader *vs)
{
 const char *mode=getenv("N810_MBX_FAST_VS");
 if(!mode||(!strcmp(mode,"0")))return NULL;
 if(vs->info.num_inputs>32||vs->info.num_outputs>32||vs->info.uses_vertexid||
    vs->info.uses_instanceid||vs->info.uses_basevertex||vs->info.uses_vertexid_nobase)return NULL;
 struct mf_program *p=calloc(1,sizeof(*p));if(!p)return NULL;
 p->reuse_inputs=getenv("N810_MBX_REUSE_INPUTS")&&!strcmp(getenv("N810_MBX_REUSE_INPUTS"),"1");
 p->profile=getenv("N810_MBX_DETAILED_PROFILE")!=NULL;
 p->inputs=vs->info.num_inputs;p->outputs=vs->info.num_outputs;p->verify=!strcmp(mode,"verify")||!strcmp(mode,"check");p->verify_limit=!strcmp(mode,"check")?4096:0;
 uint32_t dependency[MF_WORDS]={0};
 for(unsigned i=0;i<p->inputs*4;++i)dependency[i]=1u<<(i/4);
 uint16_t temp[64][4];bool uniform[MF_WORDS]={0};unsigned imm=0;bool ended=false,valid=true;
 memset(temp,0xff,sizeof(temp));memset(p->output,0xff,sizeof(p->output));
 for(unsigned i=MF_CONST;i<MF_RESULT;++i)uniform[i]=true;
 struct tgsi_parse_context parse;
 if(tgsi_parse_init(&parse,vs->state.tokens)!=TGSI_PARSE_OK){free(p);return NULL;}
 while(!tgsi_parse_end_of_tokens(&parse)&&valid){
  tgsi_parse_token(&parse);
  if(parse.FullToken.Token.Type==TGSI_TOKEN_TYPE_IMMEDIATE){
   if(imm==32||parse.FullToken.FullImmediate.Immediate.NrTokens!=5){valid=false;break;}
   for(unsigned i=0;i<4;++i)memcpy(&p->r[MF_IMM+imm*4+i],&parse.FullToken.FullImmediate.u[i].Float,4);
   ++imm;continue;
  }
  if(parse.FullToken.Token.Type!=TGSI_TOKEN_TYPE_INSTRUCTION)continue;
  const struct tgsi_full_instruction *in=&parse.FullToken.FullInstruction;
  unsigned opcode=in->Instruction.Opcode,ns=0;
  if(opcode==TGSI_OPCODE_END){ended=true;break;}
  switch(opcode){
   case TGSI_OPCODE_MOV:case TGSI_OPCODE_RSQ:case TGSI_OPCODE_RCP:ns=1;break;
   case TGSI_OPCODE_ADD:case TGSI_OPCODE_MUL:case TGSI_OPCODE_DP3:case TGSI_OPCODE_DP4:
   case TGSI_OPCODE_MIN:case TGSI_OPCODE_MAX:case TGSI_OPCODE_SLT:ns=2;break;
   case TGSI_OPCODE_MAD:ns=3;break;
   default:valid=false;
  }
  if(!valid||p->count==256||in->Instruction.NumDstRegs!=1||in->Instruction.NumSrcRegs!=ns||
     in->Dst[0].Register.Indirect||in->Dst[0].Register.Dimension){valid=false;break;}
  struct mf_op *o=&p->ops[p->count];o->opcode=opcode;o->mask=in->Dst[0].Register.WriteMask;
  o->saturate=in->Instruction.Saturate;o->dst=MF_RESULT+p->count*4;o->uniform=true;
  unsigned used=opcode==TGSI_OPCODE_DP3?7:opcode==TGSI_OPCODE_DP4?15:
                (opcode==TGSI_OPCODE_RSQ||opcode==TGSI_OPCODE_RCP)?1:o->mask;
  for(unsigned s=0;s<ns&&valid;++s){
   const struct tgsi_full_src_register *src=&in->Src[s];
   if(src->Register.Indirect||(src->Register.Dimension&&(src->Dimension.Indirect||src->Dimension.Index!=0))){valid=false;break;}
   int idx=src->Register.Index;unsigned sw[4]={src->Register.SwizzleX,src->Register.SwizzleY,src->Register.SwizzleZ,src->Register.SwizzleW};
   o->abs|=src->Register.Absolute<<s;o->neg|=src->Register.Negate<<s;
   for(unsigned c=0;c<4;++c)if(used&(1<<c)){
    unsigned ref=65535;
    if(idx>=0)switch(src->Register.File){
     case TGSI_FILE_INPUT:if((unsigned)idx<p->inputs)ref=MF_INPUT+idx*4+sw[c];break;
     case TGSI_FILE_CONSTANT:if(idx<256){ref=MF_CONST+idx*4+sw[c];p->constants=MAX2(p->constants,(unsigned)idx+1);}break;
     case TGSI_FILE_IMMEDIATE:if((unsigned)idx<imm)ref=MF_IMM+idx*4+sw[c];break;
     case TGSI_FILE_TEMPORARY:if(idx<64)ref=temp[idx][sw[c]];break;
     case TGSI_FILE_OUTPUT:if((unsigned)idx<p->outputs)ref=p->output[idx][sw[c]];break;
    }
    if(ref>=MF_WORDS){valid=false;break;}
    o->src[s][c]=ref;o->uniform&=uniform[ref];p->dependencies[p->count]|=dependency[ref];
   }
  }
  int dst=in->Dst[0].Register.Index;uint16_t *mapping=NULL;
  if(dst>=0&&in->Dst[0].Register.File==TGSI_FILE_TEMPORARY&&dst<64)mapping=temp[dst];
  if(dst>=0&&in->Dst[0].Register.File==TGSI_FILE_OUTPUT&&(unsigned)dst<p->outputs)mapping=p->output[dst];
  if(!valid||!mapping){valid=false;break;}
  for(unsigned c=0;c<4;++c)if(o->mask&(1<<c)){mapping[c]=o->dst+c;uniform[o->dst+c]=o->uniform;dependency[o->dst+c]=p->dependencies[p->count];}
  if(o->uniform)p->uniform_ops[p->uniform_count++]=p->count;
  else p->vertex_ops[p->vertex_count++]=p->count;
  ++p->count;
 }
 tgsi_parse_free(&parse);
 for(unsigned i=0;i<p->outputs;++i)for(unsigned c=0;c<4;++c)if(p->output[i][c]>=MF_WORDS)valid=false;
 if(!valid||!ended){free(p);return NULL;}
 for(unsigned i=0;i<p->outputs;++i)p->output_contiguous[i]=p->output[i][1]==p->output[i][0]+1&&p->output[i][2]==p->output[i][0]+2&&p->output[i][3]==p->output[i][0]+3;
 /* Cache one independently expensive input chain. A shader with only one
  * dependency group has no independent work to save; avoid taxing every
  * position-only vertex with comparisons and conditional native blocks. */
 if(p->reuse_inputs){
  unsigned best=0;uint32_t selected=0,all=0;
  for(unsigned i=0;i<p->vertex_count;++i)all|=p->dependencies[p->vertex_ops[i]];
  for(unsigned input=0;input<p->inputs;++input){
   uint32_t bit=1u<<input;unsigned cost=0;
   for(unsigned i=0;i<p->vertex_count;++i)if(p->dependencies[p->vertex_ops[i]]==bit)++cost;
   if(cost>best && (all&~bit)){best=cost;selected=bit;}
  }
  p->reuse_mask=selected;p->reuse_inputs=best>=2;
 }
 if(getenv("N810_MBX_DUMP_VERTEX"))for(unsigned i=0;i<p->vertex_count;++i){
  unsigned k=p->vertex_ops[i];const struct mf_op *o=&p->ops[k];
  fprintf(stderr,"N810_MBX_VERTEX_OP index=%u opcode=%u mask=%u abs=%u neg=%u saturate=%u dependencies=%08x\n",k,o->opcode,o->mask,o->abs,o->neg,o->saturate,p->dependencies[k]);
 }
 mf_compile_all_native(p);
 mf_memory_inventory(p);
 p->result_cache=getenv("N810_MBX_VERTEX_CACHE")&&!strcmp(getenv("N810_MBX_VERTEX_CACHE"),"1");
 p->uniform_cache=p->result_cache||(getenv("N810_MBX_UNIFORM_CACHE")&&!strcmp(getenv("N810_MBX_UNIFORM_CACHE"),"1"));
 if(p->result_cache){
  p->cached_vertices=calloc(16,(p->inputs+p->outputs)*16);
  if(!p->cached_vertices)p->result_cache=false;
 }
 fprintf(stderr,"N810_MBX_VERTEX_PROGRAM ops=%u uniform_ops=%u reuse_inputs=%u mode=%s\n",p->count,p->uniform_count,p->reuse_inputs,p->verify?"verify":"fast");
 return p;
}
static uint64_t mf_wall_ns,mf_calls,mf_vertices;
static uint64_t mf_clock(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (uint64_t)t.tv_sec*1000000000+t.tv_nsec;}
static bool mf_run(struct mf_program *p,struct draw_vertex_shader *vs,const float (*input)[4],float (*output)[4],
 const void *constants[PIPE_MAX_CONSTANT_BUFFERS],const unsigned sizes[PIPE_MAX_CONSTANT_BUFFERS],unsigned count,unsigned istride,unsigned ostride)
{
 struct mbx_trace_stamp trace=mbx_trace_begin();
 uint64_t began=p->profile?mf_clock():0;
 if(p->constants&&(!constants[0]||sizes[0]<p->constants*16))return false;
 bool changed=!p->uniform_cache||!p->uniform_ready || (p->constants&&memcmp(p->r+MF_CONST,constants[0],p->constants*16));
 if(changed||!p->uniform_cache){
  if(p->constants)memcpy(p->r+MF_CONST,constants[0],p->constants*16);
  if(p->native_uniform_run)p->native_uniform_run(p);
  else for(unsigned i=0;i<p->uniform_count;++i)mf_execute(p,&p->ops[p->uniform_ops[i]]);
  p->uniform_ready=true;p->cache_valid=0;
 }else ++p->uniform_reused;
 bool clamp[32];
 uint32_t clamp_mask=0;
 for(unsigned i=0;i<p->outputs;++i)
  if((clamp[i]=vs->draw->rasterizer->clamp_vertex_color&&(vs->info.output_semantic_name[i]==TGSI_SEMANTIC_COLOR||vs->info.output_semantic_name[i]==TGSI_SEMANTIC_BCOLOR)))clamp_mask|=1u<<i;
 if(clamp_mask!=p->cached_clamp){p->cached_clamp=clamp_mask;p->cache_valid=0;}
 for(unsigned v=0;v<count;++v){
  float *cached=NULL;unsigned cache_slot=0;
  if(p->result_cache){
   /* Exact input bytes and draw constants form the key. Never approximate
    * positions, normals, colors, signed zero or NaN payloads. */
   uint32_t hash=2166136261u;
   for(unsigned i=0;i<p->inputs*4;++i){uint32_t word;memcpy(&word,(const char *)input+i*4,4);hash=(hash^word)*16777619u;}
   hash^=hash>>16;hash*=0x7feb352du;hash^=hash>>15;hash*=0x846ca68bu;hash^=hash>>16;
   cache_slot=hash&15;
   cached=p->cached_vertices+cache_slot*(p->inputs+p->outputs)*4;
   if((p->cache_valid&(1u<<cache_slot))&&!memcmp(cached,input,p->inputs*16)){
    memcpy(output,cached+p->inputs*4,p->outputs*16);++p->cache_hits;
    goto next_vertex;
   }
   ++p->cache_misses;
  }
  /* Fixed-size copies inline to native loads/stores instead of calling the
   * general libc memcpy once for every small vertex. */
  p->dirty_inputs=(!p->reuse_inputs||v==0)?UINT32_MAX:~p->reuse_mask;
  for(unsigned i=0;i<p->inputs;++i){
   float *dst=p->r+MF_INPUT+i*4;
   if(!p->reuse_inputs||v==0||!(p->reuse_mask&(1u<<i))||memcmp(dst,input[i],16)){
    p->dirty_inputs|=1u<<i;memcpy(dst,input[i],16);
   }
  }
  if(p->native_run)p->native_run(p);
  else for(unsigned i=0;i<p->vertex_count;++i){unsigned op=p->vertex_ops[i];if(!p->reuse_inputs||(p->dependencies[op]&p->dirty_inputs))mf_execute(p,&p->ops[op]);}
  for(unsigned i=0;i<p->outputs;++i){
   if(!clamp[i]&&p->output_contiguous[i]){memcpy(output[i],p->r+p->output[i][0],16);continue;}
   for(unsigned c=0;c<4;++c){float f=p->r[p->output[i][c]];output[i][c]=clamp[i]?SATURATE(f):f;}
  }
  if(cached){memcpy(cached,input,p->inputs*16);memcpy(cached+p->inputs*4,output,p->outputs*16);p->cache_valid|=1u<<cache_slot;}
 next_vertex:
  input=(const float (*)[4])((const char *)input+istride);output=(float (*)[4])((char *)output+ostride);
 }
 mbx_trace_end_n("vertex_shader",trace,count,4096);
 if(mbx_trace_enabled()&&++p->trace_calls%4096==0)
  fprintf(stderr,"N810_MBX_CACHE context=%p calls=%llu vertices_hit=%llu vertices_missed=%llu uniform_draws_reused=%llu vertex_cache=%u uniform_cache=%u input_reuse=%u\n",
   (void *)p,(unsigned long long)p->trace_calls,(unsigned long long)p->cache_hits,(unsigned long long)p->cache_misses,(unsigned long long)p->uniform_reused,p->result_cache,p->uniform_cache,p->reuse_inputs);
 if(!p->profile)return true;
 mf_wall_ns+=mf_clock()-began;mf_vertices+=count;++mf_calls;
 if((mf_calls&2047)==0)fprintf(stderr,"N810_MBX_VERTEX_PROFILE calls=%llu vertices=%llu wall_us=%llu\n",
    (unsigned long long)mf_calls,(unsigned long long)mf_vertices,(unsigned long long)(mf_wall_ns/1000));
 return true;
}
