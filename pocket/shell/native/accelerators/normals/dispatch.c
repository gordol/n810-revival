/* SPDX-License-Identifier: MIT */
#include <math.h>
#include <stddef.h>
#include <stdint.h>
#ifdef N810_ARM_VFP
#include <asm/hwcap.h>
#include <sys/auxv.h>
uint32_t n810_normals_fpscr(void);
void normals_accum_vfp(const double *,const uint32_t *,double *,size_t);
void normals_finish_vfp(const double *,double *,unsigned char *,size_t);
#endif
void normals_accum_soft(const double *,const uint32_t *,double *,size_t);
void normals_finish_soft(const double *,double *,unsigned char *,size_t);
uint32_t n810_normals_abi(void){return 1;}
int n810_normals_vfp(void)
{
#ifdef N810_ARM_VFP
    return (getauxval(AT_HWCAP)&HWCAP_VFP) && !(n810_normals_fpscr()&0x03f79f00u);
#else
    return 0;
#endif
}
static int select_backend(int mode)
{
    if(mode<0 || mode>2)return -1;
    if(mode==1)return 1;
    if(n810_normals_vfp())return 2;
    return mode==2 ? -3 : 1;
}
static int overlap(const void *a,size_t na,const void *b,size_t nb)
{
    uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;
    if(na>UINTPTR_MAX-x || nb>UINTPTR_MAX-y)return 1;
    return x<y+nb && y<x+na;
}
int n810_normal_accumulate(const double *v,const uint32_t *t,double *s,
                          size_t nv,size_t nt,int mode)
{
    size_t i,j;int backend=select_backend(mode);
    if(backend<0)return backend;
    if(nv>65536 || nt>256)return -1;
    if(!nt)return backend;
    if(!nv || !v || !t || !s || ((uintptr_t)v|(uintptr_t)s)%_Alignof(double) ||
       (uintptr_t)t%_Alignof(uint32_t))return -1;
    if(overlap(v,3*nv*sizeof(double),s,3*nv*sizeof(double)) ||
       overlap(t,3*nt*sizeof(uint32_t),s,3*nv*sizeof(double)))return -1;
    for(i=0;i<3*nt;i++) {
        if(t[i]>=nv)return -1;
        for(j=0;j<3;j++) {
            double point=v[3*t[i]+j],sum=s[3*t[i]+j];
            if(!isfinite(point) || fabs(point)>1e12 ||
               !isfinite(sum) || fabs(sum)>1e40)return -2;
        }
    }
#ifdef N810_ARM_VFP
    if(backend==2)normals_accum_vfp(v,t,s,nt);
    else
#endif
        normals_accum_soft(v,t,s,nt);
    return backend;
}
int n810_normal_finish(const double *s,double *out,unsigned char *active,size_t n,int mode)
{
    size_t i;int backend=select_backend(mode);
    if(backend<0)return backend;
    if(n>256)return -1;
    if(!n)return backend;
    if(!s || !out || !active || ((uintptr_t)s|(uintptr_t)out)%_Alignof(double))return -1;
    if(overlap(s,3*n*sizeof(double),out,3*n*sizeof(double)) ||
       overlap(s,3*n*sizeof(double),active,n) ||
       overlap(out,3*n*sizeof(double),active,n))return -1;
    for(i=0;i<3*n;i++)if(!isfinite(s[i]) || fabs(s[i])>1e40)return -2;
#ifdef N810_ARM_VFP
    if(backend==2)normals_finish_vfp(s,out,active,n);
    else
#endif
        normals_finish_soft(s,out,active,n);
    return backend;
}
