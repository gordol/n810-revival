/* SPDX-License-Identifier: MIT. Adjacent draw concatenation; no vertex dedup. */
#ifndef MBX_DRAW_BATCH_H
#define MBX_DRAW_BATCH_H
#include "draw/mbx_vgp_wire.h"
#include <string.h>
static unsigned mbx_batch_prefix(const struct mbx_vgp_wire_draw *d)
{return 64+8*d->instructions+16*(d->uniforms+d->immediates);}
static int mbx_batch_shape(const struct mbx_vgp_wire_draw *d,unsigned bytes){
 if(!d||bytes<64||d->bytes!=bytes||!d->instructions||d->instructions>128||d->uniforms>83||d->immediates>6||d->inputs<1||d->inputs>3||!d->vertices||d->vertices>4096||!d->triangles||d->triangles>256)return 0;
 return mbx_batch_prefix(d)+16*d->inputs*d->vertices+((6*d->triangles+3)&~3U)==bytes;
}
/* Same conservative formula as the kernel draw encoder. Charge only actual
 * scissor transitions and omit a second program/state block when concatenated. */
static unsigned mbx_batch_command_words(const struct mbx_vgp_wire_draw *d,unsigned masks,int merged){
 unsigned words=(d->reserved&8)?(d->inputs==3?12U:8U):d->inputs==2?((d->reserved&131072)?8U:7U):4U;
 return 106*masks+(merged?0:25+2*d->instructions+(d->uniforms?1+4*d->uniforms:0)+(d->immediates?1+4*d->immediates:0))+(9+3*!!(d->reserved&4)+3*words)*d->triangles;
}
/* Last-record length survives resource-table insertions, which move every draw
 * together. Clear/restore invalidate it. No per-draw scan of previous records. */
static struct mbx_vgp_wire_draw *mbx_batch_previous(void *wire,unsigned capacity,unsigned last,
 const struct mbx_vgp_wire_draw *next,const void *program,const void *uniforms,const void *immediates){
 struct mbx_vgp_wire_frame *f=wire;
 if(!wire||capacity<64||f->bytes<64||f->bytes>capacity||!f->draws||last>f->bytes-64||last<64||!mbx_batch_shape(next,next->bytes))return NULL;
 struct mbx_vgp_wire_draw *d=(void*)((unsigned char*)wire+f->bytes-last);
 if(!mbx_batch_shape(d,last)||d->instructions!=next->instructions||d->uniforms!=next->uniforms||d->immediates!=next->immediates||d->inputs!=next->inputs||d->smooth!=next->smooth||d->cull_mode!=next->cull_mode||d->reserved!=next->reserved||memcmp(d->viewport,next->viewport,sizeof d->viewport)||d->vertices+next->vertices>4096||d->triangles+next->triangles>256)return NULL;
 const unsigned char *p=(const void*)(d+1);
 if(memcmp(p,program,8*d->instructions))return NULL;p+=8*d->instructions;
 if(d->uniforms&&memcmp(p,uniforms,16*d->uniforms))return NULL;p+=16*d->uniforms;
 if(d->immediates&&memcmp(p,immediates,16*d->immediates))return NULL;
 return d;
}
/* Caller just emitted a fully checked adjacent record. Preserve the exact
 * old/new triangle order and provoking vertices; only rebase new indices. */
static unsigned mbx_batch_join(struct mbx_vgp_wire_draw *d,struct mbx_vgp_wire_draw *next){
 unsigned short indices[768];unsigned prefix=mbx_batch_prefix(d),stride=16*d->inputs;
 unsigned old_vertices=d->vertices,old_indices=3*d->triangles,new_indices=3*next->triangles;
 unsigned next_vertices=next->vertices,next_triangles=next->triangles,next_bytes=next->bytes;
 unsigned char *vertices=(unsigned char*)d+prefix;
 unsigned char *incoming=(unsigned char*)next+prefix;
 unsigned short *source=(void*)(incoming+stride*next_vertices);
 memcpy(indices,vertices+stride*d->vertices,old_indices*2);
 memmove(vertices+stride*d->vertices,incoming,stride*next_vertices);
 unsigned short *out=(void*)(vertices+stride*(d->vertices+next_vertices));
 memcpy(out,indices,old_indices*2);
 for(unsigned i=0;i<new_indices;i++)out[old_indices+i]=source[i]+old_vertices;
 unsigned total_indices=old_indices+new_indices;
 if(total_indices&1)out[total_indices]=0;
 unsigned merged=prefix+stride*(d->vertices+next_vertices)+((2*total_indices+3)&~3U);
 unsigned saved=d->bytes+next_bytes-merged;
 d->bytes=merged;d->vertices+=next_vertices;d->triangles+=next_triangles;return saved;
}
#endif
