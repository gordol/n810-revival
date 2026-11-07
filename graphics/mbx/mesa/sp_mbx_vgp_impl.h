/* SPDX-License-Identifier: MIT */
static bool sp_mbx_vgp_draw(struct draw_context *draw,const struct draw_vertex_info *v,
                           const struct draw_prim_info *prim)
{
 struct softpipe_context *sp=(struct softpipe_context *)draw->pipe;
 struct sp_mbx_capture *c=sp->mbx_capture;
 if(!c||!c->vgp)return false;
 softpipe_get_vbuf_vertex_info(sp);
 sp_mbx_prepare(sp);
 if(!c->state_ready)mbx_fail("GPU vertex render state not ready");
 if(draw->gs.geometry_shader||draw->rasterizer->flatshade_first||draw->rasterizer->clip_plane_enable||
    draw->rasterizer->rasterizer_discard||draw->rasterizer->fill_front!=PIPE_POLYGON_MODE_FILL||
    draw->rasterizer->fill_back!=PIPE_POLYGON_MODE_FILL||draw->rasterizer->offset_tri||
    draw->rasterizer->light_twoside||v->count>4096||prim->count>16384||prim->primitive_count>4096)
    mbx_fail("unsupported GPU vertex pipeline state");
 const struct draw_vertex_shader *vs=draw->vs.vertex_shader;
 if(vs->state.stream_output.num_outputs)mbx_fail("GPU stream output unsupported");
 unsigned tokens=tgsi_num_tokens(vs->state.tokens);
 if(tokens>16384)mbx_fail("GPU shader exceeds token limit");
 struct mbx_vgp_cached_shader *cached=c->vgp->shaders;
 for(;cached;cached=cached->next)
   if(cached->tokens==tokens&&!memcmp(cached->code,vs->state.tokens,tokens*4))break;
 if(!cached){
   cached=calloc(1,sizeof(*cached)+tokens*4);
   if(!cached||!mbx_vgp_compile(vs->state.tokens,&cached->program))mbx_fail("GPU vertex shader unsupported");
   cached->tokens=tokens;memcpy(cached->code,vs->state.tokens,tokens*4);
   cached->next=c->vgp->shaders;c->vgp->shaders=cached;
 }
 const struct mbx_vgp_shader *p=&cached->program;
 if(vs->info.num_inputs!=p->inputs||draw->pt.user.vs_constants_size[0]<p->constants*16)
    mbx_fail("GPU vertex input or uniforms mismatch");
 for(unsigned i=1;i<PIPE_MAX_CONSTANT_BUFFERS;++i)
   if(draw->pt.user.vs_constants_size[i])mbx_fail("GPU additional uniform buffer unsupported");
 unsigned source[16384];unsigned short indices[768];unsigned count=0;
 for(unsigned i=0;i<prim->count;++i)source[i]=prim->linear?prim->start+i:prim->elts[i];
 if(mbx_vgp_topology(prim->prim,source,prim->count,prim->primitive_lengths,prim->primitive_count,
                     v->count,indices,768,&count))mbx_fail("GPU primitive topology unsupported");
 if(!count)return true;
 unsigned bytes=64+p->count*8+(p->constants+p->immediates+p->inputs*v->count)*16+((count*2+3)&~3U);
 struct mbx_vgp_wire_frame *f=(void *)c->vgp->data;
 if(f->draws==64||bytes>sizeof(c->vgp->data)-f->bytes||count/3>256||c->header.triangles+count/3>2048)
   mbx_fail("GPU frame capacity exceeded");
 struct mbx_vgp_wire_draw *h=(void *)(c->vgp->data+f->bytes);memset(h,0,bytes);
 h->bytes=bytes;h->instructions=p->count;h->uniforms=p->constants;h->immediates=p->immediates;
 h->inputs=p->inputs;h->vertices=v->count;h->triangles=count/3;h->smooth=!draw->rasterizer->flatshade;
 /* GPU mode1 retains negative screen-space winding; mode2 positive. */
 unsigned face=draw->rasterizer->cull_face;
 if(face==PIPE_FACE_FRONT_AND_BACK) return true;
 if(face){
   bool front_negative=draw->rasterizer->front_ccw;
   if(draw->viewports[0].scale[1]>0)front_negative=!front_negative;
   bool keep_negative=face==PIPE_FACE_BACK?front_negative:!front_negative;
   h->cull_mode=keep_negative?1:2;
 }
 for(unsigned i=0;i<3;++i){memcpy(h->viewport+2*i,&draw->viewports[0].translate[i],4);memcpy(h->viewport+2*i+1,&draw->viewports[0].scale[i],4);}
 unsigned char *out=(void *)(h+1);
 memcpy(out,p->words,p->count*8);out+=p->count*8;
 memcpy(out,draw->pt.user.vs_constants[0],p->constants*16);out+=p->constants*16;
 memcpy(out,p->immediate,p->immediates*16);out+=p->immediates*16;
 for(unsigned i=0;i<v->count;++i){
   const struct vertex_header *vertex=(const void *)((const char *)v->verts+i*v->stride);
   memcpy(out,vertex->data,p->inputs*16);out+=p->inputs*16;
 }
 memcpy(out,indices,count*2);f->bytes+=bytes;++f->draws;c->header.triangles+=count/3;
 return true;
}
