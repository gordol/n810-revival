#include "mbx_context.c"
/* SPDX-License-Identifier: GPL-2.0-only */
/* Original fixed offscreen probe. No recovered code is linked or executed. */
#include <linux/dma-mapping.h>
#include <linux/fs.h>
#include <linux/miscdevice.h>
#include <linux/string.h>
#include "mbx_dma.h"
#include "mbx_mmu.h"
#include "mbx_engine.h"
#include "mbx_packets.h"
#include "mbx_packets.c"
#include "mbx_vertex_program.c"
#define GPU_CAPTURE_BYTES (64U+3U*4096U+2U*32768U+65536U+4096U+36864U)
static unsigned int probe_mode, expected_core_id, expected_revision, expected_product_id, expected_part_number;
static unsigned int fill_pixel=0x12345678U, operation_samples=1000U;
static unsigned int operation_pause_min_us=100U, operation_pause_max_us=200U;
static unsigned int observed_core_id, observed_revision, observed_product_id, observed_part_number;
static unsigned int gpu_attempted, gpu_submitted, gpu_interrupt_mask, gpu_mask_changed;
static unsigned int gpu_words_written, gpu_completion_status, gpu_capture_valid;
static unsigned int gpu_dma_stage, gpu_quiesced, gpu_phase, gpu_ta_completed;
static unsigned int gpu_pipeline_cycles,gpu_pipeline_initialized;
static unsigned int display_base,display_bytes;
/* Map only the requested target capacity; all remaining virtual pages retain
 * the checked guard mapping. Immutable for the complete service lifetime. */
static unsigned int gpu_frame_capacity_bytes=MBX_FRAME_PAGES*4096U;
module_param(gpu_frame_capacity_bytes,uint,0400);
static bool gpu_frame_contiguous,gpu_frame_streaming;
module_param(gpu_frame_streaming,bool,0400);
module_param(gpu_frame_contiguous,bool,0400);
static unsigned int gpu_known_context_finish;
module_param(gpu_known_context_finish,uint,0400);
module_param(display_base,uint,0400);module_param(display_bytes,uint,0400);
module_param(gpu_pipeline_cycles,uint,0400);module_param(gpu_pipeline_initialized,uint,0400);
module_param(gpu_ta_completed,uint,0400);
module_param(gpu_phase,uint,0400);
#define MBX_OWNED_EVENTS (MBX_ALLOC_COMPLETE|MBX_CONTEXT_COMPLETE|MBX_TA_COMPLETE|MBX_RENDER_COMPLETE|0x400U)
static int gpu_error;
module_param(probe_mode,uint,0400);
module_param(expected_core_id,uint,0400);
module_param(expected_revision,uint,0400);
module_param(expected_product_id,uint,0400);
module_param(expected_part_number,uint,0400);
module_param(fill_pixel,uint,0400);
module_param(operation_samples,uint,0400);
module_param(operation_pause_min_us,uint,0400);
module_param(operation_pause_max_us,uint,0400);
module_param(observed_core_id,uint,0400);
module_param(observed_revision,uint,0400);
module_param(observed_product_id,uint,0400);
module_param(observed_part_number,uint,0400);
module_param(gpu_interrupt_mask,uint,0400);
module_param(gpu_mask_changed,uint,0400);
module_param(gpu_attempted,uint,0400);
module_param(gpu_submitted,uint,0400);
module_param(gpu_words_written,uint,0400);
module_param(gpu_completion_status,uint,0400);
module_param(gpu_capture_valid,uint,0400);
module_param(gpu_dma_stage,uint,0400);
module_param(gpu_quiesced,uint,0400);
module_param(gpu_error,int,0400);
static void __iomem *gpu_core,*gpu_port,*gpu_ta_control,*gpu_2d_port;
static struct device *gpu_device;
static struct mbx_dma_memory gpu_memory;
static unsigned char gpu_capture[GPU_CAPTURE_BYTES] __aligned(4);
static bool gpu_capture_registered;
static ssize_t gpu_capture_read(struct file *file,char __user *buf,size_t count,loff_t *offset)
{
    (void)file;
    if(!smp_load_acquire(&gpu_capture_valid))return -EAGAIN;
    return simple_read_from_buffer(buf,count,offset,gpu_capture,sizeof(gpu_capture));
}
static const struct file_operations gpu_capture_ops={
    .owner=THIS_MODULE,.read=gpu_capture_read,.llseek=no_llseek,
};
static struct miscdevice gpu_capture_device={
    .minor=MISC_DYNAMIC_MINOR,.name="n810-mbx-capture",.fops=&gpu_capture_ops,.mode=0400,
};
static int gpu_capture_create(void)
{
    int error=misc_register(&gpu_capture_device);
    gpu_capture_registered=!error;return error;
}
static void gpu_capture_remove(void)
{
    if(gpu_capture_registered){misc_deregister(&gpu_capture_device);gpu_capture_registered=false;}
}
static int gpu_validate_settings(void)
{
    if(probe_mode && (!display_base || !display_bytes || display_bytes>0x04000000U ||
       (u64)display_base+display_bytes>0x100000000ULL))return -EINVAL;
    if(probe_mode>2U || fill_pixel==0x3c3c3c3cU || !operation_samples || operation_samples>1000U ||
       operation_pause_min_us<100U || operation_pause_max_us>200U ||
       operation_pause_max_us<operation_pause_min_us)return -EINVAL;
    if(probe_mode && (expected_core_id==~0U || expected_revision==~0U ||
       (!expected_core_id && expected_product_id!=0xb105f00dU)))return -EINVAL;
    observed_core_id=observed_revision=gpu_attempted=gpu_submitted=gpu_words_written=0;
    gpu_completion_status=gpu_capture_valid=gpu_dma_stage=gpu_quiesced=gpu_phase=gpu_ta_completed=0;gpu_error=0;
    observed_product_id=observed_part_number=gpu_interrupt_mask=gpu_mask_changed=0;
    return 0;
}
static unsigned int gpu_read(void *cookie,unsigned int offset)
{(void)cookie;return readl(gpu_core+offset);}
static void gpu_write(void *cookie,unsigned int offset,unsigned int value)
{(void)cookie;writel(value,gpu_core+offset);}
static void gpu_pause(void *cookie)
{(void)cookie;usleep_range(operation_pause_min_us,operation_pause_max_us);}
static unsigned int gpu_status(void *cookie)
{return gpu_read(cookie,MBX_EVENT_STATUS);}
/* Read only registers already used by the owner. Packet-boundary snapshots
 * distinguish a FIFO that never accepts geometry from later DPM rejection.
 * Do not read the write-only data/control apertures as an acknowledgement. */
static void gpu_trace_boundary(void *cookie,const char *label,unsigned command)
{
    pr_info("n810_mbx_gpu_probe: ta-boundary %s command=%u events=%08x ctl=%08x mmu=%08x context=%08x setup=%08x\n",
        label,command,gpu_status(cookie),gpu_read(cookie,0x108),
        gpu_read(cookie,0x1020),gpu_read(cookie,0x810),gpu_read(cookie,0x85c));
}
static int gpu_mark(void *cookie)
{int error;(void)cookie;error=mbx_dma_submit(&gpu_memory);gpu_dma_stage=gpu_memory.stage;return error;}
static void gpu_wbar(void *cookie){(void)cookie;dma_wmb();wmb();}
static void gpu_rbar(void *cookie){(void)cookie;rmb();dma_rmb();}
static void gpu_capture_finish(void)
{
    __le32 *header=(__le32 *)gpu_capture;
    header[0]=cpu_to_le32(0x3142584dU); /* MXB1 */
    header[1]=cpu_to_le32(sizeof(gpu_capture));header[2]=cpu_to_le32((u32)gpu_memory.ta_dma);
    header[3]=cpu_to_le32(observed_core_id);header[4]=cpu_to_le32(observed_revision);
    header[5]=cpu_to_le32(gpu_completion_status);header[6]=cpu_to_le32(gpu_words_written);
    header[7]=cpu_to_le32(gpu_quiesced);header[8]=cpu_to_le32((u32)gpu_memory.tables_dma);
    header[9]=cpu_to_le32((u32)gpu_memory.target_dma);header[10]=cpu_to_le32((u32)gpu_memory.guard_dma);
    header[11]=cpu_to_le32(observed_product_id);header[12]=cpu_to_le32(observed_part_number);
    header[13]=cpu_to_le32((u32)gpu_memory.parameters_dma);header[14]=cpu_to_le32((u32)gpu_memory.tiles_dma);header[15]=cpu_to_le32(0x56534154);
    memcpy(gpu_capture+64+4096,gpu_memory.target,4096);
    memcpy(gpu_capture+64+8192,gpu_memory.guard,4096);
    memcpy(gpu_capture+64+12288,gpu_memory.tables,32768);
    memcpy(gpu_capture+77888,gpu_memory.parameters,65536);
    memcpy(gpu_capture+143424,gpu_memory.tiles,4096);
    memcpy(gpu_capture+147520,gpu_memory.ta,36864);
    smp_store_release(&gpu_capture_valid,1U);
}
static int gpu_wait_event(void *cookie,struct mbx_gpu_result *result,unsigned mask)
{
    unsigned i,status;
    for(i=0;i<operation_samples;++i){
        status=gpu_status(cookie);++result->samples;result->completion_status=status;
        if(status==~0U || (status&0x2a0U))return -EIO;
        if(status&mask){gpu_rbar(cookie);return 0;}
        gpu_pause(cookie);
    }
    return -ETIMEDOUT;
}
static int gpu_fresh_event(void *cookie,unsigned mask)
{
    unsigned status;
    gpu_write(cookie,MBX_EVENT_CLEAR,mask);gpu_wbar(cookie);
    status=gpu_status(cookie);
    return status==~0U || (status&(0x2a0U|mask)) ? -EIO : 0;
}
struct gpu_context_call { void *cookie; struct mbx_gpu_result *result; };
static int gpu_context_write(void *opaque,unsigned reg,unsigned value)
{
    struct gpu_context_call *call=opaque;
    gpu_write(call->cookie,reg,value);gpu_wbar(call->cookie);
    if(reg!=MBX_EVENT_CLEAR)++call->result->words_written;
    return 0;
}
static int gpu_context_fresh(void *opaque,unsigned mask)
{struct gpu_context_call *call=opaque;return gpu_fresh_event(call->cookie,mask);}
static int gpu_context_wait(void *opaque,unsigned mask)
{struct gpu_context_call *call=opaque;return gpu_wait_event(call->cookie,call->result,mask);}
static void gpu_context_settle(void *opaque)
{(void)opaque;msleep(500);}
/* Isolate native color-input binding from ISP color consumption. The TA's
 * physically captured opaque17-word object has XY pairs at2..7, Z/W at8..13
 * and three packed colors at14..16. Validate the complete known scene before
 * modifying parameter colors; the CPU never writes render-target pixels. */
static int gpu_patch_known_scene_colors(void)
{
    __le32 *parameters=gpu_memory.parameters;
    unsigned objects[2],count=0,at,j;
    dma_rmb();
    for(at=0xb000U/4U;at+17U<=65536U/4U;++at){
        unsigned seen=0;
        if(le32_to_cpu(parameters[at])!=0xe0000000U ||
           le32_to_cpu(parameters[at+1])!=0x14202f80U)continue;
        for(j=0;j<3;++j){
            unsigned x=le32_to_cpu(parameters[at+2+2*j]);
            unsigned y=le32_to_cpu(parameters[at+3+2*j]),bit;
            if(x==0x3f800000U && y==0x3f800000U)bit=1;
            else if(x==0x41f00000U && y==0x3f800000U)bit=2;
            else if(x==0x3f800000U && y==0x41f00000U)bit=4;
            else return -EILSEQ;
            if(seen&bit)return -EILSEQ;
            seen|=bit;
        }
        if(seen!=7 || count==2)return -EILSEQ;
        for(j=8;j<14;++j)
            if(le32_to_cpu(parameters[at+j])!=0x3f800000U)return -EILSEQ;
        objects[count++]=at;
    }
    if(count!=2)return -EILSEQ;
    for(at=0;at<count;++at)
        for(j=14;j<17;++j)parameters[objects[at]+j]=cpu_to_le32(0xff00ff00U);
    dma_wmb();
    pr_info("n810_mbx_gpu_probe: patched validated TA parameter colors objects=%u; no CPU target writes\n",count);
    return 0;
}
static struct mbx_gpu_result gpu_allocator_initialize(void *cookie)
{
    static const unsigned pairs[6][2]={{0x824,0x80000},{0x828,27},{0x82c,31},
        {0x838,1},{0x83c,0x10000},{0x6d8,0x09000000}};
    struct mbx_gpu_result result={0};unsigned i;
    struct gpu_context_call context_call={cookie,&result};
    const struct mbx_context_io context_io={&context_call,gpu_context_write,
        gpu_context_fresh,gpu_context_wait,gpu_context_settle};
    result.error=gpu_fresh_event(cookie,MBX_ALLOC_COMPLETE);if(result.error)return result;
    result.error=gpu_mark(cookie);if(result.error)return result;result.submitted=1;gpu_phase=3;
    for(i=0;i<6;++i){gpu_write(cookie,pairs[i][0],pairs[i][1]);++result.words_written;wmb();}
    result.error=gpu_wait_event(cookie,&result,MBX_ALLOC_COMPLETE);if(result.error)return result;
    gpu_phase=4;
    /* Global TA mask is installed at801bb458..45c before context loads. */
    gpu_write(cookie,0x848,0x7fff);++result.words_written;wmb();
    pr_info("n810_mbx_gpu_probe: allocator-ready events=%08x ctl=%08x free=%08x/%08x\n",gpu_status(cookie),gpu_read(cookie,0x108),gpu_read(cookie,0x828),gpu_read(cookie,0x82c));
    /* Start with the fresh surface context, not the scratch retirement seed.
     * The reference loads its normal context at801bdcf4..801bdd78. The
     * reserved-page scratch seed is loaded at801be068 only AFTER the
     * post-submission availability poll801bdfbc. Keep it separate. */
    result.error=gpu_fresh_event(cookie,MBX_CONTEXT_COMPLETE);if(result.error)return result;
    gpu_write(cookie,0x864,0x94000);++result.words_written;wmb();
    gpu_write(cookie,0x820,0x92000);++result.words_written;wmb();
    gpu_phase=5;gpu_write(cookie,0x814,1);++result.words_written;wmb();
    result.error=gpu_wait_event(cookie,&result,MBX_CONTEXT_COMPLETE);if(result.error)return result;
    gpu_phase=6;
    /*834 is retirement, not startup. Keep the fresh surface context loaded. */
    gpu_phase=7;
    gpu_write(cookie,MBX_EVENT_CLEAR,MBX_ALLOC_COMPLETE);wmb();
    gpu_phase=8;
    pr_info("n810_mbx_gpu_probe: context-ready events=%08x ctl=%08x\n",gpu_status(cookie),gpu_read(cookie,0x108));
    {
        static const unsigned setup[8][2]={{0x6ec,0},
            {0x840,0x90000},{0x844,0x20000},{0x84c,32U<<16},{0x850,32U<<16},
            {0x854,0x3727c5ac},{0x858,0x3727c5ac},{0x85c,0x001404e1}};
        /* Interior, nondegenerate geometry in both windings separates
         * primitive rejection from the full-screen clear-path assumptions. */
        const struct mbx_vertex vertices[6]={
            {0x3f800000,0x3f800000,0x3f800000,0xff00ff00},
            {0x41f00000,0x3f800000,0x3f800000,0xff00ff00},
            {0x3f800000,0x41f00000,0x3f800000,0xff00ff00},
            {0x3f800000,0x3f800000,0x3f800000,0xff00ff00},
            {0x3f800000,0x41f00000,0x3f800000,0xff00ff00},
            {0x41f00000,0x3f800000,0x3f800000,0xff00ff00}};
        struct mbx_command commands[43+MBX_VERTEX_STARTUP_WORDS];
        unsigned status,selection=0,command_count=0;
        result.error=mbx_encode_triangle_batch(32,32,vertices,2,commands,43,&command_count);if(result.error)return result;
        /* Preserve the new-frame preamble, then initialize the original
         * pass-through program before the first geometry packet. */
        memmove(commands+2+MBX_VERTEX_STARTUP_WORDS,commands+2,
            (command_count-2)*sizeof(commands[0]));
        result.error=mbx_encode_vertex_startup(commands+2,MBX_VERTEX_STARTUP_WORDS);
        if(result.error)return result;
        command_count+=MBX_VERTEX_STARTUP_WORDS;
        result.error=gpu_fresh_event(cookie,MBX_TA_COMPLETE);if(result.error)return result;
        /*8049f680 prepares these alongside the TA surface. No680 kick. */
        {
            static const unsigned render[19][2]={
                {0x608,0x20000},{0x610,0x30001},{0x614,0x1e3ce508},
                {0x618,0x1e3ce508},{0x61c,0x20007},{0x63c,0},
                {0x644,0},{0x648,1},{0x64c,0},{0x650,1},
                {0x654,31U<<16},{0x658,31U<<16},{0x65c,0x1000},
                {0x660,16},{0x674,0},{0x6d0,1},{0x6dc,0x3f800001},
                {0x860,0x10001},{0x60c,0x10000}};
            for(i=0;i<19;++i){gpu_write(cookie,render[i][0],render[i][1]);++result.words_written;wmb();}
        }
        for(i=0;i<8;++i){gpu_write(cookie,setup[i][0],setup[i][1]);++result.words_written;wmb();}
        for(i=0;i<operation_samples;++i){
            unsigned used;
            status=gpu_status(cookie);++result.samples;
            if(status==~0U || (status&0x2a0U)){result.error=-EIO;return result;}
            used=(status>>16)&255U;
            if(used>59U){result.error=-EIO;return result;}
            if(59U-used>=42U)break;
            gpu_pause(cookie);
        }
        if(i==operation_samples){result.error=-ETIMEDOUT;return result;}
        /* Nokia GLES 8049f52c..538: after surface setup, start TA at800.
         * Supplying FIFO data without this start never reaches TA completion. */
        gpu_write(cookie,0x800,1);++result.words_written;wmb();
        /*801bcf38 resumes TA after a context reload. Test whether the
         * explicitly seeded first context also needs this resume. */
        gpu_write(cookie,0x804,1);++result.words_written;wmb();
        gpu_phase=9;
        pr_info("n810_mbx_gpu_probe: ta-start events=%08x ctl=%08x\n",gpu_status(cookie),gpu_read(cookie,0x108));
        gpu_trace_boundary(cookie,"start",0);
        for(i=0;i<command_count;++i){
            unsigned sample;
            /* Larger real application streams cannot assume the whole frame
             * fits the59-word FIFO. Account for control writes too, as the
             * reference reserves four bytes for each sideband word. */
            for(sample=0;sample<operation_samples;++sample){
                unsigned queued;
                status=gpu_status(cookie);++result.samples;
                if(status==~0U || (status&0x2a0U)){result.error=-EIO;return result;}
                queued=(status>>16)&255U;
                if(queued<59U)break;
                if(queued>59U){result.error=-EIO;return result;}
                gpu_pause(cookie);
            }
            if(sample==operation_samples){result.error=-ETIMEDOUT;return result;}
            writel(commands[i].value,commands[i].destination==MBX_FIFO ? gpu_port : gpu_ta_control);
            ++result.words_written;wmb();
            if(i==1 || i==2+MBX_VERTEX_STARTUP_WORDS-1 ||
               i==MBX_VERTEX_STARTUP_WORDS+6 || i==MBX_VERTEX_STARTUP_WORDS+8 ||
               i==MBX_VERTEX_STARTUP_WORDS+20 || i==MBX_VERTEX_STARTUP_WORDS+21 ||
               i==command_count-1)
                gpu_trace_boundary(cookie,"stream",i+1);
        }
        /* The availability poll belongs AFTER TA submission. The original
         * render transition801bdfbc..801be164 selects the context at80c,
         * requests its transition at808, then observes fresh event10. */
        gpu_phase=14;
        pr_info("n810_mbx_gpu_probe: ta-stream events=%08x ctl=%08x\n",gpu_status(cookie),gpu_read(cookie,0x108));
        for(i=0;i<operation_samples;++i){
            status=gpu_status(cookie);++result.samples;result.completion_status=status;
            /* Original vertex setup lets the TA finish the frame directly.
             * Do not clear a fresh completion and ask808 to finish it again.
             * Require both the owned event and an empty FIFO. */
            if(status!=~0U && !(status&0x2a0U) &&
               (status&MBX_TA_COMPLETE) && !(status&0x00ff0000U)){
                result.error=0;break;
            }
            result.error=mbx_context_selection(status,&selection);
            if(result.error!=-EAGAIN)break;
            gpu_pause(cookie);
        }
        if(result.error==-EAGAIN && !(status&0xff000000U) &&
           gpu_read(cookie,0x810)==0){
            selection=0;result.error=0;gpu_known_context_finish=1;
            pr_info("n810_mbx_gpu_probe: diagnostic finish of owned context0 events=%08x\n",status);
        }
        gpu_trace_boundary(cookie,"drained",command_count);
        if(result.error)return result;
        gpu_phase=15;
        if(!(status&MBX_TA_COMPLETE)){
            result.error=mbx_context_finish(&context_io,selection);if(result.error)return result;
        }
        gpu_ta_completed=1;gpu_phase=10;
        pr_info("n810_mbx_gpu_probe: triangle-ta-complete events=%08x words=%u\n",result.completion_status,result.words_written);
        /* Save post-geometry DPM state for independent list reconstruction. */
        result.error=gpu_fresh_event(cookie,MBX_CONTEXT_COMPLETE);if(result.error)return result;
        gpu_write(cookie,0x864,0x94000);++result.words_written;wmb();
        gpu_write(cookie,0x820,0x92000);++result.words_written;wmb();
        gpu_write(cookie,0x810,0);++result.words_written;wmb();
        gpu_write(cookie,0x818,1);++result.words_written;wmb();
        result.error=gpu_wait_event(cookie,&result,MBX_CONTEXT_COMPLETE);
        if(result.error)return result;
        /* The TA has generated the actual region headers and object-list
         * pointers in the owned tile allocation. Render that scene with the
         * nineteen shared ISP registers already installed above. No CPU
         * rasterization or CPU write to the render target occurs. */
        result.error=gpu_patch_known_scene_colors();if(result.error)return result;
        result.error=gpu_fresh_event(cookie,MBX_RENDER_COMPLETE);
        if(result.error)return result;
        gpu_phase=16;gpu_rbar(cookie);gpu_wbar(cookie);
        gpu_write(cookie,0x680,1);++result.words_written;gpu_wbar(cookie);
        result.error=gpu_wait_event(cookie,&result,MBX_RENDER_COMPLETE);
    }
    return result;
}
/* Nokia801ba400..801ba498 uses16 internal reset cycles for the
 * detected core1.1.3 path, separately from the SoC PRCM reset. */
static int gpu_pipeline_initialize(void)
{
    unsigned i,mask=readl(gpu_core+0x130);int error=0;
    if(mask==~0U)return -EIO;
    writel(mask&~0xffffU,gpu_core+0x130);wmb();
    for(i=0;i<16;++i){
        writel(0x111,gpu_core+0x80);wmb();msleep(500);
        writel(0,gpu_core+0x80);wmb();msleep(500);
        /* Reference 801ba480 clears events, then immediately decrements and
         * branches to the next cycle. Its other two delay call sites are on
         * mutually exclusive branches, not three delays per cycle. */
        writel(0xffff,gpu_core+0x134);wmb();
        ++gpu_pipeline_cycles;
        pr_info("n810_mbx_gpu_probe: pipeline-cycle=%u events=%08x control=%08x\n",gpu_pipeline_cycles,readl(gpu_core+0x12c),readl(gpu_core+0x108));
        if(readl(gpu_core+0xf00)!=observed_core_id){error=-EIO;break;}
    }
    if(!error){writel(0x80,gpu_core+0x85c);wmb();gpu_pipeline_initialized=1;}
    writel(mask,gpu_core+0x130);wmb();
    if(readl(gpu_core+0x130)!=mask)error=-EIO;
    return error;
}
#include "mbx_render_service.h"
static int gpu_owned_operation(void *cookie,unsigned int *retain)
{
    struct mbx_mmu_io mmu={cookie,gpu_read,gpu_write,gpu_pause,operation_samples};
    struct mbx_gpu_result result;
    unsigned int tables[8],i,control;
    int error;
    gpu_attempted=1;*retain=0;
    observed_product_id=0;
    for(i=0;i<4;++i){
        unsigned int value=readl(gpu_core+0xff0U+4U*i);
        observed_product_id|=value<<(8U*i);
    }
    observed_core_id=readl(gpu_core+0xf00);
    if(observed_product_id==0xb105f00dU){
        observed_part_number=(readl(gpu_core+0xfe0)&255U)|((readl(gpu_core+0xfe4)&15U)<<8);
        observed_revision=readl(gpu_core+0xfe8);
        if(observed_part_number!=0x910U && observed_part_number!=0x930U){gpu_error=-ENODEV;return gpu_error;}
    }else{
        observed_revision=readl(gpu_core+0xf10);
        if((observed_core_id&0xffff0000U)!=0x01010000U &&
           (observed_core_id&0xffff0000U)!=0x01020000U){gpu_error=-ENODEV;return gpu_error;}
    }
    if(observed_core_id==~0U || observed_revision==~0U){gpu_error=-EIO;return gpu_error;}
    if(!probe_mode)return 0;
    if(observed_core_id!=expected_core_id || observed_revision!=expected_revision ||
       observed_product_id!=expected_product_id || observed_part_number!=expected_part_number){gpu_error=-ENODEV;return gpu_error;}
    error=gpu_pipeline_initialize();if(error){gpu_error=error;return error;}
    error=mbx_dma_allocate(gpu_device,&gpu_memory);
    if(error){gpu_error=error;return error;}
    gpu_dma_stage=gpu_memory.stage;
    memcpy(gpu_capture+64,gpu_memory.target,4096);
    memcpy(gpu_capture+64+12288+32768,gpu_memory.tables,32768);
    for(i=0;i<8;++i)tables[i]=(u32)gpu_memory.tables_dma+4096U*i;
    error=mbx_dma_attach(&gpu_memory);gpu_dma_stage=gpu_memory.stage;
    if(error){mbx_dma_release(&gpu_memory);gpu_dma_stage=gpu_memory.stage;gpu_error=error;return error;}
    gpu_interrupt_mask=readl(gpu_core+0x130);
    if(gpu_interrupt_mask==~0U){error=-EIO;goto retained;}
    gpu_mask_changed=1;
    writel(gpu_interrupt_mask&~MBX_OWNED_EVENTS,gpu_core+0x130);
    if(readl(gpu_core+0x130)!=(gpu_interrupt_mask&~MBX_OWNED_EVENTS)){error=-EIO;goto retained;}
    error=mbx_mmu_enable(&mmu,tables);
    if(error)goto retained;
    if(probe_mode==2){
        error=gpu_service_baseline(cookie);
        if(error)goto retained;
        gpu_capture_finish();
        error=misc_register(&gpu_service_device);
        if(error)goto retained;
        gpu_service_registered=true;gpu_service_active=1;
        *retain=1;gpu_error=0;
        pr_info("n810_mbx_gpu_probe: Mesa service ready; exact1024pixel baseline PASS, persistent owned buffers, no CPU target drawing\n");
        return 0;
    }
    result=gpu_allocator_initialize(cookie);
    gpu_submitted=result.submitted;gpu_words_written=result.words_written;
    gpu_completion_status=result.completion_status;
    error=result.error;
    if(error&&result.submitted)goto retained;
    /* A pre-submit rejection can detach tables; no command references them.
     * After submission only observed completion permits this disable attempt. */
    {int disable=mbx_mmu_disable(&mmu);if(disable){error=disable;goto retained;}}
    control=readl(gpu_core+0x1020);
    {int quiet=mbx_dma_quiesce(&gpu_memory,control,gpu_completion_status,MBX_RENDER_COMPLETE);
     if(quiet){error=quiet;goto retained;}}
    gpu_dma_stage=gpu_memory.stage;gpu_quiesced=1;gpu_phase=13;
    if(result.submitted){
        error=mbx_dma_verify_fill8(&gpu_memory,fill_pixel);
        gpu_capture_finish();
    }
    {int release=mbx_dma_release(&gpu_memory);if(release){error=release;goto retained;}}
    gpu_dma_stage=gpu_memory.stage;
    writel(MBX_OWNED_EVENTS,gpu_core+MBX_EVENT_CLEAR);
    if(readl(gpu_core+MBX_EVENT_STATUS)&MBX_OWNED_EVENTS){error=-EIO;goto retained;}
    writel(gpu_interrupt_mask,gpu_core+0x130);
    if(readl(gpu_core+0x130)!=gpu_interrupt_mask){error=-EIO;goto retained;}
    gpu_mask_changed=0;gpu_error=error;return error;
retained:
    gpu_error=error;gpu_dma_stage=gpu_memory.stage;*retain=1;return error;
}
#include "mbx_dma.c"
#include "mbx_mmu.c"
