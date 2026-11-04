/* SPDX-License-Identifier: MIT */
#include <stdint.h>
#include <stdio.h>
#include <math.h>
uint32_t n810_coverage_abi(void);
int n810_coverage_vfp(void);
int n810_coverage_step(const double *,const uint32_t *,float *,uint32_t *,float *,double *,
                      size_t,size_t,size_t,size_t,int,size_t,size_t,int);
int main(void)
{
    double p[]={.1,.1,1,.9,.1,1,.1,.9,1},s[32]={0};
    uint32_t t[]={0,1,2},ids[192];float d[64],w[128]={0};
    int i,calls=0,selected=n810_coverage_vfp()?2:1;
    for(i=0;i<64;i++)d[i]=INFINITY;
    for(i=0;i<192;i++)ids[i]=UINT32_MAX;
    if(n810_coverage_abi()!=1)return 1;
    while(!s[30]) {
        if(n810_coverage_step(p,t,d,ids,w,s,3,1,8,8,1,1,3,0)!=selected)return 2;
        if(++calls>100)return 3;
    }
    if(s[0]!=1 || s[17]!=64 || s[18]<=0 || calls<2)return 4;
    if(n810_coverage_step(p,t,d,ids,w,s,3,1,8,8,1,1,4097,0)!=-1)return 5;
    if(!n810_coverage_vfp() && n810_coverage_step(p,t,d,ids,w,s,3,1,8,8,1,1,3,2)!=-3)return 6;
    {
        double empty[32]={0};
        if(n810_coverage_step((const double *)(uintptr_t)1,(const uint32_t *)(uintptr_t)1,
            d,ids,w,empty,0,0,8,8,0,1,3,0)!=selected || !empty[30])return 7;
    }
    printf("{\"status\":\"PASS\",\"vfp\":%d,\"steps\":%d}\n",n810_coverage_vfp(),calls);
    return 0;
}
