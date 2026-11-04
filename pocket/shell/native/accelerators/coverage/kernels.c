/* SPDX-License-Identifier: MIT */
#include <math.h>
#include <stddef.h>
#include <stdint.h>
#ifndef RASTER_NAME
#error RASTER_NAME required
#endif
/* State: triangle, prepared, x,y,x0,x1,y1, ax,ay,az,bx,by,bz,cx,cy,cz,area,
 * tested,updated,prepared_count,degenerate,empty,inside,unused,
 * width,height,nv,nt,perspective,unused,done,version. */
static double min3(double a,double b,double c){double v=a;if(b<v)v=b;if(c<v)v=c;return v;}
static double max3(double a,double b,double c){double v=a;if(b>v)v=b;if(c>v)v=c;return v;}
int RASTER_NAME(const double *p,const uint32_t *t,float *depths,uint32_t *ids,
                float *weights,double *s,size_t nt,size_t width,size_t height,
                int perspective,size_t triangle_budget,size_t pixel_budget)
{
    size_t triangles=0,pixels=0;
    while((size_t)s[0]<nt && triangles<triangle_budget && pixels<pixel_budget) {
        size_t k=(size_t)s[0];
        if(!s[1]) {
            uint32_t a=t[3*k],b=t[3*k+1],c=t[3*k+2];
            double ax=p[3*a]*(double)width,ay=p[3*a+1]*(double)height,az=p[3*a+2];
            double bx=p[3*b]*(double)width,by=p[3*b+1]*(double)height,bz=p[3*b+2];
            double cx=p[3*c]*(double)width,cy=p[3*c+1]*(double)height,cz=p[3*c+2];
            double area=(bx-ax)*(cy-ay)-(by-ay)*(cx-ax),x0,x1,y0,y1;
            s[19]+=1.0;
            if(fabs(area)<1e-8) {s[20]+=1.0;s[0]+=1.0;triangles++;continue;}
            x0=floor(min3(ax,bx,cx));if(x0<0.0)x0=0.0;
            x1=ceil(max3(ax,bx,cx));if(x1>(double)(width-1))x1=(double)(width-1);
            y0=floor(min3(ay,by,cy));if(y0<0.0)y0=0.0;
            y1=ceil(max3(ay,by,cy));if(y1>(double)(height-1))y1=(double)(height-1);
            if(x0>x1 || y0>y1) {s[21]+=1.0;s[0]+=1.0;triangles++;continue;}
            s[2]=x0;s[3]=y0;s[4]=x0;s[5]=x1;s[6]=y1;
            s[7]=ax;s[8]=ay;s[9]=az;s[10]=bx;s[11]=by;s[12]=bz;
            s[13]=cx;s[14]=cy;s[15]=cz;s[16]=area;s[1]=1.0;
        }
        while(s[3]<=s[6] && pixels<pixel_budget) {
            size_t x=(size_t)s[2],y=(size_t)s[3],index=y*width+x;
            double px=(double)x+0.5,py=(double)y+0.5;
            /* Preserve the reference expression/operation order. */
            double w1=((s[10]-px)*(s[14]-py)-(s[11]-py)*(s[13]-px))/s[16];
            double w2=((s[13]-px)*(s[8]-py)-(s[14]-py)*(s[7]-px))/s[16];
            double w3=1.0-w1-w2;
            if(!(w1 < -1e-8 || w2 < -1e-8 || w3 < -1e-8)) {
                double depth;
                s[22]+=1.0;
                if(perspective) {
                    double denominator=w1/s[9]+w2/s[12]+w3/s[15];
                    if(denominator==0.0)return -4;
                    depth=1.0/denominator;
                    w1=w1*depth/s[9];w2=w2*depth/s[12];
                } else depth=w1*s[9]+w2*s[12]+w3*s[15];
                if(depth<(double)depths[index]) {
                    depths[index]=(float)depth;
                    ids[3*index]=t[3*k];ids[3*index+1]=t[3*k+1];ids[3*index+2]=t[3*k+2];
                    weights[2*index]=(float)w1;weights[2*index+1]=(float)w2;
                    s[18]+=1.0;
                }
            }
            s[17]+=1.0;pixels++;
            s[2]+=1.0;
            if(s[2]>s[5]){s[2]=s[4];s[3]+=1.0;}
        }
        if(s[3]>s[6]){s[0]+=1.0;s[1]=0.0;triangles++;}
    }
    if((size_t)s[0]==nt)s[30]=1.0;
    return 0;
}
