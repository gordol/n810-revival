/* SPDX-License-Identifier: MIT */
#include "pixels.h"
#include <math.h>
#ifdef N810_ARM_VFP
#include <asm/hwcap.h>
#include <sys/auxv.h>
uint32_t cw_pixels_fpscr(void);
int pixels_shade_vfp(PIXEL_SHADE_ARGS);
void pixels_pack_vfp(PIXEL_PACK_ARGS);
#endif
int pixels_shade_soft(PIXEL_SHADE_ARGS);
void pixels_pack_soft(PIXEL_PACK_ARGS);

uint32_t cw_pixels_abi(void) { return 3; }
int cw_pixels_vfp(void)
{
#ifdef N810_ARM_VFP
    return (getauxval(AT_HWCAP)&HWCAP_VFP) && !(cw_pixels_fpscr()&0x03f79f00u);
#else
    return 0;
#endif
}
static int choose(int mode)
{
    if (mode<0 || mode>2) return -1;
    if (mode==1) return 1;
    if (cw_pixels_vfp()) return 2;
    return mode==2 ? -3 : 1;
}
static int range_ok(const void *p,size_t n,size_t alignment)
{
    uintptr_t a=(uintptr_t)p;
    return !n || (p && !(a%alignment) && a<=UINTPTR_MAX-n);
}
static int overlap(const void *a,size_t an,const void *b,size_t bn)
{
    uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;
    return an && bn && x<y+bn && y<x+an;
}
static int bounded(double v) { return isfinite(v) && fabs(v)<=1000000.0; }

int cw_pixels_shade(PIXEL_SHADE_ARGS,int mode)
{
    int selected=choose(mode);
    if (selected<0) return selected;
    if (!width || !height || ns>470400 || nv>65536 ||
        (uint64_t)width*height!=ns || start>ns || count>4096 || count>ns-start ||
        season<0 || season>3) return -1;
    if (!count) return selected;
    const void *inputs[]={ids,weights,haze,albedos,colors,lights,sky,fog,water_mask,water_xyz,camera,sun,moon};
    size_t lengths[]={ns*3*sizeof(uint32_t),ns*2*sizeof(float),ns*sizeof(float),
        ns*sizeof(uint32_t),nv*3*sizeof(double),nv*3*sizeof(double),3*sizeof(double),3*sizeof(double),
        ns*sizeof(uint8_t),ns*3*sizeof(double),3*sizeof(double),3*sizeof(double),3*sizeof(double)};
    size_t alignments[]={_Alignof(uint32_t),_Alignof(float),_Alignof(float),_Alignof(uint32_t),
        _Alignof(double),_Alignof(double),_Alignof(double),_Alignof(double),_Alignof(uint8_t),
        _Alignof(double),_Alignof(double),_Alignof(double),_Alignof(double)};
    size_t out_bytes=ns*3*sizeof(double);
    if (!range_ok(output,out_bytes,_Alignof(double))) return -1;
    for (size_t i=0;i<13;i++) {
        if (!range_ok(inputs[i],lengths[i],alignments[i]) ||
            overlap(output,out_bytes,inputs[i],lengths[i])) return -1;
    }
    if (!bounded(sunlight) || !bounded(moonlight)) return -2;
    for (size_t c=0;c<3;c++)
        if (!bounded(sky[c]) || !bounded(fog[c]) || !bounded(camera[c]) || !bounded(sun[c]) || !bounded(moon[c])) return -2;
    for (size_t i=start;i<start+count;i++) {
        if (water_mask[i]>1) return -1;
        if (ids[i*3]==UINT32_MAX) continue;
        if (water_mask[i]) for (size_t c=0;c<3;c++) if (!bounded(water_xyz[i*3+c])) return -2;
        for (size_t j=0;j<3;j++) {
            if (ids[i*3+j]>=nv) return -1;
            for (size_t ch=0;ch<3;ch++)
                if (!bounded(colors[ids[i*3+j]*3+ch]) ||
                    !bounded(lights[ids[i*3+j]*3+ch])) return -2;
        }
        if (!bounded(weights[i*2]) || !bounded(weights[i*2+1]) ||
            !isfinite(haze[i]) || haze[i]<0 || haze[i]>1 ||
            (albedos[i]!=UINT32_MAX && albedos[i]>UINT32_C(0xffffff))) return -2;
    }
    int status;
#ifdef N810_ARM_VFP
    if (selected==2) status=pixels_shade_vfp(PIXEL_SHADE_VALUES); else
#endif
        status=pixels_shade_soft(PIXEL_SHADE_VALUES);
    if (status<0) return status;
    return selected;
}

int cw_pixels_pack(PIXEL_PACK_ARGS,int mode)
{
    int selected=choose(mode);
    if (selected<0) return selected;
    if (ns>470400 || start>ns || count>4096 || count>ns-start) return -1;
    if (!count) return selected;
    size_t in_bytes=ns*3*sizeof(double),out_bytes=ns*sizeof(uint32_t);
    if (!range_ok(pixels,in_bytes,_Alignof(double)) ||
        !range_ok(output,out_bytes,_Alignof(uint32_t)) || overlap(pixels,in_bytes,output,out_bytes)) return -1;
    for (size_t i=start*3;i<(start+count)*3;i++) if (!isfinite(pixels[i])) return -2;
#ifdef N810_ARM_VFP
    if (selected==2) pixels_pack_vfp(PIXEL_PACK_VALUES); else
#endif
        pixels_pack_soft(PIXEL_PACK_VALUES);
    return selected;
}
