/* SPDX-License-Identifier: MIT */
#include <math.h>
#include <stddef.h>
#include <stdint.h>
#ifdef N810_ARM_VFP
#include <asm/hwcap.h>
#include <sys/auxv.h>
uint32_t n810_finish_fpscr(void);
void finish_vfp(const double *,double *,size_t);
#endif
void finish_soft(const double *,double *,size_t);
uint32_t n810_finish_abi(void){return 1;}
int n810_finish_vfp(void)
{
#ifdef N810_ARM_VFP
    return (getauxval(AT_HWCAP)&HWCAP_VFP) && !(n810_finish_fpscr()&0x03f79f00u);
#else
    return 0;
#endif
}
int n810_ground_color(const double *in,double *out,size_t n,int mode)
{
    size_t i;uintptr_t x=(uintptr_t)in,y=(uintptr_t)out;
    int selected=mode==1?1:n810_finish_vfp()?2:1;
    if(mode<0 || mode>2 || n>128)return -1;
    if(mode==2 && selected!=2)return -3;
    if(!n)return selected;
    if(!in || !out || x%_Alignof(double) || y%_Alignof(double))return -1;
    if(x>UINTPTR_MAX-4*n*sizeof(double) || y>UINTPTR_MAX-3*n*sizeof(double) ||
       (x<y+3*n*sizeof(double) && y<x+4*n*sizeof(double)))return -1;
    for(i=0;i<4*n;i++)if(!isfinite(in[i]) || fabs(in[i])>1e12)return -2;
#ifdef N810_ARM_VFP
    if(selected==2)finish_vfp(in,out,n);else finish_soft(in,out,n);
#else
    finish_soft(in,out,n);
#endif
    return selected;
}
