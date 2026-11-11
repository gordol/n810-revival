/* SPDX-License-Identifier: MIT. General two-texture pointwise channel operation.
 * Existing verified sampler + channel merge, no new GPU packet or kernel ABI. */
#include "window_channels_wire.h"
#include "mesa/state_tracker/st_format.h"
static int mbx_channels_texture(struct gl_context *ctx,unsigned name,
 struct gl_texture_object **object,struct pipe_resource **resource){
 struct gl_texture_object *o=_mesa_lookup_texture(ctx,name);struct pipe_resource *r;
 if(!name||!o||o->Target!=GL_TEXTURE_2D||o->Attrib.BaseLevel||!o->Image[0][0]||o->Image[0][0]->NumSamples)return -EINVAL;
 if(o->pt&&o->Image[0][0]->pt&&o->pt!=o->Image[0][0]->pt)return -EINVAL;
 r=o->pt?o->pt:o->Image[0][0]->pt;if(!r)return -ENODATA;
 if(r->target!=PIPE_TEXTURE_2D||r->last_level||r->depth0!=1||r->array_size!=1||r->nr_samples>1||softpipe_resource(r)->dt||
  (r->format!=PIPE_FORMAT_R8G8B8A8_UNORM&&r->format!=PIPE_FORMAT_B8G8R8A8_UNORM))return -ENOTSUP;
 if(o->Attrib.MinLevel||o->Attrib.MinLayer||o->Image[0][0]->_BaseFormat!=GL_RGBA||
  st_mesa_format_to_pipe_format(ctx->st,o->Image[0][0]->TexFormat)!=r->format)return -ENOTSUP;
 *object=o;*resource=r;return 0;
}
static int mbx_window_channels(unsigned source,unsigned mask,unsigned target,unsigned mode,struct mbx_window_view *view,const struct mbx_window_rect *region){
 if(!view||mode>MBX_WINDOW_BINARY_RED_ALPHA||!source||!mask||!target||target==source||target==mask)return -EINVAL;
 int error=mbx_job_enter();if(error)return error;struct mbx_job_scope scope __attribute__((cleanup(mbx_job_scope_end)))={1};
 struct gl_context *ctx=_mesa_get_current_context();const char *device=getenv("N810_MBX_DEVICE");
 if(!ctx||!ctx->st||!ctx->st->pipe||!device||strcmp(device,"1"))return -ENODEV;
 if(mbx_job_shared()<=0||!mbx_windows_requested())return -ENOTSUP;
 struct sp_mbx_capture *c=capture(softpipe_context(ctx->st->pipe));
 if(!c||!c->vgp||c->gpu_fd<0||mbx_export.armed||mbx_export.held||c->vgp->use_template||c->resident_dirty)return -EBUSY;
 if(c->header.magic&&c->header.triangles!=c->rendered_count)return -EBUSY;
 struct gl_texture_object *objects[3];struct pipe_resource *r[3];unsigned names[3]={source,mask,target};
 for(unsigned i=0;i<3;i++){error=mbx_channels_texture(ctx,names[i],objects+i,r+i);if(error)return error;}
 if(r[2]==r[0]||r[2]==r[1]||r[2]==c->reference_target)return -EBUSY;
 unsigned fullw=r[0]->width0,fullh=r[0]->height0,x=0,y=0,w=fullw,h=fullh;
 if(!fullw||!fullh||r[1]->width0!=fullw||r[1]->height0!=fullh)return -ENOTSUP;
 if(region){
  if(fullw>1024||fullh>1024)return -ENOTSUP;
  x=region->x;y=region->y;w=region->width;h=region->height;
  if(!w||!h||w>128||h>128||x>=fullw||y>=fullh||w>fullw-x||h>fullh-y)return -EINVAL;
  /* Cropped GPU-only images have no canonical upload to pack. Whole128x128
   * ALPHA inputs retain the existing resident fast path. */
  if((x||y||w!=fullw||h!=fullh)&&(mbx_window_find(c,r[0])>=0||mbx_window_find(c,r[1])>=0||
     softpipe_resource(r[0])->mbx_content.external_only||softpipe_resource(r[1])->mbx_content.external_only))return -ENOTSUP;
 }
 unsigned sw=w<=128&&h<=128?128:w,sh=w<=128&&h<=128?128:h;
 if(r[2]->width0!=sw||r[2]->height0!=sh||
  !((sw==128&&sh==128)||(c->window_layout==2&&sw==240&&sh==320)))return -ENOTSUP;
 for(unsigned i=0;i<2;i++){
  const struct gl_sampler_attrib *s=&objects[i]->Sampler.Attrib;
  if(s->MinFilter!=GL_NEAREST||s->MagFilter!=GL_NEAREST||s->CompareMode!=GL_NONE||s->LodBias||s->MaxAnisotropy>1||
   (s->WrapS!=GL_REPEAT&&s->WrapS!=GL_CLAMP_TO_EDGE)||(s->WrapT!=GL_REPEAT&&s->WrapT!=GL_CLAMP_TO_EDGE))return -ENOTSUP;
 }
 const GLenum identity[4]={GL_RED,GL_GREEN,GL_BLUE,GL_ALPHA};
 for(unsigned i=0;i<3;i++)if(objects[0]->Attrib.Swizzle[i]!=identity[i])return -ENOTSUP;
 if(objects[1]->Attrib.Swizzle[mode?0:3]!=identity[mode?0:3])return -ENOTSUP;
 for(unsigned i=0;i<14;i++)if(c->window[i].resource==r[2]&&(c->window[i].imported||c->window[i].exported))return -EBUSY;
 int destination=mbx_window_available(c,r[2]);if(destination<0)return destination;
 struct mbx_window_token inputs[2]={{0}};unsigned char *packets[2]={NULL,NULL};unsigned lengths[2]={0};
 const char *fused=getenv("N810_MBX_CHANNEL_UPLOAD_MERGE");
 if(fused&&!strcmp(fused,"1")&&mbx_window_channels_upload_prefer(w,h,sw,sh)&&
    mbx_window_find(c,r[0])<0&&mbx_window_find(c,r[1])<0){
  struct mbx_linear_source images[2];
  for(unsigned i=0;i<2;i++){
   struct softpipe_resource *s=softpipe_resource(r[i]);
   if(s->mbx_content.external_only||!s->data||s->mbx_mapping_bytes||s->stride[0]<fullw*4U)return -ENOTSUP;
   images[i]=(struct mbx_linear_source){(const unsigned char*)s->data+s->level_offset[0]+(size_t)y*s->stride[0]+(size_t)x*4U,(size_t)(h-1)*s->stride[0]+w*4U,s->stride[0],w,h,r[i]->format==PIPE_FORMAT_R8G8B8A8_UNORM,0,0};
  }
  unsigned capacity=80+sw*sh*8U;
  packets[0]=malloc(capacity);if(!packets[0])return -ENOMEM;
  error=mbx_window_channels_upload_pack(images,images+1,mode,packets[0],capacity,sw,sh,lengths);
  if(error)goto done;
  mbx_window_choose(c,r[2]);softpipe_resource(r[2])->mbx_content.external_only=1;c->vgp->textures.valid=0;
  struct mbx_window_request request={.version=c->window_layout,.destination=(unsigned)destination};
  if(ioctl(c->gpu_fd,MBX_WINDOW_BIND,&request)||write(c->gpu_fd,packets[0],lengths[0])!=(ssize_t)lengths[0]||
     ioctl(c->gpu_fd,MBX_WINDOW_QUERY,&c->window[destination].token)){error=-EIO;goto done;}
  goto complete;
 }
 for(unsigned i=0;i<2;i++){
  int slot=mbx_window_find(c,r[i]);
  if(slot>=0){
   if((i&&mode)||w!=sw||h!=sh){error=-ENOTSUP;goto done;}
   inputs[i]=c->window[slot].token;continue;
  }
  struct softpipe_resource *s=softpipe_resource(r[i]);unsigned pitch;size_t payload=mbx_linear_size(w,h,&pitch);
  if(s->mbx_content.external_only||!s->data||s->mbx_mapping_bytes||s->stride[0]<fullw*4U||!payload){error=-ENOTSUP;goto done;}
  struct mbx_linear_source image={(const unsigned char*)s->data+s->level_offset[0]+(size_t)y*s->stride[0]+(size_t)x*4U,(size_t)(h-1)*s->stride[0]+w*4U,s->stride[0],w,h,r[i]->format==PIPE_FORMAT_R8G8B8A8_UNORM,0,0};
  packets[i]=malloc(MBX_WINDOW_CHECKPOINT_BYTES+payload);if(!packets[i]){error=-ENOMEM;goto done;}
  error=mbx_window_channel_pack(&image,i?mode:0,packets[i],MBX_WINDOW_CHECKPOINT_BYTES+payload,sw,sh,lengths+i);if(error)goto done;
 }
 if(inputs[0].session&&inputs[1].session&&inputs[0].slot==inputs[1].slot){error=-ENOTSUP;goto done;}
 /* Complete validation and allocation before reserving storage or starting a
  * GPU job. Never return an old CPU shadow as the composed output. */
 mbx_window_choose(c,r[2]);softpipe_resource(r[2])->mbx_content.external_only=1;c->vgp->textures.valid=0;
 for(unsigned i=0;i<2;i++)if(packets[i]){
  struct mbx_window_request q={.version=c->window_layout,.destination=14+i};
  if(ioctl(c->gpu_fd,MBX_WINDOW_BIND,&q)||write(c->gpu_fd,packets[i],lengths[i])!=(ssize_t)lengths[i]||ioctl(c->gpu_fd,MBX_WINDOW_QUERY,inputs+i)){error=-EIO;goto done;}
 }
 struct mbx_window_request merge={.version=c->window_layout,.destination=(unsigned)destination,.source={inputs[0],inputs[1]}};
 unsigned packet[20]={0x3156474dU,10,80,0,sw,sh,0,0,0,0,0x3f800000U,0,1,0,0,0,11,0,0,8};
 if(ioctl(c->gpu_fd,MBX_WINDOW_BIND,&merge)||write(c->gpu_fd,packet,sizeof packet)!=sizeof packet||ioctl(c->gpu_fd,MBX_WINDOW_QUERY,&c->window[destination].token)){error=-EIO;goto done;}
complete:;
 struct softpipe_resource *out=softpipe_resource(r[2]);++out->timestamp;mbx_content_clear(&out->mbx_content);mbx_content_complete(&out->mbx_content,out->timestamp);out->mbx_content.external_only=1;
 c->window[destination].timestamp=out->timestamp;++c->window_renders;
 *view=(struct mbx_window_view){w,h,sw,sh};error=0;
done:
 free(packets[0]);free(packets[1]);return error;
}

__attribute__((visibility("default"))) int n810_mbx_window_channels(unsigned source,unsigned mask,unsigned target,unsigned mode,struct mbx_window_view *view){
 return mbx_window_channels(source,mask,target,mode,view,NULL);
}
__attribute__((visibility("default"))) int n810_mbx_window_channels_region(unsigned source,unsigned mask,unsigned target,const struct mbx_window_rect *rect,unsigned mode,struct mbx_window_view *view){
 if(!rect)return -EINVAL;
 struct mbx_window_rect region=*rect;
 return mbx_window_channels(source,mask,target,mode,view,&region);
}
#include "mbx_window_channels_batch_impl.h"
