/* SPDX-License-Identifier: MIT */
#ifndef MBX_CHANNEL_WIRE_H
#define MBX_CHANNEL_WIRE_H
/* Pack two already-rendered tightly packed BGRA regions. Set RGBA bits select
 * source B. No CPU blending, pixel evaluation, addresses or register commands. */
int mbx_pack_channel_region(unsigned width,unsigned height,unsigned mask,
 const void *a,unsigned a_bytes,const void *b,unsigned b_bytes,
 void *out,unsigned capacity,unsigned *written);
#endif
