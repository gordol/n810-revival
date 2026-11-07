/* SPDX-License-Identifier: MIT */
#include "../common/mbx_vgp_transform.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
/* Decode only fields used by this original program, independently of emitter. */
static void evaluate(const unsigned *w,const float *v,const float c[128][4],float pos[4],float color[4],float clip[2])
{
 float r[4]={0};
 for(unsigned i=0;i<8;++i){
  unsigned a=w[2*i],b=w[2*i+1],op=a&31,d=(b>>26)&31,mask=(b>>22)&15;
  unsigned bank=(b>>16)&3,idx=b&15;
  if(bank==1)idx|=((b>>12)&7)<<4;
  const float *src=bank==0?v:bank==1?c[idx]:r;
  float value[4];
  if(op==8){
   unsigned ci=((b>>4)&15)|(((b>>12)&7)<<4);assert(((b>>18)&3)==1);
   float sum=0;for(unsigned j=0;j<4;++j)sum+=src[j]*c[ci][j];
   for(unsigned j=0;j<4;++j)value[j]=sum;
  }else{assert(op==1);for(unsigned j=0;j<4;++j)value[j]=src[(a>>(8+2*j))&3];}
  float *out=d==19?r:d==0?pos:d==1?color:clip;
  assert(d==19||d==0||d==1||d==7);
  for(unsigned j=0;j<4;++j)if(mask&(1U<<j)){assert(d!=7||j<2);out[j]=value[j];}
 }
}
int main(void)
{
 unsigned w[16],saved[16];memset(w,0xa5,sizeof(w));memcpy(saved,w,sizeof(w));
 assert(mbx_vgp_transform(125,0,0,w,16)<0&&!memcmp(w,saved,sizeof(w)));
 assert(mbx_vgp_transform(0,128,0,w,16)<0&&!memcmp(w,saved,sizeof(w)));
 assert(mbx_vgp_transform(0,0,127,w,16)<0&&!memcmp(w,saved,sizeof(w)));
 assert(mbx_vgp_transform(0,0,0,w,15)<0&&!memcmp(w,saved,sizeof(w)));
 assert(mbx_vgp_transform(0,0,0,NULL,16)<0);
 for(unsigned trial=0;trial<10000;++trial){
  float c[128][4]={{0}},v[4],p[4]={0},color[4]={0},clip[2]={0},expected[4]={0};
  unsigned base=trial%12,ci=64+trial%32,plane=100+trial%26;
  for(unsigned j=0;j<4;++j){v[j]=(float)((int)((trial+3*j)%17)-8);c[ci][j]=(float)j;
   for(unsigned k=0;k<4;++k)c[base+j][k]=(float)((int)((trial+j+2*k)%7)-3);}
  c[plane][2]=1;c[plane][3]=1;c[plane+1][2]=-1;c[plane+1][3]=1;
  assert(mbx_vgp_transform(base,ci,plane,w,16)==8);
  evaluate(w,v,c,p,color,clip);
  for(unsigned j=0;j<4;++j){for(unsigned k=0;k<4;++k)expected[j]+=v[k]*c[base+j][k];assert(p[j]==expected[j]);}
  assert(color[0]==2&&color[1]==1&&color[2]==0&&color[3]==3);
  assert(clip[0]==p[2]+p[3]&&clip[1]==-p[2]+p[3]);
 }
 puts("PASS original VGP transform encoding:10000 matrices/colors/clip planes; atomic bounds rejection. Hardware execution not claimed.");
}
