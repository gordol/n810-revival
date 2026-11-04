/* SPDX-License-Identifier: MIT */
#ifndef CW_PIXELS_H
#define CW_PIXELS_H
#include <stddef.h>
#include <stdint.h>

/* All buffers remain owned by the caller for the duration of each call.
 * Modes: 0 auto, 1 soft, 2 VFP required. Success returns the selected mode.
 * -1 invalid shape/range/alias, -2 invalid numeric domain, -3 unavailable VFP.
 * The dispatcher validates the complete requested batch before output writes.
 */
#define PIXEL_SHADE_ARGS const uint32_t *ids,const float *weights,const float *haze, \
 const uint32_t *albedos,const double *colors,const double *lights, \
 size_t nv,size_t ns,size_t start,size_t count,uint32_t width,uint32_t height, \
 double sunlight,const double *sky,const double *fog,int season, \
 const uint8_t *water_mask,const double *water_xyz,const double *camera, \
 const double *sun,const double *moon,double moonlight,double *output
#define PIXEL_SHADE_VALUES ids,weights,haze,albedos,colors,lights,nv,ns,start,count,width,height,sunlight,sky,fog,season,water_mask,water_xyz,camera,sun,moon,moonlight,output
#define PIXEL_PACK_ARGS const double *pixels,uint32_t *output,size_t ns,size_t start,size_t count
#define PIXEL_PACK_VALUES pixels,output,ns,start,count

uint32_t cw_pixels_abi(void);
int cw_pixels_vfp(void);
int cw_pixels_shade(PIXEL_SHADE_ARGS,int mode);
int cw_pixels_pack(PIXEL_PACK_ARGS,int mode);
#endif
