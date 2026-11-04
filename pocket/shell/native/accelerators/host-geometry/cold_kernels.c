/* SPDX-License-Identifier: MIT */
#define RASTER_NAME cold_coverage
#include "kernels/coverage.c"
#define ACCUM_NAME cold_normals
#define FINISH_NAME cold_normalize
#include "kernels/normals.c"
#define COLOR_NAME cold_colors
#include "kernels/raster-finish.c"
void cold_materials(const uint32_t*t,const uint32_t*m,uint32_t*out,size_t n){
 for(size_t i=0;i<n;i++)for(size_t j=0;j<3;j++)out[t[3*i+j]]=m[i];
}
uint32_t cold_geometry_abi(void){return 1;}
/* CPython 3.12+ compensated three-term sum, without changing multiplication
 * order. Earlier reference interpreters select ordinary summation. */
static double sum3(double a,double b,double c,int compensated){
 double hi=0.0,lo=0.0,x[3]={a,b,c};
 for(size_t j=0;j<3;j++){
  double t=hi+x[j];
  if(compensated)lo+=fabs(hi)>=fabs(x[j])?(hi-t)+x[j]:(x[j]-t)+hi;
  hi=t;
 }
 return compensated?hi+lo:hi;
}
void cold_project(const double*restrict v,const double*restrict p,double*restrict out,size_t n,int compensated){
 for(size_t i=0;i<n;i++){
  double x=v[3*i]-p[0],y=v[3*i+1]-p[1],z=v[3*i+2]-p[2];
  double d=sum3(x*p[12],y*p[13],z*p[14],compensated);
  double scale=p[3]&&fabs(d)>1e-9?p[3]/d:1.0;
  out[3*i]=sum3(x*p[6],y*p[7],z*p[8],compensated)*scale/p[4]+.5;
  out[3*i+1]=sum3(x*p[9],y*p[10],z*p[11],compensated)*scale/p[5]+.5;
  out[3*i+2]=d;
 }
}
