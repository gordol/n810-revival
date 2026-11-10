/* SPDX-License-Identifier: MIT
 * MBX bring-up input at Mesa's post-transform, post-clip, post-cull boundary.
 * Optional capture preserves CPU reference rendering. Explicit GPU mode
 * suppresses CPU triangle rasterization and requires completed MBX jobs.
 * No application-specific geometry exists here: ordinary GLX applications
 * supply the vertices and render state.
 */
#define MBX_PRIVATE_RESOURCE_BUILD 1
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
#include <sys/stat.h>
#include <sys/mman.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <fcntl.h>
#include <unistd.h>
#include <stddef.h>
#include <time.h>
#include <pthread.h>
#include <errno.h>
#include <limits.h>
#include "mbx_service_abi.h"
#include "mbx_color_cache.h"

_Static_assert(offsetof(struct softpipe_context, pipe) == 0,
               "Gallium context base must remain at offset zero");

/* The privileged launcher owns authorization. The application receives only
 * this bounded render device, never root credentials or raw MMIO access. */
static int mbx_inherited_service_fd(void)
{
   const char *value=getenv("N810_MBX_RENDER_FD");
   if(!value)return -2;
   char *end;errno=0;long fd=strtol(value,&end,10);
   if(!*value||*end||errno||fd<0||fd>INT_MAX)return -1;
   struct mbx_service_info info={0};
   if(ioctl((int)fd,MBX_SERVICE_INFO,&info)||info.version!=1||info.active!=1||
      info.baseline_verified!=1||info.reserved)return -1;
   return (int)fd;
}

const char *sp_mbx_renderer_name(void)
{
   const char *mode=getenv("N810_MBX_DEVICE");
   if(mode && !strcmp(mode,"1")) {
      unsigned active=0,baseline=0;
      int inherited=mbx_inherited_service_fd();
      if(inherited>=0)active=baseline=1;
      else if(inherited==-1)return "Nokia MBX requested - inherited GPU service unavailable";
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
#include "mbx_image_abi.h"
#include "sp_mbx_vgp.h"
#include "mbx_texture_cache.h"
#include "mbx_linear_cache.h"
#include "mbx_image_abi.h"
struct mbx_window_entry {struct pipe_resource *resource;struct mbx_window_token token;unsigned timestamp;bool imported,exported;};
struct mbx_surface_history {
 struct pipe_resource *target;
 struct mbx_frame header;
 unsigned char *wire;
 unsigned bytes,timestamp,command_words,mask_commands,batch_clip[4];
 uint64_t content_generation;
 uint64_t age;
};
struct sp_mbx_capture {
 struct mbx_window_entry window[14];
 unsigned window_first,window_count,window_layout;
 bool shared_jobs,window_checkpoint;
 uint64_t window_renders,window_samples,window_skipped_read_bytes;
 bool defer_readback,resident_dirty,surface_diagnostics;
 struct mbx_resident_token resident_token;
 uint64_t resident_skipped_bytes,resident_read_bytes;
 struct mbx_surface_history history[4];
 uint64_t history_clock;
 unsigned command_words,mask_commands,batch_clip[4];
   struct mbx_texture_cache *texture_cache;
   struct mbx_resource_cache *resource_cache;
   struct mbx_linear_entry linear_cache[5];
   uint64_t linear_wire_hits,linear_wire_skipped_bytes,history_skipped_bytes;
   uint64_t linear_clock,linear_hits,linear_rebuilds,linear_packed_bytes;
   unsigned texture_linear_width,texture_linear_height;
   unsigned texture_uv_width,texture_uv_height,texture_crop_x,texture_crop_y;
   bool texture_deferred;
   struct mbx_vgp_queue *vgp;
   struct mbx_frame header;
   struct mbx_trace_stamp geometry_begin;
   struct mbx_triangle *triangles;
   const char *path;
   int done;
   struct pipe_resource *reference_target;
   int gpu_fd;
   unsigned rendered_count,reference_timestamp;
   struct mbx_triangle state_template;
   struct mbx_color_cache color_cache;
   int color_slot;
   unsigned texture_index;
   bool texture_modulate,constant_color,texture_active,texture_bound,state_ready,early_cull,direct_pack,direct_pack_check;
   unsigned direct_pack_verified;
   void *wire_job;
   unsigned char *separate_rgb_wire,*separate_alpha_wire,*separate_merge_wire;
   bool separate_reported;
   uint16_t *pixels;
   uint8_t *rgba;
   size_t pixel_capacity;
   uint32_t expand_hi[256],expand_lo[256];
   bool expand_ready;
   unsigned profile_frames;
   uint64_t profile_pack,profile_submit,profile_read,profile_present,profile_geometry,frame_started;
};

#include "mbx_cpu_profile.h"
/* Diagnostics are opt-in; never poll/sample or format frame logs in normal use. */
#include <pthread.h>
static pthread_once_t mbx_debug_once = PTHREAD_ONCE_INIT;
static bool mbx_debug_value;
static void mbx_debug_init(void)
{
   const char *v = getenv("N810_MBX_DEBUG");
   mbx_debug_value = v && !strcmp(v, "1");
}
static bool mbx_debug_enabled(void)
{
   pthread_once(&mbx_debug_once, mbx_debug_init);
   return mbx_debug_value;
}
#include "sp_mbx_backend.h"
#include "mbx_surface_history.h"
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
         const char *diagnostics=getenv("N810_MBX_SURFACE_DIAGNOSTICS");
         const char *trace=getenv("N810_MBX_TRACE");
         c->surface_diagnostics=(diagnostics&&!strcmp(diagnostics,"1"))||(trace&&!strcmp(trace,"1"));
         bool gpu_vertices=gpu&&getenv("N810_MBX_GPU_VERTEX")&&!strcmp(getenv("N810_MBX_GPU_VERTEX"),"1");
         if(!gpu_vertices){
            c->triangles = calloc(MBX_MAX_TRIANGLES, sizeof(*c->triangles));
            if (!c->triangles) { free(c); return NULL; }
         }
         c->path = strdup(path ? path : "GPU");
         if (!c->path) { free(c->triangles); free(c); return NULL; }
         c->gpu_fd=-1;c->rendered_count=~0U;
         c->direct_pack=gpu&&getenv("N810_MBX_DIRECT_PACK")&&!strcmp(getenv("N810_MBX_DIRECT_PACK"),"1");
         c->direct_pack_check=c->direct_pack;
         c->early_cull=getenv("N810_MBX_EARLY_CULL")&&!strcmp(getenv("N810_MBX_EARLY_CULL"),"1");
         if(gpu){
            pthread_once(&mbx_ready_once,mbx_wait_for_launcher);
            int inherited=mbx_inherited_service_fd();
            if(inherited==-1)mbx_fail("inherited GPU service validation failed");
            c->gpu_fd=inherited>=0?fcntl(inherited,F_DUPFD_CLOEXEC,3):open("/dev/n810-mbx-render",O_RDWR|O_CLOEXEC);
            if(c->gpu_fd<0)mbx_fail("verified GPU service unavailable");
            mbx_window_client_range(c,inherited);
         }
         if(gpu&&getenv("N810_MBX_GPU_VERTEX")&&!strcmp(getenv("N810_MBX_GPU_VERTEX"),"1")){
            c->vgp=calloc(1,sizeof(*c->vgp));if(!c->vgp)mbx_fail("GPU queue allocation");
            c->vgp->use_template=getenv("N810_MBX_TEMPLATE")&&!strcmp(getenv("N810_MBX_TEMPLATE"),"1");
            if(c->vgp->use_template){
               c->vgp->update=calloc(1,MBX_VGP_UPDATE_MAX_BYTES);
               if(!c->vgp->update)mbx_fail("GPU template update allocation");
            }
            sp->draw->mbx_vgp_submit=sp_mbx_vgp_draw;
            c->direct_pack=false;
         }
         sp->mbx_capture = c;
      }
   }
   return sp->mbx_capture;
}

#include "mbx_mixed_state.h"

bool sp_mbx_clear(struct softpipe_context *sp, unsigned buffers,
                  const struct pipe_scissor_state *scissor,
                  const union pipe_color_union *color, double depth)
{
   struct sp_mbx_capture *c = capture(sp);
   if (!c || (c->done && c->gpu_fd<0)) return false;
   bool mixed=mbx_mixed_requested(getenv("N810_MBX_EXPERIMENTAL_MIXED"));
   if(mixed&&c->gpu_fd>=0){
      if(!getenv("N810_MBX_EXPERIMENTAL_2D"))mbx_fail("mixed state requires 2D resource frames");
      if(!mbx_mixed_clear(buffers,PIPE_CLEAR_COLOR0,PIPE_CLEAR_DEPTH,depth,scissor!=NULL,sp->framebuffer.zsbuf!=NULL))
         mbx_fail("mixed target requires complete color and attached-depth initialization");
   }
   /* Depth/stencil-only clears are unobservable in strict GPU 2D: all
    * depth/stencil tests and reads are rejected. Preserve color/history. */
   if(!mixed&&c->gpu_fd>=0&&c->vgp&&getenv("N810_MBX_EXPERIMENTAL_2D")&&buffers&&
      !(buffers&~(PIPE_CLEAR_DEPTH|PIPE_CLEAR_STENCIL)))return true;
   if(c->gpu_fd>=0&&getenv("N810_MBX_EXPERIMENTAL_2D")&&sp->framebuffer.nr_cbufs==1&&sp->framebuffer.cbufs[0]){
      const struct pipe_surface *surface=sp->framebuffer.cbufs[0];
      if(surface->u.tex.level||surface->u.tex.first_layer||surface->u.tex.last_layer)mbx_fail("2D surface subresources unsupported");
   }
   /* A clear starts a new reference frame. Never join separate frames. */
   if(c->gpu_fd>=0){
      sp_mbx_present(sp);
      c->header.triangles=c->header.rejected=c->header.clear_buffers=c->header.scissored_clear=0;
      c->rendered_count=~0U;c->window_checkpoint=false;
      if(c->vgp)c->vgp->last_draw_bytes=0;
   }else{
      if (c->header.triangles) sp_mbx_flush(sp);
      if (c->done) return false;
   }
   c->command_words=512; /* frame begin, two masks, clear and end */
   c->header.magic = 0x3146424d; /* MBF1, little-endian ARM/x86 */
   c->header.version = 1;
   c->header.header_bytes = sizeof(c->header);
   c->header.triangle_bytes = sizeof(struct mbx_triangle);
   c->header.width = sp->framebuffer.width;
   c->header.height = sp->framebuffer.height;
   c->mask_commands=0;c->batch_clip[0]=c->batch_clip[1]=0;c->batch_clip[2]=c->header.width;c->batch_clip[3]=c->header.height;
   if (sp->framebuffer.nr_cbufs == 1 && sp->framebuffer.cbufs[0])
   { pipe_resource_reference(&c->reference_target, sp->framebuffer.cbufs[0]->texture);
      c->reference_timestamp=softpipe_resource(c->reference_target)->timestamp; }
   c->header.clear_buffers |= buffers;
   c->header.scissored_clear |= scissor != NULL;
   if (color && (buffers & PIPE_CLEAR_COLOR))
      memcpy(c->header.clear_color, color->f, sizeof(c->header.clear_color));
   if (buffers & PIPE_CLEAR_DEPTH) c->header.clear_depth = depth;
   if(c->vgp){
      c->vgp->update_bytes=sizeof(struct mbx_vgp_wire_update);
      unsigned resource_version=c->vgp->use_template?c->vgp->template_frame.version:2;
      if(resource_version<3||resource_version>5)resource_version=2;
      unsigned resource_bytes=resource_version==5?16384:resource_version==4?32768:resource_version==3?8192:0;
      if(++c->vgp->resource_epoch==0)mbx_fail("resource epoch exhausted");
      struct mbx_vgp_wire_frame *f=(void *)c->vgp->data;memset(f,0,sizeof(*f));
      f->magic=MBX_VGP_WIRE_MAGIC;f->version=resource_version;f->bytes=sizeof(*f)+resource_bytes;
      if(getenv("N810_MBX_EXPERIMENTAL_2D")){
         const char *multi=getenv("N810_MBX_MULTI_TEXTURE");
         if(!multi||strcmp(multi,"1"))mbx_fail("2D resource frames require multi-resource mode");
         enum pipe_format target=c->reference_target?c->reference_target->format:PIPE_FORMAT_NONE;
         bool rgba=target==PIPE_FORMAT_R8G8B8A8_UNORM||target==PIPE_FORMAT_B8G8R8A8_UNORM;
         if(!rgba&&target!=PIPE_FORMAT_B5G6R5_UNORM)mbx_fail("unsupported lossless 2D target format");
         f->version=rgba?10:9;f->bytes=64;memset(c->vgp->data+48,0,16);
      }
      c->texture_bound=false;
      f->width=c->header.width;f->height=c->header.height;
      memcpy(f->clear_color,c->header.clear_color,16);memcpy(&f->clear_depth,&c->header.clear_depth,4);
      f->clear_buffers=5;
      if((!mixed||!sp->framebuffer.zsbuf)&&(f->version==9||f->version==10)){
         /* Physical depth is irrelevant in this strictly depth-disabled path.
          * All depth/stencil reads and depth/stencil draws fail closed. */
         float unused_depth=1.0f;memcpy(&f->clear_depth,&unused_depth,4);
      }
      /* Stencil clear is an unobserved lazy value in this restricted 2D path.
       * Stencil testing, depth/stencil maps, and texture sampling stay rejected.
       * Never claim stencil rendering support from accepting this dead clear. */
      bool surface=f->version==9||f->version==10;
      bool desktop_target=getenv("N810_MBX_DESKTOP_TARGET")&&!strcmp(getenv("N810_MBX_DESKTOP_TARGET"),"1")&&f->version==9&&f->width==800&&f->height==480;
      bool dimensions=desktop_target||(surface?(f->width>=16&&f->width<=400&&f->height>=16&&f->height<=400&&
         !(f->width&15)&&(!(f->height&15)||(f->version==10&&f->width==240&&f->height==241))&&f->width*f->height*(f->version==10?4:2)<=320000):
         (f->width==400&&f->height==400));
      if((surface?(!(c->header.clear_buffers&PIPE_CLEAR_COLOR0)||
         (c->header.clear_buffers&~(PIPE_CLEAR_COLOR0|PIPE_CLEAR_DEPTH|PIPE_CLEAR_STENCIL))):
         c->header.clear_buffers!=(PIPE_CLEAR_COLOR0|PIPE_CLEAR_DEPTH))||!dimensions)
      {fprintf(stderr,"N810_MBX_REJECT_CLEAR width=%u height=%u buffers=%x format=%u version=%u\n",f->width,f->height,c->header.clear_buffers,c->reference_target?c->reference_target->format:0,f->version);
         mbx_fail("GPU vertex clear or dimensions unsupported");}
   }
   if(c->gpu_fd>=0&&c->reference_target){struct mbx_surface_content *state=&softpipe_resource(c->reference_target)->mbx_content;mbx_content_clear(state);mbx_content_trace(state,c->reference_target,"clear");}
   c->state_ready=false;
   c->frame_started=mbx_time_ns();
   c->geometry_begin=mbx_trace_begin();
   return c->gpu_fd>=0;
}

void sp_mbx_before_cpu_write(struct softpipe_context *sp,struct pipe_resource *resource)
{
   struct sp_mbx_capture *c=sp->mbx_capture;
   if(c&&c->gpu_fd>=0&&getenv("N810_MBX_EXPERIMENTAL_2D")&&c->reference_target==resource)
      sp_mbx_present(sp);
   if(softpipe_resource(resource)->mbx_content.external_only)mbx_fail("exported final target has no CPU image; explicit capture required");
}

void sp_mbx_checkpoint(struct softpipe_context *sp)
{
 struct sp_mbx_capture *c=sp->mbx_capture;
 if(!c)return;
 c->defer_readback=mbx_resident_requested();
 sp_mbx_present(sp);
 c->defer_readback=false;
}

void sp_mbx_framebuffer_changed(struct softpipe_context *sp)
{
   struct sp_mbx_capture *c=sp->mbx_capture;
   if(!c||c->gpu_fd<0)return;
   sp_mbx_present(sp);
   mbx_history_save(c);
   /* A bind is not a write. Retain the last target's immutable command
    * history across temporary binds. Prepare rejects a different target;
    * only an explicit color clear can replace this history. */
   c->state_ready=false;
}

bool sp_mbx_early_cull(struct softpipe_context *sp)
{ return sp->mbx_capture && sp->mbx_capture->early_cull; }

void sp_mbx_invalidate(struct softpipe_context *sp)
{
   if(sp->mbx_capture)sp->mbx_capture->state_ready=false;
}

#include "mbx_texture_subset.h"
/* Exact copy equivalence only for a fragment whose alpha is proven one.
 * Gallium factor ZERO is decimal 17; do not confuse it with inverse alpha. */
static bool mbx_opaque_copy(struct softpipe_context *sp,struct sp_mbx_capture *c)
{
 const struct pipe_rt_blend_state *b=&sp->blend->rt[0];
 if(!b->blend_enable||b->rgb_func!=PIPE_BLEND_ADD||b->alpha_func!=PIPE_BLEND_ADD||
    b->rgb_src_factor!=PIPE_BLENDFACTOR_SRC_ALPHA||b->alpha_src_factor!=PIPE_BLENDFACTOR_ONE)return false;
 const bool premultiply=b->rgb_dst_factor==PIPE_BLENDFACTOR_ZERO&&b->alpha_dst_factor==PIPE_BLENDFACTOR_ZERO;
 const bool over=b->rgb_dst_factor==PIPE_BLENDFACTOR_INV_SRC_ALPHA&&
    (b->alpha_dst_factor==PIPE_BLENDFACTOR_ONE||b->alpha_dst_factor==PIPE_BLENDFACTOR_INV_SRC_ALPHA);
 // For proven Sa=1 on these UNORM targets, destination contribution is zero
 // and output alpha is exactly one in either separate-alpha equation.
 if(!premultiply&&!(over&&getenv("N810_MBX_OPAQUE_BLEND_COPY")))return false;
 const struct pipe_sampler_view *v=c->texture_active?sp->sampler_views[PIPE_SHADER_FRAGMENT][0]:NULL;
 const float *k=sp->mapped_constants[PIPE_SHADER_FRAGMENT][0];
 return (c->constant_color&&k&&sp->const_buffer_size[PIPE_SHADER_FRAGMENT][0]>=16&&k[3]==1.0f)||
        (v&&mbx_alpha_view(sp)&&v->swizzle_a==PIPE_SWIZZLE_1&&mbx_texture_fragment(sp->fs_variant->tokens,true));
}
static void sp_mbx_prepare(struct softpipe_context *sp)
{
   struct sp_mbx_capture *c=capture(sp);
   if(!c || (c->done && c->gpu_fd<0))return;
   c->state_ready=false;
   mbx_history_restore(sp,c);
   if(c->gpu_fd>=0&&(!c->header.magic||!c->reference_target||
      sp->framebuffer.nr_cbufs!=1||!sp->framebuffer.cbufs[0]||
      c->reference_target!=sp->framebuffer.cbufs[0]->texture))
      mbx_fail("GPU target needs an explicit supported clear before drawing");
   if(c->gpu_fd>=0&&getenv("N810_MBX_EXPERIMENTAL_2D")&&
      softpipe_resource(c->reference_target)->timestamp!=c->reference_timestamp)
      mbx_fail("GPU target changed outside retained command history");
   struct mbx_triangle t={0};
   int slot=-1;unsigned mode=0;
   c->texture_active=c->vgp&&getenv("N810_MBX_EXPERIMENTAL_TEXTURE")&&sp->num_sampler_views[PIPE_SHADER_FRAGMENT]==1;
   c->texture_modulate=c->texture_active&&getenv("N810_MBX_EXPERIMENTAL_MODULATE")&&mbx_modulate_fragment(sp->fs_variant->tokens);
   for (unsigned i = 0; i < sp->fs_variant->info.num_inputs; ++i) {
      if ((c->texture_active?(sp->fs_variant->info.input_semantic_name[i]==TGSI_SEMANTIC_GENERIC||sp->fs_variant->info.input_semantic_name[i]==TGSI_SEMANTIC_TEXCOORD):sp->fs_variant->info.input_semantic_name[i] == TGSI_SEMANTIC_COLOR) &&
          sp->fs_variant->info.input_semantic_index[i] == 0) {
         slot = sp->setup_info.attrib[i].src_index;
         mode = sp->setup_info.attrib[i].interp;
         break;
      }
   }
   c->constant_color=c->vgp&&!c->texture_active&&sp->fs_variant->info.num_inputs==0&&mbx_fragment_constant(sp->fs_variant->tokens);
   if(c->constant_color){slot=0;mode=SP_INTERP_CONSTANT;}
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
      if(t.blend_enabled){
         const struct pipe_rt_blend_state *b=&sp->blend->rt[0];
         const struct pipe_sampler_view *view=c->texture_active?sp->sampler_views[PIPE_SHADER_FRAGMENT][0]:NULL;
         const float *constant=sp->mapped_constants[PIPE_SHADER_FRAGMENT][0];
         /* For a proven alpha-one fragment, both equations yield alpha one
          * for every UNORM destination. This is a state equivalence, not an
          * approximation for translucent textures or per-vertex colors. */
         bool source_opaque=(c->constant_color&&constant&&sp->const_buffer_size[PIPE_SHADER_FRAGMENT][0]>=16&&constant[3]==1.0f)||
             (view&&mbx_alpha_view(sp)&&view->swizzle_a==PIPE_SWIZZLE_1&&mbx_texture_fragment(sp->fs_variant->tokens,true));
         bool opaque_separate=source_opaque&&b->rgb_src_factor==PIPE_BLENDFACTOR_SRC_ALPHA&&b->rgb_dst_factor==PIPE_BLENDFACTOR_INV_SRC_ALPHA&&
             b->alpha_src_factor==PIPE_BLENDFACTOR_ONE&&b->alpha_dst_factor==PIPE_BLENDFACTOR_ONE;
         /* RGB565 has no stored alpha lane. Keep the RGB equation/factors
          * fully checked; independent alpha factors cannot affect its output. */
         bool opaque_target=c->reference_target&&c->reference_target->format==PIPE_FORMAT_B5G6R5_UNORM;
         bool separate_gpu=mbx_checkpoint_enabled(getenv("N810_MBX_SEPARATE_ALPHA"))&&c->vgp&&
             ((struct mbx_vgp_wire_frame*)c->vgp->data)->version==10&&
             b->rgb_src_factor==PIPE_BLENDFACTOR_SRC_ALPHA&&b->rgb_dst_factor==PIPE_BLENDFACTOR_INV_SRC_ALPHA&&
             b->alpha_src_factor==PIPE_BLENDFACTOR_ONE&&(b->alpha_dst_factor==PIPE_BLENDFACTOR_ONE||b->alpha_dst_factor==PIPE_BLENDFACTOR_INV_SRC_ALPHA);
         bool premultiply_copy=mbx_checkpoint_enabled(getenv("N810_MBX_SEPARATE_ALPHA"))&&c->vgp&&
             ((struct mbx_vgp_wire_frame*)c->vgp->data)->version==10&&!c->texture_active&&!sp->depth_stencil->depth_enabled&&
             b->rgb_src_factor==PIPE_BLENDFACTOR_SRC_ALPHA&&b->rgb_dst_factor==PIPE_BLENDFACTOR_ZERO&&
             b->alpha_src_factor==PIPE_BLENDFACTOR_ONE&&b->alpha_dst_factor==PIPE_BLENDFACTOR_ZERO;
         if(!getenv("N810_MBX_EXPERIMENTAL_BLEND") ||
            b->rgb_func!=PIPE_BLEND_ADD || b->alpha_func!=PIPE_BLEND_ADD ||
            (!mbx_opaque_copy(sp,c)&&!opaque_separate&&!opaque_target&&!separate_gpu&&!premultiply_copy&&(b->rgb_src_factor!=b->alpha_src_factor || b->rgb_dst_factor!=b->alpha_dst_factor)) ||
            !(mbx_opaque_copy(sp,c)||premultiply_copy||(b->rgb_src_factor==PIPE_BLENDFACTOR_SRC_ALPHA&&b->rgb_dst_factor==PIPE_BLENDFACTOR_INV_SRC_ALPHA)||
              (b->rgb_src_factor==PIPE_BLENDFACTOR_ONE&&b->rgb_dst_factor==PIPE_BLENDFACTOR_INV_SRC_ALPHA)||
              (b->rgb_src_factor==PIPE_BLENDFACTOR_ONE&&b->rgb_dst_factor==PIPE_BLENDFACTOR_ONE)))
         {fprintf(stderr,"N810_MBX_REJECT_BLEND rgb=%u,%u,%u alpha=%u,%u,%u\n",b->rgb_func,b->rgb_src_factor,b->rgb_dst_factor,b->alpha_func,b->alpha_src_factor,b->alpha_dst_factor);
            fprintf(stderr,"N810_MBX_REJECT_BLEND_SOURCE texture=%u format=%u swizzle_a=%u constant=%u opaque=%u\n",c->texture_active,view?view->format:0,view?view->swizzle_a:0,c->constant_color,source_opaque);
            mbx_fail("unsupported experimental blend equation or factors");}
      }

      bool clip_supported=!t.clip[0]&&!t.clip[1]&&t.clip[2]==c->header.width&&t.clip[3]==c->header.height;
      if(getenv("N810_MBX_EXPERIMENTAL_2D")&&getenv("N810_MBX_EXPERIMENTAL_SCISSOR"))
         clip_supported=t.clip[0]<=t.clip[2]&&t.clip[1]<=t.clip[3]&&t.clip[2]<=c->header.width&&t.clip[3]<=c->header.height;
      bool depth_supported=t.depth_enabled==1&&t.depth_write==1&&t.depth_func==1;
      if(getenv("N810_MBX_EXPERIMENTAL_2D"))depth_supported=mbx_mixed_depth(mbx_mixed_requested(getenv("N810_MBX_EXPERIMENTAL_MIXED")),t.depth_enabled,t.depth_write,t.depth_func);
      if(!depth_supported||t.color_mask!=15||
         t.shader_inputs!=(c->texture_modulate?2U:c->constant_color?0U:1U)||t.sampler_views!=(c->texture_active?1U:0U)||!clip_supported||
         (mode!=SP_INTERP_CONSTANT&&mode!=SP_INTERP_PERSPECTIVE)||
         sp->depth_stencil->alpha_enabled||sp->depth_stencil->stencil[0].enabled||
         sp->depth_stencil->stencil[1].enabled||sp->blend->logicop_enable||
         sp->active_query_count||(c->texture_active?!(c->texture_modulate||mbx_texture_fragment(sp->fs_variant->tokens,mbx_alpha_view(sp))):(info->num_instructions!=2||
         info->opcode_count[TGSI_OPCODE_MOV]!=1||info->opcode_count[TGSI_OPCODE_END]!=1)))
      {fprintf(stderr,"N810_MBX_REJECT_STATE clip=%u,%u,%u,%u target=%u,%u inputs=%u samplers=%u mode=%u alpha=%u stencil=%u,%u mask=%u\n",t.clip[0],t.clip[1],t.clip[2],t.clip[3],c->header.width,c->header.height,t.shader_inputs,t.sampler_views,mode,sp->depth_stencil->alpha_enabled,sp->depth_stencil->stencil[0].enabled,sp->depth_stencil->stencil[1].enabled,t.color_mask);
         mbx_fail("render state or fragment shader outside supported subset");}
   }
   if(c->texture_active)mbx_texture_upload(sp,c);
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
   if (!c || c->vgp || c->done || !c->header.triangles) return;
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
   if(c->shared_jobs&&(mbx_export.armed||mbx_export.held||mbx_window_retire(c)))mbx_fail("shared context still owns a published image or final sink");
   if(c->gpu_fd>=0)close(c->gpu_fd);
   unsigned history_bytes=0;for(unsigned i=0;i<4;++i){history_bytes+=c->history[i].bytes;free(c->history[i].wire);pipe_resource_reference(&c->history[i].target,NULL);}
   if(history_bytes)if(mbx_debug_enabled()) fprintf(stderr,"N810_MBX_SURFACE_HISTORY storage_bytes=%u slots=4\n",history_bytes);
   pipe_resource_reference(&c->reference_target,NULL);
   if(c->vgp){
      struct mbx_vgp_cached_shader *s=c->vgp->shaders;
      while(s){struct mbx_vgp_cached_shader *next=s->next;free(s);s=next;}if(mbx_debug_enabled()) fprintf(stderr,"N810_MBX_TEXTURE_RESIDENCY compact_jobs=%llu compact_bytes=%llu\n",(unsigned long long)c->vgp->texture_compact_jobs,(unsigned long long)c->vgp->texture_compact_bytes);free(c->vgp->textures.data);free(c->vgp->texture_compact);free(c->vgp->update);for(unsigned i=0;i<MBX_VGP_PREPARED_SLOTS;++i)free(c->vgp->template_snapshot[i]);free(c->vgp);
   }
   if(c->resource_cache){
      if(mbx_debug_enabled()) fprintf(stderr,"N810_MBX_RESOURCE_CACHE hits=%llu rebuilds=%llu storage_bytes=%u\n",
       (unsigned long long)c->resource_cache->hits,(unsigned long long)c->resource_cache->rebuilds,(unsigned)sizeof(*c->resource_cache));
      free(c->resource_cache);
   }
   if(c->texture_cache){
      if(mbx_debug_enabled()) fprintf(stderr,"N810_MBX_TEXTURE_CACHE hits=%llu rebuilds=%llu storage_bytes=%u\n",
         (unsigned long long)c->texture_cache->hits,(unsigned long long)c->texture_cache->rebuilds,(unsigned)sizeof(*c->texture_cache));
      free(c->texture_cache);
   }
   if(mbx_debug_enabled()) fprintf(stderr,"N810_MBX_LINEAR_CACHE hits=%llu rebuilds=%llu packed_bytes=%llu\n",(unsigned long long)c->linear_hits,(unsigned long long)c->linear_rebuilds,(unsigned long long)c->linear_packed_bytes);
   if(mbx_debug_enabled()) fprintf(stderr,"N810_MBX_RESOURCE_REFERENCES hits=%llu skipped_compare_bytes=%llu skipped_history_bytes=%llu\n",(unsigned long long)c->linear_wire_hits,(unsigned long long)c->linear_wire_skipped_bytes,(unsigned long long)c->history_skipped_bytes);
   if(c->window_renders||c->window_samples)if(mbx_debug_enabled()) fprintf(stderr,"N810_MBX_WINDOW_IMAGES renders=%llu samples=%llu skipped_read_bytes=%llu\n",(unsigned long long)c->window_renders,(unsigned long long)c->window_samples,(unsigned long long)c->window_skipped_read_bytes);
   for(unsigned i=0;i<14;i++)pipe_resource_reference(&c->window[i].resource,NULL);
   for(unsigned i=0;i<5;i++){pipe_resource_reference(&c->linear_cache[i].resource,NULL);free(c->linear_cache[i].upload);}
   free(c->wire_job);free(c->separate_rgb_wire);free(c->separate_alpha_wire);free(c->separate_merge_wire);free(c->pixels);free(c->rgba);
   mbx_trace_flush();
   free((void *)c->path); free(c->triangles); free(c);
   sp->mbx_capture = NULL;
}

#include "mbx_window_export_impl.h"
