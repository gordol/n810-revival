/* SPDX-License-Identifier: MIT
 * Conservative sampler-state selection, never CPU sampling/rasterization.
 * 1 means every admitted affine sprite fragment is magnified (or unit scale).
 * 0 means unknown/minifying: preserve the original mixed sampler and reject
 * it until the hardware path supports it. Never infer linear == nearest.
 */
#ifndef SG_AFFINE_FILTER_H
#define SG_AFFINE_FILTER_H
#include <math.h>
static int sg_affine_magnified(const float projection[16], const float model[16],
 const float xyuv[16], const int viewport[4], unsigned width, unsigned height)
{
 double pos[4][2];
 if(!width||!height||viewport[2]<=0||viewport[3]<=0)return 0;
 for(unsigned j=0;j<16;j++)if(!isfinite(projection[j])||!isfinite(model[j])||!isfinite(xyuv[j]))return 0;
 /* Strict affine restriction; perspective selection requires per-fragment LOD. */
 if(model[3]!=0||model[7]!=0||model[11]!=0||model[15]!=1||
    projection[3]!=0||projection[7]!=0||projection[11]!=0||projection[15]!=1)return 0;
 for(unsigned i=0;i<4;i++){
  double v[4]={xyuv[4*i],xyuv[4*i+1],0,1},eye[4]={0},clip[4]={0};
  for(unsigned r=0;r<4;r++)for(unsigned c=0;c<4;c++)eye[r]+=(double)model[c*4+r]*v[c];
  for(unsigned r=0;r<4;r++)for(unsigned c=0;c<4;c++)clip[r]+=(double)projection[c*4+r]*eye[c];
  pos[i][0]=clip[0]*viewport[2]*0.5;pos[i][1]=clip[1]*viewport[3]*0.5;
  if(!isfinite(pos[i][0])||!isfinite(pos[i][1]))return 0;
 }
 const unsigned tris[2][3]={{0,1,2},{0,3,1}};
 for(unsigned t=0;t<2;t++){
  unsigned a=tris[t][0],b=tris[t][1],c=tris[t][2];
  double dx1=pos[b][0]-pos[a][0],dy1=pos[b][1]-pos[a][1];
  double dx2=pos[c][0]-pos[a][0],dy2=pos[c][1]-pos[a][1];
  double det=dx1*dy2-dx2*dy1;
  if(!isfinite(det)||det==0)return 0;
  double du1=((double)xyuv[4*b+2]-xyuv[4*a+2])*width;
  double du2=((double)xyuv[4*c+2]-xyuv[4*a+2])*width;
  double dv1=((double)xyuv[4*b+3]-xyuv[4*a+3])*height;
  double dv2=((double)xyuv[4*c+3]-xyuv[4*a+3])*height;
  double x=fabs((du1*dy2-du2*dy1)/det)+fabs((dv1*dy2-dv2*dy1)/det);
  double y=fabs((du2*dx1-du1*dx2)/det)+fabs((dv2*dx1-dv1*dx2)/det);
  /* L1 bounds the usual Euclidean texture footprint conservatively. */
  if(!isfinite(x)||!isfinite(y)||x>1||y>1)return 0;
 }
 return 1;
}
#endif
