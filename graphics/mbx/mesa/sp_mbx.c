/* SPDX-License-Identifier: MIT
 * MBX bring-up input at Mesa's post-transform, post-clip, post-cull boundary.
 * Optional capture preserves CPU reference rendering. Explicit GPU mode
 * suppresses CPU triangle rasterization and requires completed MBX jobs.
 * No application-specific geometry exists here: ordinary GLX applications
 * supply the vertices and render state.
 */
#include "sp_mbx.h"
#include "sp_context.h"
#include "sp_state.h"
#include "sp_setup.h"
#include "sp_screen.h"
#include "sp_texture.h"
#include "sp_tile_cache.h"
#include "frontend/sw_winsys.h"
#include "util/u_inlines.h"
#include "util/format/u_format.h"
#include "util/u_math.h"
#include "pipe/p_shader_tokens.h"
#include "tgsi/tgsi_dump.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <fcntl.h>
#include <unistd.h>
#include <stddef.h>
#include <time.h>
#include <pthread.h>
#include "mbx_color_cache.h"

_Static_assert(offsetof(struct softpipe_context, pipe) == 0,
               "Gallium context base must remain at offset zero");

const char *sp_mbx_renderer_name(void)
{
   const char *mode=getenv("N810_MBX_DEVICE");
   if(mode && !strcmp(mode,"1")) {
      unsigned active=0,baseline=0;
      FILE *f=fopen("/sys/module/n810_mbx_gpu_probe/parameters/gpu_service_active","r");
      if(f){if(fscanf(f,"%u",&active)!=1)active=0;fclose(f);}
      f=fopen("/sys/module/n810_mbx_gpu_probe/parameters/gpu_service_baseline_verified","r");
      if(f){if(fscanf(f,"%u",&baseline)!=1)baseline=0;fclose(f);}
      if(!(active==1&&baseline==1)&&getenv("N810_MBX_READY_FD"))
         return "Nokia MBX GPU driver / initialization pending";
      if(active==1&&baseline==1&&getenv("N810_MBX_GPU_VERTEX")&&!strcmp(getenv("N810_MBX_GPU_VERTEX"),"1"))return "Nokia MBX GPU transform, lighting and rasterizer";
      return active==1 && baseline==1 ? "Nokia MBX GPU rasterizer / Mesa CPU vertex processing" : "Nokia MBX requested - GPU service unavailable";
   }
   return "softpipe (CPU software rasterizer)";
}

#include "mbx_trace.h"

#define MBX_MAX_TRIANGLES 16384
struct mbx_screen_vertex { float position[4], color[4]; };
struct mbx_triangle {
   uint32_t depth_enabled, depth_write, depth_func, interpolation;
   uint32_t blend_enabled, color_mask, shader_inputs, sampler_views;
   uint32_t clip[4];
   struct mbx_screen_vertex vertex[3];
};
struct mbx_frame {
   uint32_t magic, version, header_bytes, triangle_bytes;
   uint32_t width, height, triangles, rejected;
   uint32_t clear_buffers, scissored_clear, reserved[2];
   float clear_color[4], clear_depth;
};
#include "sp_mbx_vgp.h"
struct sp_mbx_capture {
   struct mbx_vgp_queue *vgp;
   struct mbx_frame header;
   struct mbx_trace_stamp geometry_begin;
   struct mbx_triangle *triangles;
   const char *path;
   int done;
   struct pipe_resource *reference_target;
   int gpu_fd;
   unsigned rendered_count;
   struct mbx_triangle state_template;
   struct mbx_color_cache color_cache;
   int color_slot;
   bool state_ready,early_cull,direct_pack,direct_pack_check;
   unsigned direct_pack_verified;
   void *wire_job;
   uint16_t *pixels;
   uint8_t *rgba;
   size_t pixel_capacity;
   uint32_t expand_hi[256],expand_lo[256];
   bool expand_ready;
   unsigned profile_frames;
   uint64_t profile_pack,profile_submit,profile_read,profile_present,profile_geometry,frame_started;
};

#include "mbx_cpu_profile.h"
#include "sp_mbx_backend.h"
#include "mbx_startup_gate.h"
static pthread_once_t mbx_ready_once=PTHREAD_ONCE_INIT;
static void mbx_wait_for_launcher(void)
{ if(mbx_startup_gate_wait())mbx_fail("launcher did not release verified GPU readiness"); }

static struct sp_mbx_capture *capture(struct softpipe_context *sp)
{
   if (!sp->mbx_capture_checked) {
      const char *path = getenv("N810_MBX_CAPTURE");
      bool gpu = getenv("N810_MBX_DEVICE") && !strcmp(getenv("N810_MBX_DEVICE"),"1");
      sp->mbx_capture_checked = true;
      if (gpu || (path && path[0] == '/')) {
         struct sp_mbx_capture *c = calloc(1, sizeof(*c));
         if (!c) return NULL;
         c->triangles = calloc(MBX_MAX_TRIANGLES, sizeof(*c->triangles));
         if (!c->triangles) { free(c); return NULL; }
         c->path = strdup(path ? path : "GPU");
         if (!c->path) { free(c->triangles); free(c); return NULL; }
         c->gpu_fd=-1;c->rendered_count=~0U;
         c->direct_pack=gpu&&getenv("N810_MBX_DIRECT_PACK")&&!strcmp(getenv("N810_MBX_DIRECT_PACK"),"1");
         c->direct_pack_check=c->direct_pack;
         c->early_cull=getenv("N810_MBX_EARLY_CULL")&&!strcmp(getenv("N810_MBX_EARLY_CULL"),"1");
         if(gpu){
            pthread_once(&mbx_ready_once,mbx_wait_for_launcher);
            c->gpu_fd=open("/dev/n810-mbx-render",O_RDWR|O_CLOEXEC);
            if(c->gpu_fd<0)mbx_fail("verified GPU service unavailable");
         }
         if(gpu&&getenv("N810_MBX_GPU_VERTEX")&&!strcmp(getenv("N810_MBX_GPU_VERTEX"),"1")){
            c->vgp=calloc(1,sizeof(*c->vgp));if(!c->vgp)mbx_fail("GPU queue allocation");
            sp->draw->mbx_vgp_submit=sp_mbx_vgp_draw;
            c->direct_pack=false;
         }
         sp->mbx_capture = c;
      }
   }
   return sp->mbx_capture;
}

bool sp_mbx_clear(struct softpipe_context *sp, unsigned buffers,
                  const struct pipe_scissor_state *scissor,
                  const union pipe_color_union *color, double depth)
{
   struct sp_mbx_capture *c = capture(sp);
   if (!c || (c->done && c->gpu_fd<0)) return false;
   /* A clear starts a new reference frame. Never join separate frames. */
   if(c->gpu_fd>=0){
      sp_mbx_present(sp);
      c->header.triangles=c->header.rejected=c->header.clear_buffers=c->header.scissored_clear=0;
      c->rendered_count=~0U;
   }else{
      if (c->header.triangles) sp_mbx_flush(sp);
      if (c->done) return false;
   }
   c->header.magic = 0x3146424d; /* MBF1, little-endian ARM/x86 */
   c->header.version = 1;
   c->header.header_bytes = sizeof(c->header);
   c->header.triangle_bytes = sizeof(struct mbx_triangle);
   c->header.width = sp->framebuffer.width;
   c->header.height = sp->framebuffer.height;
   if (sp->framebuffer.nr_cbufs == 1 && sp->framebuffer.cbufs[0])
      pipe_resource_reference(&c->reference_target, sp->framebuffer.cbufs[0]->texture);
   c->header.clear_buffers |= buffers;
   c->header.scissored_clear |= scissor != NULL;
   if (color && (buffers & PIPE_CLEAR_COLOR))
      memcpy(c->header.clear_color, color->f, sizeof(c->header.clear_color));
   if (buffers & PIPE_CLEAR_DEPTH) c->header.clear_depth = depth;
   if(c->vgp){
      struct mbx_vgp_wire_frame *f=(void *)c->vgp->data;memset(f,0,sizeof(*f));
      f->magic=MBX_VGP_WIRE_MAGIC;f->version=1;f->bytes=sizeof(*f);
      f->width=c->header.width;f->height=c->header.height;
      memcpy(f->clear_color,c->header.clear_color,16);memcpy(&f->clear_depth,&c->header.clear_depth,4);
      f->clear_buffers=5;
      if(c->header.clear_buffers!=(PIPE_CLEAR_COLOR0|PIPE_CLEAR_DEPTH)||f->width!=400||f->height!=400)
         mbx_fail("GPU vertex clear or dimensions unsupported");
   }
   c->state_ready=false;
   c->frame_started=mbx_time_ns();
   c->geometry_begin=mbx_trace_begin();
   return c->gpu_fd>=0;
}

bool sp_mbx_early_cull(struct softpipe_context *sp)
{ return sp->mbx_capture && sp->mbx_capture->early_cull; }

void sp_mbx_invalidate(struct softpipe_context *sp)
{
   if(sp->mbx_capture)sp->mbx_capture->state_ready=false;
}

static void sp_mbx_prepare(struct softpipe_context *sp)
{
   struct sp_mbx_capture *c=capture(sp);
   if(!c || (c->done && c->gpu_fd<0))return;
   c->state_ready=false;
   struct mbx_triangle t={0};
   int slot=-1;unsigned mode=0;
   for (unsigned i = 0; i < sp->fs_variant->info.num_inputs; ++i) {
      if (sp->fs_variant->info.input_semantic_name[i] == TGSI_SEMANTIC_COLOR &&
          sp->fs_variant->info.input_semantic_index[i] == 0) {
         slot = sp->setup_info.attrib[i].src_index;
         mode = sp->setup_info.attrib[i].interp;
         break;
      }
   }
   if (slot < 0 || slot >= PIPE_MAX_SHADER_OUTPUTS) return;
   t.depth_enabled = sp->depth_stencil->depth_enabled;
   t.depth_write = sp->depth_stencil->depth_writemask;
   t.depth_func = sp->depth_stencil->depth_func;
   t.interpolation = mode;
   t.blend_enabled = sp->blend->rt[0].blend_enable;
   t.color_mask = sp->blend->rt[0].colormask;
   t.shader_inputs = sp->fs_variant->info.num_inputs;
   t.sampler_views = sp->num_sampler_views[PIPE_SHADER_FRAGMENT];
   t.clip[0] = sp->cliprect[0].minx; t.clip[1] = sp->cliprect[0].miny;
   t.clip[2] = sp->cliprect[0].maxx; t.clip[3] = sp->cliprect[0].maxy;
   if(c->gpu_fd>=0 || getenv("N810_MBX_VALIDATE_CAPTURE")){
      const struct tgsi_shader_info *info=&sp->fs_variant->info;
      if(t.depth_enabled!=1||t.depth_write!=1||t.depth_func!=1||t.blend_enabled||t.color_mask!=15||
         t.shader_inputs!=1||t.sampler_views||t.clip[0]||t.clip[1]||
         t.clip[2]!=c->header.width||t.clip[3]!=c->header.height||
         (mode!=SP_INTERP_CONSTANT&&mode!=SP_INTERP_PERSPECTIVE)||
         sp->depth_stencil->alpha_enabled||sp->depth_stencil->stencil[0].enabled||
         sp->depth_stencil->stencil[1].enabled||sp->blend->logicop_enable||
         sp->active_query_count||info->num_instructions!=2||
         info->opcode_count[TGSI_OPCODE_MOV]!=1||info->opcode_count[TGSI_OPCODE_END]!=1)
         mbx_fail("render state or fragment shader outside supported subset");
   }
   c->state_template=t;c->color_slot=slot;c->state_ready=true;
}

#include "sp_mbx_vgp_impl.h"

bool sp_mbx_triangle(struct softpipe_context *sp, const float (*v0)[4],
                     const float (*v1)[4], const float (*v2)[4],
                     const float (*provoking)[4])
{
   struct sp_mbx_capture *c = capture(sp);
   if(c&&c->vgp)mbx_fail("CPU vertex fallback attempted in GPU-only frame");
   const float (*vertices[3])[4] = {v0, v1, v2};
   struct mbx_triangle *t;
   int slot = -1;
   unsigned mode = 0;
   if (!c || (c->done && c->gpu_fd<0)) return false;
   if (!c->header.magic || c->header.triangles == (c->direct_pack?512:MBX_MAX_TRIANGLES))
      goto reject;
   if(!c->state_ready)sp_mbx_prepare(sp);
   if(!c->state_ready)goto reject;
   if(c->direct_pack){
      if(!c->wire_job)c->wire_job=malloc(sizeof(struct mbx_wire_job));
      if(!c->wire_job)mbx_fail("direct packet allocation failed");
      struct mbx_wire_job *job=c->wire_job;
      if(!mbx_pack_direct(&job->p[c->header.triangles],&c->color_cache,vertices,provoking,
                         c->color_slot,c->state_template.interpolation==SP_INTERP_PERSPECTIVE))goto reject;
      if(!c->direct_pack_check){++c->header.triangles;return true;}
   }
   /* Construct once in the unpublished destination slot. Rejection never
    * advances the count, so incomplete vertices cannot reach the GPU. */
   t=&c->triangles[c->header.triangles];
   /* All vertex words are validated and overwritten below. Copying their
    * zero template first only adds stores and cache traffic per triangle. */
   memcpy(t,&c->state_template,offsetof(struct mbx_triangle,vertex));
   slot=c->color_slot;mode=t->interpolation;
   for (unsigned i = 0; i < 3; ++i) {
      const float *color = mode == SP_INTERP_CONSTANT ? provoking[slot] : vertices[i][slot];
      if(!mbx_finite4(vertices[i][0]))goto reject;
      if(i==0 || mode!=SP_INTERP_CONSTANT)
         if(!mbx_finite4(color))goto reject;
      memcpy(t->vertex[i].position,vertices[i][0],16);
      memcpy(t->vertex[i].color,color,16);
   }
   ++c->header.triangles;
   return c->gpu_fd>=0;
reject:
   ++c->header.rejected;
   if(c->gpu_fd>=0)mbx_fail("invalid or unsupported geometry");
   return false;
}

static int write_all(int fd, const void *data, size_t bytes)
{
   const char *p = data;
   while (bytes) {
      ssize_t n = write(fd, p, bytes);
      if (n <= 0) return -1;
      p += n; bytes -= n;
   }
   return 0;
}

static void save_reference_image(struct softpipe_context *sp, struct sp_mbx_capture *c)
{
   struct softpipe_resource *r;
   struct sw_winsys *winsys = softpipe_screen(sp->pipe.screen)->winsys;
   unsigned width=c->header.width, height=c->header.height;
   void *map;
   uint8_t *rgba;
   char *name;
   int fd;
   if (!c->reference_target || !width || !height || width>4096 || height>4096) return;
   r=softpipe_resource(c->reference_target);
   for (unsigned i=0;i<sp->framebuffer.nr_cbufs;++i)
      if (sp->cbuf_cache[i]) sp_flush_tile_cache(sp->cbuf_cache[i]);
   map=r->dt ? winsys->displaytarget_map(winsys,r->dt,PIPE_MAP_READ) : r->data;
   if (!map) return;
   rgba=malloc((size_t)width*height*4);
   name=malloc(strlen(c->path)+6);
   if (rgba && name) {
      util_format_read_4ub(r->base.format,rgba,width*4,map,r->stride[0],0,0,width,height);
      sprintf(name,"%s.rgba",c->path);
      fd=open(name,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW,0600);
      if(fd>=0){write_all(fd,rgba,(size_t)width*height*4);close(fd);}
   }
   free(rgba);free(name);
   if(r->dt)winsys->displaytarget_unmap(winsys,r->dt);
}

void sp_mbx_flush(struct softpipe_context *sp)
{
   struct sp_mbx_capture *c = sp->mbx_capture;
   if (!c || c->done || !c->header.triangles) return;
   /* Exclusive create prevents overwriting earlier evidence or following a
    * pre-existing symlink. A short file is rejected by the frame reader. */
   int fd = open(c->path, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0600);
   int error = fd < 0;
   if (fd >= 0) {
      error = write_all(fd, &c->header, sizeof(c->header)) ||
              write_all(fd, c->triangles, c->header.triangles * sizeof(*c->triangles));
      if (close(fd)) error = 1;
   }
   fprintf(stderr, "N810_MBX_REFERENCE capture=%s triangles=%u rejected=%u GPU_jobs=0 status=%s\n",
           c->path, c->header.triangles, c->header.rejected, error ? "FAILED" : "SAVED");
   if (!error) save_reference_image(sp,c);
   c->done = 1;
}

void sp_mbx_finish(void)
{ n810_mbx_async_drain(); }

void sp_mbx_destroy(struct softpipe_context *sp)
{
   struct sp_mbx_capture *c = sp->mbx_capture;
   if (!c) return;
   sp_mbx_finish();
   if(c->gpu_fd>=0)close(c->gpu_fd);
   pipe_resource_reference(&c->reference_target,NULL);
   if(c->vgp){
      struct mbx_vgp_cached_shader *s=c->vgp->shaders;
      while(s){struct mbx_vgp_cached_shader *next=s->next;free(s);s=next;}free(c->vgp);
   }
   free(c->wire_job);free(c->pixels);free(c->rgba);
   mbx_trace_flush();
   free((void *)c->path); free(c->triangles); free(c);
   sp->mbx_capture = NULL;
}
