/* SPDX-License-Identifier: MIT */
#ifndef MBX_SURFACE_CHECKPOINT_H
#define MBX_SURFACE_CHECKPOINT_H
#include "draw/mbx_vgp_wire.h"
#include <stdint.h>
#include <string.h>
/* Preserve a completed native BGRA framebuffer verbatim. The GPU's existing
 * background texture plane supplies it beneath the next bounded draw batch.
 * This is storage/transport, not CPU compositing or rasterization. */
static int mbx_surface_checkpoint(void *wire,unsigned capacity,const void *bgra,
 unsigned bytes,unsigned stride,unsigned width,unsigned height)
{
 const unsigned payload=240U*320U*4U,needed=80U+payload;
 uintptr_t dst=(uintptr_t)wire,src=(uintptr_t)bgra;
 if(!wire||!bgra||width!=240||height!=320||capacity<needed||stride<960||
    bytes<960||319U>(bytes-960U)/stride||dst>UINTPTR_MAX-capacity||src>UINTPTR_MAX-bytes||
    !(dst+capacity<=src||src+bytes<=dst))return -22;
 struct mbx_vgp_wire_frame f={.magic=MBX_VGP_WIRE_MAGIC,.version=10,
  .bytes=needed,.width=240,.height=320,.clear_depth=0x3f800000U};
 unsigned table[8]={1,payload,0,0,7,payload,0,(240U<<16)|320U};
 memcpy(wire,&f,48);memcpy((unsigned char*)wire+48,table,sizeof table);
 for(unsigned y=0;y<320;++y)memcpy((unsigned char*)wire+80+y*960,(const unsigned char*)bgra+(size_t)y*stride,960);
 return 0;
}
#endif
