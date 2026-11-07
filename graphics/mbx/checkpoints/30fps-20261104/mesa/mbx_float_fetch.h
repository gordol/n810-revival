/* SPDX-License-Identifier: MIT
 * Exact float attribute expansion. No arithmetic or floating-point loads:
 * preserve every source bit and append OpenGL's zero/one missing channels.
 * The temporary also preserves the original unpack-then-emit overlap behavior.
 */
#ifndef MBX_FLOAT_FETCH_H
#define MBX_FLOAT_FETCH_H
#include <stdint.h>
#include <string.h>
static inline void mbx_float_fetch4(void *dst,const void *src,unsigned words)
{
 uint32_t value[4]={0,0,0,0x3f800000};
 switch(words){
 case 1:memcpy(value,src,4);break;
 case 2:memcpy(value,src,8);break;
 case 3:memcpy(value,src,12);break;
 case 4:memcpy(value,src,16);break;
 default:__builtin_trap();
 }
 memcpy(dst,value,16);
}
#endif
