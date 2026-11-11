/* SPDX-License-Identifier: MIT */
/* Original, deliberately narrow texture path. No software texture sampling. */
static bool mbx_texture_source(const struct tgsi_full_src_register *s,unsigned file,unsigned index)
{
 return s->Register.File==file&&s->Register.Index==index&&!s->Register.Indirect&&!s->Register.Dimension&&
  !s->Register.Negate&&!s->Register.Absolute&&s->Register.SwizzleX==0&&s->Register.SwizzleY==1&&s->Register.SwizzleZ==2&&s->Register.SwizzleW==3;
}
#include "mbx_modulate_fragment.h"
static bool mbx_texture_fragment(const struct tgsi_token *tokens, bool alpha_texture)
{
 struct tgsi_parse_context p;unsigned phase=0,temp=0;bool ok=true,ended=false;
 if(tgsi_parse_init(&p,tokens)!=TGSI_PARSE_OK)return false;
 while(!tgsi_parse_end_of_tokens(&p)&&ok){
  tgsi_parse_token(&p);
  if(p.FullToken.Token.Type==TGSI_TOKEN_TYPE_DECLARATION)continue;
  if(p.FullToken.Token.Type==TGSI_TOKEN_TYPE_PROPERTY){
   const struct tgsi_full_property *v=&p.FullToken.FullProperty;
   if(v->Property.PropertyName!=TGSI_PROPERTY_FS_COLOR0_WRITES_ALL_CBUFS||v->Property.NrTokens!=2||v->u[0].Data!=1)ok=false;
   continue;
  }
  if(p.FullToken.Token.Type!=TGSI_TOKEN_TYPE_INSTRUCTION){ok=false;break;}
  const struct tgsi_full_instruction *i=&p.FullToken.FullInstruction;
  if(i->Instruction.Opcode==TGSI_OPCODE_END){ended=phase==4;break;}
  if(i->Instruction.Saturate||i->Instruction.NumDstRegs!=1||i->Dst[0].Register.Indirect||i->Dst[0].Register.Dimension){ok=false;break;}
  if(phase==0&&i->Instruction.Opcode==TGSI_OPCODE_MOV&&i->Instruction.NumSrcRegs==1&&i->Dst[0].Register.File==TGSI_FILE_TEMPORARY&&i->Dst[0].Register.WriteMask==15){
   struct tgsi_full_src_register source=i->Src[0];source.Register.SwizzleZ=2;
   if(i->Src[0].Register.SwizzleZ!=0||!mbx_texture_source(&source,TGSI_FILE_INPUT,0)){ok=false;break;}
   temp=i->Dst[0].Register.Index;phase=1;
  }else if(phase==1&&i->Instruction.Opcode==TGSI_OPCODE_TXP&&i->Instruction.NumSrcRegs==2&&i->Instruction.Texture&&i->Texture.Texture==TGSI_TEXTURE_2D&&i->Texture.NumOffsets==0&&
     ((i->Dst[0].Register.File==TGSI_FILE_TEMPORARY&&i->Dst[0].Register.Index==temp)||
      (alpha_texture&&i->Dst[0].Register.File==TGSI_FILE_OUTPUT&&i->Dst[0].Register.Index==0))&&i->Dst[0].Register.WriteMask==15&&
     mbx_texture_source(&i->Src[0],TGSI_FILE_TEMPORARY,temp)&&i->Src[1].Register.File==TGSI_FILE_SAMPLER&&i->Src[1].Register.Index==0&&!i->Src[1].Register.Indirect&&!i->Src[1].Register.Dimension)phase=i->Dst[0].Register.File==TGSI_FILE_OUTPUT?4:2;
  else if(phase==2&&alpha_texture&&i->Instruction.Opcode==TGSI_OPCODE_MOV&&i->Instruction.NumSrcRegs==1&&i->Dst[0].Register.File==TGSI_FILE_OUTPUT&&i->Dst[0].Register.Index==0&&i->Dst[0].Register.WriteMask==15&&mbx_texture_source(&i->Src[0],TGSI_FILE_TEMPORARY,temp))phase=4;
  else if(phase==2&&!alpha_texture&&i->Instruction.Opcode==TGSI_OPCODE_MOV&&i->Instruction.NumSrcRegs==1&&i->Dst[0].Register.File==TGSI_FILE_OUTPUT&&i->Dst[0].Register.Index==0&&i->Dst[0].Register.WriteMask==7&&mbx_texture_source(&i->Src[0],TGSI_FILE_TEMPORARY,temp))phase=3;
  else if(phase==3&&i->Instruction.Opcode==TGSI_OPCODE_MOV&&i->Instruction.NumSrcRegs==1&&i->Dst[0].Register.File==TGSI_FILE_OUTPUT&&i->Dst[0].Register.Index==0&&i->Dst[0].Register.WriteMask==8){
   const struct tgsi_full_src_register *r=&i->Src[0];
   ok=r->Register.File==TGSI_FILE_CONSTANT&&r->Register.Index==0&&!r->Register.Indirect&&!r->Register.Negate&&!r->Register.Absolute&&r->Register.SwizzleW==3&&(!r->Register.Dimension||(!r->Dimension.Indirect&&!r->Dimension.Index));phase=4;
  }else ok=false;
 }
 tgsi_parse_free(&p);return ok&&ended;
}
#include "sg_texture_resource.c"
#include "mbx_resource_cache.h"
static bool mbx_alpha_view(struct softpipe_context *sp)
{
 const struct pipe_sampler_view *v=sp->sampler_views[PIPE_SHADER_FRAGMENT][0];
 return v&&(v->format==PIPE_FORMAT_R8G8B8A8_UNORM||v->format==PIPE_FORMAT_B8G8R8A8_UNORM);
}
#include "mbx_wire_resources.h"
static void mbx_multi_upload(struct sp_mbx_capture *c,const unsigned char *upload,unsigned version,unsigned bytes){
 if((version==4&&getenv("N810_MBX_MIXED_RESOURCES")?mbx_wire_resource_append_rgb565_arena(c->vgp->data,sizeof(c->vgp->data),upload,bytes,&c->texture_index):mbx_wire_resource_append(c->vgp->data,sizeof(c->vgp->data),upload,version,bytes,&c->texture_index)))
  mbx_fail("bounded frame resource table rejected");
}
#include "linear_resource.c"
static bool mbx_linear_texture_upload(struct softpipe_context *sp,struct sp_mbx_capture *c,unsigned x,unsigned y,unsigned w,unsigned h){
 const struct pipe_sampler_view *v=sp->sampler_views[PIPE_SHADER_FRAGMENT][0];
 const struct pipe_sampler_state *s=sp->samplers[PIPE_SHADER_FRAGMENT][0];
 if(!getenv("N810_MBX_LINEAR_TEXTURE")||!v||!s||(v->format!=PIPE_FORMAT_R8G8B8A8_UNORM&&v->format!=PIPE_FORMAT_B8G8R8A8_UNORM&&v->format!=PIPE_FORMAT_R8G8B8X8_UNORM&&v->format!=PIPE_FORMAT_B8G8R8X8_UNORM))return false;
 if(sp->num_samplers[PIPE_SHADER_FRAGMENT]!=1||v->target!=PIPE_TEXTURE_2D||v->u.tex.first_level||v->u.tex.last_level||v->u.tex.first_layer||v->u.tex.last_layer||
    v->swizzle_r!=PIPE_SWIZZLE_X||v->swizzle_g!=PIPE_SWIZZLE_Y||v->swizzle_b!=PIPE_SWIZZLE_Z||(v->swizzle_a!=PIPE_SWIZZLE_W&&v->swizzle_a!=PIPE_SWIZZLE_1)||
    s->wrap_s!=s->wrap_t||(s->wrap_s!=PIPE_TEX_WRAP_REPEAT&&s->wrap_s!=PIPE_TEX_WRAP_CLAMP_TO_EDGE)||s->min_img_filter!=PIPE_TEX_FILTER_NEAREST||s->mag_img_filter!=PIPE_TEX_FILTER_NEAREST||s->min_mip_filter!=PIPE_TEX_MIPFILTER_NONE||s->compare_mode||s->unnormalized_coords||s->lod_bias||s->max_anisotropy>1)
 {fprintf(stderr,"N810_MBX_LINEAR_SAMPLER samplers=%u format=%u target=%u levels=%u,%u layers=%u,%u swizzle=%u,%u,%u,%u wrap=%u,%u,%u filters=%u,%u,%u compare=%u unnormalized=%u lod_bias=%g anisotropy=%u\n",
   sp->num_samplers[PIPE_SHADER_FRAGMENT],v->format,v->target,v->u.tex.first_level,v->u.tex.last_level,v->u.tex.first_layer,v->u.tex.last_layer,
   v->swizzle_r,v->swizzle_g,v->swizzle_b,v->swizzle_a,s->wrap_s,s->wrap_t,s->wrap_r,s->min_img_filter,s->mag_img_filter,s->min_mip_filter,s->compare_mode,s->unnormalized_coords,(double)s->lod_bias,s->max_anisotropy);
  mbx_fail("linear texture sampler outside validated subset");}
 struct softpipe_resource *r=softpipe_resource(v->texture);
 if(mbx_windows_requested()){
  int slot=mbx_window_find(c,v->texture);
  if(slot>=0){
   if(x||y||w||h||r->base.width0!=128||r->base.height0!=128||s->wrap_s!=PIPE_TEX_WRAP_CLAMP_TO_EDGE||v->swizzle_a!=PIPE_SWIZZLE_W)mbx_fail("rendered image sampler outside exact subset");
   if(mbx_wire_resources_compact(c->vgp->data,sizeof(c->vgp->data)))mbx_fail("rendered image resource compaction");
   if(mbx_wire_resource_append_window(c->vgp->data,sizeof(c->vgp->data),c->window[slot].token,&c->texture_index))mbx_fail("rendered image resource admission");
   c->texture_uv_width=c->texture_uv_height=c->texture_linear_width=c->texture_linear_height=128;
   c->texture_crop_x=c->texture_crop_y=1; /* raw linear image: no upload halo */
   c->texture_deferred=false;c->texture_bound=true;++c->window_samples;return true;
  }
 }

 if(r->mbx_content.external_only)mbx_fail("exported final target cannot be sampled as a CPU texture");unsigned pitch;
 if(!r||!r->base.width0||!r->base.height0||r->base.width0>1024||r->base.height0>1024)mbx_fail("linear atlas image dimensions");
 c->texture_uv_width=r->base.width0;c->texture_uv_height=r->base.height0;
 if(!w&&(r->base.width0>320||r->base.height0>320)){
  c->texture_deferred=true;return true;
 }
 if(!w){w=r->base.width0;h=r->base.height0;}
 if(x>r->base.width0||y>r->base.height0||w>r->base.width0-x||h>r->base.height0-y)mbx_fail("atlas crop bounds");
 unsigned crop[4]={x,y,w,h};size_t bytes=mbx_linear_size(w,h,&pitch);
 if(!r||r->dt||r->mbx_mapping_bytes||!r->data||r->base.format!=v->format||!bytes||r->base.depth0!=1||r->base.last_level||r->base.nr_samples>1||r->stride[0]<r->base.width0*4)
  mbx_fail("linear texture image outside validated resource subset");
 if((v->format==PIPE_FORMAT_R8G8B8X8_UNORM||v->format==PIPE_FORMAT_B8G8R8X8_UNORM)&&v->swizzle_a!=PIPE_SWIZZLE_1)mbx_fail("RGBX texture must force opaque alpha");
 unsigned flags=(v->format==PIPE_FORMAT_R8G8B8A8_UNORM||v->format==PIPE_FORMAT_R8G8B8X8_UNORM)|((v->swizzle_a==PIPE_SWIZZLE_1)<<1)|((s->wrap_s==PIPE_TEX_WRAP_REPEAT)<<2);
 /* Four small immutable images plus one bounded large-image scratch entry.
  * References prevent resource identity reuse; timestamp/crop/sampler changes
  * invalidate conversion. GPU upload and post-job verification are unchanged. */
 struct mbx_linear_entry *entry=mbx_linear_choose(c->linear_cache,v->texture,r->timestamp,flags,crop,bytes);
 if(!mbx_linear_matches(entry,v->texture,r->timestamp,flags,crop)){
  entry->wire_epoch=0;
  if(entry->capacity<bytes){unsigned char *memory=realloc(entry->upload,bytes);if(!memory)mbx_fail("linear resource allocation");entry->upload=memory;entry->capacity=bytes;}
  struct mbx_linear_source source={(const unsigned char*)r->data+r->level_offset[0]+(size_t)y*r->stride[0]+x*4,(size_t)(h-1)*r->stride[0]+w*4,r->stride[0],w,h,flags&1,(flags>>1)&1,(flags>>2)&1};
  if(mbx_linear_pack(&source,entry->upload,entry->capacity))mbx_fail("linear resource byte preparation");
  pipe_resource_reference(&entry->resource,v->texture);entry->timestamp=r->timestamp;entry->flags=flags;memcpy(entry->crop,crop,sizeof(crop));++c->linear_rebuilds;c->linear_packed_bytes+=bytes;
 }else ++c->linear_hits;
 entry->used=++c->linear_clock;
 /* Immutable resource reference + timestamp/crop/sampler identity proves
  * the same upload already belongs to this canonical frame. Its table index
  * survives append/compaction, but never clear, restore or checkpoint. */
 bool wire_hit=getenv("N810_MBX_RESOURCE_REFERENCES")&&mbx_linear_wire_matches(entry,c->vgp->resource_epoch);
 if(wire_hit){c->texture_index=entry->wire_index;++c->linear_wire_hits;c->linear_wire_skipped_bytes+=bytes;}
 int appended=wire_hit?0:(getenv("N810_MBX_RESERVED_RESOURCES")?mbx_wire_resource_append_linear_reserved:mbx_wire_resource_append_linear)(c->vgp->data,sizeof(c->vgp->data),entry->upload,w,h,bytes,&c->texture_index);
 if(appended==-28&&getenv("N810_MBX_SURFACE_CHECKPOINT")&&c->header.width==240&&c->header.height==320&&
    c->header.triangles!=c->rendered_count&&((struct mbx_vgp_wire_frame*)c->vgp->data)->draws){
  /* Append failure is transactional. Finish only the already encoded draws,
   * then retry the unchanged incoming image against their exact GPU result.
   * This does not present an intermediate image to the application/display. */
  bool ready=c->state_ready;
  sp_mbx_checkpoint(sp);
  c->state_ready=ready;
  if(c->header.triangles||((struct mbx_vgp_wire_frame*)c->vgp->data)->clear_buffers)
   mbx_fail("resource-pressure checkpoint did not retire history");
  appended=(getenv("N810_MBX_RESERVED_RESOURCES")?mbx_wire_resource_append_linear_reserved:mbx_wire_resource_append_linear)(c->vgp->data,sizeof(c->vgp->data),entry->upload,w,h,bytes,&c->texture_index);
  fprintf(stderr,"N810_MBX_RESOURCE_CHECKPOINT incoming_bytes=%u retry=%d CPU_blended_pixels=0\n",(unsigned)bytes,appended);
 }
 if(appended)mbx_fail("linear resource batching capacity exceeded");
 entry->wire_epoch=c->vgp->resource_epoch;entry->wire_index=c->texture_index;
 c->texture_linear_width=w;c->texture_linear_height=h;c->texture_crop_x=x;c->texture_crop_y=y;c->texture_deferred=false;c->texture_bound=true;return true;
}
static void mbx_texture_upload(struct softpipe_context *sp,struct sp_mbx_capture *c)
{
 c->texture_linear_width=c->texture_linear_height=0;c->texture_deferred=false;
 if(mbx_linear_texture_upload(sp,c,0,0,0,0))return;
 const struct pipe_sampler_view *v=sp->sampler_views[PIPE_SHADER_FRAGMENT][0];
 const struct pipe_sampler_state *s=sp->samplers[PIPE_SHADER_FRAGMENT][0];
 bool alpha_texture=mbx_alpha_view(sp);
 const float *alpha=sp->mapped_constants[PIPE_SHADER_FRAGMENT][0];
 if(!alpha_texture&&(!alpha||sp->const_buffer_size[PIPE_SHADER_FRAGMENT][0]<16||alpha[3]!=1.0f))mbx_fail("RGB texture replacement alpha must be one");
 if(!v||!s||sp->num_samplers[PIPE_SHADER_FRAGMENT]!=1||v->target!=PIPE_TEXTURE_2D||(!alpha_texture&&v->format!=PIPE_FORMAT_B5G6R5_UNORM)||
    v->u.tex.first_level||v->u.tex.last_level||v->u.tex.first_layer||v->u.tex.last_layer||
    v->swizzle_r!=PIPE_SWIZZLE_X||v->swizzle_g!=PIPE_SWIZZLE_Y||v->swizzle_b!=PIPE_SWIZZLE_Z||v->swizzle_a!=(alpha_texture?PIPE_SWIZZLE_W:PIPE_SWIZZLE_1)||
    s->wrap_s!=PIPE_TEX_WRAP_CLAMP_TO_EDGE||s->wrap_t!=PIPE_TEX_WRAP_CLAMP_TO_EDGE||s->min_img_filter!=PIPE_TEX_FILTER_NEAREST||
    s->mag_img_filter!=PIPE_TEX_FILTER_NEAREST||s->min_mip_filter!=PIPE_TEX_MIPFILTER_NONE||s->compare_mode||s->unnormalized_coords||s->lod_bias||s->max_anisotropy>1)
 {
  fprintf(stderr,"N810_MBX_REJECT_SAMPLER count=%u view=%u sampler=%u format=%u target=%u size=%ux%u levels=%u,%u layers=%u,%u swizzle=%u,%u,%u,%u wrap=%u,%u filter=%u,%u mip=%u compare=%u unnormalized=%u lod_bias=%g anisotropy=%u\n",
   sp->num_samplers[PIPE_SHADER_FRAGMENT],!!v,!!s,v?v->format:0,v?v->target:0,v&&v->texture?v->texture->width0:0,v&&v->texture?v->texture->height0:0,
   v?v->u.tex.first_level:0,v?v->u.tex.last_level:0,v?v->u.tex.first_layer:0,v?v->u.tex.last_layer:0,
   v?v->swizzle_r:0,v?v->swizzle_g:0,v?v->swizzle_b:0,v?v->swizzle_a:0,
   s?s->wrap_s:0,s?s->wrap_t:0,s?s->min_img_filter:0,s?s->mag_img_filter:0,s?s->min_mip_filter:0,s?s->compare_mode:0,s?s->unnormalized_coords:0,s?s->lod_bias:0,s?s->max_anisotropy:0);
  mbx_fail("texture sampler outside resource candidate subset");
 }
 struct softpipe_resource *r=softpipe_resource(v->texture);
 if(r->mbx_content.external_only)mbx_fail("exported final target cannot be sampled as a CPU texture");
 unsigned side=r?r->base.width0:0,bytes_per_pixel=alpha_texture?4:2;
 if(!r||r->dt||r->mbx_mapping_bytes||!r->data||r->base.format!=v->format||(side!=64&&side!=128)||
    r->base.height0!=side||r->base.depth0!=1||r->base.last_level||r->base.nr_samples>1||r->stride[0]<side*bytes_per_pixel||
    (alpha_texture&&side!=64))mbx_fail("texture image outside bounded resource candidate");
 if(alpha_texture){
  const char *layout=getenv("N810_MBX_NATIVE32_LAYOUT");
  if(!layout||strcmp(layout,"bgra"))
   mbx_fail("native32 layout requires explicit physical-test admission");
 }
 struct mbx_vgp_wire_frame *f=(void *)c->vgp->data;
 unsigned bytes=side*side*bytes_per_pixel,version=alpha_texture?5:side==128?4:3;
 unsigned char staging[32768];const unsigned char *upload=staging;
 const unsigned char *source=(const unsigned char *)r->data+r->level_offset[0];
 const char *cache=getenv("N810_MBX_TEXTURE_CACHE");
 if(version==3&&cache&&!strcmp(cache,"1")){
  if(!c->texture_cache){c->texture_cache=calloc(1,sizeof(*c->texture_cache));if(!c->texture_cache)mbx_fail("texture cache allocation");}
  upload=mbx_texture_cached(c->texture_cache,source,r->stride[0]);
 }else{
  struct sg_texture_desc desc={side,alpha_texture?SG_RGBA8888:SG_RGB565,r->stride[0],(side-1)*r->stride[0]+side*bytes_per_pixel};
  if(cache&&!strcmp(cache,"1")){
   if(!c->resource_cache){c->resource_cache=calloc(1,sizeof(*c->resource_cache));if(!c->resource_cache)mbx_fail("resource cache allocation");}
   upload=mbx_resource_cached(c->resource_cache,source,&desc);if(!upload)mbx_fail("resource cache packing failed");
  }else if(sg_texture_pack(staging,sizeof(staging),source,&desc))mbx_fail("texture resource packing failed");
  /* Physical native32 proof establishes BGRA byte order. This is a lossless
   * upload conversion, not sampling or rasterization; retain all8-bit lanes. */
  if(alpha_texture&&v->format==PIPE_FORMAT_R8G8B8A8_UNORM){
   mbx_resource_bgra(staging,upload,bytes);upload=staging;
  }
 }
 const char *multi=getenv("N810_MBX_MULTI_TEXTURE");
 if(multi&&!strcmp(multi,"1")){mbx_multi_upload(c,upload,version,bytes);c->texture_bound=true;return;}
 c->texture_index=0;
 unsigned old_bytes=f->version==5?16384:f->version==4?32768:f->version==3?8192:0;
 bool changed=f->version!=version||memcmp(c->vgp->data+48,upload,bytes);
 if(changed){
  if(c->texture_bound)mbx_fail("texture changes within one frame unsupported");
  if(f->bytes<48+old_bytes||f->bytes>sizeof(c->vgp->data)||bytes>sizeof(c->vgp->data)-(f->bytes-old_bytes))
   mbx_fail("texture insertion exceeds bounded frame storage");
  /* Earlier draws are untextured. Preserve their exact bytes and dynamic
   * update order when first binding changes the reserved resource prefix. */
  memmove(c->vgp->data+48+bytes,c->vgp->data+48+old_bytes,f->bytes-48-old_bytes);
  memcpy(c->vgp->data+48,upload,bytes);f->bytes=f->bytes-old_bytes+bytes;f->version=version;
  c->vgp->template_dirty=true;
 }
 c->texture_bound=true;
}

#include "mbx_constant_color.h"
