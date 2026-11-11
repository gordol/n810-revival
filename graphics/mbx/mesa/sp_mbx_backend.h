#include "mbx_template_update.h"
/* SPDX-License-Identifier: MIT
 * Userspace fixed-function raster transport. Included after private Mesa
 * capture structures; never executes CPU fragment rasterization.
 */
extern void n810_mbx_async_drain(void);
extern int n810_mbx_async_submit(struct sw_displaytarget *,int,const void *,size_t,size_t);
extern int n810_mbx_shared_bind(struct sw_displaytarget *,int,size_t);
struct mbx_wire_vertex { uint32_t x,y,z,w,color; };
struct mbx_wire_primitive { uint32_t depth,write,func,smooth; struct mbx_wire_vertex v[3]; };
struct mbx_wire_job { uint32_t magic,version,count,width,height,reserved; struct mbx_wire_primitive p[512]; };
_Static_assert(sizeof(struct mbx_wire_primitive)==76,"MBX primitive ABI");
static void mbx_fail(const char *reason)
{
   fprintf(stderr,"N810_MBX_GPU_FAILED: %s; no software raster fallback\n",reason);
   /* A fatal renderer-thread error must not run process-global destructors
    * concurrently with native guest/service threads. Kernel FD cleanup and
    * the independent supervisor remain responsible for GPU/device cleanup. */
   fflush(stderr);
   _exit(1);
}
#include "mbx_window_cache.h"
#include "separate_blend.c"
#include "surface_checkpoint.h"
#include "channel_rows.h"
#include "channel_wire.c"
#include "resident_checkpoint.h"
#include "mbx_surface_export.h"
static void mbx_separate_read(int fd,void *out,size_t bytes)
{
 size_t got=0;while(got<bytes){ssize_t n=read(fd,(char*)out+got,bytes-got);if(n<=0)mbx_fail("separate-alpha GPU readback failed");got+=n;}
}
static uint32_t mbx_float_bits(float f)
{ uint32_t v; memcpy(&v,&f,4); return v; }
/* Binary32 exponent validation avoids serial VFP-to-ARM flag transfers.
 * Preserve every finite value, including subnormals and signed zero. */
static inline bool mbx_finite4(const float *v)
{
 uint32_t b[4];memcpy(b,v,sizeof(b));
 return (b[0]&0x7fffffffu)<0x7f800000u && (b[1]&0x7fffffffu)<0x7f800000u &&
        (b[2]&0x7fffffffu)<0x7f800000u && (b[3]&0x7fffffffu)<0x7f800000u;
}
static bool mbx_pack_direct(struct mbx_wire_primitive *p,struct mbx_color_cache *cache,
                            const float (*vertices[3])[4],const float (*provoking)[4],unsigned slot,bool smooth)
{
   p->depth=p->write=p->func=1;p->smooth=smooth;
   uint32_t flat=0;
   if(!smooth){
      if(!mbx_finite4(provoking[slot]))return false;
      flat=mbx_cached_color(cache,provoking[slot]);
   }
   for(unsigned i=0;i<3;++i){
      if(!mbx_finite4(vertices[i][0]))return false;
      memcpy(&p->v[i].x,vertices[i][0],16);
      if(smooth){
         if(!mbx_finite4(vertices[i][slot]))return false;
         p->v[i].color=mbx_cached_color(cache,vertices[i][slot]);
      }else p->v[i].color=flat;
   }
   return true;
}
static void mbx_fill_job(struct sp_mbx_capture *c,struct mbx_wire_job *job)
{
   unsigned count=c->header.triangles;
   if(count>512||c->header.width>512||c->header.height>512||(c->header.width&1))
      mbx_fail("frame exceeds bounded service capacity");
   memset(job,0,24);job->magic=0x314a424d;job->version=2;
   job->width=c->header.width;job->height=c->header.height;job->count=count;
   for(unsigned i=0;i<count;++i){
      const struct mbx_triangle *t=&c->triangles[i];
      struct mbx_wire_primitive *p=&job->p[i];
      p->depth=p->write=p->func=1;p->smooth=t->interpolation==SP_INTERP_PERSPECTIVE;
      uint32_t flat=p->smooth?0:mbx_cached_color(&c->color_cache,t->vertex[0].color);
      for(unsigned j=0;j<3;++j){
         const float *v=t->vertex[j].position,*color=t->vertex[j].color;
         p->v[j].x=mbx_float_bits(v[0]);p->v[j].y=mbx_float_bits(v[1]);
         p->v[j].z=mbx_float_bits(v[2]);p->v[j].w=mbx_float_bits(v[3]);
         p->v[j].color=p->smooth?mbx_cached_color(&c->color_cache,color):flat;
      }
   }
}

static uint64_t mbx_time_ns(void)
{ if(!mbx_debug_enabled())return 0; struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (uint64_t)t.tv_sec*1000000000+t.tv_nsec; }

void sp_mbx_present(struct softpipe_context *sp)
{
   if(mbx_debug_enabled())mbx_profile_poll();
   struct sp_mbx_capture *c=sp->mbx_capture;
   if(!c||c->gpu_fd<0||!c->header.magic)return;
   if(c->rendered_count==c->header.triangles){
      if(!c->defer_readback)mbx_resident_materialize(c,true);
      return;
   }
   /* Sample steady rendering after shader verification and startup settle. */
   if(mbx_debug_enabled()&&c->profile_frames==200)mbx_profile_begin();
   bool surface2d=c->vgp&&(((struct mbx_vgp_wire_frame *)c->vgp->data)->version==9||((struct mbx_vgp_wire_frame *)c->vgp->data)->version==10);
   if(c->header.rejected||c->header.scissored_clear||(!surface2d&&c->header.clear_depth!=1.0f))
      mbx_fail("unsupported framebuffer clear/state");
   for(unsigned i=0;i<4;++i){
      float value=c->header.clear_color[i];
      if(c->vgp&&((struct mbx_vgp_wire_frame *)c->vgp->data)->version>=9){
         if(!(value>=0.0f&&value<=1.0f))mbx_fail("2D clear color outside normalized range");
      }else if(value!=0.0f)mbx_fail("nonblack clear unsupported during bring-up");
   }
   if(!c->reference_target)mbx_fail("missing render target");
   struct softpipe_resource *r=softpipe_resource(c->reference_target);
   if(surface2d&&r->timestamp!=c->reference_timestamp)
      mbx_fail("GPU target changed outside retained command history");
   struct sw_winsys *winsys=softpipe_screen(sp->pipe.screen)->winsys;
   mbx_trace_end("geometry",c->geometry_begin,c->header.triangles);
   struct mbx_trace_stamp trace=mbx_trace_begin();
   void *map=r->dt ? winsys->displaytarget_map(winsys,r->dt,PIPE_MAP_WRITE) : r->data;
   if(!map)mbx_fail("render target mapping failed");
   mbx_trace_end("target_map",trace,1);trace=mbx_trace_begin();
   uint64_t t0=mbx_time_ns(),t1,t2,t3,t4;
   if(c->frame_started)c->profile_geometry+=t0-c->frame_started;
   unsigned width=c->header.width,height=c->header.height;
   size_t total=(size_t)width*height,got=0;
   if(total>512*512&&!(surface2d&&width==800&&height==480&&r->base.format==PIPE_FORMAT_B5G6R5_UNORM&&getenv("N810_MBX_DESKTOP_TARGET")&&!strcmp(getenv("N810_MBX_DESKTOP_TARGET"),"1")))mbx_fail("presentation capacity exceeded");
   if(!c->wire_job)c->wire_job=malloc(sizeof(struct mbx_wire_job));
   if(c->pixel_capacity<total){
      free(c->pixels);free(c->rgba);
      c->pixels=malloc(total*4);c->rgba=malloc(total*4);c->pixel_capacity=total;
   }
   struct mbx_wire_job *job=c->wire_job;
   uint16_t *pixels=c->pixels;uint8_t *rgba=c->rgba;
   if(!job||!pixels||!rgba)mbx_fail("presentation allocation failed");
   if(c->vgp){ /* Raw GPU vertex queue is already assembled. */ }else if(c->direct_pack){
      if(c->header.triangles>512||width>512||height>512||(width&1))mbx_fail("direct frame exceeds capacity");
      memset(job,0,24);job->magic=0x314a424d;job->version=2;
      job->count=c->header.triangles;job->width=width;job->height=height;
      if(c->direct_pack_check){
         struct mbx_wire_job *reference=malloc(sizeof(*reference));
         if(!reference)mbx_fail("direct packet verification allocation");
         mbx_fill_job(c,reference);
         bool equal=!memcmp(job,reference,24+job->count*sizeof(job->p[0]));free(reference);
         if(!equal)mbx_fail("direct geometry packet mismatch");
         if(++c->direct_pack_verified==10){
            c->direct_pack_check=false;
            if(mbx_debug_enabled()) fprintf(stderr,"N810_MBX_DIRECT_PACK_VERIFIED frames=10 bit_exact=1\n");
         }
      }
   }else mbx_fill_job(c,job);
   bool native=r->base.format==PIPE_FORMAT_B5G6R5_UNORM;
   bool native32=c->vgp&&((struct mbx_vgp_wire_frame *)c->vgp->data)->version==10;
   if(native32&&r->base.format!=PIPE_FORMAT_B8G8R8A8_UNORM&&r->base.format!=PIPE_FORMAT_R8G8B8A8_UNORM)
      mbx_fail("32-bit target format changed during frame");
   if(native&&!c->vgp){job->version=3;job->reserved=r->stride[0];}
   size_t read_bytes=native&&!c->vgp?(size_t)r->stride[0]*height:total*(native32?4:2);
   /* A tight native target can receive the checked kernel read directly.
    * Padded targets keep the established row-copy path. Completion stays
    * synchronous; all kernel validation and buffer bounds stay unchanged. */
   bool direct_native=native&&r->stride[0]==width*2;
   void *read_target=native&&(!c->vgp||direct_native)?map:pixels;
   if(!c->profile_frames)if(mbx_debug_enabled()) fprintf(stderr,"N810_MBX_NATIVE_READ direct=%u stride=%u row_bytes=%u\n",direct_native,r->stride[0],width*(native32?4:2));
   mbx_trace_end("packet_build",trace,c->header.triangles);trace=mbx_trace_begin();
   bool window_target=mbx_windows_requested()&&native32&&width==128&&height==128&&!r->dt;
   unsigned window_slot=window_target?mbx_window_choose(c,&r->base):0;
   if(window_target&&c->vgp->textures.valid){
      /* Uploaded glyph/texture bytes survive image rendering. Retire only a
       * descriptor snapshot containing image tokens that might be replaced. */
      unsigned table[4];memcpy(table,c->vgp->textures.descriptors,16);
      for(unsigned i=0;i<table[0];i++){struct mbx_wire_resource d;memcpy(&d,c->vgp->textures.descriptors+16+16*i,16);if(d.version==13)c->vgp->textures.valid=0;}
   }
   bool export_surface=mbx_export.armed;
   if(mbx_export.held)mbx_fail("borrowed surface cannot be overwritten");
   if(export_surface&&(!native||native32||!c->vgp||r->dt||!surface2d))mbx_fail("surface export requires private RGB565 final target");
   bool shared=getenv("N810_MBX_SHARED_IMAGE")&&!strcmp(getenv("N810_MBX_SHARED_IMAGE"),"1");
   bool async=getenv("N810_MBX_ASYNC")&&!strcmp(getenv("N810_MBX_ASYNC"),"1");
   if(export_surface&&(shared||async||c->defer_readback))mbx_fail("surface export ownership mode conflict");
   if(c->vgp&&c->vgp->use_template&&async)mbx_fail("template updates require synchronous ownership");
   if(c->vgp&&(shared&&r->stride[0]!=width*2))mbx_fail("GPU vertex shared image stride mismatch");
   if(async&&(!shared||!native||!r->dt))mbx_fail("async requires native shared target");
   if(!async&&shared&&(!native||!r->dt||n810_mbx_shared_bind(r->dt,c->gpu_fd,read_bytes)))
      mbx_fail("shared GPU image unavailable");
   mbx_trace_end("target_reuse_wait",trace,1);trace=mbx_trace_begin();
   t1=mbx_time_ns();
   if(c->vgp&&((struct mbx_vgp_wire_frame*)c->vgp->data)->version==10&&
      mbx_wire_resources_compact(c->vgp->data,sizeof(c->vgp->data)))mbx_fail("private resource assembly normalization failed");
   size_t bytes=24+job->count*sizeof(job->p[0]);
   void *submit_job=job;
   if(c->vgp){submit_job=c->vgp->data;bytes=((struct mbx_vgp_wire_frame *)submit_job)->bytes;}
   /* Diagnostic write-ahead capture, deliberately excluded from FPS runs.
    * Keep the exact annotated frame even if the subsequent GPU write fails.
    * Atomic replace retains only one bounded private frame, never a release. */
   if(c->vgp&&getenv("N810_MBX_PRIVATE_PENDING_WIRE")){
      const struct mbx_vgp_wire_frame *f=submit_job;
      if(f->draws>=32){
         const char *dir="/home/nokia/.local/share/symbian-private/runtime";
         int dfd=open(dir,O_RDONLY|O_DIRECTORY|O_NOFOLLOW);
         if(dfd<0)mbx_fail("private pending directory unavailable");
         int fd=openat(dfd,"pending-vgp.tmp",O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW,0600);
         if(fd<0){close(dfd);mbx_fail("private pending capture open failed");}
         size_t saved=0;
         while(saved<bytes){ssize_t n=write(fd,(const char*)submit_job+saved,bytes-saved);
            if(n<0&&errno==EINTR)continue;
            if(n<=0){close(fd);unlinkat(dfd,"pending-vgp.tmp",0);close(dfd);mbx_fail("private pending capture write failed");}saved+=n;
         }
         if(fsync(fd)){close(fd);close(dfd);mbx_fail("private pending capture sync failed");}close(fd);
         if(renameat(dfd,"pending-vgp.tmp",dfd,"pending-vgp.wire")||fsync(dfd)){close(dfd);mbx_fail("private pending capture publish failed");}
         close(dfd);
         if(mbx_debug_enabled()) fprintf(stderr,"GPU_PENDING_WIRE draws=%u bytes=%zu target=%u,%u\n",f->draws,bytes,f->width,f->height);
      }
   }
   const unsigned combine_jobs=mbx_resident_requested()&&width==240&&height==320?1:(height+191)/192;
   unsigned separate_draws=0;
   if(native32&&getenv("N810_MBX_SEPARATE_ALPHA")){
      if(mbx_split_separate_blend(submit_job,bytes,NULL,NULL,0,&separate_draws))mbx_fail("separate-alpha command validation failed");
      if(separate_draws){
         if(async||shared||c->vgp->use_template)mbx_fail("separate-alpha requires synchronous private buffers");
         if(!c->separate_rgb_wire)c->separate_rgb_wire=malloc(MBX_VGP_WIRE_MAX_BYTES);
         if(!c->separate_alpha_wire)c->separate_alpha_wire=malloc(MBX_VGP_WIRE_MAX_BYTES);
         if(!c->separate_merge_wire)c->separate_merge_wire=malloc(640080);
         if(!c->separate_rgb_wire||!c->separate_alpha_wire||!c->separate_merge_wire)mbx_fail("separate-alpha buffers unavailable");
         if(mbx_split_separate_blend(submit_job,bytes,c->separate_rgb_wire,c->separate_alpha_wire,MBX_VGP_WIRE_MAX_BYTES,&separate_draws))mbx_fail("separate-alpha replay split failed");
         submit_job=c->separate_rgb_wire;
      }
   }
   bool gpu_merge=separate_draws&&mbx_resident_requested()&&getenv("N810_MBX_RESIDENT_ALPHA")&&
      !strcmp(getenv("N810_MBX_RESIDENT_ALPHA"),"1")&&width==240&&height==320;
   struct mbx_resident_token rgb_token={0},alpha_token={0};
   unsigned rgb_slot=0,alpha_slot=1,merge_slot=2;
   if(gpu_merge){
      struct mbx_image_layout layout;
      if(ioctl(c->gpu_fd,MBX_IMAGE_LAYOUT,&layout)||layout.version!=1||layout.images!=3||layout.image_bytes<read_bytes)
         mbx_fail("resident alpha requires three owned images");
      if(c->resident_dirty){merge_slot=c->resident_token.slot;rgb_slot=(merge_slot+1)%3;alpha_slot=(merge_slot+2)%3;}
      if(ioctl(c->gpu_fd,MBX_IMAGE_SELECT,&rgb_slot))mbx_fail("resident RGB target selection failed");
   }
   bool resident_job=c->resident_dirty;
   bool want_resident=c->defer_readback&&native32&&width==240&&height==320&&
      r->base.format==PIPE_FORMAT_B8G8R8A8_UNORM&&!r->dt;
   bool keep_resident=window_target||(want_resident&&!separate_draws);
   if((resident_job||keep_resident)&&(async||shared||c->vgp->use_template))mbx_fail("resident ownership mode conflict");
   if(resident_job){
      struct mbx_resident_bind bind={.version=1,.destination=gpu_merge?rgb_slot:(c->resident_token.slot==0?1:0),.source=c->resident_token};
      if(ioctl(c->gpu_fd,MBX_RESIDENT_BIND,&bind))mbx_fail("resident source token rejected");
   }
   bool template_update=false;
   if(c->vgp&&c->vgp->use_template){
      struct mbx_vgp_queue *q=c->vgp;
      struct mbx_vgp_wire_frame *f=(void *)q->data;
      for(unsigned slot=0;slot<MBX_VGP_PREPARED_SLOTS;++slot){
         if(q->template_slot_generation[slot]&&mbx_template_update(q->template_snapshot[slot],q->template_snapshot_bytes[slot],
               f,bytes,q->template_slot_generation[slot],q->update,MBX_VGP_UPDATE_MAX_BYTES,&q->update_bytes)){
            q->template_generation=q->template_slot_generation[slot];
            submit_job=q->update;bytes=q->update_bytes;template_update=true;break;
         }
      }
   }
   bool texture_residency=c->vgp&&getenv("N810_MBX_TEXTURE_RESIDENCY")&&!strcmp(getenv("N810_MBX_TEXTURE_RESIDENCY"),"1");
   bool texture_reference=false;
   unsigned canonical_bytes=bytes;
   if(texture_residency){
      struct mbx_vgp_queue *q=c->vgp;
      if(async||shared||q->use_template||(!window_target&&(separate_draws||keep_resident))||resident_job)
         mbx_fail("texture residency requires synchronous private canonical jobs");
      if(!q->textures.data){q->textures.data=malloc(MBX_WIRE_LINEAR_PAYLOAD);q->texture_compact=malloc(MBX_VGP_WIRE_MAX_BYTES+32);if(!q->textures.data||!q->texture_compact)mbx_fail("texture residency allocation");}
      unsigned compact_bytes;
      if(!mbx_texture_ref_pack(&q->textures,submit_job,bytes,q->texture_compact,MBX_VGP_WIRE_MAX_BYTES+32,&compact_bytes)||
         (getenv("N810_MBX_TEXTURE_SUBSET")&&!strcmp(getenv("N810_MBX_TEXTURE_SUBSET"),"1")&&!mbx_texture_ref_pack_subset(&q->textures,submit_job,bytes,q->texture_compact,MBX_VGP_WIRE_MAX_BYTES+32,&compact_bytes))){
         texture_reference=true;submit_job=q->texture_compact;bytes=compact_bytes;++q->texture_compact_jobs;q->texture_compact_bytes+=bytes;
      }
   }
   if(window_target)mbx_window_bind_target(c,separate_draws?14:window_slot);
   if(async){if(n810_mbx_async_submit(r->dt,c->gpu_fd,submit_job,bytes,read_bytes))mbx_fail("async submission failed");}
   else {ssize_t sent=write(c->gpu_fd,submit_job,bytes);if(sent!=(ssize_t)bytes){int failure=errno;fprintf(stderr,"N810_MBX_WRITE_REJECT sent=%ld bytes=%zu errno=%d fd=%d\n",(long)sent,bytes,failure,c->gpu_fd);mbx_fail("GPU frame rejected or failed");}}
   if(texture_residency&&!texture_reference){
      struct mbx_vgp_queue *q=c->vgp;struct mbx_texture_resident_info info;struct mbx_wire_resources rr;
      if(ioctl(c->gpu_fd,MBX_TEXTURE_RESIDENT_INFO,&info)||info.version!=1)mbx_fail("texture residency receipt unavailable");
      if(mbx_wire_resources_parse(q->data,canonical_bytes,&rr))mbx_fail("texture residency canonical frame rejected");
      if(info.generation&&mbx_texture_resident_eligible(&rr)){
         if(!mbx_texture_resident_matches(&q->textures,q->data,&rr)&&mbx_texture_resident_commit(&q->textures,q->data,&rr))mbx_fail("texture residency snapshot rejected");
         if(info.bytes!=rr.bytes)mbx_fail("texture residency byte count mismatch");
         q->textures.generation=info.generation;q->textures.session=info.session;q->textures.valid=1;
      }else if(!info.generation||info.generation!=q->textures.generation||info.session!=q->textures.session)q->textures.valid=0;
   }
   if(c->vgp&&c->vgp->use_template){
      struct mbx_vgp_queue *q=c->vgp;
      if(template_update){++q->template_updates;q->template_update_bytes+=bytes;}
      else{
         struct mbx_template_info info;
         ++q->template_uploads;q->template_upload_bytes+=bytes;q->template_generation=0;
         if(ioctl(c->gpu_fd,MBX_TEMPLATE_INFO,&info)){
            if(errno!=ENODATA)mbx_fail("GPU template query failed");
         }else{
            struct mbx_vgp_wire_frame *f=(void *)q->data;
            if(info.version!=1||!info.generation||info.bytes!=f->bytes||info.draws!=f->draws)
               mbx_fail("GPU template identity mismatch");
            unsigned slot=q->template_next;
            q->template_next=(slot+1)%MBX_VGP_PREPARED_SLOTS;
            if(q->template_snapshot_capacity[slot]<bytes){
               unsigned char *saved=realloc(q->template_snapshot[slot],bytes);
               if(!saved)mbx_fail("prepared frame snapshot allocation");
               q->template_snapshot[slot]=saved;q->template_snapshot_capacity[slot]=bytes;
            }
            memcpy(q->template_snapshot[slot],f,bytes);q->template_snapshot_bytes[slot]=bytes;
            q->template_slot_generation[slot]=info.generation;
            q->template_generation=info.generation;q->template_frame=*f;
         }
         q->template_dirty=false;
      }
      if(!c->profile_frames||c->profile_frames%120==0)if(mbx_debug_enabled()) fprintf(stderr,
         "N810_MBX_TEMPLATE uploads=%u updates=%u upload_bytes=%llu update_bytes=%llu generation=%u\n",
         q->template_uploads,q->template_updates,(unsigned long long)q->template_upload_bytes,
         (unsigned long long)q->template_update_bytes,q->template_generation);
   }
   mbx_trace_end(async?"queue_submit":"gpu_submit",trace,c->header.triangles);trace=mbx_trace_begin();
   t2=mbx_time_ns();
   if(window_target){c->resident_dirty=false;}else if(keep_resident){
      if(ioctl(c->gpu_fd,MBX_RESIDENT_QUERY,&c->resident_token))mbx_fail("resident completion token missing");
      c->resident_dirty=true;c->resident_skipped_bytes+=read_bytes;
   }else c->resident_dirty=false;
   if(gpu_merge&&ioctl(c->gpu_fd,MBX_RESIDENT_QUERY,&rgb_token))mbx_fail("resident RGB completion missing");
   if(export_surface){
      if(gpu_merge||keep_resident||separate_draws)mbx_fail("surface export requires one RGB565 completion");
      if(ioctl(c->gpu_fd,MBX_SURFACE_ACQUIRE,&mbx_export.image))mbx_fail("completed surface acquire failed");
      mbx_export.fd=dup(c->gpu_fd);
      if(mbx_export.fd<0){ioctl(c->gpu_fd,MBX_SURFACE_RELEASE,&mbx_export.image);mbx_fail("surface owner reference failed");}
      mbx_export.held=1;
   }
   while(!export_surface&&!gpu_merge&&!keep_resident&&!shared&&got<read_bytes){
      ssize_t n=read(c->gpu_fd,(char *)read_target+got,read_bytes-got);
      if(n<=0)mbx_fail("GPU readback failed");
      got+=n;
   }
   if(window_target&&separate_draws){
      struct mbx_window_token rgb,alpha;
      if(ioctl(c->gpu_fd,MBX_WINDOW_QUERY,&rgb))mbx_fail("window RGB completion missing");
      mbx_window_bind_target(c,15);
      const void *alpha_job=c->separate_alpha_wire;unsigned alpha_bytes=canonical_bytes;
      if(texture_residency){
         struct mbx_vgp_queue *q=c->vgp;unsigned packed;
         if(!mbx_texture_ref_pack(&q->textures,alpha_job,alpha_bytes,q->texture_compact,MBX_VGP_WIRE_MAX_BYTES+32,&packed)||
            !mbx_texture_ref_pack_subset(&q->textures,alpha_job,alpha_bytes,q->texture_compact,MBX_VGP_WIRE_MAX_BYTES+32,&packed)){
            alpha_job=q->texture_compact;alpha_bytes=packed;++q->texture_compact_jobs;q->texture_compact_bytes+=packed;
         }
      }
      if(write(c->gpu_fd,alpha_job,alpha_bytes)!=(ssize_t)alpha_bytes||ioctl(c->gpu_fd,MBX_WINDOW_QUERY,&alpha))mbx_fail("window alpha render failed");
      struct mbx_window_request merge={.version=1,.destination=window_slot,.source={rgb,alpha}};
      unsigned packet[20]={0x3156474dU,10,80,0,128,128,0,0,0,0,0x3f800000U,0,1,0,0,0,11,0,0,8};
      if(ioctl(c->gpu_fd,MBX_WINDOW_BIND,&merge)||write(c->gpu_fd,packet,sizeof(packet))!=sizeof(packet))mbx_fail("window alpha merge failed");
   }else if(gpu_merge){
      if(resident_job){
         struct mbx_resident_bind bind={.version=1,.destination=alpha_slot,.source=c->resident_token};
         if(ioctl(c->gpu_fd,MBX_RESIDENT_BIND,&bind))mbx_fail("resident alpha source rejected");
      }else if(ioctl(c->gpu_fd,MBX_IMAGE_SELECT,&alpha_slot))mbx_fail("resident alpha target selection failed");
      if(write(c->gpu_fd,c->separate_alpha_wire,bytes)!=(ssize_t)bytes||
         ioctl(c->gpu_fd,MBX_RESIDENT_QUERY,&alpha_token))mbx_fail("resident alpha replay failed");
      struct mbx_resident_merge merge={.version=1,.destination=merge_slot,.rgb=rgb_token,.alpha=alpha_token};
      unsigned packet[20]={0x3156474dU,10,80,0,240,320,0,0,0,0,0x3f800000U,0,1,0,0,0,11,0,0,8};
      if(ioctl(c->gpu_fd,MBX_RESIDENT_MERGE,&merge)||write(c->gpu_fd,packet,sizeof(packet))!=sizeof(packet))
         mbx_fail("resident channel merge failed");
      c->resident_skipped_bytes+=2*read_bytes;
      if(want_resident){
         if(ioctl(c->gpu_fd,MBX_RESIDENT_QUERY,&c->resident_token))mbx_fail("resident merge completion missing");
         keep_resident=true;c->resident_dirty=true;c->resident_skipped_bytes+=read_bytes;
      }else mbx_separate_read(c->gpu_fd,pixels,read_bytes);
      if(!c->separate_reported)if(mbx_debug_enabled()) fprintf(stderr,"N810_MBX_SEPARATE_ALPHA resident_merge=1 intermediate_read_bytes=0 merge_upload_bytes=0 CPU_blended_pixels=0\n");
      c->separate_reported=true;
   }else if(separate_draws){
      if(resident_job){
         /* Replay alpha against the SAME immutable source as RGB. RGB has
          * already been read; overwrite only its destination bank. */
         struct mbx_resident_bind bind={.version=1,.destination=(c->resident_token.slot==0?1:0),.source=c->resident_token};
         if(ioctl(c->gpu_fd,MBX_RESIDENT_BIND,&bind))mbx_fail("resident alpha source token rejected");
      }
      if(write(c->gpu_fd,c->separate_alpha_wire,bytes)!=(ssize_t)bytes)mbx_fail("separate-alpha GPU replay failed");
      mbx_separate_read(c->gpu_fd,rgba,read_bytes);
      for(unsigned y=0;y<height;){
         unsigned start,rows;
         if(mbx_resident_requested()&&width==240&&height==320){start=0;rows=320;}
         else if(mbx_channel_rows(height,y,&start,&rows))mbx_fail("separate-alpha row plan failed");
         unsigned region_bytes=width*rows*4,packet_bytes=0;unsigned char *rgb_region=(unsigned char*)pixels+(size_t)start*width*4;
         if(mbx_pack_channel_region(width,rows,8,rgb_region,region_bytes,rgba+(size_t)start*width*4,region_bytes,c->separate_merge_wire,640080,&packet_bytes))mbx_fail("separate-alpha channel packet failed");
         if(write(c->gpu_fd,c->separate_merge_wire,packet_bytes)!=(ssize_t)packet_bytes)mbx_fail("separate-alpha GPU combine failed");
         if(want_resident&&start==0&&rows==320){
            if(ioctl(c->gpu_fd,MBX_RESIDENT_QUERY,&c->resident_token))mbx_fail("resident alpha completion token missing");
            keep_resident=true;c->resident_dirty=true;c->resident_skipped_bytes+=region_bytes;
         }else mbx_separate_read(c->gpu_fd,rgb_region,region_bytes);
         y=start+rows;
      }
      if(!c->separate_reported)if(mbx_debug_enabled()) fprintf(stderr,"N810_MBX_SEPARATE_ALPHA draws=%u replay_passes=2 combine_jobs=%u CPU_blended_pixels=0\n",separate_draws,combine_jobs);
      c->separate_reported=true;
   }
   mbx_trace_end("readback",trace,got);trace=mbx_trace_begin();
   t3=mbx_time_ns();
   if(export_surface||keep_resident){ /* Completed pixels stay in the kernel-owned image. */
   }else if(native32){
      /* GPU output is physically verified little-endian BGRA8. Copy/swizzle
       * only; preserve every color and alpha bit, with no CPU rasterization. */
      for(unsigned y=0;y<height;++y){
         const uint32_t *src=(const uint32_t *)pixels+y*width;
         uint32_t *dst=(uint32_t *)((char *)map+y*r->stride[0]);
         if(r->base.format==PIPE_FORMAT_B8G8R8A8_UNORM)memcpy(dst,src,width*4);
         else for(unsigned x=0;x<width;++x){uint32_t v=src[x];dst[x]=(v&0xff00ff00)|((v&255)<<16)|((v>>16)&255);}
      }
   }else if(native){
      if(c->vgp&&!shared&&!direct_native)for(unsigned y=0;y<height;++y)
         memcpy((char *)map+y*r->stride[0],pixels+y*width,width*2);
      /* Completed GPU rows already occupy the X shared-memory image. */
   }else if(r->base.format==PIPE_FORMAT_B8G8R8A8_UNORM||r->base.format==PIPE_FORMAT_B8G8R8X8_UNORM){
      if(!c->expand_ready){
         for(unsigned i=0;i<256;++i){
            unsigned p=i<<8;
            c->expand_hi[i]=0xff000000|((p&0xf800)<<8)|((p&0xe000)<<3)|((p&0x07e0)<<5)|((p&0x0600)>>1);
            c->expand_lo[i]=((i&0xe0)<<5)|((i&31)<<3)|((i&28)>>2);
         }
         c->expand_ready=true;
      }
      const uint32_t *restrict hi=c->expand_hi,*restrict lo=c->expand_lo;
      for(unsigned y=0;y<height;++y){
         uint32_t *restrict dst=(uint32_t *)((char *)map+y*r->stride[0]);
         const uint16_t *restrict src=pixels+y*width;
         for(unsigned x=0;x<width;++x){
            uint32_t p=src[x];
            dst[x]=hi[p>>8]|lo[p&255];
         }
      }
   }else{
   for(size_t i=0;i<total;++i){
      unsigned p=pixels[i],red=p>>11,green=(p>>5)&63,blue=p&31;
      rgba[4*i]=(red<<3)|(red>>2);rgba[4*i+1]=(green<<2)|(green>>4);
      rgba[4*i+2]=(blue<<3)|(blue>>2);rgba[4*i+3]=255;
   }
   util_format_write_4ub(r->base.format,rgba,width*4,map,r->stride[0],0,0,width,height);
   }
   mbx_trace_end("convert",trace,native?0:total);
   t4=mbx_time_ns();
   c->profile_pack+=t1-t0;c->profile_submit+=t2-t1;
   c->profile_read+=t3-t2;c->profile_present+=t4-t3;
   if(c->vgp&&c->profile_frames&&c->profile_frames%120==0)if(mbx_debug_enabled()) fprintf(stderr,"N810_MBX_RETAIN enabled=%u skipped_bytes=%llu copied_bytes=%llu\n",c->vgp->retain,(unsigned long long)c->vgp->retained_bytes,(unsigned long long)c->vgp->copied_bytes);
   if(++c->profile_frames%20==0)if(mbx_debug_enabled()) fprintf(stderr,
      "N810_MBX_PROFILE frames=%u format=%u geometry_us=%llu pack_us=%llu submit_us=%llu read_us=%llu present_us=%llu\n",
      c->profile_frames,r->base.format,
      (unsigned long long)(c->profile_geometry/c->profile_frames/1000),
      (unsigned long long)(c->profile_pack/c->profile_frames/1000),
      (unsigned long long)(c->profile_submit/c->profile_frames/1000),
      (unsigned long long)(c->profile_read/c->profile_frames/1000),
      (unsigned long long)(c->profile_present/c->profile_frames/1000));
   if(r->dt)winsys->displaytarget_unmap(winsys,r->dt);
   if(surface2d){c->reference_timestamp=++r->timestamp;mbx_content_complete(&r->mbx_content,r->timestamp);}
   r->mbx_content.external_only=export_surface||window_target;
   if(window_target){
      if(ioctl(c->gpu_fd,MBX_WINDOW_QUERY,&c->window[window_slot].token))mbx_fail("rendered window completion missing");
      c->window[window_slot].timestamp=r->timestamp;++c->window_renders;c->window_skipped_read_bytes+=read_bytes;
   }
   c->rendered_count=c->header.triangles;
   if(c->vgp&&!async&&(c->profile_frames==1||c->profile_frames%20==0))
      if(mbx_debug_enabled()) fprintf(stderr,"N810_MBX_GPU_VERTEX frames=%u transform=GPU lighting=GPU CPU_shaded_vertices=0\n",c->profile_frames);
   /* Keep first-frame proof and periodic diagnostics without waking the log
    * reader and status window for every frame. Kernel job counts remain exact. */
   if(!async&&(c->profile_frames==1||c->profile_frames%20==0))
      if(mbx_debug_enabled()) fprintf(stderr,"N810_MBX_GPU_FRAME triangles=%u GPU_jobs=%u CPU_raster_triangles=0\n",c->header.triangles,separate_draws?2u+combine_jobs:1u);
   if(native32&&width==240&&height==320&&getenv("N810_MBX_SURFACE_CHECKPOINT")){
      if(async||shared||c->vgp->use_template)mbx_fail("checkpoint requires synchronous private ownership");
      if(++c->vgp->resource_epoch==0)mbx_fail("resource epoch exhausted");
      unsigned retired=((struct mbx_vgp_wire_frame*)c->vgp->data)->draws;
      if(keep_resident?mbx_resident_checkpoint(c->vgp->data,sizeof(c->vgp->data)):
         mbx_surface_checkpoint(c->vgp->data,sizeof(c->vgp->data),pixels,read_bytes,width*4,width,height))mbx_fail("completed surface checkpoint rejected");
      if(mbx_resident_requested())if(mbx_debug_enabled()) fprintf(stderr,"N810_MBX_RESIDENT skipped_read_bytes=%llu materialized_bytes=%llu dirty=%u\n",(unsigned long long)c->resident_skipped_bytes,(unsigned long long)c->resident_read_bytes,c->resident_dirty);
      c->mask_commands=0;c->batch_clip[0]=c->batch_clip[1]=0;c->batch_clip[2]=width;c->batch_clip[3]=height;c->command_words=512;c->header.triangles=0;c->rendered_count=0;c->state_ready=false;c->texture_bound=false;
      if(c->profile_frames==1||c->profile_frames%20==0)if(mbx_debug_enabled()) fprintf(stderr,"N810_MBX_CHECKPOINT retired_draws=%u retained_draws=0 GPU_background=1 CPU_blended_pixels=0\n",retired);
   }

}
