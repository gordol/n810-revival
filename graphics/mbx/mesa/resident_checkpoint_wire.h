/* SPDX-License-Identifier: MIT
 * Private backend transport. Applications still use ordinary OpenGL.
 * One active target only: CPU access and target switches materialize it.
 */
static int mbx_resident_checkpoint(void *wire,unsigned capacity)
{
 if(!wire||capacity<80)return -22;
 struct mbx_vgp_wire_frame f={.magic=MBX_VGP_WIRE_MAGIC,.version=10,
  .bytes=80,.width=240,.height=320,.clear_depth=0x3f800000U};
 unsigned table[8]={1,0,0,0,10,0,0,(240U<<16)|320U};
 memcpy(wire,&f,48);memcpy((unsigned char*)wire+48,table,32);return 0;
}
/* Expand only the background descriptor; preserve appended textures and draws.
 * Used when a job needs an existing nonresident path such as separate alpha.
 * 307200 is 128-byte aligned, preserving every texture payload alignment.
 */
static int mbx_resident_expand(void *wire,unsigned capacity,const void *pixels)
{
 struct mbx_wire_resources r;unsigned *h=wire;unsigned char *raw=wire;
 const unsigned extra=240U*320U*4U;
 if(!wire||!pixels||capacity<80||h[2]>capacity||
    mbx_wire_resources_parse(wire,h[2],&r)||!r.count||r.item[0].version!=10||
    extra>capacity-h[2]||extra>MBX_WIRE_LINEAR_PAYLOAD-r.bytes)return -22;
 memmove(raw+r.data_offset+extra,raw+r.data_offset,h[2]-r.data_offset);
 memcpy(raw+r.data_offset,pixels,extra);
 h[2]+=extra;h[13]+=extra;h[16]=7;h[17]=extra;
 for(unsigned i=1;i<r.count;++i)h[16+4*i+2]+=extra;
 return 0;
}
