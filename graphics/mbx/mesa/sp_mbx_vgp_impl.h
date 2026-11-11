/* SPDX-License-Identifier: MIT */
/* The queue owns the destination bytes. Compare contents, never source pointers.
 * A changed layout is safe too: every new payload byte is checked or written. */
static void mbx_vgp_retain_copy(struct mbx_vgp_queue *q,void *dst,const void *src,size_t bytes)
{
 if((q->retain||q->use_template)&&!memcmp(dst,src,bytes))q->retained_bytes+=bytes;
 else{memcpy(dst,src,bytes);q->copied_bytes+=bytes;if(q->use_template)q->template_dirty=true;}
}
/* Constant-size memcpy lets the ARM compiler inline small attribute tuples.
 * memcpy preserves every bit and supports unaligned source/destination. */
static unsigned char *mbx_vgp_copy_vertices(unsigned char *out,const unsigned char *source,
                                           unsigned stride,unsigned count,unsigned bytes)
{
 if(((uintptr_t)out|(uintptr_t)source|stride)&3U){
  for(unsigned i=0;i<count;++i){memcpy(out,source,bytes);out+=bytes;source+=stride;}return out;
 }
 out=__builtin_assume_aligned(out,4);source=__builtin_assume_aligned(source,4);
#define MBX_COPY_VERTICES(N) do {for(unsigned i=0;i<count;++i){memcpy(out,source,N);out+=N;source+=stride;}return out;} while(0)
 switch(bytes){
 case 16: MBX_COPY_VERTICES(16);
 case 32: MBX_COPY_VERTICES(32);
 case 48: MBX_COPY_VERTICES(48);
 case 64: MBX_COPY_VERTICES(64);
 default: MBX_COPY_VERTICES(bytes);
 }
#undef MBX_COPY_VERTICES
}
static bool sp_mbx_vgp_draw_attempt(struct draw_context *draw,const struct draw_vertex_info *v,
                           const struct draw_prim_info *prim,bool retried)
{
 struct softpipe_context *sp=(struct softpipe_context *)draw->pipe;
 struct sp_mbx_capture *c=sp->mbx_capture;
 if(!c||!c->vgp)return false;
 if(!c->vgp->retain_checked){
  const char *v=getenv("N810_MBX_RETAIN_PAYLOAD");c->vgp->retain=v&&!strcmp(v,"1");
  v=getenv("N810_MBX_CLEAR_HEADER_ONLY");c->vgp->clear_header_only=v&&!strcmp(v,"1");
  v=getenv("N810_MBX_FIXED_COPY");c->vgp->fixed_copy=v&&!strcmp(v,"1");
  c->vgp->retain_checked=true;
 }
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
   if((cached->program.constant_color!=~0U)==c->constant_color&&cached->tokens==tokens&&!memcmp(cached->code,vs->state.tokens,tokens*4))break;
 if(!cached){
   cached=calloc(1,sizeof(*cached)+tokens*4);
   if(!cached||!mbx_vgp_compile_color(vs->state.tokens,&cached->program,c->constant_color))mbx_fail("GPU vertex shader unsupported");
   cached->tokens=tokens;memcpy(cached->code,vs->state.tokens,tokens*4);
   cached->next=c->vgp->shaders;c->vgp->shaders=cached;
 }
 const struct mbx_vgp_shader *p=&cached->program;
 if(p->texture_outputs!=c->texture_active)mbx_fail("texture varying and sampler mismatch");
 if(p->texture_matrix_constant!=~0U&&!mbx_vgp_affine_q(draw->pt.user.vs_constants[0],draw->pt.user.vs_constants_size[0],p->texture_matrix_constant))
  mbx_fail("texture matrix must preserve q=1");
 if(p->texture_outputs&&p->texture_q_input){
  if(!p->texture_input||p->inputs!=p->texture_input+1)mbx_fail("texture input layout mismatch");
  for(unsigned i=0;i<v->count;++i){
   const struct vertex_header *vertex=(const void *)((const char *)v->verts+i*v->stride);
   unsigned q;memcpy(&q,&vertex->data[p->texture_input][3],4);
   if(q!=0x3f800000U)mbx_fail("projective UV array q other than one unsupported");
  }
 }else if(p->texture_outputs){
  unsigned q=p->texture_q_constant,value;
  if(q<4*p->constants){
   if(draw->pt.user.vs_constants_size[0]<(q+1)*4)mbx_fail("texture q uniform missing");
   memcpy(&value,(const unsigned char *)draw->pt.user.vs_constants[0]+q*4,4);
  }else if(q>=384&&q<384+4*p->immediates)value=((const unsigned *)p->immediate)[q-384];
  else mbx_fail("texture q source unsupported");
  if(value!=0x3f800000U)mbx_fail("projective texture q other than one unsupported");
 }
 if(vs->info.num_inputs!=p->inputs||draw->pt.user.vs_constants_size[0]<(p->constants-(c->constant_color?1:0))*16)
    mbx_fail("GPU vertex input or uniforms mismatch");
 for(unsigned i=1;i<PIPE_MAX_CONSTANT_BUFFERS;++i)
   if(draw->pt.user.vs_constants_size[i])mbx_fail("GPU additional uniform buffer unsupported");
 unsigned uniform_storage[MBX_VGP_UNIFORM_LIMIT*4];
 const void *uniform_data=draw->pt.user.vs_constants[0];
 if(c->constant_color){
  if(!sp->mapped_constants[PIPE_SHADER_FRAGMENT][0]||sp->const_buffer_size[PIPE_SHADER_FRAGMENT][0]<16||p->constant_color+1!=p->constants)
   mbx_fail("fragment color constant missing");
  if(p->constant_color)memcpy(uniform_storage,uniform_data,p->constant_color*16);
  memcpy(uniform_storage+p->constant_color*4,sp->mapped_constants[PIPE_SHADER_FRAGMENT][0],16);uniform_data=uniform_storage;
 }
 if(c->texture_active&&c->texture_deferred){
  if(!p->texture_input||p->inputs!=p->texture_input+1||!v->count)mbx_fail("atlas UV layout");
  if(p->texture_matrix_constant!=~0U){
   const unsigned *m=(const unsigned*)draw->pt.user.vs_constants[0]+p->texture_matrix_constant*4;
   for(unsigned i=0;i<16;++i)if(m[i]!=(i%5==0?0x3f800000U:0))mbx_fail("atlas texture matrix must be identity");
  }
  float lo[2]={1,1},hi[2]={0,0};
  for(unsigned i=0;i<v->count;++i){const struct vertex_header *vertex=(const void*)((const char*)v->verts+i*v->stride);
   for(unsigned a=0;a<2;++a){float q=vertex->data[p->texture_input][a];if(!(q>=0&&q<=1))mbx_fail("atlas UV range");if(q<lo[a])lo[a]=q;if(q>hi[a])hi[a]=q;}
  }
  unsigned dims[2]={c->texture_uv_width,c->texture_uv_height},start[2],end[2];
  for(unsigned a=0;a<2;++a){
   double low=(double)lo[a]*dims[a],high=(double)hi[a]*dims[a];
   if(!(low>=1&&high<=dims[a]-1)){
    fprintf(stderr,"N810_MBX_ATLAS_EDGE axis=%u low=%g high=%g size=%u\n",a,low,high,dims[a]);mbx_fail("atlas crop requires interior UV halo");
   }
   start[a]=(unsigned)floor(low)-1;end[a]=(unsigned)ceil(high)+1;
   if(end[a]<=start[a]||end[a]-start[a]>320)mbx_fail("atlas used region exceeds bounded upload");
  }
  if(c->surface_diagnostics)fprintf(stderr,"N810_MBX_ATLAS_CROP source=%u,%u region=%u,%u,%u,%u\n",dims[0],dims[1],start[0],start[1],end[0]-start[0],end[1]-start[1]);
  if(!mbx_linear_texture_upload(sp,c,start[0],start[1],end[0]-start[0],end[1]-start[1]))mbx_fail("atlas upload rejected");
 }
 struct mbx_vgp_shader linear_program;
 if(c->texture_active&&c->texture_linear_width){
  if(!p->texture_input||p->inputs!=p->texture_input+1||p->constants>=MBX_VGP_UNIFORM_LIMIT)mbx_fail("linear UV input or constant capacity");
  if(p->texture_matrix_constant!=~0U){
   const unsigned *m=(const unsigned*)draw->pt.user.vs_constants[0]+p->texture_matrix_constant*4;
   for(unsigned i=0;i<16;++i)if(m[i]!=(i%5==0?0x3f800000U:0))mbx_fail("linear texture matrix must be identity");
  }
  for(unsigned i=0;i<v->count;++i){const struct vertex_header *vertex=(const void*)((const char*)v->verts+i*v->stride);
   if(!(vertex->data[p->texture_input][0]>=0&&vertex->data[p->texture_input][0]<=1&&vertex->data[p->texture_input][1]>=0&&vertex->data[p->texture_input][1]<=1))mbx_fail("linear texture coordinates outside admitted border range");
  }
  if(uniform_data!=uniform_storage)memcpy(uniform_storage,uniform_data,p->constants*16);
  linear_program=*p;unsigned slot=linear_program.constants++;
  struct mbx_vgp_source sources[3]={{2,9,0xe4,0},{1,slot,0xe4,0},{1,slot,0xee,0}};
  if(!mbx_vgp_append(&linear_program,3,3,3,sources,3))mbx_fail("linear UV program capacity");
  float affine[4]={c->texture_uv_width/2048.0f,c->texture_uv_height/2048.0f,(1.0f-c->texture_crop_x)/2048.0f,(1.0f-c->texture_crop_y)/2048.0f};
  memcpy(uniform_storage+slot*4,affine,16);uniform_data=uniform_storage;p=&linear_program;
 }
 unsigned source[16384];unsigned short indices[768];unsigned count=0;
 for(unsigned i=0;i<prim->count;++i)source[i]=prim->linear?prim->start+i:prim->elts[i];
 if(mbx_vgp_topology(prim->prim,source,prim->count,prim->primitive_lengths,prim->primitive_count,
                     v->count,indices,768,&count))mbx_fail("GPU primitive topology unsupported");
 if(!count)return true;
 const unsigned *clip=c->state_template.clip;
 if(clip[0]>=clip[2]||clip[1]>=clip[3])return true;
 if(getenv("N810_MBX_EXPERIMENTAL_SCISSOR")&&getenv("N810_MBX_SURFACE_DIAGNOSTICS"))fprintf(stderr,"GPU_MASK clip=%u,%u,%u,%u target=%u,%u enabled=%u\n",clip[0],clip[1],clip[2],clip[3],c->header.width,c->header.height,sp->rasterizer->scissor);
 bool scissor=clip[0]||clip[1]||clip[2]!=c->header.width||clip[3]!=c->header.height;
 if(scissor){
  if(p->constants>=MBX_VGP_UNIFORM_LIMIT)mbx_fail("scissor metadata capacity");
  if(uniform_data!=uniform_storage)memcpy(uniform_storage,uniform_data,p->constants*16);
  memcpy(uniform_storage+p->constants*4,clip,16);uniform_data=uniform_storage;
 }
 unsigned uniforms=p->constants+(scissor?1:0);
 unsigned bytes=64+p->count*8+(uniforms+p->immediates+p->inputs*v->count)*16+((count*2+3)&~3U);
 struct mbx_vgp_wire_frame *f=(void *)c->vgp->data;
 /* Kernel draw encoder upper bound, including two changed-scissor masks.
  * Each mask is25+16+21+42+2=106words (including mask control). Textured vertices cost at most36/triangle.
  * Keep this cumulative rather than rescanning all preceding wire records. */
 unsigned mask_commands=memcmp(clip,c->batch_clip,sizeof c->batch_clip)?(scissor?2:1):0;
 unsigned command_words=212+25+2*p->count+(uniforms?1+4*uniforms:0)+(p->immediates?1+4*p->immediates:0)+36*(count/3);
 if(count/3>256)mbx_fail("single GPU draw exceeds triangle capacity");
 if(f->version==10&&bytes>sizeof(c->vgp->data)-f->bytes)
  if(mbx_wire_resources_compact(c->vgp->data,sizeof(c->vgp->data)))mbx_fail("draw capacity normalization failed");
 /* The per-triangle estimate ignores native strip reuse. For opaque v9
  * frames it rejects valid cell batches; the kernel's exact encoder remains
  * authoritative and checks remaining capacity before submission. Keep the estimate for
  * v10 pressure checkpoints, plus every wire/draw/triangle bound below. */
 if(c->mask_commands+mask_commands>32||(f->version!=9&&(c->command_words>65536U||command_words>65536U-c->command_words))||f->draws>=MBX_VGP_WIRE_MAX_DRAWS||f->bytes>sizeof(c->vgp->data)||bytes>sizeof(c->vgp->data)-f->bytes||c->header.triangles+count/3>2048){
  if(mbx_debug_enabled()) fprintf(stderr,"N810_MBX_DRAW_PRESSURE draws=%u bytes=%u incoming=%u triangles=%u incoming_triangles=%u target=%u,%u retry=%u\n",f->draws,f->bytes,bytes,c->header.triangles,count/3,c->header.width,c->header.height,retried);
  if(retried||!f->draws||!getenv("N810_MBX_SURFACE_CHECKPOINT")||c->header.width!=240||c->header.height!=320||c->vgp->use_template)
   mbx_fail("GPU frame capacity exceeded");
  /* Finish only previously encoded draws. Re-enter preparation from scratch:
   * checkpoint replaces texture resources and invalidates shader state. */
  sp_mbx_checkpoint(sp);
  f=(void *)c->vgp->data;
  if(f->draws||f->clear_buffers||c->header.triangles)mbx_fail("draw checkpoint did not retire history");
  return sp_mbx_vgp_draw_attempt(draw,v,prim,true);
 }
 struct mbx_vgp_wire_draw header,*destination=(void *)(c->vgp->data+f->bytes);
 struct mbx_vgp_wire_draw *h=c->vgp->use_template?&header:destination;
 memset(h,0,(c->vgp->use_template||c->vgp->retain||c->vgp->clear_header_only)?sizeof(*h):bytes);
 h->bytes=bytes;h->instructions=p->count;h->uniforms=uniforms;h->immediates=p->immediates;
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
 if(sp->blend->rt[0].blend_enable&&!mbx_opaque_copy(sp,c)){
  const struct pipe_rt_blend_state *b=&sp->blend->rt[0];
  h->reserved=b->rgb_src_factor==PIPE_BLENDFACTOR_SRC_ALPHA?1:
              b->rgb_dst_factor==PIPE_BLENDFACTOR_ONE?3:2;
  if(f->version==10&&getenv("N810_MBX_SEPARATE_ALPHA")&&b->rgb_src_factor==PIPE_BLENDFACTOR_SRC_ALPHA&&
     b->rgb_dst_factor==PIPE_BLENDFACTOR_INV_SRC_ALPHA&&b->alpha_src_factor==PIPE_BLENDFACTOR_ONE&&b->alpha_dst_factor==PIPE_BLENDFACTOR_ONE)
      h->reserved|=MBX_ALPHA_ADDITIVE_ANNOTATION;
  if(f->version==10&&getenv("N810_MBX_SEPARATE_ALPHA")&&b->rgb_src_factor==PIPE_BLENDFACTOR_SRC_ALPHA&&
     b->rgb_dst_factor==PIPE_BLENDFACTOR_INV_SRC_ALPHA&&b->alpha_src_factor==PIPE_BLENDFACTOR_ONE&&b->alpha_dst_factor==PIPE_BLENDFACTOR_INV_SRC_ALPHA)
      h->reserved|=MBX_ALPHA_OVER_ANNOTATION;
  if(f->version==10&&getenv("N810_MBX_SEPARATE_ALPHA")&&!c->texture_active&&!sp->depth_stencil->depth_enabled&&
     b->rgb_src_factor==PIPE_BLENDFACTOR_SRC_ALPHA&&b->rgb_dst_factor==PIPE_BLENDFACTOR_ZERO&&
     b->alpha_src_factor==PIPE_BLENDFACTOR_ONE&&b->alpha_dst_factor==PIPE_BLENDFACTOR_ZERO)
      h->reserved=MBX_PREMULTIPLY_COPY_FLAG|MBX_ALPHA_COPY_ANNOTATION;
 }

 if(!sp->depth_stencil->depth_enabled){if((f->version!=9&&f->version!=10))mbx_fail("2D state requires wire v9");h->reserved|=64;}
 if(scissor)h->reserved|=128;
 if(c->texture_active){h->reserved|=4;if(f->version==6||f->version==9||f->version==10)h->reserved|=mbx_resource_index_flags(c->texture_index);}
 if(p->texture_input)h->reserved|=8;
 if(c->texture_modulate)h->reserved|=65536;
 if(p->color_input&&p->inputs==2&&!p->texture_input)h->reserved|=131072;
 for(unsigned i=0;i<3;++i){memcpy(h->viewport+2*i,&draw->viewports[0].translate[i],4);memcpy(h->viewport+2*i+1,&draw->viewports[0].scale[i],4);}
 if(c->vgp->use_template){
  if(memcmp(destination,h,36)||destination->reserved!=h->reserved)c->vgp->template_dirty=true;
  memcpy(destination,h,sizeof(*h));h=destination;
  /* Compact state is assembled once from the final canonical frame, after
   * resource insertion/compaction. Do not serialize it again per draw. */
 }
 unsigned char *out=(void *)(h+1);
 mbx_vgp_retain_copy(c->vgp,out,p->words,p->count*8);out+=p->count*8;
 memcpy(out,uniform_data,uniforms*16);out+=uniforms*16;
 mbx_vgp_retain_copy(c->vgp,out,p->immediate,p->immediates*16);out+=p->immediates*16;
 if(c->vgp->fixed_copy&&!c->vgp->retain&&!c->vgp->use_template){
  const struct vertex_header *first=(const void *)v->verts;
  out=mbx_vgp_copy_vertices(out,(const unsigned char *)first->data,v->stride,v->count,p->inputs*16);
  c->vgp->copied_bytes+=(uint64_t)v->count*p->inputs*16;
 }else for(unsigned i=0;i<v->count;++i){
   const struct vertex_header *vertex=(const void *)((const char *)v->verts+i*v->stride);
   mbx_vgp_retain_copy(c->vgp,out,vertex->data,p->inputs*16);out+=p->inputs*16;
 }
 mbx_vgp_retain_copy(c->vgp,out,indices,count*2);
 if(count&1){unsigned short zero=0;mbx_vgp_retain_copy(c->vgp,out+count*2,&zero,2);}
 if((c->vgp->use_template||c->vgp->retain||c->vgp->clear_header_only||c->vgp->fixed_copy)&&c->vgp->retain_verified<128){
  unsigned char *reference=calloc(1,bytes);if(!reference)mbx_fail("retained packet verification allocation");
  memcpy(reference,h,64);unsigned char *check=reference+64;
  memcpy(check,p->words,p->count*8);check+=p->count*8;
  memcpy(check,uniform_data,uniforms*16);check+=uniforms*16;
  memcpy(check,p->immediate,p->immediates*16);check+=p->immediates*16;
  for(unsigned i=0;i<v->count;++i){const struct vertex_header *vertex=(const void *)((const char *)v->verts+i*v->stride);memcpy(check,vertex->data,p->inputs*16);check+=p->inputs*16;}
  memcpy(check,indices,count*2);
  bool equal=!memcmp(reference,h,bytes);free(reference);if(!equal)mbx_fail("retained packet mismatch");
  if(++c->vgp->retain_verified==128)if(mbx_debug_enabled()) fprintf(stderr,"N810_MBX_PACKET_VERIFIED draws=128 packet_bit_exact=1 clear=%u fixed=%u retain=%u\n",c->vgp->clear_header_only,c->vgp->fixed_copy,c->vgp->retain);
 }
 c->mask_commands+=mask_commands;memcpy(c->batch_clip,clip,sizeof c->batch_clip);
 c->command_words+=command_words;
 f->bytes+=bytes;++f->draws;c->header.triangles+=count/3;
 mbx_content_draw(&softpipe_resource(c->reference_target)->mbx_content);
 return true;
}

static bool sp_mbx_vgp_draw(struct draw_context *draw,const struct draw_vertex_info *v,const struct draw_prim_info *prim)
{ return sp_mbx_vgp_draw_attempt(draw,v,prim,false); }
