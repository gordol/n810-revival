/* SPDX-License-Identifier: MIT */
#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "../mesa/mbx_vgp_shader.h"
#include "../common/mbx_vgp_draw.h"
#include "../common/mbx_vgp_topology.h"
static void exact_read(FILE *f,void *p,size_t n){assert(fread(p,1,n,f)==n);}
static void execute(const struct mbx_vgp_shader *p,const float input[32][4],const float constant[128][4],float output[8][4])
{
 float temp[14][4]={{0}};
 for(unsigned i=0;i<p->count;++i){
  unsigned a=p->words[2*i],b=p->words[2*i+1],op=a&31,dst=b>>26,mask=(b>>22)&15;
  unsigned ns=op==3?3:(op==1||op==5||op==6)?1:2;
  float src[3][4]={{0}},value[4]={0};
  for(unsigned s=0;s<ns;++s){unsigned bank=(b>>(16+2*s))&3,index=(b>>(4*s))&15;
   if(bank==1)index|=((b>>12)&7)<<4;
   assert(bank<3);const float *from=bank==0?input[index]:bank==1?constant[index]:temp[index];
   for(unsigned j=0;j<4;++j){src[s][j]=from[(a>>(8+8*s+2*j))&3];if(a&(1u<<(5+s)))src[s][j]=-src[s][j];}
  }
  if(op==7||op==8){float sum=src[0][0]*src[1][0];for(unsigned j=1;j<(op==7?3:4);++j)sum+=src[0][j]*src[1][j];for(unsigned j=0;j<4;++j)value[j]=sum;}
  else for(unsigned j=0;j<4;++j)switch(op){
   case 1:value[j]=src[0][j];break;case 2:value[j]=src[0][j]+src[1][j];break;
   case 3:value[j]=src[0][j]*src[1][j]+src[2][j];break;case 4:value[j]=src[0][j]*src[1][j];break;
   case 5:value[j]=1.0f/src[0][0];break;case 6:value[j]=1.0f/sqrtf(src[0][0]);break;
   case 9:value[j]=fminf(src[0][j],src[1][j]);break;case 10:value[j]=fmaxf(src[0][j],src[1][j]);break;
   case 11:value[j]=src[0][j]<src[1][j];break;default:abort();
  }
  float *to=dst>=16?temp[dst-16]:output[dst];for(unsigned j=0;j<4;++j)if(mask&(1u<<j))to[j]=value[j];
 }
}
int main(int argc,char **argv)
{
 assert(argc==2);FILE *f=fopen(argv[1],"rb");assert(f);unsigned draws=0,vertices=0,values=0,max_program=0;
 unsigned frame_commands=60,frame_triangles=0,frame_input_bytes=0;
 uint64_t frame_encode_cpu_ns=0;
 uint32_t h[16];
 while(fread(h,1,sizeof(h),f)==sizeof(h)){
  assert(h[0]==0x3152474d&&h[1]==1&&h[8]<=4096&&h[9]<=32&&h[10]<=32&&h[11]<=16384&&h[12]<=16384);
  struct tgsi_token *tokens=malloc(h[11]*4);exact_read(f,tokens,h[11]*4);
  float constants[128][4]={{0}};assert(h[12]<=96*16);exact_read(f,constants,h[12]);
  unsigned *indices=malloc(h[5]*4),*lengths=malloc(h[7]*4);
  assert(indices&&lengths);exact_read(f,indices,h[5]*4);exact_read(f,lengths,h[7]*4);
  float *inputs=malloc(h[8]*h[9]*16),*reference=malloc(h[8]*h[10]*16);assert(inputs&&reference);
  exact_read(f,inputs,h[8]*h[9]*16);exact_read(f,reference,h[8]*h[10]*16);
  /* Reject a non-vertex processor without exposing a partial program. */
  if(!draws){
   struct tgsi_processor *processor=(struct tgsi_processor *)(tokens+1);
   unsigned saved=processor->Processor;
   struct mbx_vgp_shader rejected,before;
   memset(&rejected,0xa5,sizeof(rejected));before=rejected;
   processor->Processor=PIPE_SHADER_FRAGMENT;
   assert(!mbx_vgp_compile(tokens,&rejected));assert(!memcmp(&before,&rejected,sizeof(before)));
   processor->Processor=saved;
  }
  struct mbx_vgp_shader p;assert(mbx_vgp_compile(tokens,&p));if(p.count>max_program)max_program=p.count;
  memcpy(constants+96,p.immediate,p.immediates*16);constants[112][2]=1;constants[112][3]=1;constants[113][2]=-1;constants[113][3]=1;
  for(unsigned k=0;k<4;++k)constants[115][k]=1;
  if(getenv("N810_MBX_SHADER_FIXTURE_DIR")){
   char path[1024];int size=snprintf(path,sizeof(path),"%s/draw-%02u.bin",getenv("N810_MBX_SHADER_FIXTURE_DIR"),draws);
   assert(size>0&&(unsigned)size<sizeof(path));FILE *fixture=fopen(path,"wbx");assert(fixture);
   unsigned header[5]={0x32465356,p.count,p.inputs,p.constants,p.immediates};
   assert(fwrite(header,1,sizeof(header),fixture)==sizeof(header));
   assert(fwrite(p.words,8,p.count,fixture)==p.count);
   assert(fwrite(constants,16,p.constants,fixture)==p.constants);
   assert(fwrite(p.immediate,16,p.immediates,fixture)==p.immediates);assert(!fclose(fixture));
  }
  /* Encode every captured application draw, including full quad strips,
   * before accepting the bridge from Mesa's fetched vertices to the GPU. */
  unsigned short triangles[32768];unsigned index_count=0,command_count=0;
  assert(!mbx_vgp_topology(h[2],indices,h[5],lengths,h[7],h[8],triangles,32768,&index_count));
  if(index_count){
   struct mbx_command commands[16384];
   struct mbx_vgp_draw raw={.program=p.words,.uniforms=(const unsigned *)constants,
    .immediates=(const unsigned *)p.immediate,.vertices=(const unsigned *)inputs,
    .indices=triangles,.instructions=p.count,.uniform_count=p.constants,
    .immediate_count=p.immediates,.input_count=h[9],.vertex_count=h[8],
    .triangle_count=index_count/3,.smooth=!h[13],
    .viewport={0x43480000,0x43480000,0x43480000,0xc3480000,0x3f000000,0x3f000000}};
   assert(!mbx_vgp_draw_encode(&raw,commands,16384,&command_count));
   if(draws<21&&getenv("N810_MBX_VGP_BENCH")){
    struct timespec begin,end;assert(!clock_gettime(CLOCK_PROCESS_CPUTIME_ID,&begin));
    for(unsigned iteration=0;iteration<200;++iteration){
     assert(!mbx_vgp_topology(h[2],indices,h[5],lengths,h[7],h[8],triangles,32768,&index_count));
     assert(!mbx_vgp_draw_encode(&raw,commands,16384,&command_count));
    }
    assert(!clock_gettime(CLOCK_PROCESS_CPUTIME_ID,&end));
    frame_encode_cpu_ns+=((uint64_t)end.tv_sec*1000000000+end.tv_nsec)-((uint64_t)begin.tv_sec*1000000000+begin.tv_nsec);
   }
  }
  if(draws<21){frame_commands+=command_count;frame_triangles+=index_count/3;frame_input_bytes+=h[8]*h[9]*16;}
  if(draws==(getenv("N810_MBX_SHADER_FIXTURE_DRAW")?strtoul(getenv("N810_MBX_SHADER_FIXTURE_DRAW"),NULL,10):0)&&getenv("N810_MBX_SHADER_FIXTURE")){
   FILE *fixture=fopen(getenv("N810_MBX_SHADER_FIXTURE"),"wbx");assert(fixture);
   unsigned header[4]={0x31465356,p.count,p.inputs,116};
   assert(fwrite(header,1,sizeof(header),fixture)==sizeof(header));
   assert(fwrite(p.words,8,p.count,fixture)==p.count);
   assert(fwrite(constants,16,116,fixture)==116);assert(!fclose(fixture));
  }
  for(unsigned v=0;v<h[8];++v){float in[32][4]={{0}},out[8][4]={{0}};memcpy(in,inputs+v*h[9]*4,h[9]*16);execute(&p,in,constants,out);
   for(unsigned slot=0;slot<h[10];++slot){unsigned dest=p.output_temp[slot]==10?0:1;assert(p.output_temp[slot]==10||p.output_temp[slot]==11);
    for(unsigned c=0;c<4;++c){float expected=reference[(v*h[10]+slot)*4+c],got=out[dest][dest==1&&c<3?2-c:c];
     if(memcmp(&expected,&got,4)){fprintf(stderr,"MISMATCH draw=%u vertex=%u output=%u channel=%u reference=%a encoded=%a\n",draws,v,slot,c,expected,got);abort();}++values;}
   }++vertices;
  }
  free(indices);free(lengths);free(tokens);free(inputs);free(reference);++draws;
 }
 assert(feof(f)&&draws==32);fclose(f);
 printf("PASS captured standard gears: %u draws, %u vertices, %u exact output values, max %u VGP instructions. Local instruction semantics only; hardware precision/dispatch not claimed.\n",draws,vertices,values,max_program);
 printf("PASS full first-frame command assembly: %u triangles before hardware culling, %u commands, %u raw input bytes; no CPU transform/light in encoder.\n",frame_triangles,frame_commands,frame_input_bytes);
 if(getenv("N810_MBX_VGP_BENCH"))printf("ENCODER_ONLY cached_shader_warm_data_cpu_us_per_frame=%.3f iterations=200 GPU_jobs=0 full_app_FPS=unmeasured\n",frame_encode_cpu_ns/200000.0);
}
