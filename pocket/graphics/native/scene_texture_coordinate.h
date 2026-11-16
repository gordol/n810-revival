/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef POCKET_SCENE_TEXTURE_COORDINATE_H
#define POCKET_SCENE_TEXTURE_COORDINATE_H
#include <float.h>
#include <math.h>
/* Normalized float coordinates lose precision when a tile boundary is
 * divided by the full image extent and later multiplied back. Recover only
 * excursions within that arithmetic's error bound; never extend a sampler
 * border or accept geometry outside its source tile. */
static int scene_texture_coordinate(float coordinate,unsigned image,unsigned origin,
 unsigned extent,unsigned pitch,int flip,float *out){
 if(!out||!image||!extent||extent>pitch||origin>image||extent>image-origin||!isfinite(coordinate))return 0;
 double pixel=(double)coordinate*image-origin;
 double roundoff=2.0*FLT_EPSILON*image;
 if(pixel<0&&pixel>=-roundoff)pixel=0;
 if(pixel>extent&&pixel<=extent+roundoff)pixel=extent;
 if(pixel<0||pixel>extent)return 0;
 float normalized=(float)(pixel/pitch);
 *out=flip?1.0f-normalized:normalized;
 return 1;
}
#endif
