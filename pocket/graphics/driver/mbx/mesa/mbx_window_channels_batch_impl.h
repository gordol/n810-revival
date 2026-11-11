/* SPDX-License-Identifier: MIT. One existing resource9 merge per atlas page. */
#include "window_channels_batch.h"
__attribute__((visibility("default"))) int n810_mbx_window_channels_batch(unsigned target,
 const struct mbx_window_channel_item *items,unsigned count,struct mbx_window_view *view){
 if(!target||!items||!count||count>MBX_WINDOW_CHANNEL_BATCH_MAX||!view)return -EINVAL;
 int error=mbx_job_enter();if(error)return error;
 struct mbx_job_scope scope __attribute__((cleanup(mbx_job_scope_end)))={1};
 struct gl_context *ctx=_mesa_get_current_context();const char *device=getenv("N810_MBX_DEVICE");
 if(!ctx||!ctx->st||!ctx->st->pipe||!device||strcmp(device,"1"))return -ENODEV;
 if(mbx_job_shared()<=0||!mbx_windows_requested())return -ENOTSUP;
 struct sp_mbx_capture *c=capture(softpipe_context(ctx->st->pipe));
 if(!c||!c->vgp||c->gpu_fd<0||mbx_export.armed||mbx_export.held||c->vgp->use_template||c->resident_dirty||
    (c->header.magic&&c->header.triangles!=c->rendered_count))return -EBUSY;
 struct gl_texture_object *object;struct pipe_resource *output;
 error=mbx_channels_texture(ctx,target,&object,&output);if(error)return error;
 if(output->width0!=128||output->height0!=128)return -ENOTSUP;
 if(output==c->reference_target)return -EBUSY;
 for(unsigned i=0;i<14;i++)if(c->window[i].resource==output&&
    (c->window[i].imported||c->window[i].exported))return -EBUSY;
 if(softpipe_resource(output)->timestamp==UINT_MAX)return -EOVERFLOW;
 struct mbx_window_upload_item *prepared=calloc(count,sizeof(*prepared));
 if(!prepared)return -ENOMEM;
 unsigned char *packet=NULL;unsigned width=0,height=0,length=0;
 const GLenum identity[4]={GL_RED,GL_GREEN,GL_BLUE,GL_ALPHA};
 for(unsigned i=0;i<count;i++){
  struct mbx_window_channel_item item=items[i];
  if(!item.source||!item.mask||item.source==target||item.mask==target||item.mode>2||
     !item.width||!item.height||item.width>128||item.height>128||
     item.dx>128-item.width||item.dy>128-item.height){error=-EINVAL;goto done;}
  struct gl_texture_object *objects[2];struct pipe_resource *r[2];
  error=mbx_channels_texture(ctx,item.source,objects,r);if(error)goto done;
  error=mbx_channels_texture(ctx,item.mask,objects+1,r+1);if(error)goto done;
  unsigned fullw=r[0]->width0,fullh=r[0]->height0;
  if(!fullw||!fullh||fullw>1024||fullh>1024||r[1]->width0!=fullw||r[1]->height0!=fullh){error=-ENOTSUP;goto done;}
  if(item.sx>=fullw||item.sy>=fullh||item.width>fullw-item.sx||item.height>fullh-item.sy){error=-EINVAL;goto done;}
  for(unsigned j=0;j<2;j++){
   const struct gl_sampler_attrib *sampler=&objects[j]->Sampler.Attrib;
   if(sampler->MinFilter!=GL_NEAREST||sampler->MagFilter!=GL_NEAREST||sampler->CompareMode||sampler->LodBias||sampler->MaxAnisotropy>1||
      (sampler->WrapS!=GL_REPEAT&&sampler->WrapS!=GL_CLAMP_TO_EDGE)||
      (sampler->WrapT!=GL_REPEAT&&sampler->WrapT!=GL_CLAMP_TO_EDGE)){error=-ENOTSUP;goto done;}
   struct softpipe_resource *s=softpipe_resource(r[j]);
   if(r[j]==output||mbx_window_find(c,r[j])>=0||s->mbx_content.external_only||!s->data||s->mbx_mapping_bytes||s->stride[0]<fullw*4U){error=-ENOTSUP;goto done;}
   struct mbx_linear_source image={(const unsigned char*)s->data+s->level_offset[0]+(size_t)item.sy*s->stride[0]+(size_t)item.sx*4U,
    (size_t)(item.height-1)*s->stride[0]+item.width*4U,s->stride[0],item.width,item.height,r[j]->format==PIPE_FORMAT_R8G8B8A8_UNORM,0,0};
   if(j)prepared[i].mask=image;else prepared[i].source=image;
  }
  for(unsigned j=0;j<3;j++)if(objects[0]->Attrib.Swizzle[j]!=identity[j]){error=-ENOTSUP;goto done;}
  unsigned channel=item.mode?0:3;
  if(objects[1]->Attrib.Swizzle[channel]!=identity[channel]){error=-ENOTSUP;goto done;}
  prepared[i].dx=item.dx;prepared[i].dy=item.dy;prepared[i].mode=item.mode;
  if(item.dx+item.width>width)width=item.dx+item.width;
  if(item.dy+item.height>height)height=item.dy+item.height;
 }
 int destination=mbx_window_available(c,output);if(destination<0){error=destination;goto done;}
 const unsigned capacity=80+128*128*8;
 packet=malloc(capacity);if(!packet){error=-ENOMEM;goto done;}
 error=mbx_window_channels_batch_pack(prepared,count,packet,capacity,&length);if(error)goto done;
 /* No target reservation or GPU work before full-page validation succeeds. */
 mbx_window_choose(c,output);softpipe_resource(output)->mbx_content.external_only=1;c->vgp->textures.valid=0;
 struct mbx_window_request request={.version=c->window_layout,.destination=(unsigned)destination};
 if(ioctl(c->gpu_fd,MBX_WINDOW_BIND,&request)||write(c->gpu_fd,packet,length)!=(ssize_t)length||
    ioctl(c->gpu_fd,MBX_WINDOW_QUERY,&c->window[destination].token)){error=-EIO;goto done;}
 struct softpipe_resource *out=softpipe_resource(output);++out->timestamp;
 mbx_content_clear(&out->mbx_content);mbx_content_complete(&out->mbx_content,out->timestamp);out->mbx_content.external_only=1;
 c->window[destination].timestamp=out->timestamp;++c->window_renders;
 *view=(struct mbx_window_view){width,height,128,128};error=0;
done:
 free(packet);free(prepared);return error;
}
