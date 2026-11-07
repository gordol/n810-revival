/* Test-only numerical interpreter, independent of dependency propagation. */
#include <math.h>
static void reference_color(const struct mbx_vgp_draw *d,unsigned vertex,float color[4])
{
 float temp[14][4]={{0}},constant[128][4]={{0}},input[2][4]={{0}};
 unsigned i,j,s;
 memcpy(input,d->vertices+vertex*4*d->input_count,16*d->input_count);
 if(d->uniform_count)memcpy(constant,d->uniforms,16*d->uniform_count);
 if(d->immediate_count)memcpy(constant+96,d->immediates,16*d->immediate_count);
 constant[112][2]=constant[112][3]=constant[113][3]=1;constant[113][2]=-1;
 for(j=0;j<4;++j)constant[115][j]=1;
 for(i=0;i<d->instructions;++i){
  unsigned a=d->program[2*i],b=d->program[2*i+1],op=a&31,dst=b>>26,mask=(b>>22)&15;
  unsigned ns=op==3?3:(op==1||op==5||op==6)?1:2;
  float src[3][4]={{0}},v[4]={0};
  for(s=0;s<ns;++s){
   unsigned bank=(b>>(16+2*s))&3,index=(b>>(4*s))&15;
   const float *p;
   if(bank==1)index|=((b>>12)&7)<<4;
   p=bank==0?input[index]:bank==1?constant[index]:temp[index];
   for(j=0;j<4;++j){src[s][j]=p[(a>>(8+8*s+2*j))&3];if(a&(1U<<(5+s)))src[s][j]=-src[s][j];}
  }
  if(op==7||op==8){
   float sum=src[0][0]*src[1][0];
   for(j=1;j<(op==7?3U:4U);++j)sum+=src[0][j]*src[1][j];
   for(j=0;j<4;++j)v[j]=sum;
  }else for(j=0;j<4;++j)switch(op){
   case 1:v[j]=src[0][j];break;case 2:v[j]=src[0][j]+src[1][j];break;
   case 3:v[j]=src[0][j]*src[1][j]+src[2][j];break;case 4:v[j]=src[0][j]*src[1][j];break;
   case 5:v[j]=1/src[0][0];break;case 6:v[j]=1/sqrtf(src[0][0]);break;
   case 9:v[j]=fminf(src[0][j],src[1][j]);break;case 10:v[j]=fmaxf(src[0][j],src[1][j]);break;
   case 11:v[j]=src[0][j]<src[1][j];break;case 12:v[j]=src[0][j]>=src[1][j];break;
   default:assert(0);
  }
  if(dst==1||dst>=16)for(j=0;j<4;++j)if(mask&(1U<<j)){
   if(dst==1)color[j]=v[j];else temp[dst-16][j]=v[j];
  }
 }
}
static int reference_uniform_color(const struct mbx_vgp_draw *d)
{
 float first[4],next[4];unsigned i;
 reference_color(d,0,first);
 for(i=1;i<d->vertex_count;++i){reference_color(d,i,next);if(memcmp(first,next,sizeof(first)))return 0;}
 return 1;
}
