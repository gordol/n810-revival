/* SPDX-License-Identifier: MIT
 * Raw Mesa input/reference pairing for the VGP backend. Diagnostic only:
 * records precede CPU shading; capture mode never claims GPU geometry work.
 */
#ifndef MBX_VGP_CAPTURE_H
#define MBX_VGP_CAPTURE_H
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "tgsi/tgsi_parse.h"
#include "mbx_vgp_shader.h"
static _Thread_local FILE *mbx_vgp_capture_file;
static _Thread_local int mbx_vgp_capture_state=-1;
static _Thread_local unsigned mbx_vgp_capture_draws,mbx_vgp_capture_vertices,mbx_vgp_capture_outputs;
static void mbx_vgp_capture_write(const void *p,size_t bytes)
{if(bytes&&fwrite(p,1,bytes,mbx_vgp_capture_file)!=bytes){perror("MBX raw vertex capture");abort();}}
static bool mbx_vgp_capture_begin(struct draw_context *draw,const struct draw_vertex_info *v,const struct draw_prim_info *prim)
{
 if(mbx_vgp_capture_state<0){
  const char *path=getenv("N810_MBX_VGP_CAPTURE");mbx_vgp_capture_state=path&&*path;
  if(mbx_vgp_capture_state){mbx_vgp_capture_file=fopen(path,"wx");if(!mbx_vgp_capture_file){perror("MBX raw capture open");abort();}}
 }
 if(!mbx_vgp_capture_state)return false;
 const struct draw_vertex_shader *vs=draw->vs.vertex_shader;
 struct mbx_vgp_shader program;
 bool compiled=mbx_vgp_compile(vs->state.tokens,&program);
 fprintf(stderr,"N810_MBX_VGP_COMPILE draw=%u accepted=%u instructions=%u inputs=%u constants=%u GPU_geometry=0\n",
  mbx_vgp_capture_draws,compiled,compiled?program.count:0,compiled?program.inputs:0,compiled?program.constants:0);
 unsigned tokens=tgsi_num_tokens(vs->state.tokens),bytes=draw->pt.user.vs_constants_size[0];
 if(v->count>4096||prim->count>16384||prim->primitive_count>4096||tokens>16384||bytes>16384||bytes%4||vs->info.num_inputs>32||vs->info.num_outputs>32)abort();
 for(unsigned i=1;i<PIPE_MAX_CONSTANT_BUFFERS;++i)if(draw->pt.user.vs_constants_size[i])abort();
 uint32_t h[16]={0x3152474d,1,prim->prim,prim->linear,prim->start,prim->count,prim->flags,prim->primitive_count,
  v->count,vs->info.num_inputs,vs->info.num_outputs,tokens,bytes,draw->rasterizer->flatshade,draw->rasterizer->front_ccw,draw->rasterizer->cull_face};
 mbx_vgp_capture_write(h,sizeof(h));
 mbx_vgp_capture_write(vs->state.tokens,tokens*4);
 mbx_vgp_capture_write(draw->pt.user.vs_constants[0],bytes);
 for(unsigned i=0;i<prim->count;++i){uint32_t index=prim->linear?prim->start+i:prim->elts[i];if(index>=v->count)abort();mbx_vgp_capture_write(&index,4);}
 for(unsigned i=0;i<prim->primitive_count;++i)mbx_vgp_capture_write(prim->primitive_lengths+i,4);
 for(unsigned i=0;i<v->count;++i){const struct vertex_header *p=(const void *)((const char *)v->verts+i*v->stride);mbx_vgp_capture_write(p->data,vs->info.num_inputs*16);}
 mbx_vgp_capture_vertices=v->count;mbx_vgp_capture_outputs=vs->info.num_outputs;return true;
}
static void mbx_vgp_capture_end(const struct draw_vertex_info *v)
{
 if(v->count!=mbx_vgp_capture_vertices)abort();
 for(unsigned i=0;i<v->count;++i){const struct vertex_header *p=(const void *)((const char *)v->verts+i*v->stride);mbx_vgp_capture_write(p->data,mbx_vgp_capture_outputs*16);}
 if(fflush(mbx_vgp_capture_file))abort();
 if(++mbx_vgp_capture_draws==32){
  if(fclose(mbx_vgp_capture_file))abort();mbx_vgp_capture_file=NULL;mbx_vgp_capture_state=0;
  fprintf(stderr,"N810_MBX_RAW_CAPTURE_COMPLETE draws=32 CPU_reference=1 GPU_geometry=0\n");
 }
}
#endif
