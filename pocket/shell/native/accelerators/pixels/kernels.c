/* SPDX-License-Identifier: MIT
 * Exact scalar pixel interpolation after canonical Python vertex lighting.
 * No projection, visibility, scene/model changes, Python callbacks or I/O.
 * Build with contraction and fast math disabled; ARM dispatch is separate.
 */
#include "pixels.h"
#include <math.h>

#ifndef SHADE_NAME
#define SHADE_NAME pixels_shade_soft
#endif
#ifndef PACK_NAME
#define PACK_NAME pixels_pack_soft
#endif

/* Ordinary Python sum starts with integer zero and visits x,y,z in order.
 * Origin/point bounds make every all-integer delta square/sum exact in double;
 * a floating delta follows the same left fold. The adapter declines water
 * when the caller's Python instead uses compensated summation.
 */
static int unit(double *v)
{
    double squared=0.0;
    for (size_t j=0;j<3;j++) squared+=v[j]*v[j];
    double size=sqrt(squared);
    if (size<1e-12) return -2;
    double inverse=1.0/size;
    for (size_t j=0;j<3;j++) v[j]=v[j]*inverse;
    return 0;
}
static int water_half(const double *point,const double *camera,const double *light,double *half)
{
    double view[3];
    for (size_t j=0;j<3;j++) view[j]=camera[j]-point[j];
    if (unit(view)) return -2;
    for (size_t j=0;j<3;j++) half[j]=view[j]+light[j];
    return unit(half);
}

int SHADE_NAME(PIXEL_SHADE_ARGS)
{
    (void)nv; (void)ns;
    const double *light=moonlight!=0.0?moon:sun;
    /* Unit's near-zero exception is checked for the whole batch before any
     * output write, in the same selected arithmetic mode as the actual shade.
     */
    for (size_t i=start;i<start+count;i++) if (ids[i*3]!=UINT32_MAX && water_mask[i]) {
        double half[3];
        if (water_half(water_xyz+i*3,camera,light,half)) return -2;
    }
    double exposure=1.0+.65*(1.0-sunlight);
    static const double winter[3]={205,214,213};
    static const double autumn[3]={1.10,.95,.88};
    static const double spring[3]={.94,1.08,.98};
    for (size_t i=start;i<start+count;i++) {
        if (ids[i*3]==UINT32_MAX) {
            double gradient=.72+.28*(i/width)/(height>1 ? height-1 : 1);
            for (size_t c=0;c<3;c++) output[i*3+c]=sky[c]*gradient;
            continue;
        }
        size_t a=ids[i*3],b=ids[i*3+1],c=ids[i*3+2];
        double wa=weights[i*2],wb=weights[i*2+1],wc=1.0-wa-wb;
        double glint=0.0,ripple=0.0;
        static const double water_base[3]={7,16,20};
        if (water_mask[i]) {
            const double *point=water_xyz+i*3;double half[3];
            (void)water_half(point,camera,light,half);
            glint=pow(half[1]>0.0?half[1]:0.0,48.0)*(moonlight*180.0+sunlight*90.0);
            ripple=.90+.1*sin(point[2]*.13+point[0]*.09);
        }
        for (size_t ch=0;ch<3;ch++) {
            double color=colors[a*3+ch]*wa+colors[b*3+ch]*wb+colors[c*3+ch]*wc;
            if (albedos[i]!=UINT32_MAX) {
                double albedo=(albedos[i]>>(16-ch*8))&255;
                if (season==1) albedo=albedo+(winter[ch]-albedo)*.38;
                else if (season==2) albedo=albedo*autumn[ch];
                else if (season==3) albedo=albedo*spring[ch];
                color=albedo*(lights[a*3+ch]*wa+lights[b*3+ch]*wb+lights[c*3+ch]*wc);
            }
            if (water_mask[i]) color=(sky[ch]*.6+water_base[ch]+glint)*ripple;
            double exposed=color*exposure;
            output[i*3+ch]=exposed+(fog[ch]-exposed)*haze[i];
        }
    }
    return 0;
}

void PACK_NAME(const double *pixels,uint32_t *output,size_t ns,size_t start,size_t count)
{
    (void)ns;
    for (size_t i=start;i<start+count;i++) {
        uint32_t color=0;
        for (size_t c=0;c<3;c++) {
            double v=pixels[i*3+c];
            uint32_t channel=v<=0 ? 0 : v>=255 ? 255 : (uint32_t)v;
            color|=channel<<(16-c*8);
        }
        output[i]=color;
    }
}
