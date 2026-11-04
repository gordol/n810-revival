/* SPDX-License-Identifier: MIT */
#include <math.h>
#include <stddef.h>
#include <stdint.h>
#ifndef COLOR_NAME
#error COLOR_NAME required
#endif
static double lattice(double x,double z)
{
    uint32_t a=(uint32_t)(int64_t)x,b=(uint32_t)(int64_t)z;
    uint32_t h=a*374761393u+b*668265263u+1013904223u;
    h=(h^(h>>13))*1274126177u;
    return (double)((h^(h>>16))&65535u)/65535.0;
}
static double noise(double x,double z,double scale)
{
    double ix,iz,u,v;
    x=x/scale;z=z/scale;ix=floor(x);iz=floor(z);u=x-ix;v=z-iz;
    u=u*u*(3.0-2.0*u);v=v*v*(3.0-2.0*v);
    return (lattice(ix,iz)*(1.0-u)+lattice(ix+1.0,iz)*u)*(1.0-v)+
           (lattice(ix,iz+1.0)*(1.0-u)+lattice(ix+1.0,iz+1.0)*u)*v;
}
static double smooth(double a,double b,double x)
{
    double t=(x-a)/(b-a);
    if(t>1.0)t=1.0;
    if(t<0.0)t=0.0;
    return t*t*(3.0-2.0*t);
}
void COLOR_NAME(const double *in,double *out,size_t n)
{
    static const double meadow_a[3]={87,99,66},meadow_b[3]={118,112,90};
    static const double wood_a[3]={23,47,34},wood_b[3]={43,76,48};
    static const double stone[3]={105,106,103},snow_rgb[3]={205,214,213};
    size_t k,i;
    for(k=0;k<n;k++) {
        double x=in[4*k],y=in[4*k+1],z=in[4*k+2],ny=in[4*k+3];
        double broad=noise(x,z,1800.0),fine=noise(x,z,190.0);
        double forest=(1.0-smooth(1500.0,2150.0,y))*smooth(.50,.90,ny);
        double canopy=noise(x,z,90.0),wood_scale=.78+.42*canopy;
        double rock=1.0-smooth(.65,.91,ny);
        double snowline=2850.0+(broad-.5)*280.0;
        double snow=smooth(snowline-160.0,snowline+240.0,y)*smooth(.40,.88,ny);
        double texture=.85+.20*fine+.07*noise(x,z,35.0);
        for(i=0;i<3;i++) {
            double meadow=meadow_a[i]+(meadow_b[i]-meadow_a[i])*broad;
            double wood=(wood_a[i]+(wood_b[i]-wood_a[i])*broad)*wood_scale;
            double base=meadow+(wood-meadow)*forest;
            base=base+(stone[i]-base)*(rock*.8);
            base=base+(snow_rgb[i]-base)*snow;
            out[3*k+i]=base*texture;
        }
    }
}
