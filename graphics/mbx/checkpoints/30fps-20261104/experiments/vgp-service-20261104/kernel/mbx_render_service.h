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
static struct mbx_vgp_wire_replay_cache gpu_service_replay_cache;
static bool gpu_wire_replay=true;
static unsigned gpu_wire_replay_hits,gpu_wire_replay_misses;
module_param(gpu_wire_replay,bool,0400);
module_param(gpu_wire_replay_hits,uint,0400);
module_param(gpu_wire_replay_misses,uint,0400);
static unsigned gpu_vgp_copy_us,gpu_vgp_encode_us,gpu_vgp_prepare_us,gpu_vgp_execute_us,gpu_vgp_verify_us,gpu_vgp_write_us;
static u64 gpu_vgp_total_ns[6];
module_param(gpu_vgp_copy_us,uint,0400);
module_param(gpu_vgp_encode_us,uint,0400);
module_param(gpu_vgp_prepare_us,uint,0400);
module_param(gpu_vgp_execute_us,uint,0400);
module_param(gpu_vgp_verify_us,uint,0400);
module_param(gpu_vgp_write_us,uint,0400);
static int gpu_service_open(struct inode *inode,struct file *file)
{
    int e=0;(void)inode;
    mutex_lock(&gpu_service_mutex);
    if(!gpu_service_active||gpu_service_failed)e=-ENODEV;
    else if(gpu_service_opened)e=-EBUSY;
    else{
        memset(&gpu_service_shader_cache,0,sizeof(gpu_service_shader_cache));
        memset(&gpu_service_replay_cache,0,sizeof(gpu_service_replay_cache));
        gpu_wire_replay_hits=gpu_wire_replay_misses=0;
        gpu_service_wire=vmalloc(MBX_VGP_WIRE_MAX_BYTES);
        gpu_service_commands=vmalloc(MBX_VGP_WIRE_MAX_COMMANDS*sizeof(*gpu_service_commands));
        if(!gpu_service_wire||!gpu_service_commands){
            vfree(gpu_service_wire);vfree(gpu_service_commands);
            gpu_service_wire=NULL;gpu_service_commands=NULL;e=-ENOMEM;goto done;
        }
        if(gpu_wire_replay){
            gpu_service_replay_cache.snapshot=vmalloc(65536);
            gpu_service_replay_cache.snapshot_capacity=65536;
            /* Optional cache allocation failure retains the full encoder. */
        }
        gpu_service_opened=true;file->private_data=NULL;
        i_size_write(file_inode(file),gpu_frame_shared?gpu_memory.frame_block_bytes:0);}
done:
    mutex_unlock(&gpu_service_mutex);return e;
}
static int gpu_service_close(struct inode *inode,struct file *file)
{(void)inode;(void)file;mutex_lock(&gpu_service_mutex);gpu_service_opened=false;vfree(gpu_service_wire);vfree(gpu_service_commands);vfree(gpu_service_replay_cache.snapshot);memset(&gpu_service_replay_cache,0,sizeof(gpu_service_replay_cache));gpu_service_wire=NULL;gpu_service_commands=NULL;mutex_unlock(&gpu_service_mutex);return 0;}
/* Typed shader/input transport. Validation completes before hardware is touched. */
static ssize_t gpu_service_write(struct file *file,const char __user *buf,size_t bytes,loff_t *off)
{
    struct mbx_vgp_wire_frame *job;
    struct mbx_gpu_result result;
    unsigned count=0,i;int e=0;u64 t[7];
    if(probe_mode!=3||bytes<sizeof(*job)||bytes>MBX_VGP_WIRE_MAX_BYTES)return -EINVAL;
    t[0]=ktime_get_ns();mutex_lock(&gpu_service_mutex);
    if(!gpu_service_active||gpu_service_failed||!gpu_service_wire||!gpu_service_commands){e=-EIO;goto out;}
    job=gpu_service_wire;
    if(copy_from_user(job,buf,bytes)){e=-EFAULT;goto out;}
    t[1]=ktime_get_ns();
    if(job->width!=400||job->height!=400){e=-EINVAL;goto out;}
    e=mbx_vgp_wire_encode_replay(job,bytes,gpu_service_commands,MBX_VGP_WIRE_MAX_COMMANDS,&count,&gpu_service_shader_cache,
                                gpu_wire_replay?&gpu_service_replay_cache:NULL);
    gpu_wire_replay_hits=gpu_service_replay_cache.hits;
    gpu_wire_replay_misses=gpu_service_replay_cache.misses;
    t[2]=ktime_get_ns();if(e)goto out;
    /* Rejected input never reaches this hardware boundary. */
    file->private_data=NULL;
    e=gpu_vgp_prepare_next(NULL);t[3]=ktime_get_ns();
    if(!e){
        gpu_wire_commands=gpu_service_commands;gpu_wire_count=count;
        result=gpu_allocator_initialize(NULL);
        gpu_wire_commands=NULL;gpu_wire_count=0;
        gpu_submitted=result.submitted;gpu_completion_status=result.completion_status;
        gpu_words_written+=result.words_written;e=result.error;
    }
    t[4]=ktime_get_ns();
    if(!e){mbx_dma_frame_for_cpu(&gpu_memory);e=mbx_dma_verify_bounds(&gpu_memory);gpu_bounds_verified=!e;}
    t[5]=ktime_get_ns();
    if(e){gpu_service_failed=1;gpu_error=e;gpu_service_active=0;}
    else{
        ++gpu_frame_round;++gpu_service_jobs;
        gpu_service_result=NULL;gpu_service_result_bytes=320000;
        file->private_data=(void *)1;*off=0;
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
    mutex_unlock(&gpu_service_mutex);return e?e:bytes;
}
static ssize_t gpu_service_read(struct file *file,char __user *buf,size_t bytes,loff_t *off)
{
    ssize_t n;mutex_lock(&gpu_service_mutex);
    if(!file->private_data||gpu_service_failed||(!gpu_service_result&&gpu_memory.frame_device_owned))n=-EAGAIN;
    else if(gpu_service_result)n=simple_read_from_buffer(buf,bytes,off,gpu_service_result,gpu_service_result_bytes);
    else if(*off<0)n=-EINVAL;
    else if(!bytes||*off>=gpu_service_result_bytes)n=0;
    else{
        size_t done=0,total=min_t(size_t,bytes,gpu_service_result_bytes-*off);
        dma_rmb();
        if(gpu_memory.frame_block)
            done=total-copy_to_user(buf,(u8 *)gpu_memory.frame_block+*off,total);
        else while(done<total){
            unsigned pos=*off+done,page=pos/4096,in_page=pos%4096;
            size_t chunk=min_t(size_t,total-done,4096-in_page);
            size_t left=copy_to_user(buf+done,(u8 *)gpu_memory.frame_pages[page]+in_page,chunk);
            done+=chunk-left;if(left)break;
        }
        *off+=done;n=done?done:-EFAULT;
    }
    mutex_unlock(&gpu_service_mutex);return n;
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
    .release=gpu_service_close,.mmap=gpu_service_mmap,.write=gpu_service_write,.read=gpu_service_read,.llseek=no_llseek};
static struct miscdevice gpu_service_device={.minor=MISC_DYNAMIC_MINOR,.name="n810-mbx-render",
    .fops=&gpu_service_ops,.mode=0600};
