/* SPDX-License-Identifier: MIT */
#include <math.h>
#include <stddef.h>
#include <stdint.h>
#ifndef ACCUM_NAME
#error ACCUM_NAME is required
#endif
#ifndef FINISH_NAME
#error FINISH_NAME is required
#endif
void ACCUM_NAME(const double *v, const uint32_t *t, double *s, size_t n)
{
    size_t i, j;
    for (i=0;i<n;i++) {
        uint32_t a=t[3*i], b=t[3*i+1], c=t[3*i+2];
        double ux=v[3*b]-v[3*a], uy=v[3*b+1]-v[3*a+1], uz=v[3*b+2]-v[3*a+2];
        double vx=v[3*c]-v[3*a], vy=v[3*c+1]-v[3*a+1], vz=v[3*c+2]-v[3*a+2];
        double nx=uy*vz-uz*vy, ny=uz*vx-ux*vz, nz=ux*vy-uy*vx;
        if (ny<0.0) {nx=nx*-1.0;ny=ny*-1.0;nz=nz*-1.0;}
        for (j=0;j<3;j++) {
            size_t k=3*t[3*i+j];
            s[k]=s[k]+nx;s[k+1]=s[k+1]+ny;s[k+2]=s[k+2]+nz;
        }
    }
}
void FINISH_NAME(const double *s, double *out, unsigned char *active, size_t n)
{
    size_t i;
    for (i=0;i<n;i++) {
        double x=s[3*i], y=s[3*i+1], z=s[3*i+2], square=0.0;
        square+=x*x;square+=y*y;square+=z*z;
        active[i]=(unsigned char)(square>1e-12);
        if (active[i]) {
            double scale=1.0/sqrt(square);
            out[3*i]=x*scale;out[3*i+1]=y*scale;out[3*i+2]=z*scale;
        } else {out[3*i]=0.0;out[3*i+1]=1.0;out[3*i+2]=0.0;}
    }
}
