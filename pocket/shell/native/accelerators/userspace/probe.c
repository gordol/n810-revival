/* SPDX-License-Identifier: MIT */
#include <float.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
uint32_t n810_compute_abi(void);
int n810_compute_vfp(void);
int n810_project(const double *,const double *,double *,size_t,int);
enum { N=257 };
static double camera[15], points[N*3], soft[N*3+2], accelerated[N*3+2];
int main(void)
{
    size_t i, frame, words=0;
    int available=n810_compute_vfp();
    if (n810_compute_abi()!=1 || n810_project(NULL,NULL,NULL,0,0)!=1 ||
        n810_project(NULL,NULL,NULL,65537,0)!=-1)
        return 2;
    for (i=0;i<N*3;++i) points[i]=((int)(i%127)-63)*0.125;
    for (frame=0;frame<32;++frame) {
        for (i=0;i<15;++i) camera[i]=((int)((i+frame)%19)-9)*0.0625;
        camera[12]=3.2;camera[13]=2.3;camera[14]=frame%2?1.25:0;
        soft[0]=soft[N*3+1]=accelerated[0]=accelerated[N*3+1]=1234567;
        if(n810_project(camera,points,soft+1,N,1)!=1 ||
           n810_project(camera,points,accelerated+1,N,0)!=(available?2:1) ||
           memcmp(soft,accelerated,sizeof soft))
            return 3;
        if(soft[0]!=1234567 || soft[N*3+1]!=1234567)
            return 4;
        for(i=0;i<N;++i) {
            size_t j;long double p[3],d=0,r=0,v=0,s=1,reference[3];
            for(j=0;j<3;++j) p[j]=(long double)points[3*i+j]-camera[j];
            for(j=0;j<3;++j) {d+=p[j]*camera[9+j];r+=p[j]*camera[3+j];v+=p[j]*camera[6+j];}
            if(camera[14] && fabsl(d)>1e-9L)s=camera[14]/d;
            reference[0]=r*s/camera[12]+.5L;reference[1]=v*s/camera[13]+.5L;reference[2]=d;
            for(j=0;j<3;++j)
                if(fabsl((long double)soft[1+3*i+j]-reference[j])>1e-11L*(1+fabsl(reference[j])))
                    return 5;
        }
        words+=N*3;
    }
    if(n810_project(camera,points,points,N,0)!=-1 ||
       n810_project(camera,points,accelerated,1,7)!=-1)
        return 6;
    camera[12]=0;
    if(n810_project(camera,points,accelerated,1,0)!=-2)return 7;
    camera[12]=3.2;points[0]=NAN;
    if(n810_project(camera,points,accelerated,1,0)!=-2)return 8;
    points[0]=0;
    if(!available && n810_project(camera,points,accelerated,1,2)!=-3)return 9;
    memset(camera,0,sizeof camera);camera[11]=1;camera[12]=camera[13]=camera[14]=1;
    points[0]=0;points[1]=0;points[2]=1e-9;
    if(n810_project(camera,points,accelerated,1,0)!=-4)return 10;
    printf("{\"status\":\"PASS\",\"vfp_used\":%s,\"frames\":32,\"output_words\":%zu,"
           "\"reference_mantissa_bits\":%d,\"soft_native_bitwise_equal\":true,"
           "\"invalid_inputs_rejected\":true,\"threshold_fallback\":true}\n",
           available?"true":"false",words,LDBL_MANT_DIG);
    return 0;
}
