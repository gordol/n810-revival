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
   exit(1);
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
{ struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (uint64_t)t.tv_sec*1000000000+t.tv_nsec; }

void sp_mbx_present(struct softpipe_context *sp)
{
   mbx_profile_poll();
   struct sp_mbx_capture *c=sp->mbx_capture;
   if(!c||c->gpu_fd<0||!c->header.magic||c->rendered_count==c->header.triangles)return;
   /* Sample steady rendering after shader verification and startup settle. */
   if(c->profile_frames==200)mbx_profile_begin();
   if(c->header.rejected||c->header.scissored_clear||c->header.clear_depth!=1.0f)
      mbx_fail("unsupported framebuffer clear/state");
   for(unsigned i=0;i<4;++i)if(c->header.clear_color[i]!=0.0f)mbx_fail("nonblack clear unsupported during bring-up");
   if(!c->reference_target)mbx_fail("missing render target");
   struct softpipe_resource *r=softpipe_resource(c->reference_target);
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
   if(total>512*512)mbx_fail("presentation capacity exceeded");
   if(!c->wire_job)c->wire_job=malloc(sizeof(struct mbx_wire_job));
   if(c->pixel_capacity<total){
      free(c->pixels);free(c->rgba);
      c->pixels=malloc(total*2);c->rgba=malloc(total*4);c->pixel_capacity=total;
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
            fprintf(stderr,"N810_MBX_DIRECT_PACK_VERIFIED frames=10 bit_exact=1\n");
         }
      }
   }else mbx_fill_job(c,job);
   bool native=r->base.format==PIPE_FORMAT_B5G6R5_UNORM;
   if(native&&!c->vgp){job->version=3;job->reserved=r->stride[0];}
   size_t read_bytes=native&&!c->vgp?(size_t)r->stride[0]*height:total*2;
   void *read_target=native&&!c->vgp?map:pixels;
   mbx_trace_end("packet_build",trace,c->header.triangles);trace=mbx_trace_begin();
   bool shared=getenv("N810_MBX_SHARED_IMAGE")&&!strcmp(getenv("N810_MBX_SHARED_IMAGE"),"1");
   bool async=getenv("N810_MBX_ASYNC")&&!strcmp(getenv("N810_MBX_ASYNC"),"1");
   if(c->vgp&&(shared&&r->stride[0]!=width*2))mbx_fail("GPU vertex shared image stride mismatch");
   if(async&&(!shared||!native||!r->dt))mbx_fail("async requires native shared target");
   if(!async&&shared&&(!native||!r->dt||n810_mbx_shared_bind(r->dt,c->gpu_fd,read_bytes)))
      mbx_fail("shared GPU image unavailable");
   mbx_trace_end("target_reuse_wait",trace,1);trace=mbx_trace_begin();
   t1=mbx_time_ns();
   size_t bytes=24+job->count*sizeof(job->p[0]);
   void *submit_job=job;
   if(c->vgp){submit_job=c->vgp->data;bytes=((struct mbx_vgp_wire_frame *)submit_job)->bytes;}
   if(async){if(n810_mbx_async_submit(r->dt,c->gpu_fd,submit_job,bytes,read_bytes))mbx_fail("async submission failed");}
   else if(write(c->gpu_fd,submit_job,bytes)!=(ssize_t)bytes)mbx_fail("GPU frame rejected or failed");
   mbx_trace_end(async?"queue_submit":"gpu_submit",trace,c->header.triangles);trace=mbx_trace_begin();
   t2=mbx_time_ns();
   while(!shared&&got<read_bytes){
      ssize_t n=read(c->gpu_fd,(char *)read_target+got,read_bytes-got);
      if(n<=0)mbx_fail("GPU readback failed");
      got+=n;
   }
   mbx_trace_end("readback",trace,got);trace=mbx_trace_begin();
   t3=mbx_time_ns();
   if(native){
      if(c->vgp&&!shared)for(unsigned y=0;y<height;++y)
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
   if(++c->profile_frames%20==0)fprintf(stderr,
      "N810_MBX_PROFILE frames=%u format=%u geometry_us=%llu pack_us=%llu submit_us=%llu read_us=%llu present_us=%llu\n",
      c->profile_frames,r->base.format,
      (unsigned long long)(c->profile_geometry/c->profile_frames/1000),
      (unsigned long long)(c->profile_pack/c->profile_frames/1000),
      (unsigned long long)(c->profile_submit/c->profile_frames/1000),
      (unsigned long long)(c->profile_read/c->profile_frames/1000),
      (unsigned long long)(c->profile_present/c->profile_frames/1000));
   if(r->dt)winsys->displaytarget_unmap(winsys,r->dt);
   c->rendered_count=c->header.triangles;
   if(c->vgp&&!async&&(c->profile_frames==1||c->profile_frames%20==0))
      fprintf(stderr,"N810_MBX_GPU_VERTEX frames=%u transform=GPU lighting=GPU CPU_shaded_vertices=0\n",c->profile_frames);
   /* Keep first-frame proof and periodic diagnostics without waking the log
    * reader and status window for every frame. Kernel job counts remain exact. */
   if(!async&&(c->profile_frames==1||c->profile_frames%20==0))
      fprintf(stderr,"N810_MBX_GPU_FRAME triangles=%u GPU_jobs=%u CPU_raster_triangles=0\n",c->header.triangles,1u);
}
