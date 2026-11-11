/* SPDX-License-Identifier: MIT. Bounded command history, never CPU pixels. */
static void mbx_history_save(struct sp_mbx_capture *c)
{
 if(!c->vgp||c->gpu_fd<0||!getenv("N810_MBX_EXPERIMENTAL_2D")||!c->header.magic||!c->reference_target)return;
 struct softpipe_resource *r=softpipe_resource(c->reference_target);
 if(r->timestamp!=c->reference_timestamp)return;
 /* Final exported surfaces have no sampleable CPU image/history contract.
  * They must be explicitly cleared before reuse, so retaining their entire
  * submitted wire stream on every FBO switch serves no future draw. */
 if(r->mbx_content.external_only&&getenv("N810_MBX_RESOURCE_REFERENCES")){c->history_skipped_bytes+=((const struct mbx_vgp_wire_frame*)c->vgp->data)->bytes;return;}
 const struct mbx_vgp_wire_frame *f=(const void *)c->vgp->data;
 if((f->version!=9&&f->version!=10)||f->bytes<64||f->bytes>sizeof(c->vgp->data))mbx_fail("invalid retained surface history");
 unsigned slot=0;
 for(unsigned i=0;i<4;++i){
  if(c->history[i].target==c->reference_target){slot=i;break;}
  if(!c->history[i].target||c->history[i].age<c->history[slot].age)slot=i;
 }
 struct mbx_surface_history *h=&c->history[slot];
 if(h->target&&h->target!=c->reference_target){struct softpipe_resource *old=softpipe_resource(h->target);++old->mbx_content.evictions;mbx_content_trace(&old->mbx_content,h->target,"history-evict");}

 if(h->target==c->reference_target&&h->timestamp==r->timestamp&&h->bytes==f->bytes){h->age=++c->history_clock;return;}
 unsigned char *wire=realloc(h->wire,f->bytes);if(!wire)mbx_fail("bounded surface history allocation failed");
 h->wire=wire;memcpy(wire,c->vgp->data,f->bytes);h->bytes=f->bytes;h->header=c->header;h->command_words=c->command_words;h->mask_commands=c->mask_commands;memcpy(h->batch_clip,c->batch_clip,sizeof h->batch_clip);
 h->timestamp=r->timestamp;h->content_generation=r->mbx_content.generation;h->age=++c->history_clock;
 pipe_resource_reference(&h->target,c->reference_target);
}
static void mbx_history_restore(struct softpipe_context *sp,struct sp_mbx_capture *c)
{
 if(!c->vgp||c->gpu_fd<0||!getenv("N810_MBX_EXPERIMENTAL_2D")||sp->framebuffer.nr_cbufs!=1||!sp->framebuffer.cbufs[0])return;
 struct pipe_surface *surface=sp->framebuffer.cbufs[0];
 if(surface->u.tex.level||surface->u.tex.first_layer||surface->u.tex.last_layer)mbx_fail("2D surface subresources unsupported");
 struct pipe_resource *target=surface->texture;
 if(c->header.magic&&c->reference_target==target)return;
 for(unsigned i=0;i<4;++i){struct mbx_surface_history *h=&c->history[i];
  if(h->target!=target)continue;
  if(h->content_generation!=softpipe_resource(target)->mbx_content.generation||h->timestamp!=softpipe_resource(target)->timestamp)mbx_fail("GPU target changed outside retained command history");
  if(h->header.width!=sp->framebuffer.width||h->header.height!=sp->framebuffer.height)mbx_fail("retained surface view changed");
  if(++c->vgp->resource_epoch==0)mbx_fail("resource epoch exhausted");
  memcpy(c->vgp->data,h->wire,h->bytes);c->header=h->header;c->command_words=h->command_words;c->mask_commands=h->mask_commands;memcpy(c->batch_clip,h->batch_clip,sizeof c->batch_clip);
  pipe_resource_reference(&c->reference_target,target);c->reference_timestamp=h->timestamp;
  c->rendered_count=h->header.triangles;c->texture_bound=false;c->state_ready=false;
  c->vgp->update_bytes=sizeof(struct mbx_vgp_wire_update);c->frame_started=mbx_time_ns();c->geometry_begin=mbx_trace_begin();
  ++softpipe_resource(target)->mbx_content.restores;mbx_content_trace(&softpipe_resource(target)->mbx_content,target,"history-hit");
  h->age=++c->history_clock;return;
 }
 struct softpipe_resource *r=softpipe_resource(target);
 mbx_content_trace(&r->mbx_content,target,"history-miss");
 if(getenv("N810_MBX_SURFACE_DIAGNOSTICS"))fprintf(stderr,"MBX_SURFACE_VIEW id=%u resource=%ux%u view=%ux%u format=%u stride=%u timestamp=%u\n",r->mbx_content.id,target->width0,target->height0,sp->framebuffer.width,sp->framebuffer.height,target->format,r->stride[0],r->timestamp);
 if(!mbx_content_ready(&r->mbx_content,r->timestamp)){
  mbx_fail(r->mbx_content.external_writes?"surface contents externally modified; explicit import required":"surface has no completed initialized contents");
 }
 /* Reuse only the previously proven BGRA background contract. Never clear
  * a valid surface to hide a replay-cache miss. Other formats remain gated. */
 if(!getenv("N810_MBX_SURFACE_RECOVERY")||!getenv("N810_MBX_SURFACE_CHECKPOINT")||
    target->format!=PIPE_FORMAT_B8G8R8A8_UNORM||sp->framebuffer.width!=240||sp->framebuffer.height!=320||
    target->width0!=240||target->height0!=320||r->dt||!r->data||r->stride[0]<960||r->stride[0]>UINT_MAX/320U)
  mbx_fail("completed surface preserved; GPU background restoration not admitted for this view");
 if(c->vgp->use_template||
    (getenv("N810_MBX_ASYNC")&&strcmp(getenv("N810_MBX_ASYNC"),"0"))||
    (getenv("N810_MBX_SHARED_IMAGE")&&strcmp(getenv("N810_MBX_SHARED_IMAGE"),"0")))
  mbx_fail("completed surface restore requires synchronous private ownership");
 if(++c->vgp->resource_epoch==0)mbx_fail("resource epoch exhausted");
 if(mbx_surface_checkpoint(c->vgp->data,sizeof(c->vgp->data),r->data,r->stride[0]*320U,r->stride[0],240,320))
  mbx_fail("completed resource background reconstruction rejected");
 c->header=(struct mbx_frame){.magic=0x3146424d,.version=1,.header_bytes=sizeof(struct mbx_frame),.triangle_bytes=sizeof(struct mbx_triangle),.width=240,.height=320};
 pipe_resource_reference(&c->reference_target,target);c->reference_timestamp=r->timestamp;
 c->mask_commands=0;c->batch_clip[0]=c->batch_clip[1]=0;c->batch_clip[2]=240;c->batch_clip[3]=320;c->command_words=512;c->rendered_count=0;c->texture_bound=false;c->state_ready=false;
 c->vgp->update_bytes=sizeof(struct mbx_vgp_wire_update);c->frame_started=mbx_time_ns();c->geometry_begin=mbx_trace_begin();
 ++r->mbx_content.restores;mbx_content_trace(&r->mbx_content,target,"completed-image-restore");

}
