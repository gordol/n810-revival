/* SPDX-License-Identifier: MIT */
#include <stdint.h>
#include <stdio.h>
uint32_t n810_normals_abi(void);
int n810_normals_vfp(void);
int n810_normal_accumulate(const double *,const uint32_t *,double *,size_t,size_t,int);
int n810_normal_finish(const double *,double *,unsigned char *,size_t,int);
int main(void)
{
    double v[]={0,0,0,1,0,0,0,0,1},s[9]={0},out[9]={0};
    uint32_t t[]={0,1,2},bad[]={0,1,9};
    unsigned char active[3]={0};
    int ready=n810_normals_vfp(),selected=ready?2:1,i;
    if(n810_normals_abi()!=1)return 1;
    if(n810_normal_accumulate(v,bad,s,3,1,0)!=-1)return 2;
    for(i=0;i<9;i++)if(s[i]!=0)return 3;
    if(n810_normal_accumulate(v,t,s,3,1,0)!=selected)return 4;
    if(n810_normal_finish(s,out,active,3,0)!=selected)return 5;
    for(i=0;i<3;i++)if(!active[i] || out[3*i]!=0 || out[3*i+1]!=1 || out[3*i+2]!=0)return 6;
    if(n810_normal_finish(s,s,active,3,0)!=-1)return 7;
    if(!ready && n810_normal_finish(s,out,active,3,2)!=-3)return 8;
    printf("{\"status\":\"PASS\",\"vfp\":%d}\n",ready);
    return 0;
}
