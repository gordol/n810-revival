/* SPDX-License-Identifier: MIT */
#include <math.h>
#include <stddef.h>
#include <stdint.h>
#ifdef N810_ARM_VFP
#include <asm/hwcap.h>
#include <sys/auxv.h>
uint32_t n810_coverage_fpscr(void);
int coverage_vfp(const double *,const uint32_t *,float *,uint32_t *,float *,double *,
                 size_t,size_t,size_t,int,size_t,size_t);
#endif
int coverage_soft(const double *,const uint32_t *,float *,uint32_t *,float *,double *,
                  size_t,size_t,size_t,int,size_t,size_t);
uint32_t n810_coverage_abi(void){return 1;}
int n810_coverage_vfp(void)
{
#ifdef N810_ARM_VFP
    return (getauxval(AT_HWCAP)&HWCAP_VFP) && !(n810_coverage_fpscr()&0x03f79f00u);
#else
    return 0;
#endif
}
static int overlap(const void *a,size_t na,const void *b,size_t nb)
{
    uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;
    if(na>UINTPTR_MAX-x || nb>UINTPTR_MAX-y)return 1;
    return x<y+nb && y<x+na;
}
static int integer(double v,double low,double high){return isfinite(v) && v>=low && v<=high && floor(v)==v;}
int n810_coverage_step(const double *p,const uint32_t *t,float *depths,uint32_t *ids,
                      float *weights,double *s,size_t nv,size_t nt,size_t width,size_t height,
                      int perspective,size_t tb,size_t pb,int mode)
{
    size_t i,j,np;int selected,status;
    const void *buffers[6]={p,t,depths,ids,weights,s};size_t bytes[6];
    if(mode<0 || mode>2)return -1;
    selected=mode==1?1:n810_coverage_vfp()?2:1;
    if(mode==2 && selected!=2)return -3;
    if(nv>65536 || nt>131072 || !width || !height || width>1024 || height>1024 ||
       width*height>470400 || !tb || tb>64 || !pb || pb>4096 ||
       (perspective!=0 && perspective!=1))return -1;
    np=width*height;
    if((nv && !p) || (nt && (!t || !nv)) || !depths || !ids || !weights || !s)return -1;
    if((nv && (uintptr_t)p%_Alignof(double)) || (uintptr_t)s%_Alignof(double) ||
       (nt && (uintptr_t)t%_Alignof(uint32_t)) ||
       ((uintptr_t)depths|(uintptr_t)ids|(uintptr_t)weights)%_Alignof(uint32_t))return -1;
    bytes[0]=3*nv*sizeof(double);bytes[1]=3*nt*sizeof(uint32_t);
    bytes[2]=np*sizeof(float);bytes[3]=3*np*sizeof(uint32_t);
    bytes[4]=2*np*sizeof(float);bytes[5]=32*sizeof(double);
    for(i=0;i<6;i++)for(j=i+1;j<6;j++)if(bytes[i] && bytes[j] && overlap(buffers[i],bytes[i],buffers[j],bytes[j]))return -1;
    if(s[31]==0.0) {
        for(i=0;i<32;i++)if(s[i]!=0.0)return -1;
        for(i=0;i<3*nv;i++)if(!isfinite(p[i]) || fabs(p[i])>1e12)return -2;
        for(i=0;i<3*nt;i++)if(t[i]>=nv || (perspective && p[3*t[i]+2]==0.0))return -2;
        s[24]=(double)width;s[25]=(double)height;s[26]=(double)nv;s[27]=(double)nt;s[28]=(double)perspective;s[31]=1.0;
    } else {
        if(s[31]!=1.0 || s[24]!=(double)width || s[25]!=(double)height || s[26]!=(double)nv ||
           s[27]!=(double)nt || s[28]!=(double)perspective ||
           !integer(s[0],0.0,(double)nt) || !integer(s[1],0.0,1.0) || !integer(s[30],0.0,1.0))return -1;
        if(s[1] && s[0]>=(double)nt)return -1;
        if(s[1]) {
            if(!integer(s[4],0.0,(double)(width-1)) || !integer(s[5],s[4],(double)(width-1)) ||
               !integer(s[2],s[4],s[5]) || !integer(s[6],0.0,(double)(height-1)) ||
               !integer(s[3],0.0,s[6]) || !isfinite(s[16]) || fabs(s[16])<1e-8)return -1;
            for(i=7;i<16;i++)if(!isfinite(s[i]) || fabs(s[i])>2e15)return -1;
            if(perspective && (s[9]==0.0 || s[12]==0.0 || s[15]==0.0))return -2;
        }
        if(s[30] && s[0]!=(double)nt)return -1;
    }
#ifdef N810_ARM_VFP
    status=selected==2?coverage_vfp(p,t,depths,ids,weights,s,nt,width,height,perspective,tb,pb):
                      coverage_soft(p,t,depths,ids,weights,s,nt,width,height,perspective,tb,pb);
#else
    status=coverage_soft(p,t,depths,ids,weights,s,nt,width,height,perspective,tb,pb);
#endif
    return status?status:selected;
}
