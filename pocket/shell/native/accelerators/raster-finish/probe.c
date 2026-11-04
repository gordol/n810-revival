/* SPDX-License-Identifier: MIT */
#include <stdio.h>
#include <stdint.h>
uint32_t n810_finish_abi(void);
int n810_finish_vfp(void);
int n810_ground_color(const double *,double *,size_t,int);
int main(void)
{
    double in[8]={100,1800,-23,.9,-23,2900,137,.78},out[6]={0};
    int vfp=n810_finish_vfp(),mode=vfp?2:1;
    if(n810_finish_abi()!=1 || n810_ground_color(in,out,2,mode)!=mode)return 1;
    if(out[0]<0 || out[0]>255 || out[5]<0 || out[5]>255)return 2;
    if(n810_ground_color(in,in,2,mode)!=-1)return 3;
    if(n810_ground_color(in,out,129,mode)!=-1)return 4;
    if(n810_ground_color(0,0,0,mode)!=mode)return 5;
    printf("{\"status\":\"PASS\",\"vfp\":%s}\n",vfp?"true":"false");
    return 0;
}
