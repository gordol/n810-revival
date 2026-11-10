/* Isolated channel-selector bring-up, disabled by default. Root-only knob;
 * invalid values/shapes reject before hardware work. */
#include "channel_select.c"
#include "channel_request.h"
/* Full diagnostics stay the default. Mode1 checks new uploads and periodic
 * completed jobs, plus every session close; admission and sync never change. */
static void mbx_dma_sink_release_channel(void);
static unsigned gpu_verification_mode;
static bool gpu_last_guard_checked;
module_param(gpu_last_guard_checked,bool,0400);
static unsigned long long gpu_verification_jobs,gpu_verification_checks,gpu_verification_skipped;
module_param(gpu_verification_mode,uint,0400);
module_param(gpu_verification_checks,ullong,0400);
module_param(gpu_verification_skipped,ullong,0400);
static int gpu_channel_select_mask=-1;
module_param(gpu_channel_select_mask,int,0600);
/* SPDX-License-Identifier: GPL-2.0-only
 * Persistent, exclusive fixed-function submission for the Mesa bring-up.
 * Userspace supplies bounded geometry, never GPU addresses or register writes.
 * The known four-color background render is mandatory startup verification.
 */
#include <linux/mutex.h>
#include <linux/ktime.h>
#include <linux/mm.h>
#include <linux/math64.h>
#include <linux/slab.h>
#include <linux/uaccess.h>
#include "mbx_parameter_data.h"
#include "mbx_texture_equal.h"
#include "mbx_surface_slots.h"
#include "mbx_image_abi.h"
static bool gpu_resident_surfaces;
module_param(gpu_resident_surfaces,bool,0400);
static unsigned gpu_resident_session;
static struct mbx_surface_slots gpu_resident_slots;
static struct mbx_surface_token gpu_resident_result;
static struct mbx_resident_bind gpu_resident_binding;
static bool gpu_resident_bound;
static struct mbx_resident_merge gpu_merge_binding;
static bool gpu_merge_bound;
static DEFINE_MUTEX(gpu_service_mutex);
static unsigned int gpu_service_active,gpu_service_failed,gpu_service_jobs;
static unsigned int gpu_service_baseline_verified;
static bool gpu_frame_background,gpu_frame_damage;
module_param(gpu_frame_damage,bool,0400);
module_param(gpu_frame_background,bool,0400);
static unsigned int gpu_frame_prepare_us,gpu_frame_clear_us,gpu_frame_render_us,gpu_frame_verify_us,gpu_frame_tail_verify_us;
static u64 gpu_frame_totals[5];
module_param(gpu_frame_prepare_us,uint,0400);
module_param(gpu_frame_clear_us,uint,0400);
module_param(gpu_frame_render_us,uint,0400);
module_param(gpu_frame_verify_us,uint,0400);
module_param(gpu_frame_tail_verify_us,uint,0400);
module_param(gpu_service_active,uint,0400);
module_param(gpu_service_failed,uint,0400);
module_param(gpu_service_jobs,uint,0400);
module_param(gpu_service_baseline_verified,uint,0400);
static bool gpu_service_opened,gpu_service_registered;
static bool gpu_frame_shared,gpu_frame_sparse_parameters;
module_param(gpu_frame_sparse_parameters,bool,0400);
module_param(gpu_service_opened,bool,0400);
module_param(gpu_frame_shared,bool,0400);
static u8 gpu_service_pixels[2048];
static void *gpu_service_result=gpu_service_pixels;
static unsigned gpu_service_result_bytes=2048,gpu_frame_width,gpu_frame_height,gpu_frame_stride;
static int gpu_service_wait(unsigned mask)
{
    unsigned i,status;
    for(i=0;i<operation_samples;++i){
        status=gpu_status(NULL);gpu_completion_status=status;
        if(status==~0U||(status&0x2a0U))return -EIO;
        if(status&mask){gpu_rbar(NULL);return 0;}
        /* Short tile jobs should not pay a scheduler tick for their first
         * completion check. Bounded spinning, then existing sleep budget. */
        if(i<128)udelay(1);else gpu_pause(NULL);
    }
    return -ETIMEDOUT;
}
struct mbx_service_vertex { u32 x,y,z,w,color; };
struct mbx_service_primitive {
    u32 depth_enabled,depth_write,depth_func,smooth;
    struct mbx_service_vertex vertices[3];
};
struct mbx_service_job { u32 magic,version,count,width,height,reserved; };

static int gpu_service_kick_surface_stride(void *cookie,unsigned background,unsigned width,unsigned height,unsigned target,unsigned stride)
{
    static const unsigned pairs[][2]={
      {0x608,0x20000},{0x610,0x30001},{0x614,0x1e3ce508},{0x618,0x1e3ce508},
      {0x61c,0x20007},{0x63c,0},{0x644,0},{0x648,1},{0x64c,0},{0x650,1},
      {0x654,31U<<16},{0x658,31U<<16},{0x65c,0x1000},{0x660,16},
      {0x674,0},{0x6d0,1},{0x6dc,0x3f800001},{0x860,0x10001}};
    unsigned i;int error;
    error=gpu_fresh_event(cookie,MBX_RENDER_COMPLETE);if(error)return error;
    gpu_write(cookie,0x83c,0x10000);
    gpu_write(cookie,0x6d8,0x09000000);gpu_write(cookie,0x85c,0x001404e1);
    for(i=0;i<ARRAY_SIZE(pairs);++i){
        unsigned value=pairs[i][1],reg=pairs[i][0];
        if(reg==0x654)value=(width-1)<<16;
        else if(reg==0x658)value=(height-1)<<16;
        else if(reg==0x65c)value=target;
        else if(reg==0x660)value=stride/4;
        gpu_write(cookie,reg,value);
    }
    gpu_write(cookie,0x60c,background);gpu_wbar(cookie);
    gpu_write(cookie,0x680,1);gpu_wbar(cookie);
    gpu_words_written+=ARRAY_SIZE(pairs)+5;
    return gpu_service_wait(MBX_RENDER_COMPLETE);
}
static int gpu_service_kick_surface(void *cookie,unsigned background,unsigned width,unsigned height,unsigned target)
{return gpu_service_kick_surface_stride(cookie,background,width,height,target,width*2);}
static int gpu_service_kick(void *cookie,unsigned background)
{return gpu_service_kick_surface(cookie,background,32,32,0x1000);}

static int gpu_service_clear_surface(unsigned width,unsigned height,unsigned target)
{
    unsigned words[20]={0xa0060040,0x1000,0x60800200,0x8000f0f0,0,0,0x00100020};
    unsigned i,status;int error;
    /* Proven32-bit fill format:16words by32rows,64-byte stride. This clears
     * the same2048-byte RGB565 target without interpreting or drawing pixels
     * on the CPU. Six FIFO pads and the original synchronization suffix. */
    for(i=7;i<20;++i)words[i]=0x70000000;words[13]=0xf0000000;
    words[0]=0xa0060000|width*2;words[1]=target;words[6]=((width/2)<<16)|height;
    error=gpu_fresh_event(NULL,0x400);if(error)return error;
    status=gpu_status(NULL);
    if(((status>>16)&255)>39)return -EBUSY;
    /* The independently verified2D FIFO is at5000a000.50008000 is TA. */
    for(i=0;i<20;++i)writel(words[i],gpu_2d_port);
    gpu_words_written+=20;gpu_wbar(NULL);
    return gpu_service_wait(0x400);
}
static int gpu_service_clear(void){return gpu_service_clear_surface(32,32,0x1000);}

static int gpu_service_baseline(void *cookie)
{
    static const u16 colors[4]={0xf800,0x07e0,0x001f,0xffff};
    unsigned region,j;int error;
    /* Exact page-separated objects and source textures from the verified
     * colorpages build. Destination is initialized only to poison by allocator. */
    memset(gpu_memory.parameters,0,65536);memset(gpu_memory.tiles,0,4096);
    for(region=0;region<4;++region){
        __le32 *b=(__le32 *)((u8 *)gpu_memory.parameters+4096*region);
        __le16 *tex=(__le16 *)((u8 *)gpu_memory.parameters+32768+8192*region);
        mbx_background32((unsigned *)b,64);
        b[1]=cpu_to_le32(0xa8804000);b[2]=cpu_to_le32(0x0e080000|((0x18000+8192*region)>>7));
        for(j=0;j<4096;++j)tex[j]=cpu_to_le16(colors[region]);
    }
    error=mbx_dma_submit(&gpu_memory);if(error)return error;
    gpu_submitted=1;gpu_dma_stage=gpu_memory.stage;
    for(region=0;region<4;++region){
        ((__le32 *)gpu_memory.tiles)[0]=cpu_to_le32(0xe2000000|(region&1)|((region>>1)<<8));
        gpu_wbar(cookie);error=gpu_service_kick(cookie,0x10000+4096*region);if(error)return error;
    }
    dma_rmb();
    for(j=0;j<1024;++j)
        if(le16_to_cpu(((__le16 *)gpu_memory.target)[j])!=colors[((j%32)/16)+2*((j/32)/16)])return -EILSEQ;
    error=mbx_dma_verify_bounds(&gpu_memory);if(error)return error;
    gpu_service_baseline_verified=1;
    memcpy(gpu_service_pixels,gpu_memory.target,2048);
    return 0;
}

static int gpu_service_validate(const struct mbx_service_job *h,size_t bytes)
{
    const struct mbx_service_primitive *p=(const void *)(h+1);unsigned i,j;
    unsigned limit=h->version>=2?512:32,max_count=h->version>=2?512:256;
    if(bytes<sizeof(*h)||h->magic!=0x314a424d||(h->version!=1&&h->version!=2&&h->version!=3)||h->count>max_count||
       !h->width||h->width>limit||!h->height||h->height>limit||(h->version<3&&h->reserved)||
       (h->version==3&&(h->reserved<h->width*2||h->reserved>1024||(h->reserved&3)))||
       (h->version>=2&&(h->width&1))||
       bytes!=sizeof(*h)+h->count*sizeof(*p))return -EINVAL;
    for(i=0;i<h->count;++i){
        if(p[i].depth_enabled!=1||p[i].depth_write!=1||p[i].depth_func!=1||p[i].smooth>1)return -EINVAL;
        for(j=0;j<3;++j){
            const struct mbx_service_vertex *v=&p[i].vertices[j];
            /* IEEE positive finite range checks without kernel floating point. */
            if(v->x>(h->version>=2?0x44000000U:0x42000000U)||v->y>(h->version>=2?0x44000000U:0x42000000U)||v->z>0x3f800000U||
               !v->w||v->w>0x3f800000U||(v->color>>24)!=255)return -EINVAL;
        }
    }
    return 0;
}

struct gpu_region_bounds {u16 x0,y0,x1,y1;};
static struct gpu_region_bounds gpu_bounds[512];
static unsigned gpu_region_counts[1024],gpu_region_offsets[1024],gpu_region_cursors[1024];
static bool gpu_previous_regions[1024];
static bool gpu_region_active(unsigned region)
{
    return gpu_region_counts[region] || (gpu_frame_background &&
           (!gpu_frame_damage || gpu_previous_regions[region]));
}
static unsigned gpu_positive_floor(unsigned bits)
{
    int exponent=(int)((bits>>23)&255)-127;
    if(exponent<0)return 0;
    return ((bits&0x7fffff)|0x800000)>>(23-exponent);
}
static int gpu_service_frame(const struct mbx_service_job *h)
{
    const struct mbx_service_primitive *p=(const void *)(h+1);
    __le32 *parameters=gpu_memory.parameters,*regions=gpu_memory.tiles;
    unsigned nx=(h->width+15)/16,ny=(h->height+15)/16,gx=(nx+3)/4,gy=(ny+3)/4;
    unsigned stride=h->version==3?h->reserved:h->width*2;
    unsigned i,j,x,y,offset=0xa000,last_header=0,active_regions=0,bytes=stride*h->height;
    u64 t0=ktime_get_ns(),t1,t2,t3,t4,t5;
    int error;
    if(gpu_frame_width&&(h->width!=gpu_frame_width||h->height!=gpu_frame_height||stride!=gpu_frame_stride))return -EINVAL;
    if(!bytes || bytes>gpu_frame_capacity_bytes ||
       bytes>gpu_memory.frame_page_count*4096U)return -ENOMEM;
    memset(gpu_region_counts,0,sizeof(gpu_region_counts));
    /* Bounding-box binning is integer-only. The GPU clips and shades the
     * original primitives; no CPU clipping or per-tile vertex copies. */
    for(i=0;i<h->count;++i){
        unsigned minx=512,miny=512,maxx=0,maxy=0;
        for(j=0;j<3;++j){
            x=gpu_positive_floor(p[i].vertices[j].x);y=gpu_positive_floor(p[i].vertices[j].y);
            if(x>h->width||y>h->height)return -EINVAL;
            minx=min(minx,x);miny=min(miny,y);maxx=max(maxx,x);maxy=max(maxy,y);
        }
        gpu_bounds[i]=(struct gpu_region_bounds){min(minx/16,nx-1),min(miny/16,ny-1),min(maxx/16,nx-1),min(maxy/16,ny-1)};
        for(y=gpu_bounds[i].y0;y<=gpu_bounds[i].y1;++y)
            for(x=gpu_bounds[i].x0;x<=gpu_bounds[i].x1;++x)++gpu_region_counts[y*nx+x];
    }
    for(i=0;i<nx*ny;++i)if(gpu_region_active(i)){
        ++active_regions;
        unsigned next=offset+(gpu_region_counts[i]+1+(gpu_frame_background?1:0))*4;
        if(next>65536)return -ENOSPC;
        gpu_region_offsets[i]=gpu_region_cursors[i]=offset;offset=next;
    }
    gpu_phase=20;
    /* Every referenced native record and list word is assigned below.
     * Clearing unreferenced parameter storage is optional bring-up overhead. */
    if(!gpu_frame_sparse_parameters)memset(parameters,0,65536);
    memset(regions,0,MBX_TILE_BYTES);
    mbx_background32((unsigned *)parameters,64);
    parameters[1]=cpu_to_le32(0xa8804000);parameters[2]=cpu_to_le32(0x0e080000|(0x22000>>7));
    /* Full-surface background triangle, constant black texel. The old
     * 32px template UV gradients otherwise sample beyond the black bitmap. */
    parameters[7]=parameters[10]=cpu_to_le32(0x44800000);
    parameters[21]=parameters[25]=0;
    if(gpu_frame_background){
        /* Owned opaque black triangle covers every pixel of the bounded
         * <=512x512 viewport. ALWAYS depth test writes the clear depth 1.0.
         * Its parameter record fits wholly in the reserved first page.
         * Each tile draws it before application geometry, preserving order. */
        __le32 *b=parameters+32;
        b[0]=cpu_to_le32(0xe0000000);b[1]=cpu_to_le32(0x22200e00);
        b[2]=0;b[3]=0;b[4]=cpu_to_le32(0x44800000);b[5]=0;
        b[6]=0;b[7]=cpu_to_le32(0x44800000);
        for(i=8;i<14;++i)b[i]=cpu_to_le32(0x3f800000);
        for(i=14;i<17;++i)b[i]=cpu_to_le32(0xff000000);
        for(i=0;i<nx*ny;++i)if(gpu_region_active(i)){
            *(__le32 *)((u8 *)parameters+gpu_region_cursors[i])=cpu_to_le32(0x40800020);
            gpu_region_cursors[i]+=4;
        }
    }
    for(i=0;i<h->count;++i){
        __le32 *o=(__le32 *)((u8 *)parameters+4096+i*68);
        o[0]=cpu_to_le32(0xe0000000);o[1]=cpu_to_le32(0x22200200|(p[i].smooth?0x400000:0));
        for(j=0;j<3;++j){
            unsigned color=p[i].vertices[j].color;
            o[2+2*j]=cpu_to_le32(p[i].vertices[j].x);o[3+2*j]=cpu_to_le32(p[i].vertices[j].y);
            o[8+j]=cpu_to_le32(p[i].vertices[j].z);o[11+j]=cpu_to_le32(p[i].vertices[j].w);
            o[14+j]=cpu_to_le32((color&0xff00ff00)|((color&255)<<16)|((color>>16)&255));
        }
        for(y=gpu_bounds[i].y0;y<=gpu_bounds[i].y1;++y)for(x=gpu_bounds[i].x0;x<=gpu_bounds[i].x1;++x){
            unsigned region=y*nx+x;
            *(__le32 *)((u8 *)parameters+gpu_region_cursors[region])=cpu_to_le32(0x40800000|((4096+i*68)/4));
            gpu_region_cursors[region]+=4;
        }
    }
    for(y=0;y<gy*4;++y)for(x=0;x<gx*4;++x){
        unsigned header=((y/4)*gx+x/4)*32+((y%4)*4+x%4)*2;
        regions[header]=cpu_to_le32(0x22000000|x|(y<<8));
        if(x<nx&&y<ny&&gpu_region_active(y*nx+x)){
            i=y*nx+x;regions[header]=cpu_to_le32(0x20000000|x|(y<<8));
            regions[header+1]=cpu_to_le32(0x10000+gpu_region_offsets[i]);
            *(__le32 *)((u8 *)parameters+gpu_region_cursors[i])=cpu_to_le32(0xf0000000);
            last_header=max(last_header,header);
        }
    }
    if(active_regions)regions[last_header]|=cpu_to_le32(0x84000000);
    error=mbx_dma_frame_for_device(&gpu_memory);if(error)return error;
    dma_wmb();gpu_phase=21;t1=ktime_get_ns();
    /* Initialize row padding once; later frames clear visible pixels in ISP. */
    if(!gpu_frame_background||!gpu_frame_width){
        error=gpu_service_clear_surface(stride/2,h->height,MBX_FRAME_VA);if(error)return error;
    }
    t2=ktime_get_ns();gpu_phase=22;
    if(active_regions){error=gpu_service_kick_surface_stride(NULL,0x10000,h->width,h->height,MBX_FRAME_VA,stride);if(error)return error;}
    t3=ktime_get_ns();
    mbx_dma_frame_for_cpu(&gpu_memory);
    error=mbx_dma_verify_bounds(&gpu_memory);if(error)return error;
    t4=ktime_get_ns();dma_rmb();gpu_phase=23;
    for(i=0;i<gpu_memory.frame_page_count;++i){
        unsigned first=i*4096,copy=first<bytes?min(4096U,bytes-first):0;

        /* Even-width RGB565 makes every used tail word-aligned. Check
         * every guard byte via native loads, not four uncached byte reads. */
        for(j=copy/4;j<4096/4;++j)if(((const u32 *)gpu_memory.frame_pages[i])[j]!=0x3c3c3c3c)return -EOVERFLOW;
    }
    t5=ktime_get_ns();
    gpu_frame_totals[0]+=t1-t0;gpu_frame_totals[1]+=t2-t1;gpu_frame_totals[2]+=t3-t2;
    gpu_frame_totals[3]+=t4-t3;gpu_frame_totals[4]+=t5-t4;
    gpu_frame_prepare_us=div_u64(div_u64(gpu_frame_totals[0],gpu_service_jobs+1),1000);
    gpu_frame_clear_us=div_u64(div_u64(gpu_frame_totals[1],gpu_service_jobs+1),1000);
    gpu_frame_render_us=div_u64(div_u64(gpu_frame_totals[2],gpu_service_jobs+1),1000);
    gpu_frame_verify_us=div_u64(div_u64(gpu_frame_totals[3],gpu_service_jobs+1),1000);
    gpu_frame_tail_verify_us=div_u64(div_u64(gpu_frame_totals[4],gpu_service_jobs+1),1000);
    /* A tile is clean once its previous content has been erased. Retain only
     * this frame's coverage, so empty tiles do not keep generating GPU work. */
    for(i=0;i<nx*ny;++i)gpu_previous_regions[i]=gpu_region_counts[i]!=0;
    gpu_frame_width=h->width;gpu_frame_height=h->height;gpu_frame_stride=stride;
    gpu_service_result=NULL;gpu_service_result_bytes=bytes;++gpu_service_jobs;
    return 0;
}

static int gpu_service_scene(const struct mbx_service_job *h)
{
    const struct mbx_service_primitive *p=(const void *)(h+1);
    __le32 *parameters=gpu_memory.parameters,*tiles=gpu_memory.tiles;
    unsigned i,j,r;int error;
    /* Completion of the previous job is required before reusing its memory. */
    if(!(gpu_status(NULL)&MBX_RENDER_COMPLETE))return -EBUSY;
    memset(parameters,0,65536);memset(tiles,0,4096);
    mbx_background32((unsigned *)parameters,64);
    parameters[1]=cpu_to_le32(0xa8804000);parameters[2]=cpu_to_le32(0x0e080000|(0x20800>>7));
    /* An empty native object list does not write uncovered target pixels.
     * Clear using the proven GPU background path before reusing this tile.
     * The source bitmap is black; the CPU never clears the render target. */
    error=gpu_service_clear();if(error)return error;
    /* Native ISP objects, reconstructed from owned TA captures. No original
     * vendor programs are uploaded and no CPU store draws target pixels. */
    for(i=0;i<h->count;++i){
        __le32 *o=(__le32 *)((u8 *)parameters+4096+i*68);
        o[0]=cpu_to_le32(0xe0000000);
        o[1]=cpu_to_le32(0x22200200|(p[i].smooth?0x400000:0));
        for(j=0;j<3;++j){
            o[2+2*j]=cpu_to_le32(p[i].vertices[j].x);
            o[3+2*j]=cpu_to_le32(p[i].vertices[j].y);
            o[8+j]=cpu_to_le32(p[i].vertices[j].z);
            o[11+j]=cpu_to_le32(p[i].vertices[j].w);
            /* FIFO normal RGBA packing is ABGR, but native ISP parameter
             * colors are ARGB. Physical gears comparison establishes this. */
            unsigned color=p[i].vertices[j].color;
            o[14+j]=cpu_to_le32((color&0xff00ff00)|((color&255)<<16)|((color>>16)&255));
        }
    }
    /* Retain the measured padded4x4 region layout. Every region's list names
     * the same clipped32x32 scene; hardware performs16x16 region clipping. */
    for(i=0;i<16;++i)tiles[2*i]=cpu_to_le32(0x22000000|(i%4)|((i/4)<<8));
    for(r=0;r<4;++r){
        unsigned index=(r&1)+4*(r>>1),offset=0xe000+r*1028;
        __le32 *list=(__le32 *)((u8 *)parameters+offset);
        tiles[2*index]=cpu_to_le32((r==3?0xa4000000:0x20000000)|(r&1)|((r>>1)<<8));
        tiles[2*index+1]=cpu_to_le32(0x10000+offset);
        for(i=0;i<h->count;++i)list[i]=cpu_to_le32(0x40800000|((4096+i*68)/4));
        list[h->count]=cpu_to_le32(0xf0000000);
    }
    if(h->count){dma_wmb();error=gpu_service_kick(NULL,0x10000);if(error)return error;}
    error=mbx_dma_verify_bounds(&gpu_memory);if(error)return error;
    dma_rmb();memcpy(gpu_service_pixels,gpu_memory.target,2048);
    gpu_service_result=gpu_service_pixels;gpu_service_result_bytes=2048;++gpu_service_jobs;
    return 0;
}

static void *gpu_service_wire;
static struct mbx_command *gpu_service_commands;
/* The exclusive service mutex serializes this bounded exact-key cache. */
static struct mbx_vgp_shader_cache gpu_service_shader_cache;
_Static_assert(MBX_LINEAR_PAYLOAD==MBX_WIRE_LINEAR_PAYLOAD,"CPU/GPU linear bounds disagree");
static struct mbx_vgp_prepared gpu_prepared_slots[MBX_VGP_PREPARED_SLOTS];
static struct mbx_command *gpu_prepared_storage[MBX_VGP_PREPARED_SLOTS];
static unsigned gpu_prepared_slot,gpu_prepared_next;
#define gpu_service_prepared (gpu_prepared_slots[gpu_prepared_slot])
#define gpu_service_replay_cache (gpu_service_prepared.cache)
/* Experimental source path; normal sessions retain their existing behavior. */
static bool gpu_prepared_commands;
module_param(gpu_prepared_commands,bool,0400);
static bool gpu_wire_replay=true;
static unsigned gpu_wire_replay_hits,gpu_wire_replay_misses;
static unsigned gpu_template_serial,gpu_template_generation;
static unsigned gpu_template_uploads,gpu_template_updates;
static unsigned long long gpu_template_upload_bytes,gpu_template_update_bytes;
static unsigned long long gpu_template_copy_ns,gpu_template_encode_ns,gpu_full_copy_ns,gpu_full_encode_ns;
module_param(gpu_template_generation,uint,0400);
module_param(gpu_template_uploads,uint,0400);
module_param(gpu_template_updates,uint,0400);
module_param(gpu_template_upload_bytes,ullong,0400);
module_param(gpu_template_update_bytes,ullong,0400);
module_param(gpu_template_copy_ns,ullong,0400);
module_param(gpu_template_encode_ns,ullong,0400);
module_param(gpu_full_copy_ns,ullong,0400);
module_param(gpu_full_encode_ns,ullong,0400);
module_param(gpu_wire_replay,bool,0400);
module_param(gpu_wire_replay_hits,uint,0400);
module_param(gpu_wire_replay_misses,uint,0400);
static unsigned gpu_frame_selected,gpu_image0_jobs,gpu_image1_jobs;
module_param(gpu_frame_selected,uint,0400);
module_param(gpu_image0_jobs,uint,0400);
module_param(gpu_image1_jobs,uint,0400);
static unsigned gpu_vgp_copy_us,gpu_vgp_encode_us,gpu_vgp_prepare_us,gpu_vgp_execute_us,gpu_vgp_verify_us,gpu_vgp_write_us;
static u64 gpu_vgp_total_ns[6];
module_param(gpu_vgp_copy_us,uint,0400);
module_param(gpu_vgp_encode_us,uint,0400);
module_param(gpu_vgp_prepare_us,uint,0400);
module_param(gpu_vgp_execute_us,uint,0400);
module_param(gpu_vgp_verify_us,uint,0400);
module_param(gpu_vgp_write_us,uint,0400);
#include "mbx_surface_lease.h"
static struct mbx_surface_lease gpu_surface_lease;
static unsigned gpu_surface_session,gpu_surface_generation;
#include "mbx_texture_resident.h"
static struct mbx_window_state gpu_windows;
static struct mbx_window_request gpu_window_binding;
static struct mbx_window_token gpu_window_result;
static bool gpu_window_bound;
static struct mbx_texture_resident gpu_texture_resident;
static void *gpu_texture_resident_wire;
static bool gpu_texture_residency;
module_param(gpu_texture_residency,bool,0400);
static unsigned long long gpu_texture_upload_bytes,gpu_texture_resident_hits,gpu_texture_ref_bytes;
module_param(gpu_texture_upload_bytes,ullong,0400);
module_param(gpu_texture_resident_hits,ullong,0400);
module_param(gpu_texture_ref_bytes,ullong,0400);
static unsigned long long gpu_sink_bytes,gpu_sink_calls;
module_param(gpu_sink_bytes,ullong,0400);
module_param(gpu_sink_calls,ullong,0400);
static int gpu_service_open(struct inode *inode,struct file *file)
{
    int e=0;(void)inode;
    mutex_lock(&gpu_service_mutex);
    if(!gpu_service_active||gpu_service_failed)e=-ENODEV;
    else if(gpu_service_opened)e=-EBUSY;
    else if(gpu_surface_session==~0U)e=-EOVERFLOW;
    else{
        if(gpu_resident_surfaces){
            if(gpu_frame_shared||(gpu_memory.frame_images!=2&&gpu_memory.frame_images!=3)){e=-EINVAL;goto done;}
            if(gpu_resident_session==~0U){e=-EOVERFLOW;goto done;}
            mbx_surface_slots_open(&gpu_resident_slots,++gpu_resident_session);
        }
        gpu_resident_bound=false;gpu_merge_bound=false;memset(&gpu_resident_result,0,sizeof(gpu_resident_result));
        memset(&gpu_service_shader_cache,0,sizeof(gpu_service_shader_cache));
        memset(gpu_prepared_slots,0,sizeof(gpu_prepared_slots));
        memset(gpu_prepared_storage,0,sizeof(gpu_prepared_storage));
        gpu_prepared_slot=gpu_prepared_next=0;
        gpu_wire_replay_hits=gpu_wire_replay_misses=0;
        gpu_template_generation=gpu_template_uploads=gpu_template_updates=0;
        gpu_template_upload_bytes=gpu_template_update_bytes=0;
        gpu_template_copy_ns=gpu_template_encode_ns=gpu_full_copy_ns=gpu_full_encode_ns=0;
        gpu_service_wire=vmalloc(MBX_VGP_WIRE_MAX_BYTES);
        if(gpu_prepared_commands){
            unsigned i;
            for(i=0;i<MBX_VGP_PREPARED_SLOTS&&gpu_service_wire;++i){
                gpu_prepared_storage[i]=vmalloc(MBX_VGP_WIRE_MAX_COMMANDS*sizeof(*gpu_service_commands));
                if(!gpu_prepared_storage[i])break;
            }
            if(!gpu_service_wire||i!=MBX_VGP_PREPARED_SLOTS){
                for(i=0;i<MBX_VGP_PREPARED_SLOTS;++i){
                    vfree(gpu_prepared_storage[i]);gpu_prepared_storage[i]=NULL;
                    vfree(gpu_prepared_slots[i].cache.snapshot);gpu_prepared_slots[i].cache.snapshot=NULL;
                }
                vfree(gpu_texture_resident_wire);gpu_texture_resident_wire=NULL;memset(&gpu_texture_resident,0,sizeof(gpu_texture_resident));vfree(gpu_service_wire);gpu_service_wire=NULL;gpu_service_commands=NULL;e=-ENOMEM;goto done;
            }
            gpu_service_commands=gpu_prepared_storage[0];
        }else{
            gpu_service_commands=vmalloc(MBX_VGP_WIRE_MAX_COMMANDS*sizeof(*gpu_service_commands));
            if(!gpu_service_wire||!gpu_service_commands){
                vfree(gpu_texture_resident_wire);gpu_texture_resident_wire=NULL;memset(&gpu_texture_resident,0,sizeof(gpu_texture_resident));vfree(gpu_service_wire);vfree(gpu_service_commands);
                gpu_service_wire=NULL;gpu_service_commands=NULL;e=-ENOMEM;goto done;
            }
            if(gpu_wire_replay){
                gpu_service_replay_cache.snapshot=vmalloc(65536);
                gpu_service_replay_cache.snapshot_capacity=65536;
            }
        }
        ++gpu_surface_session;gpu_verification_jobs=0;gpu_windows=(struct mbx_window_state){.session=gpu_surface_session,.layout=gpu_window_native?2:1};gpu_window_bound=false;memset(&gpu_window_result,0,sizeof(gpu_window_result));gpu_texture_resident.session=gpu_surface_session;gpu_texture_resident.valid=0;gpu_surface_generation=0;memset(&gpu_surface_lease,0,sizeof(gpu_surface_lease));
        gpu_memory.frame_active=0;gpu_frame_selected=0;gpu_service_opened=true;file->private_data=NULL;
        i_size_write(file_inode(file),gpu_frame_shared?gpu_memory.frame_block_bytes:0);}
done:
    mutex_unlock(&gpu_service_mutex);return e;
}
/* Caller holds gpu_service_mutex. Reject retained ownership before changing
 * the selected object, its identity or the replacement cursor. */
static int gpu_service_select_prepared(unsigned bytes)
{
    unsigned slot=gpu_prepared_next;struct mbx_vgp_prepared *o;
    if(!gpu_prepared_commands||slot>=MBX_VGP_PREPARED_SLOTS)return -EINVAL;
    o=gpu_prepared_slots+slot;
    if(o->busy||o->exports)return -EBUSY;
    if(o->fault||!gpu_prepared_storage[slot])return -EIO;
    if(bytes<sizeof(struct mbx_vgp_wire_frame)||bytes>MBX_VGP_WIRE_MAX_BYTES)return -EINVAL;
    if(gpu_template_serial==~0U)return -EOVERFLOW;
    /* Allocate before touching the old identity or replacement cursor. Keep
     * a bounded high-water capacity so alternating frame sizes do not churn.
     * Four slots remain capped at four maximum wire buffers in total. */
    if(o->cache.snapshot_capacity<bytes){
        void *replacement=vmalloc(bytes);
        if(!replacement)return -ENOMEM;
        vfree(o->cache.snapshot);o->cache.snapshot=replacement;
        o->cache.snapshot_capacity=bytes;
    }
    o->generation=gpu_template_serial;
    gpu_prepared_slot=slot;gpu_prepared_next=(slot+1)%MBX_VGP_PREPARED_SLOTS;
    gpu_service_commands=gpu_prepared_storage[slot];return 0;
}
static void gpu_service_free_storage(void)
{
    unsigned i;
    if(gpu_prepared_commands){
        for(i=0;i<MBX_VGP_PREPARED_SLOTS;++i){
            vfree(gpu_prepared_storage[i]);gpu_prepared_storage[i]=NULL;
            vfree(gpu_prepared_slots[i].cache.snapshot);
        }
    }else{vfree(gpu_service_commands);vfree(gpu_service_replay_cache.snapshot);}
    vfree(gpu_texture_resident_wire);gpu_texture_resident_wire=NULL;memset(&gpu_texture_resident,0,sizeof(gpu_texture_resident));vfree(gpu_service_wire);gpu_service_wire=NULL;gpu_service_commands=NULL;
    memset(gpu_prepared_slots,0,sizeof(gpu_prepared_slots));
}
static int gpu_service_close(struct inode *inode,struct file *file)
{
    unsigned i;(void)inode;(void)file;mutex_lock(&gpu_service_mutex);
    if(gpu_prepared_commands)for(i=0;i<MBX_VGP_PREPARED_SLOTS;++i)if(gpu_prepared_slots[i].busy||gpu_prepared_slots[i].exports){
        gpu_service_opened=false;gpu_service_failed=1;mutex_unlock(&gpu_service_mutex);return 0;
    }
    if(gpu_verification_mode&&gpu_service_active&&!gpu_service_failed){
        int checked=mbx_dma_verify_bounds(&gpu_memory);++gpu_verification_checks;
        if(!checked&&gpu_texture_resident.valid&&gpu_texture_resident.bytes&&
           !mbx_texture_equal((u8*)gpu_memory.linear+4096,gpu_texture_resident.data,gpu_texture_resident.bytes))checked=-EILSEQ;
        gpu_bounds_verified=!checked;gpu_last_guard_checked=true;
        if(checked){gpu_service_opened=false;gpu_service_failed=1;gpu_error=checked;mutex_unlock(&gpu_service_mutex);return 0;}
    }
    mbx_dma_sink_release_channel();
    gpu_service_opened=false;memset(&gpu_surface_lease,0,sizeof(gpu_surface_lease));
    mbx_surface_slots_invalidate(&gpu_resident_slots);gpu_resident_bound=false;gpu_merge_bound=false;
    gpu_template_generation=0;gpu_service_free_storage();mutex_unlock(&gpu_service_mutex);return 0;
}
/* Called only by attended recovery after DMA quiescence and release. */
static int gpu_service_retire_prepared(unsigned reset_complete,unsigned mmu_control,unsigned tables_cleared)
{
    unsigned i;int e;
    if(!gpu_prepared_commands)return 0;
    /* Preflight every object before retiring any; exported or invalid busy
     * ownership is never partially released. */
    for(i=0;i<MBX_VGP_PREPARED_SLOTS;++i){
        struct mbx_vgp_prepared *o=gpu_prepared_slots+i;
        if(o->exports||(o->busy&&(!o->valid||!o->session||!o->generation)))return -EINVAL;
    }
    for(i=0;i<MBX_VGP_PREPARED_SLOTS;++i){
        void *snapshot=gpu_prepared_slots[i].cache.snapshot;
        e=mbx_vgp_prepared_retire_after_reset(gpu_prepared_slots+i,reset_complete,mmu_control,tables_cleared);
        if(e)return e;
        /* close cleared metadata, retain allocation only for the final free. */
        gpu_prepared_slots[i].cache.snapshot=snapshot;
    }
    gpu_service_free_storage();gpu_template_generation=0;return 0;
}
/* Cumulative diagnostics; read only after submissions stop (ARMv6 u64). */
static unsigned long long gpu_return_cpu_ns,gpu_bounds_check_ns,gpu_return_profile_jobs;
static unsigned long long gpu_bounds_only_ns,gpu_texture_verify_ns,gpu_texture_verify_bytes,gpu_read_lock_ns,gpu_read_copy_ns,gpu_read_bytes,gpu_read_calls;
module_param(gpu_bounds_only_ns,ullong,0400);
module_param(gpu_texture_verify_ns,ullong,0400);
module_param(gpu_texture_verify_bytes,ullong,0400);
module_param(gpu_read_lock_ns,ullong,0400);
module_param(gpu_read_copy_ns,ullong,0400);
module_param(gpu_read_bytes,ullong,0400);
module_param(gpu_read_calls,ullong,0400);
static bool gpu_capture_success=true;
static unsigned long long gpu_success_capture_ns;
module_param(gpu_capture_success,bool,0400);
module_param(gpu_success_capture_ns,ullong,0400);
module_param(gpu_return_cpu_ns,ullong,0400);
module_param(gpu_bounds_check_ns,ullong,0400);
module_param(gpu_return_profile_jobs,ullong,0400);
/* Typed shader/input transport. Validation completes before hardware is touched. */
static ssize_t gpu_service_write(struct file *file,const char __user *buf,size_t bytes,loff_t *off)
{
    struct mbx_vgp_wire_frame *job;
    const struct mbx_vgp_wire_frame *texture_job;const u8 *texture_data;unsigned texture_bytes=0;struct mbx_wire_resources resources;
    struct mbx_gpu_result result;
    size_t submitted_bytes=bytes;bool texture_reference=false,texture_reused=false,window_started=false,window_merge=false;
    unsigned count=0,i;int channel_mask;bool update=false,resident_job=false,resident_started=false,merge_job=false,prepared_started=false,prepared_hardware=false;int e=0;u64 t[7],returned=0;
    if(probe_mode!=3||bytes<sizeof(struct mbx_vgp_wire_update)||bytes>MBX_VGP_WIRE_MAX_BYTES)return -EINVAL;
    t[0]=ktime_get_ns();mutex_lock(&gpu_service_mutex);
    if(gpu_verification_mode>1||!gpu_service_active||gpu_service_failed||!gpu_service_wire||!gpu_service_commands){e=-EIO;goto out;}
    if(gpu_surface_lease.held){e=-EBUSY;goto out;}
    if(gpu_surface_generation==~0U){e=-EOVERFLOW;goto out;}
    memset(&gpu_surface_lease.image,0,sizeof(gpu_surface_lease.image));
    channel_mask=gpu_channel_select_mask;
    if(channel_mask < -1 || channel_mask > 15){e=-EINVAL;goto out;}
    job=gpu_service_wire;
    /* The resident canonical buffer owns its texture bytes. A reference
     * changes only header/draw ranges; no texture reconstruction/copy. */
    if(copy_from_user(job,buf,32)){gpu_template_generation=0;e=-EFAULT;goto out;}
    if(job->magic==MBX_TEXTURE_REF_MAGIC){
        struct mbx_texture_ref ref;
        memcpy(&ref,job,32);
        if(!gpu_texture_residency||!gpu_texture_resident_wire||ref.data_offset>1088||bytes<32+ref.data_offset){e=-ESTALE;goto out;}
        if(copy_from_user((u8 *)job+32,buf+32,ref.data_offset)){e=-EFAULT;goto out;}
        if(mbx_texture_ref_validate(&gpu_texture_resident,job,32+ref.data_offset,bytes,MBX_VGP_WIRE_MAX_BYTES)){e=-ESTALE;goto out;}
        job=gpu_texture_resident_wire;
        memcpy(job,(u8 *)gpu_service_wire+32,ref.data_offset);
        if(copy_from_user((u8 *)job+ref.data_offset+ref.texture_bytes,buf+32+ref.data_offset,ref.frame_bytes-ref.data_offset-ref.texture_bytes)){
            gpu_texture_resident.valid=0;e=-EFAULT;goto out;
        }
        bytes=ref.frame_bytes;texture_reference=true;
    }else if(copy_from_user((u8 *)job+32,buf+32,bytes-32)){gpu_template_generation=0;e=-EFAULT;goto out;}
    t[1]=ktime_get_ns();
    update=job->magic==MBX_VGP_UPDATE_MAGIC;
    /* Typed bounded channel-combine request. The resource descriptor carries
     * only RGBA channel bits; addresses/strides derive from validated dimensions. */
    if(!update){struct mbx_wire_resources channel_resources;
        e=mbx_wire_resources_parse(job,bytes,&channel_resources);if(e)goto out;
        if(channel_resources.count==1&&(channel_resources.item[0].version==9||channel_resources.item[0].version==11))
            channel_mask=channel_resources.item[0].reserved;
    }
    if(update){
        if(channel_mask>=0){e=-EINVAL;goto out;}
        if(gpu_prepared_commands){
            struct mbx_vgp_prepared_handle handle;
            int slot=mbx_vgp_prepared_find(gpu_prepared_slots,MBX_VGP_PREPARED_SLOTS,gpu_surface_session,
                ((struct mbx_vgp_wire_update *)job)->generation);
            if(slot<0){e=-EINVAL;goto out;}
            gpu_prepared_slot=slot;gpu_service_commands=gpu_prepared_storage[slot];
            gpu_template_generation=gpu_service_prepared.generation;
            e=mbx_vgp_prepared_dispatch(&gpu_service_prepared,gpu_surface_session,job,bytes,
                gpu_service_commands,MBX_VGP_WIRE_MAX_COMMANDS,gpu_service_replay_cache.snapshot,
                gpu_service_replay_cache.snapshot_capacity,&gpu_service_shader_cache,&handle,&count);
            prepared_started=!e;
        }else e=mbx_vgp_wire_apply_update(job,bytes,gpu_template_generation,gpu_service_commands,
                MBX_VGP_WIRE_MAX_COMMANDS,&count,&gpu_service_replay_cache);
    }else{
        /* A full upload may replace command storage, even if later rejected. */
        gpu_template_generation=0;
        if(bytes<sizeof(*job)||!job->width||!job->height||((job->width>400||job->height>400)&&!(gpu_desktop_target&&job->version==9&&job->width==800&&job->height==480&&!gpu_frame_shared&&gpu_memory.frame_images==1))||(job->width&15)||((job->height&15)&&!(job->version==10&&job->width==240&&job->height==241))||((gpu_frame_shared||gpu_memory.frame_images!=1)&&!(gpu_resident_surfaces&&job->version==10&&job->width*job->height<=80000U)&&(job->width!=400||job->height!=400))){e=-EINVAL;goto out;}
        if(job->width*job->height*(job->version==10?4U:2U)>gpu_frame_capacity_bytes||
           (job->version==10&&(gpu_frame_shared||(gpu_memory.frame_images!=1&&!gpu_resident_surfaces)))){e=-EINVAL;goto out;}
        if(channel_mask<0&&!job->clear_buffers&&!(job->width==240&&job->height==320)){e=-EINVAL;goto out;}
        if(gpu_template_serial==~0U){e=-EOVERFLOW;goto out;}
        if(gpu_prepared_commands){
            struct mbx_vgp_prepared_handle handle;
            /* External surface dependencies and post-encode command mutation
             * remain on the established path, never silently cached. */
            if(channel_mask>=0||gpu_resident_surfaces||gpu_frame_shared||!job->clear_buffers){e=-EINVAL;goto out;}
            e=gpu_service_select_prepared(bytes);if(e)goto out;
            e=mbx_vgp_prepared_dispatch(&gpu_service_prepared,gpu_surface_session,job,bytes,
                gpu_service_commands,MBX_VGP_WIRE_MAX_COMMANDS,gpu_service_replay_cache.snapshot,
                gpu_service_replay_cache.snapshot_capacity,&gpu_service_shader_cache,&handle,&count);
            gpu_template_serial=gpu_service_prepared.generation;
            if(!e){prepared_started=true;gpu_template_generation=handle.generation;}
        }else{
            e=mbx_vgp_wire_encode_replay(job,bytes,gpu_service_commands,MBX_VGP_WIRE_MAX_COMMANDS,&count,&gpu_service_shader_cache,
                                        gpu_wire_replay?&gpu_service_replay_cache:NULL);
            if(!e&&gpu_service_replay_cache.bytes)gpu_template_generation=++gpu_template_serial;
        }
    }
    gpu_wire_replay_hits=gpu_service_replay_cache.hits;
    gpu_wire_replay_misses=gpu_service_replay_cache.misses;
    t[2]=ktime_get_ns();if(e)goto out;
    /* Updates keep the exact resource snapshot owned by this exclusive file.
     * Full uploads use the newly validated wire; neither path trusts an address. */
    texture_job=update?(const void *)gpu_service_replay_cache.snapshot:job;
    e=mbx_wire_resources_parse(texture_job,texture_job->bytes,&resources);if(e)goto out;
    texture_bytes=resources.bytes;texture_data=(const u8 *)texture_job+resources.data_offset;
    resident_job=resources.count&&resources.item[0].version==10;
    merge_job=resources.count&&resources.item[0].version==11;
    window_merge=merge_job&&gpu_window_bound;
    if(gpu_window_bound){
        bool upload_merge=channel_mask>=0&&!mbx_window_channel_upload_validate(texture_job,&resources,channel_mask);
        if(!gpu_window_images||!gpu_memory.windows||update||gpu_resident_surfaces||gpu_prepared_commands||texture_job->version!=10||
           (channel_mask>=0&&!window_merge&&!upload_merge)||
           (window_merge||upload_merge?texture_job->clear_buffers!=0:texture_job->clear_buffers!=5)){e=-EINVAL;goto out;}
        struct mbx_window_state trial=gpu_windows;
        if(mbx_window_begin_sized(&trial,&gpu_window_binding,window_merge?2:0,texture_job->width,texture_job->height)){e=-EINVAL;goto out;}
    }
    for(i=0;i<resources.count;i++)if(resources.item[i].version==13||resources.item[i].version==14){
        struct mbx_window_token token={resources.item[i].reserved,resources.item[i].bytes,resources.item[i].offset};
        if(!gpu_window_images||!gpu_memory.windows||resources.item[i].version!=(gpu_window_native?14U:13U)||mbx_window_lookup(&gpu_windows,token)||
           gpu_windows.width[token.slot]!=mbx_window_width(gpu_window_native?2:1,token.slot)||gpu_windows.height[token.slot]!=mbx_window_height(gpu_window_native?2:1,token.slot)||
           (gpu_window_bound&&token.slot==gpu_window_binding.destination)){e=-EINVAL;goto out;}
    }
    if(merge_job&&!window_merge){
        struct mbx_surface_token a={gpu_merge_binding.rgb.session,gpu_merge_binding.rgb.generation,gpu_merge_binding.rgb.slot};
        struct mbx_surface_token b={gpu_merge_binding.alpha.session,gpu_merge_binding.alpha.generation,gpu_merge_binding.alpha.slot};
        if(!gpu_merge_bound||gpu_memory.frame_images!=3||channel_mask!=8||update||
           mbx_surface_slots_lookup(&gpu_resident_slots,&a,240,320)||
           mbx_surface_slots_lookup(&gpu_resident_slots,&b,240,320)||
           a.slot==b.slot||gpu_merge_binding.destination==a.slot||gpu_merge_binding.destination==b.slot){e=-EINVAL;goto out;}
    }else if(gpu_merge_bound){e=-EINVAL;goto out;}

    if(resident_job){
        struct mbx_surface_token source={gpu_resident_binding.source.session,gpu_resident_binding.source.generation,gpu_resident_binding.source.slot};
        if(!gpu_resident_surfaces||!gpu_resident_bound||update||channel_mask>=0||texture_job->clear_buffers||
           mbx_surface_slots_lookup(&gpu_resident_slots,&source,240,320)||source.slot==gpu_resident_binding.destination){e=-EINVAL;goto out;}
    }else if(gpu_resident_bound){e=-EINVAL;goto out;}
    if(gpu_resident_surfaces&&(update||texture_job->version!=10||texture_job->width*texture_job->height>80000U)){e=-EINVAL;goto out;}

    if(channel_mask>=0){
        unsigned added;
        if(update||mbx_channel_request_validate(texture_job,&resources,channel_mask)||!count||gpu_service_commands[count-1].destination!=MBX_FIFO||
           gpu_service_commands[count-1].value!=0xf0000000U){e=-EINVAL;goto out;}
        /* Keep the accepted full-area GPU mask initialization. Replace only
         * frame-end with the bounded two-source packet and a fresh frame-end. */
        --count;
        e=mbx_channel_select_region(texture_job->width,texture_job->height,channel_mask,gpu_service_commands+count,
                              MBX_VGP_WIRE_MAX_COMMANDS-count,&added);
        if(e)goto out;
        if(merge_job){
            unsigned j,found=0;
            unsigned width=texture_job->width,height=texture_job->height;
            unsigned old[2]={0x0e000000U|((width>>4)<<18)|(0x201000U>>7),
                             0x0e000000U|((width>>4)<<18)|((0x201000U+width*height*4U)>>7)};
            unsigned slots[2]={gpu_merge_binding.rgb.slot,gpu_merge_binding.alpha.slot};
            for(j=count;j<count+added;++j)if(gpu_service_commands[j].destination==MBX_FIFO&&
                found<2&&gpu_service_commands[j].value==old[found]){
                unsigned address=window_merge?mbx_window_address(gpu_window_native?2:1,gpu_window_binding.source[found].slot):MBX_FRAME_VA+slots[found]*gpu_memory.frame_image_pages*4096U;
                gpu_service_commands[j].value=0x0e000000U|((width>>4)<<18)|(address>>7);++found;
            }
            if(found!=2){e=-EINVAL;goto out;}
        }
        count+=added;
        e=mbx_vgp_frame_end(gpu_service_commands+count,MBX_VGP_WIRE_MAX_COMMANDS-count,&added);
        if(e)goto out;
        count+=added;gpu_template_generation=0;
    }

    gpu_wire_width=texture_job->width;gpu_wire_height=texture_job->height;gpu_wire_pixel_bytes=texture_job->version==10?4:2;
    gpu_window_target_va=0;
    if(gpu_window_bound){
        e=mbx_window_begin_sized(&gpu_windows,&gpu_window_binding,window_merge?2:0,texture_job->width,texture_job->height);if(e)goto out;
        window_started=true;gpu_window_target_va=mbx_window_address(gpu_window_native?2:1,gpu_window_binding.destination);
        memset(&gpu_window_result,0,sizeof(gpu_window_result));
    }
    /* Rejected input never reaches this hardware boundary. */
    if(gpu_resident_surfaces&&texture_job->width==240&&texture_job->height==320){
        struct mbx_surface_token source={gpu_resident_binding.source.session,gpu_resident_binding.source.generation,gpu_resident_binding.source.slot};
        if(resident_job)gpu_memory.frame_active=gpu_resident_binding.destination;
        if(merge_job)gpu_memory.frame_active=gpu_merge_binding.destination;
        e=mbx_surface_slots_begin(&gpu_resident_slots,gpu_memory.frame_active,240,320,resident_job?&source:NULL);
        if(e)goto out;
        resident_started=true;gpu_resident_bound=false;gpu_merge_bound=false;gpu_frame_selected=gpu_memory.frame_active;
        gpu_memory.frame_sample_other=resident_job||merge_job;
        memset(&gpu_resident_result,0,sizeof(gpu_resident_result));
    }
    if(gpu_resident_surfaces&&!resident_started){
        /* Other bounded native32 jobs are never residency sources. Retire
         * both tokens without resetting the session generation counter. */
        gpu_resident_slots.slot[0].valid=gpu_resident_slots.slot[1].valid=gpu_resident_slots.slot[2].valid=0;
        memset(&gpu_resident_result,0,sizeof(gpu_resident_result));
        gpu_memory.frame_sample_other=false;
    }
    file->private_data=NULL;
    if(gpu_texture_residency&&mbx_texture_resident_eligible(&resources)){
        if(!gpu_texture_resident_wire){gpu_texture_resident_wire=vmalloc(MBX_VGP_WIRE_MAX_BYTES);if(!gpu_texture_resident_wire){e=-ENOMEM;goto out;}}
        texture_reused=texture_reference&&gpu_texture_resident.valid&&gpu_texture_resident.data==(const u8 *)texture_job+resources.data_offset&&gpu_texture_resident.bytes==resources.bytes;
    }
    /* Untextured jobs do not mutate the linear texture allocation. */
    if(texture_bytes&&!texture_reused)gpu_texture_resident.valid=0;
    if(texture_bytes&&!texture_reused){
        gpu_texture_upload_bytes+=texture_bytes;
        if(mbx_resources_use_linear(&resources)){
            if(texture_bytes>MBX_LINEAR_PAYLOAD){e=-EINVAL;goto out;}
            memcpy((u8*)gpu_memory.linear+4096,texture_data,texture_bytes);
        }else memcpy((u8 *)gpu_memory.parameters+MBX_PARAMETER_BYTES-texture_bytes,texture_data,texture_bytes);
    }
    /* Isolated fixed64x64 native32 background-copy diagnostic. Addresses
     * derive only from the validated reserved driver resource allocation. */
    {
        unsigned *background=gpu_memory.parameters;
        mbx_background32(background,64);
        background[7]=texture_job->width==800?0x44d00000U:0x44800000U;background[10]=0x44800000U;
        if(channel_mask>=0){
            background[1]=0xa8804000U;
            background[2]=0x0e080000U|((MBX_TILE_VA+MBX_TILE_BITMAP_OFFSET)>>7);
            background[21]=background[25]=0;
        }else if(resident_job){
            unsigned address=MBX_FRAME_VA+gpu_resident_slots.source*gpu_memory.frame_image_pages*4096U;
            background[1]=0xa8818000U;
            background[2]=0x0e000000U|((240U>>4)<<18)|(address>>7);
            background[21]=background[25]=0x3f000000U;
        }else if(!texture_job->clear_buffers){
            if(texture_job->version!=10||texture_job->width!=240||texture_job->height!=320||!resources.count||resources.item[0].version!=7||texture_bytes>MBX_LINEAR_PAYLOAD){e=-EINVAL;goto out;}
            background[1]=0xa8818000U;
            background[2]=0x0e000000U|(((resources.item[0].reserved>>16)>>4)<<18)|((MBX_LINEAR_VA+4096)>>7);
            background[21]=background[25]=0x3f000000U;
        }else{
            background[1]=0xa8804000U;
            background[2]=0x0e080000U|((MBX_TILE_VA+MBX_TILE_BITMAP_OFFSET)>>7);
            background[21]=background[25]=0;
        }
    }
    prepared_hardware=prepared_started;
    e=gpu_vgp_prepare_next(NULL);t[3]=ktime_get_ns();
    if(!e){
        gpu_wire_commands=gpu_service_commands;gpu_wire_count=count;
        result=gpu_allocator_initialize(NULL);
        gpu_wire_commands=NULL;gpu_wire_count=0;
        gpu_submitted=result.submitted;gpu_completion_status=result.completion_status;
        gpu_words_written+=result.words_written;e=result.error;
    }
    t[4]=ktime_get_ns();
    if(!e){u64 phase;bool verify=!gpu_verification_mode||!(gpu_verification_jobs++%32)||(texture_bytes&&!texture_reused);
        mbx_dma_frame_for_cpu(&gpu_memory);returned=ktime_get_ns();
        if(verify){e=mbx_dma_verify_bounds(&gpu_memory);gpu_bounds_verified=!e;gpu_last_guard_checked=true;++gpu_verification_checks;}
        else{gpu_bounds_verified=true;gpu_last_guard_checked=false;++gpu_verification_skipped;}
        phase=ktime_get_ns();gpu_bounds_only_ns+=phase-returned;
        if(!e&&texture_bytes&&(!gpu_verification_mode||!texture_reused)){
            if(!mbx_texture_equal(mbx_resources_use_linear(&resources)?(u8*)gpu_memory.linear+4096:(u8 *)gpu_memory.parameters+MBX_PARAMETER_BYTES-texture_bytes,texture_data,texture_bytes))e=-EILSEQ;
            gpu_texture_verify_ns+=ktime_get_ns()-phase;gpu_texture_verify_bytes+=texture_bytes;
        }
    }
    t[5]=ktime_get_ns();
    if(e){gpu_texture_resident.valid=0;gpu_service_failed=1;gpu_error=e;gpu_service_active=0;}
    else{
        /* Completed private pixels have no CPU writers. Reads/guards still
         * invalidate on GPU completion; the next device transition need not
         * clean an allocation that the CPU has only read. */
        if(gpu_readonly_frame_cache&&!gpu_frame_shared&&gpu_memory.frame_images==1)gpu_memory.frame_cpu_reads_only=true;
        if(texture_reused)++gpu_texture_resident_hits;
        else if(gpu_texture_residency&&!update&&mbx_texture_resident_eligible(&resources)){
            void *old=gpu_texture_resident_wire;
            if(gpu_texture_resident.generation==~0U){gpu_texture_resident.valid=0;e=-EOVERFLOW;goto out;}
            gpu_texture_resident_wire=gpu_service_wire;gpu_service_wire=old;
            gpu_texture_resident.data=(u8 *)gpu_texture_resident_wire+resources.data_offset;
            memcpy(gpu_texture_resident.descriptors,(u8 *)texture_job+48,resources.data_offset-48);
            gpu_texture_resident.bytes=resources.bytes;gpu_texture_resident.prefix=resources.data_offset;
            ++gpu_texture_resident.generation;gpu_texture_resident.valid=1;
        }
        if(texture_reference)gpu_texture_ref_bytes+=submitted_bytes;
        if(update){++gpu_template_updates;gpu_template_update_bytes+=bytes;
            gpu_template_copy_ns+=t[1]-t[0];gpu_template_encode_ns+=t[2]-t[1];}
        else{++gpu_template_uploads;gpu_template_upload_bytes+=submitted_bytes;
            gpu_full_copy_ns+=t[1]-t[0];gpu_full_encode_ns+=t[2]-t[1];}
        gpu_return_cpu_ns+=returned-t[4];gpu_bounds_check_ns+=t[5]-returned;++gpu_return_profile_jobs;
        ++gpu_frame_round;++gpu_service_jobs;
        /* Success snapshots are diagnostic copies, not rendering or guards.
         * Keep the existing default; a measured normal-mode comparison may
         * disable these copies. Fault/recovery capture remains unconditional. */
        if(gpu_capture_success){
            u64 capture_started=ktime_get_ns();
            gpu_capture_finish();
            gpu_capture_service_job=gpu_service_jobs;
            gpu_success_capture_ns+=ktime_get_ns()-capture_started;
            pr_info("MBX_DIAGNOSTIC_CAPTURE service_job=%u width=%u height=%u words=%u\n",gpu_service_jobs,gpu_wire_width,gpu_wire_height,count);
        }
        if(gpu_memory.frame_active)++gpu_image1_jobs;else ++gpu_image0_jobs;
        gpu_service_result=NULL;gpu_service_result_bytes=gpu_wire_pixel_bytes*gpu_wire_width*gpu_wire_height;
        if(gpu_wire_pixel_bytes==2)gpu_surface_lease.image=(struct mbx_owned_surface){
            .version=1,.session=gpu_surface_session,.generation=++gpu_surface_generation,
            .slot=gpu_memory.frame_active,.format=MBX_SURFACE_RGB565,.width=gpu_wire_width,
            .height=gpu_wire_height,.stride=gpu_wire_width*2,.bytes=gpu_service_result_bytes,.flags=MBX_SURFACE_COMPLETE};
        file->private_data=window_started?NULL:(void *)1;*off=0;
        for(i=0;i<5;++i)gpu_vgp_total_ns[i]+=t[i+1]-t[i];
        gpu_vgp_total_ns[5]+=t[5]-t[0];
        gpu_vgp_copy_us=div_u64(gpu_vgp_total_ns[0],gpu_service_jobs*1000U);
        gpu_vgp_encode_us=div_u64(gpu_vgp_total_ns[1],gpu_service_jobs*1000U);
        gpu_vgp_prepare_us=div_u64(gpu_vgp_total_ns[2],gpu_service_jobs*1000U);
        gpu_vgp_execute_us=div_u64(gpu_vgp_total_ns[3],gpu_service_jobs*1000U);
        gpu_vgp_verify_us=div_u64(gpu_vgp_total_ns[4],gpu_service_jobs*1000U);
        gpu_vgp_write_us=div_u64(gpu_vgp_total_ns[5],gpu_service_jobs*1000U);
    }
out:
    if(window_started){int done=mbx_window_complete(&gpu_windows,!e,&gpu_window_result);if(!e)e=done;if(e)mbx_window_invalidate(&gpu_windows);}
    gpu_window_target_va=0;gpu_window_bound=false;
    if(prepared_started&&(!e||!prepared_hardware)){
        struct mbx_vgp_prepared_handle handle={gpu_surface_session,gpu_template_generation};
        int finished=mbx_vgp_prepared_complete(&gpu_service_prepared,handle,!e);
        if(!e)e=finished;
    }
    /* On a hardware failure leave prepared ownership pinned. Existing fault
     * retention governs recovery; close must not free retained command storage. */
    if(resident_started){
        int completion=mbx_surface_slots_complete(&gpu_resident_slots,!e,&gpu_resident_result);
        if(completion&&!e)e=completion;
        if(e)mbx_surface_slots_invalidate(&gpu_resident_slots);
    }
    gpu_resident_bound=false;gpu_merge_bound=false;
    mutex_unlock(&gpu_service_mutex);return e?e:submitted_bytes;
}
static ssize_t gpu_service_read(struct file *file,char __user *buf,size_t bytes,loff_t *off)
{
    u64 entered=ktime_get_ns(),locked;ssize_t n;mutex_lock(&gpu_service_mutex);locked=ktime_get_ns();gpu_read_lock_ns+=locked-entered;
    if(!file->private_data||gpu_service_failed||(!gpu_service_result&&gpu_memory.frame_device_owned))n=-EAGAIN;
    else if(gpu_service_result)n=simple_read_from_buffer(buf,bytes,off,gpu_service_result,gpu_service_result_bytes);
    else if(*off<0)n=-EINVAL;
    else if(!bytes||*off>=gpu_service_result_bytes)n=0;
    else{
        size_t done=0,total=min_t(size_t,bytes,gpu_service_result_bytes-*off);
        dma_rmb();
        if(gpu_memory.frame_block)
            done=total-copy_to_user(buf,(u8 *)gpu_memory.frame_block+gpu_memory.frame_active*gpu_memory.frame_image_pages*4096U+*off,total);
        else while(done<total){
            unsigned pos=*off+done,page=gpu_memory.frame_active*gpu_memory.frame_image_pages+pos/4096,in_page=pos%4096;
            size_t chunk=min_t(size_t,total-done,4096-in_page);
            size_t left=copy_to_user(buf+done,(u8 *)gpu_memory.frame_pages[page]+in_page,chunk);
            done+=chunk-left;if(left)break;
        }
        *off+=done;n=done?done:-EFAULT;
    }
    gpu_read_copy_ns+=ktime_get_ns()-locked;++gpu_read_calls;if(n>0)gpu_read_bytes+=n;
    mutex_unlock(&gpu_service_mutex);return n;
}
#include "mbx_image_abi.h"
#include "mbx_service_abi.h"
#include "mbx_dma_sink.h"
static long gpu_service_ioctl(struct file *file,unsigned command,unsigned long argument)
{
    unsigned selected;long e=0;(void)file;
    mutex_lock(&gpu_service_mutex);
    if(!gpu_service_opened||!gpu_service_active||gpu_service_failed){e=-ENODEV;goto done;}
    if(command==MBX_TEXTURE_RESIDENT_INFO){
        unsigned info[4]={1,gpu_surface_session,gpu_texture_resident.valid?gpu_texture_resident.generation:0,gpu_texture_resident.bytes};
        if(!gpu_texture_residency)e=-EOPNOTSUPP;
        else if(copy_to_user((void __user *)argument,info,sizeof(info)))e=-EFAULT;
    }else if(command==MBX_SURFACE_ACQUIRE){
        if(!file->private_data||gpu_memory.frame_device_owned||!gpu_surface_lease.image.generation)e=-ENODATA;
        else if(gpu_surface_lease.held)e=-EBUSY;
        else if(copy_to_user((void __user *)argument,&gpu_surface_lease.image,sizeof(gpu_surface_lease.image)))e=-EFAULT;
        else gpu_surface_lease.held=1;
    }else if(command==MBX_SURFACE_RELEASE){
        struct mbx_owned_surface image;
        if(copy_from_user(&image,(void __user *)argument,sizeof(image)))e=-EFAULT;
        else if(!mbx_lease_matches(&gpu_surface_lease,&image))e=-ESTALE;
        else gpu_surface_lease.held=0;
    }else if(command==MBX_SURFACE_COPY_SINK){
        struct mbx_surface_sink sink;unsigned row;
        if(copy_from_user(&sink,(void __user *)argument,sizeof(sink))){e=-EFAULT;goto done;}
        if(!mbx_lease_sink_valid(&gpu_surface_lease,&sink)||gpu_memory.frame_device_owned||
           sink.address>ULONG_MAX||sink.capacity>ULONG_MAX-sink.address){e=-EINVAL;goto done;}
        ++gpu_sink_calls;dma_rmb();
        for(row=0;row<sink.height&&!e;row++){
            size_t source=(sink.y+(sink.reverse_rows?sink.height-1-row:row))*sink.surface.stride+sink.x*2;
            size_t remaining=sink.width*2;char __user *dest=(char __user *)(unsigned long)sink.address+(size_t)row*sink.stride;
            source+=sink.surface.slot*gpu_memory.frame_image_pages*4096U;
            while(remaining){
                size_t chunk=remaining,left;const u8 *data;
                if(gpu_memory.frame_block)data=(u8 *)gpu_memory.frame_block+source;
                else{chunk=min_t(size_t,remaining,4096-source%4096);data=(u8 *)gpu_memory.frame_pages[source/4096]+source%4096;}
                left=copy_to_user(dest,data,chunk);gpu_sink_bytes+=chunk-left;
                if(left){e=-EFAULT;break;}source+=chunk;dest+=chunk;remaining-=chunk;
            }
        }
    }else if(command==MBX_SURFACE_DMA_SINK){
        struct mbx_surface_dma_sink sink;
        if(copy_from_user(&sink,(void __user *)argument,sizeof(sink)))e=-EFAULT;
        else e=mbx_surface_dma_copy(file,&sink);
    }else if(command==MBX_SERVICE_INFO){
        struct mbx_service_info info={1,gpu_service_active,gpu_service_baseline_verified,0};
        if(copy_to_user((void __user *)argument,&info,sizeof(info)))e=-EFAULT;
     }else if(command==MBX_WINDOW_LAYOUT){
        struct mbx_window_layout layout={.version=gpu_window_native?2:1,.slots=16,.client_mask=MBX_WINDOW_CLIENT_MASK,.native_mask=gpu_window_native?3:0,.width=gpu_window_native?240:0,.height=gpu_window_native?320:0,.stride=gpu_window_native?960:0,.arena_bytes=MBX_WINDOW_BYTES};
        if(!gpu_window_images||!gpu_memory.windows)e=-ENODEV;
        else if(copy_to_user((void __user *)argument,&layout,sizeof(layout)))e=-EFAULT;
     }else if(command==MBX_WINDOW_QUERY){
        if(!gpu_window_images||mbx_window_lookup(&gpu_windows,gpu_window_result))e=-ENODATA;
        else if(copy_to_user((void __user *)argument,&gpu_window_result,sizeof(gpu_window_result)))e=-EFAULT;
    }else if(command==MBX_WINDOW_BIND){
        struct mbx_window_request request;struct mbx_window_state trial=gpu_windows;
        if(!gpu_window_images||!gpu_memory.windows||gpu_window_bound||gpu_surface_lease.held||gpu_memory.frame_device_owned){e=-EBUSY;goto done;}
        if(copy_from_user(&request,(void __user *)argument,sizeof(request))){e=-EFAULT;goto done;}
        unsigned layout=gpu_window_native?2:1;
        unsigned width=mbx_window_width(layout,request.destination),height=mbx_window_height(layout,request.destination);
        if(request.source[0].generation){
            if(request.source[0].slot>=16){e=-EINVAL;goto done;}
            width=gpu_windows.width[request.source[0].slot];height=gpu_windows.height[request.source[0].slot];
        }
        if(mbx_window_begin_sized(&trial,&request,request.source[0].generation?2:0,width,height)){e=-EINVAL;goto done;}
        gpu_window_binding=request;gpu_window_bound=true;
    }else if(command==MBX_RESIDENT_QUERY){
        if(!gpu_resident_surfaces||!gpu_resident_result.generation)e=-ENODATA;
        else if(copy_to_user((void __user *)argument,&gpu_resident_result,sizeof(gpu_resident_result)))e=-EFAULT;
    }else if(command==MBX_RESIDENT_BIND){
        struct mbx_resident_bind bind;struct mbx_surface_token source;
        if(!gpu_resident_surfaces||gpu_memory.frame_device_owned||gpu_resident_bound||gpu_merge_bound){e=-EBUSY;goto done;}
        if(copy_from_user(&bind,(void __user *)argument,sizeof(bind))){e=-EFAULT;goto done;}
        source=(struct mbx_surface_token){bind.source.session,bind.source.generation,bind.source.slot};
        if(bind.version!=1||bind.destination>=gpu_memory.frame_images||bind.destination==source.slot||mbx_surface_slots_lookup(&gpu_resident_slots,&source,240,320)){e=-EINVAL;goto done;}
        gpu_resident_binding=bind;gpu_resident_bound=true;
    }else if(command==MBX_RESIDENT_MERGE){
        struct mbx_resident_merge bind;struct mbx_surface_token a,b;
        if(!gpu_resident_surfaces||gpu_memory.frame_images!=3||gpu_memory.frame_device_owned||gpu_resident_bound||gpu_merge_bound){e=-EBUSY;goto done;}
        if(copy_from_user(&bind,(void __user *)argument,sizeof(bind))){e=-EFAULT;goto done;}
        a=(struct mbx_surface_token){bind.rgb.session,bind.rgb.generation,bind.rgb.slot};
        b=(struct mbx_surface_token){bind.alpha.session,bind.alpha.generation,bind.alpha.slot};
        if(bind.version!=1||bind.destination>=3||a.slot==b.slot||bind.destination==a.slot||bind.destination==b.slot||
           mbx_surface_slots_lookup(&gpu_resident_slots,&a,240,320)||mbx_surface_slots_lookup(&gpu_resident_slots,&b,240,320)){e=-EINVAL;goto done;}
        gpu_merge_binding=bind;gpu_merge_bound=true;
    }else if(command==MBX_IMAGE_LAYOUT){
        struct mbx_image_layout layout={1,gpu_memory.frame_images,gpu_memory.frame_image_pages*4096U,gpu_frame_capacity_bytes};
        if(copy_to_user((void __user *)argument,&layout,sizeof(layout)))e=-EFAULT;
    }else if(command==MBX_TEMPLATE_INFO){
        struct mbx_template_info info={1,gpu_template_generation,gpu_service_replay_cache.bytes,gpu_service_replay_cache.draws};
        if(!gpu_template_generation)e=-ENODATA;
        else if(copy_to_user((void __user *)argument,&info,sizeof(info)))e=-EFAULT;
    }else if(command==MBX_IMAGE_SELECT){
        if(gpu_surface_lease.held){e=-EBUSY;goto done;}
        if(copy_from_user(&selected,(void __user *)argument,sizeof(selected))){e=-EFAULT;goto done;}
        if(selected>=gpu_memory.frame_images){e=-EINVAL;goto done;}
        if(gpu_memory.frame_device_owned){e=-EBUSY;goto done;}
        gpu_memory.frame_active=selected;gpu_frame_selected=selected;
        file->private_data=NULL;
    }else e=-ENOTTY;
 done:mutex_unlock(&gpu_service_mutex);return e;
}
/* Read-only export of the already-owned target, never arbitrary physical
 * memory. Every VMA retains this file and therefore its exclusive owner and
 * module reference. Recovery refuses while any such reference survives. */
static int gpu_service_mmap(struct file *file,struct vm_area_struct *vma)
{
    int e;(void)file;
    mutex_lock(&gpu_service_mutex);
    if(!gpu_frame_shared||!gpu_service_active||gpu_service_failed||(!gpu_memory.frame_block&&(!gpu_memory.frame_streaming||!gpu_memory.frame_page_count)))e=-ENODEV;
    else if(vma->vm_pgoff||!(vma->vm_flags&VM_SHARED)||(vma->vm_flags&VM_WRITE)||
            vma->vm_end-vma->vm_start!=gpu_memory.frame_block_bytes)e=-EINVAL;
    else{
        vma->vm_flags&=~VM_MAYWRITE;
        vma->vm_flags|=VM_DONTEXPAND|VM_DONTDUMP;
        if(gpu_memory.frame_streaming){
            unsigned long address;
            e=0;
            for(address=vma->vm_start;address<vma->vm_end;address+=PAGE_SIZE){
                e=vm_insert_page(vma,address,virt_to_page(gpu_memory.frame_pages[(address-vma->vm_start)/PAGE_SIZE]));
                if(e)break;
            }
        }else e=dma_mmap_attrs(gpu_memory.device,vma,gpu_memory.frame_block,
                              gpu_memory.frame_block_dma,gpu_memory.frame_block_bytes,0);
    }
    mutex_unlock(&gpu_service_mutex);return e;
}
static const struct file_operations gpu_service_ops={.owner=THIS_MODULE,.open=gpu_service_open,
    .release=gpu_service_close,.unlocked_ioctl=gpu_service_ioctl,.mmap=gpu_service_mmap,.write=gpu_service_write,.read=gpu_service_read,.llseek=no_llseek};
static struct miscdevice gpu_service_device={.minor=MISC_DYNAMIC_MINOR,.name="n810-mbx-render",
    .fops=&gpu_service_ops,.mode=0600};
