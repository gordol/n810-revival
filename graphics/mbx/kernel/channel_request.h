/* SPDX-License-Identifier: MIT */
#ifndef MBX_CHANNEL_REQUEST_H
#define MBX_CHANNEL_REQUEST_H
#include "mbx_vgp_wire.h"
#include "mbx_wire_resources.h"
/* Shared by the real service admission boundary and host tests. */
static inline int mbx_channel_request_validate(const struct mbx_vgp_wire_frame *f,
 const struct mbx_wire_resources *r,unsigned mask){
 if(!f||!r||mask>15||f->version!=10||f->width<16||f->width>320||f->height<16||(f->height>192&&!(f->width==240&&f->height==320))||
    (f->width&15)||(f->height&15)||f->draws||f->clear_buffers||r->count!=1||(r->bytes!=f->width*f->height*8U&&!(r->item[0].version==11&&r->bytes==0)))return -22;
 if(r->item[0].version==11)return ((f->width==240&&f->height==320)||(f->width==128&&f->height==128))&&mask==8&&r->item[0].reserved==8?0:-22;
 if(r->item[0].version==9)return r->item[0].reserved==mask?0:-22;
 if(r->item[0].version==7)return r->item[0].reserved==((f->width<<16)|(f->height*2U))?0:-22;
 return -22;
}
#endif
