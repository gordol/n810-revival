/* SPDX-License-Identifier: MIT. Included once after the softpipe MBX backend.
 * GL names stay process/context local; only the fixed descriptor crosses IPC.
 */
#ifndef MBX_WINDOW_EXPORT_TEST
#include "mesa/main/context.h"
#include "mesa/main/texobj.h"
#include "mesa/state_tracker/st_context.h"
#endif
__attribute__((visibility("default"))) int n810_mbx_transaction_begin(void){return mbx_job_enter();}
__attribute__((visibility("default"))) int n810_mbx_transaction_end(void){return mbx_job_leave();}
static int mbx_window_texture(unsigned texture,struct sp_mbx_capture **capture_out,struct pipe_resource **resource_out){
 struct gl_context *ctx=_mesa_get_current_context();struct gl_texture_object *object;
 struct pipe_resource *resource;struct sp_mbx_capture *c;
 const char *device=getenv("N810_MBX_DEVICE");
 if(!ctx||!ctx->st||!ctx->st->pipe||!device||strcmp(device,"1"))return -ENODEV;
 if(mbx_job_shared()<=0||!mbx_windows_requested())return -ENOTSUP;
 object=_mesa_lookup_texture(ctx,texture);
 if(!texture||!object||object->Target!=GL_TEXTURE_2D||object->Attrib.BaseLevel||
    !object->Image[0][0]||object->Image[0][0]->NumSamples)return -EINVAL;
 if(object->pt&&object->Image[0][0]->pt&&object->pt!=object->Image[0][0]->pt)return -EINVAL;
 resource=object->pt?object->pt:object->Image[0][0]->pt;
 if(!resource)return -ENODATA;
 if(resource->target!=PIPE_TEXTURE_2D||resource->last_level||!((resource->width0==128&&resource->height0==128)||(resource->width0==240&&resource->height0==320))||resource->depth0!=1||resource->array_size!=1||
    (resource->format!=PIPE_FORMAT_R8G8B8A8_UNORM&&resource->format!=PIPE_FORMAT_B8G8R8A8_UNORM)||
    softpipe_resource(resource)->dt)return -EINVAL;
 c=capture(softpipe_context(ctx->st->pipe));
 if(!c||c->gpu_fd<0)return -ENODEV;
 if(c->window_layout==1&&(resource->width0!=128||resource->height0!=128))return -EINVAL;
 if(c->header.magic&&c->rendered_count!=c->header.triangles)return -EBUSY;
 *capture_out=c;*resource_out=resource;return 0;
}
__attribute__((visibility("default"))) int n810_mbx_window_export(unsigned texture,struct mbx_window_image *out){
 struct sp_mbx_capture *c;struct pipe_resource *resource;int error,slot;
 if(!out)return -EINVAL;
 error=mbx_job_enter();if(error)return error;
 struct mbx_job_scope scope __attribute__((cleanup(mbx_job_scope_end)))={1};
 error=mbx_window_texture(texture,&c,&resource);if(error)return error;
 slot=mbx_window_find(c,resource);
 if(slot<0||c->window[slot].imported)return -ENODATA;
 if(c->window[slot].exported)return -EBUSY;
 c->window[slot].exported=true;
 *out=(struct mbx_window_image){.version=c->window_layout,.width=resource->width0,.height=resource->height0,.format=MBX_WINDOW_LOGICAL_RGBA8,.token=c->window[slot].token,.stride_bytes=c->window_layout==2?resource->width0*4U:0};
 return 0;
}
__attribute__((visibility("default"))) int n810_mbx_window_export_release(unsigned texture,const struct mbx_window_image *image){
 struct sp_mbx_capture *c;struct pipe_resource *resource;int error,slot;
 if(!mbx_window_image_valid(image))return -EINVAL;
 error=mbx_job_enter();if(error)return error;
 struct mbx_job_scope scope __attribute__((cleanup(mbx_job_scope_end)))={1};
 error=mbx_window_texture(texture,&c,&resource);if(error)return error;
 if(image->version!=c->window_layout||image->width!=resource->width0||image->height!=resource->height0)return -EINVAL;
 slot=mbx_window_find(c,resource);
 if(slot<0||!c->window[slot].exported||memcmp(&c->window[slot].token,&image->token,sizeof(image->token)))return -ESTALE;
 c->window[slot].exported=false;return 0;
}
__attribute__((visibility("default"))) int n810_mbx_window_import(unsigned texture,const struct mbx_window_image *image){
 struct sp_mbx_capture *c;struct pipe_resource *resource;struct softpipe_resource *r;int error;
 if(!mbx_window_image_valid(image))return -EINVAL;
 error=mbx_job_enter();if(error)return error;
 struct mbx_job_scope scope __attribute__((cleanup(mbx_job_scope_end)))={1};
 error=mbx_window_texture(texture,&c,&resource);if(error)return error;
 struct mbx_window_token latest;
 if(ioctl(c->gpu_fd,MBX_WINDOW_QUERY,&latest)||latest.session!=image->token.session)return -ESTALE;
 if(image->version!=c->window_layout||image->width!=resource->width0||image->height!=resource->height0)return -EINVAL;
 unsigned slot=image->token.slot;
 if(slot>=c->window_first&&slot<c->window_first+c->window_count)return -EACCES;
 if(c->window[slot].resource&&c->window[slot].resource!=resource)return -EBUSY;
 for(unsigned i=0;i<14;++i)if(c->window[i].resource==resource&&!c->window[i].imported)return -EBUSY;
 r=softpipe_resource(resource);if(r->timestamp==UINT_MAX)return -EOVERFLOW;
 for(unsigned i=0;i<14;++i)if(i!=slot&&c->window[i].resource==resource){
  pipe_resource_reference(&c->window[i].resource,NULL);c->window[i]=(struct mbx_window_entry){0};
 }
 struct mbx_window_entry *entry=&c->window[slot];
 pipe_resource_reference(&entry->resource,resource);entry->token=image->token;entry->timestamp=++r->timestamp;entry->imported=true;
 mbx_content_clear(&r->mbx_content);mbx_content_complete(&r->mbx_content,r->timestamp);r->mbx_content.external_only=1;
 if(c->vgp)c->vgp->textures.valid=0;
 return 0;
}
__attribute__((visibility("default"))) int n810_mbx_window_forget(unsigned texture){
 struct sp_mbx_capture *c;struct pipe_resource *resource;int error;
 error=mbx_job_enter();if(error)return error;
 struct mbx_job_scope scope __attribute__((cleanup(mbx_job_scope_end)))={1};
 error=mbx_window_texture(texture,&c,&resource);if(error)return error;
 for(unsigned i=0;i<14;++i)if(c->window[i].resource==resource&&c->window[i].imported){
  pipe_resource_reference(&c->window[i].resource,NULL);c->window[i]=(struct mbx_window_entry){0};
  if(c->vgp)c->vgp->textures.valid=0;return 0;
 }
 return -ENOENT;
}

__attribute__((visibility("default"))) int n810_mbx_window_get_layout(struct mbx_window_layout *out){
 if(!out)return -EINVAL;int fd=mbx_inherited_service_fd();if(fd<0)return -ENODEV;
 if(ioctl(fd,MBX_WINDOW_LAYOUT,out))return -errno;
 return mbx_window_layout_valid(out)?0:-EPROTO;
}
#ifndef MBX_WINDOW_EXPORT_TEST
#include "mbx_window_channels_impl.h"
#endif
