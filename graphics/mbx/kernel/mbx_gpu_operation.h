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
#include "mbx_vgp_transform.c"
#include "mbx_gears_frame.c"
#include "mbx_vgp_stream.c"
static unsigned int vgp_test_translate,gpu_frame_round;
static bool gpu_bounds_verified;
/* Observed wall times, not hardware cycle counters. FIFO feeding overlaps TA
 * execution; completion polling includes detection latency. Successful frames
 * include startup proof frames, so use counter deltas for benchmark intervals.
 * Read only with submissions stopped: ARMv6 64-bit reads are not atomic.
 * Reuse the existing six timestamps: no extra clock reads or per-frame logs. */
static unsigned long long gpu_profile_frames, gpu_profile_fifo_ns;
static unsigned long long gpu_profile_ta_finish_ns, gpu_profile_raster_observed_ns;
module_param(gpu_profile_frames,ullong,0400);
module_param(gpu_profile_fifo_ns,ullong,0400);
module_param(gpu_profile_ta_finish_ns,ullong,0400);
module_param(gpu_profile_raster_observed_ns,ullong,0400);
#define GPU_PROFILE_RANGE(name) \
static unsigned long long name##_min_ns, name##_max_ns; \
module_param(name##_min_ns,ullong,0400); \
module_param(name##_max_ns,ullong,0400)
GPU_PROFILE_RANGE(gpu_profile_fifo);
GPU_PROFILE_RANGE(gpu_profile_ta_finish);
GPU_PROFILE_RANGE(gpu_profile_raster_observed);
#undef GPU_PROFILE_RANGE
static void gpu_profile_range(unsigned long long *minimum,
                              unsigned long long *maximum, u64 elapsed)
{
    if (!gpu_profile_frames || elapsed < *minimum) *minimum = elapsed;
    if (!gpu_profile_frames || elapsed > *maximum) *maximum = elapsed;
}
/* Diagnostic printk is opt-in; cumulative counters remain enabled. */
static bool gpu_profile_verbose;
module_param(gpu_profile_verbose,bool,0400);
static bool gpu_vgp_log(void){return gpu_profile_verbose &&
    (gpu_frame_round<4||gpu_frame_round%120==0);}
module_param(vgp_test_translate,uint,0400);
#define GPU_CAPTURE_BYTES (64U+3U*4096U+2U*32768U+MBX_PARAMETER_BYTES+MBX_TILE_BYTES+MBX_TA_BYTES+MBX_FRAME_PAGES*4096U)
static unsigned int probe_mode, expected_core_id, expected_revision, expected_product_id, expected_part_number;
static unsigned int fill_pixel=0x12345678U, operation_samples=1000U;
static unsigned int operation_pause_min_us=100U, operation_pause_max_us=200U;
static unsigned gpu_fifo_spin_polls,gpu_control_spin_polls,gpu_control_spins,gpu_raster_pause_us;
module_param(gpu_raster_pause_us,uint,0400);
module_param(gpu_control_spin_polls,uint,0400);
module_param(gpu_control_spins,uint,0400);
static unsigned int observed_core_id, observed_revision, observed_product_id, observed_part_number;
static unsigned int gpu_attempted, gpu_submitted, gpu_interrupt_mask, gpu_mask_changed;
static unsigned int gpu_words_written, gpu_completion_status, gpu_capture_valid;
static unsigned int gpu_dma_stage, gpu_quiesced, gpu_phase, gpu_ta_completed;
static unsigned int gpu_pipeline_cycles,gpu_pipeline_initialized;
static unsigned int gpu_reset_pause_us=500000;
static unsigned int gpu_startup_reset_us,gpu_startup_allocate_us,gpu_startup_proof_us;
module_param(gpu_reset_pause_us,uint,0400);
module_param(gpu_startup_reset_us,uint,0400);
module_param(gpu_startup_allocate_us,uint,0400);
module_param(gpu_startup_proof_us,uint,0400);
static unsigned int display_base,display_bytes;
/* Map only the requested target capacity; all remaining virtual pages retain
 * the checked guard mapping. Immutable for the complete service lifetime. */
static bool gpu_readonly_frame_cache;
module_param(gpu_readonly_frame_cache,bool,0400);
static unsigned long long gpu_frame_device_ns,gpu_frame_cpu_ns,gpu_frame_clean_skipped_bytes;
module_param(gpu_frame_device_ns,ullong,0400);
module_param(gpu_frame_cpu_ns,ullong,0400);
module_param(gpu_frame_clean_skipped_bytes,ullong,0400);
static bool gpu_desktop_target;
module_param(gpu_desktop_target,bool,0400);
#include "mbx_desktop_layout.h"
static unsigned int gpu_frame_capacity_bytes=320000U;
static unsigned gpu_frame_buffers=1;
module_param(gpu_frame_buffers,uint,0400);
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
static unsigned int gpu_capture_service_job;
module_param(gpu_capture_service_job,uint,0400);
module_param(gpu_dma_stage,uint,0400);
module_param(gpu_quiesced,uint,0400);
module_param(gpu_error,int,0400);
static void __iomem *gpu_core,*gpu_port,*gpu_ta_control,*gpu_2d_port;
static struct device *gpu_device;
static struct mbx_dma_memory gpu_memory;
static unsigned char gpu_capture[GPU_CAPTURE_BYTES] __aligned(4);
static bool gpu_capture_registered;
static unsigned gpu_capture_size=GPU_CAPTURE_BYTES-(MBX_FRAME_PAGES-79U)*4096U;
static ssize_t gpu_capture_read(struct file *file,char __user *buf,size_t count,loff_t *offset)
{
    (void)file;
    if(!smp_load_acquire(&gpu_capture_valid))return -EAGAIN;
    return simple_read_from_buffer(buf,count,offset,gpu_capture,gpu_capture_size);
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
    if(probe_mode && (gpu_frame_capacity_bytes!=(gpu_desktop_target?768000U:320000U) || gpu_frame_contiguous))return -EINVAL;
    if(gpu_desktop_target&&(probe_mode!=3||gpu_frame_buffers!=1||!gpu_frame_streaming))return -EINVAL;
    if(gpu_frame_buffers<1||gpu_frame_buffers>3||
       (gpu_frame_buffers>=2&&(probe_mode!=3||!gpu_frame_streaming)))return -EINVAL;
    if((probe_mode>3U || probe_mode==2U) || fill_pixel==0x3c3c3c3cU || !operation_samples || operation_samples>1000U ||
       operation_pause_min_us<100U || operation_pause_max_us>200U ||
       operation_pause_max_us<operation_pause_min_us||gpu_fifo_spin_polls>32||gpu_control_spin_polls>128||gpu_raster_pause_us>1000||
       (gpu_raster_pause_us&&gpu_raster_pause_us<100))return -EINVAL;
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
static bool gpu_profile_sleeps;
module_param(gpu_profile_sleeps,bool,0400);
#define GPU_SLEEP_COUNTERS(label) \
 static unsigned gpu_sleep_##label##_calls,gpu_sleep_##label##_us,gpu_sleep_##label##_overshoot_us,gpu_sleep_##label##_max_us; \
 module_param(gpu_sleep_##label##_calls,uint,0400); \
 module_param(gpu_sleep_##label##_us,uint,0400); \
 module_param(gpu_sleep_##label##_overshoot_us,uint,0400); \
 module_param(gpu_sleep_##label##_max_us,uint,0400)
GPU_SLEEP_COUNTERS(fifo);
GPU_SLEEP_COUNTERS(ta);
GPU_SLEEP_COUNTERS(raster);
GPU_SLEEP_COUNTERS(other);
#undef GPU_SLEEP_COUNTERS
static void gpu_pause_range(void *cookie,unsigned minimum,unsigned maximum)
{
 u64 start;unsigned elapsed,overshoot;(void)cookie;
 if(!gpu_profile_sleeps){usleep_range(minimum,maximum);return;}
 start=ktime_get_ns();usleep_range(minimum,maximum);
 elapsed=div_u64(ktime_get_ns()-start,1000);
 overshoot=elapsed>maximum?elapsed-maximum:0;
 /* Observed sleep duration includes timer and scheduling delay; it is not
  * GPU execution time. Native-width counters are sufficient for bounded runs. */
#define GPU_SLEEP_ADD(label) do{++gpu_sleep_##label##_calls;gpu_sleep_##label##_us+=elapsed; \
 gpu_sleep_##label##_overshoot_us+=overshoot;gpu_sleep_##label##_max_us=max(gpu_sleep_##label##_max_us,elapsed);}while(0)
 if(gpu_phase==9)GPU_SLEEP_ADD(fifo);
 else if(gpu_phase==14||gpu_phase==15)GPU_SLEEP_ADD(ta);
 else if(gpu_phase==16)GPU_SLEEP_ADD(raster);
 else GPU_SLEEP_ADD(other);
#undef GPU_SLEEP_ADD
}
static void gpu_pause(void *cookie)
{gpu_pause_range(cookie,operation_pause_min_us,operation_pause_max_us);}
static unsigned int gpu_status(void *cookie)
{return gpu_read(cookie,MBX_EVENT_STATUS);}
/* Read only registers already used by the owner. Packet-boundary snapshots
 * distinguish a FIFO that never accepts geometry from later DPM rejection.
 * Do not read the write-only data/control apertures as an acknowledgement. */
static void gpu_trace_boundary(void *cookie,const char *label,unsigned command)
{
    if(gpu_vgp_log())pr_info("n810_mbx_gpu_probe: ta-boundary %s command=%u events=%08x ctl=%08x mmu=%08x context=%08x setup=%08x\n",
        label,command,gpu_status(cookie),gpu_read(cookie,0x108),
        gpu_read(cookie,0x1020),gpu_read(cookie,0x810),gpu_read(cookie,0x85c));
}
static void gpu_stream_write(void *cookie,const struct mbx_command *command)
{
 /* Both apertures are default-ioremap registers of the same peripheral.
  * Same-thread FIFO order is preserved by writel_relaxed. The stream's
  * explicit wmb closes each bounded credit burst; readl observes credits
  * and completion. Avoid draining the ARM write buffer for every word. */
 (void)cookie;writel_relaxed(command->value,command->destination==MBX_FIFO?gpu_port:gpu_ta_control);
}
static void gpu_stream_barrier(void *cookie){(void)cookie;wmb();}
static bool gpu_fifo_batch;
static unsigned gpu_fifo_status_reads,gpu_fifo_pauses,gpu_fifo_words,gpu_fifo_spins;
module_param(gpu_fifo_batch,bool,0400);
module_param(gpu_fifo_status_reads,uint,0400);
module_param(gpu_fifo_pauses,uint,0400);
module_param(gpu_fifo_words,uint,0400);
module_param(gpu_fifo_spins,uint,0400);
module_param(gpu_fifo_spin_polls,uint,0400);
static void gpu_stream_relax(void *cookie){(void)cookie;cpu_relax();}
static void gpu_stream_write_batch(void *cookie,const struct mbx_command *commands,unsigned count)
{
 unsigned i;
 /* Same ordered writes and the same credit/barrier boundary; avoid an
  * indirect function call for each of the thousands of command words. */
 for(i=0;i<count;++i)gpu_stream_write(cookie,commands+i);
}
static int gpu_mark(void *cookie)
{
 int error;
 if(gpu_memory.stage==MBX_DMA_SUBMITTED){
  unsigned events=gpu_status(cookie);
  if(!gpu_frame_round||!gpu_ta_completed||events==~0U||(events&0x2a0U)||
     (events&0x114U)!=0x114U)return -EBUSY;
  return 0;
 }
 error=mbx_dma_submit(&gpu_memory);gpu_dma_stage=gpu_memory.stage;return error;
}
static void gpu_wbar(void *cookie){(void)cookie;dma_wmb();wmb();}
static void gpu_rbar(void *cookie){(void)cookie;rmb();dma_rmb();}
static void gpu_capture_finish(void)
{
    unsigned page;
    __le32 *header=(__le32 *)gpu_capture;
    header[0]=cpu_to_le32(0x3142584dU); /* MXB1 */
    gpu_capture_size=GPU_CAPTURE_BYTES-(MBX_FRAME_PAGES-gpu_memory.frame_page_count)*4096U;
    header[1]=cpu_to_le32(gpu_capture_size);header[2]=cpu_to_le32((u32)gpu_memory.ta_dma);
    header[3]=cpu_to_le32(observed_core_id);header[4]=cpu_to_le32(observed_revision);
    header[5]=cpu_to_le32(gpu_completion_status);header[6]=cpu_to_le32(gpu_words_written);
    header[7]=cpu_to_le32(gpu_quiesced);header[8]=cpu_to_le32((u32)gpu_memory.tables_dma);
    header[9]=cpu_to_le32((u32)gpu_memory.target_dma);header[10]=cpu_to_le32((u32)gpu_memory.guard_dma);
    header[11]=cpu_to_le32(observed_product_id);header[12]=cpu_to_le32(observed_part_number);
    header[13]=cpu_to_le32((u32)gpu_memory.parameters_dma);header[14]=cpu_to_le32((u32)gpu_memory.tiles_dma);header[15]=cpu_to_le32(MBX_PARAMETER_BYTES);
    memcpy(gpu_capture+64+4096,gpu_memory.target,4096);
    memcpy(gpu_capture+64+8192,gpu_memory.guard,4096);
    memcpy(gpu_capture+64+12288,gpu_memory.tables,32768);
    memcpy(gpu_capture+77888,gpu_memory.parameters,MBX_PARAMETER_BYTES);
    memcpy(gpu_capture+77888+MBX_PARAMETER_BYTES,gpu_memory.tiles,MBX_TILE_BYTES);
    memcpy(gpu_capture+77888+MBX_PARAMETER_BYTES+MBX_TILE_BYTES,gpu_memory.ta,MBX_TA_BYTES);
    for(page=0;page<gpu_memory.frame_page_count;++page)
        memcpy(gpu_capture+77888+MBX_PARAMETER_BYTES+MBX_TILE_BYTES+MBX_TA_BYTES+page*4096,gpu_memory.frame_pages[page],4096);
    smp_store_release(&gpu_capture_valid,1U);
}
static void gpu_control_pause(void *cookie,unsigned mask,unsigned sample)
{
 if(mask!=MBX_RENDER_COMPLETE&&sample<gpu_control_spin_polls){cpu_relax();++gpu_control_spins;}
 else if(mask==MBX_RENDER_COMPLETE&&gpu_raster_pause_us)gpu_pause_range(cookie,gpu_raster_pause_us,gpu_raster_pause_us+100);
 else gpu_pause(cookie);
}
static int gpu_wait_event(void *cookie,struct mbx_gpu_result *result,unsigned mask)
{
    unsigned i,status;
    for(i=0;i<operation_samples;++i){
        status=gpu_status(cookie);++result->samples;result->completion_status=status;
        if(status==~0U || (status&0x2a0U))return -EIO;
        if(status&mask){gpu_rbar(cookie);return 0;}
        gpu_control_pause(cookie,mask,i);
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
static struct mbx_command *gpu_wire_commands;
static unsigned gpu_wire_count;
/* Per-submission bounded failure evidence; no per-word logging. These register
 * offsets already participate in the validated allocator/context path. Preserve
 * the first failed job through recovery instead of reporting last good capture. */
static unsigned gpu_fault_command_count,gpu_fault_commands_written;
static unsigned gpu_fault_free_start,gpu_fault_free_end,gpu_fault_context;
static unsigned gpu_fault_allocator_start,gpu_fault_allocator_end;
module_param(gpu_fault_command_count,uint,0400);
module_param(gpu_fault_commands_written,uint,0400);
module_param(gpu_fault_free_start,uint,0400);
module_param(gpu_fault_free_end,uint,0400);
module_param(gpu_fault_context,uint,0400);
module_param(gpu_fault_allocator_start,uint,0400);
module_param(gpu_fault_allocator_end,uint,0400);

/* Service-owned packed RGB565 bounds; startup proof remains 400x400. */
static unsigned gpu_wire_width=400,gpu_wire_height=400,gpu_wire_pixel_bytes=2;
static unsigned gpu_window_target_va;
module_param(gpu_window_images,bool,0400);
static struct mbx_gpu_result gpu_allocator_initialize(void *cookie)
{
    static const unsigned pairs[6][2]={{0x824,MBX_TA_VA},{0x828,27},{0x82c,(MBX_PARAMETER_VA+MBX_PARAMETER_BYTES)/4096U-9U},
        {0x838,1},{0x83c,0x10000},{0x6d8,0x09000000}};
    struct mbx_gpu_result result={0};unsigned i;
    struct gpu_context_call context_call={cookie,&result};
    const struct mbx_context_io context_io={&context_call,gpu_context_write,
        gpu_context_fresh,gpu_context_wait,gpu_context_settle};
    result.error=gpu_fresh_event(cookie,MBX_ALLOC_COMPLETE);if(result.error)return result;
    result.error=gpu_mark(cookie);if(result.error)return result;result.submitted=1;gpu_phase=3;gpu_ta_completed=0;
    for(i=0;i<6;++i){gpu_write(cookie,pairs[i][0],pairs[i][1]);++result.words_written;wmb();}
    result.error=gpu_wait_event(cookie,&result,MBX_ALLOC_COMPLETE);if(result.error)return result;
    gpu_fault_allocator_start=gpu_read(cookie,0x828);gpu_fault_allocator_end=gpu_read(cookie,0x82c);
    gpu_phase=4;
    /* Global TA mask is installed at801bb458..45c before context loads. */
    gpu_write(cookie,0x848,0x7fff);++result.words_written;wmb();
    if(gpu_vgp_log())pr_info("n810_mbx_gpu_probe: allocator-ready events=%08x ctl=%08x free=%08x/%08x\n",gpu_status(cookie),gpu_read(cookie,0x108),gpu_read(cookie,0x828),gpu_read(cookie,0x82c));
    /* Start with the fresh surface context, not the scratch retirement seed.
     * The reference loads its normal context at801bdcf4..801bdd78. The
     * reserved-page scratch seed is loaded at801be068 only AFTER the
     * post-submission availability poll801bdfbc. Keep it separate. */
    result.error=gpu_fresh_event(cookie,MBX_CONTEXT_COMPLETE);if(result.error)return result;
    gpu_write(cookie,0x864,MBX_TA_SAVE_B_VA);++result.words_written;wmb();
    gpu_write(cookie,0x820,MBX_TA_SAVE_A_VA);++result.words_written;wmb();
    gpu_phase=5;gpu_write(cookie,0x814,1);++result.words_written;wmb();
    result.error=gpu_wait_event(cookie,&result,MBX_CONTEXT_COMPLETE);if(result.error)return result;
    gpu_phase=6;
    /*834 is retirement, not startup. Keep the fresh surface context loaded. */
    gpu_phase=7;
    gpu_write(cookie,MBX_EVENT_CLEAR,MBX_ALLOC_COMPLETE);wmb();
    gpu_phase=8;
    if(gpu_vgp_log())pr_info("n810_mbx_gpu_probe: context-ready events=%08x ctl=%08x\n",gpu_status(cookie),gpu_read(cookie,0x108));
    {
        static const unsigned setup[8][2]={{0x6ec,0},
            {0x840,MBX_TA_STATE_VA},{0x844,MBX_TILE_VA},{0x84c,400U<<16},{0x850,400U<<16},
            {0x854,0x3727c5ac},{0x858,0x3727c5ac},{0x85c,0x018460e1}};
        static struct mbx_command fixture_commands[24000];
        struct mbx_command *commands=gpu_wire_commands?gpu_wire_commands:fixture_commands;
        unsigned status,selection=0,command_count=0;struct mbx_desktop_layout layout;
        if(mbx_desktop_layout(gpu_wire_width,gpu_wire_height,gpu_desktop_target,&layout)){result.error=-EINVAL;return result;}
        u64 times[6];
        if(vgp_test_translate){result.error=-EINVAL;return result;}
        times[0]=ktime_get_ns();
        if(gpu_wire_commands)command_count=gpu_wire_count;
        else result.error=mbx_encode_gears_frame(commands,ARRAY_SIZE(fixture_commands),&command_count,gpu_frame_round==1);
        times[1]=ktime_get_ns();
        if(result.error)return result;
        result.error=gpu_fresh_event(cookie,MBX_TA_COMPLETE);if(result.error)return result;
        /*8049f680 prepares these alongside the TA surface. No680 kick. */
        {
            static const unsigned render[19][2]={
                {0x608,MBX_TILE_VA},{0x610,0x30001},{0x614,0x1e3ce508},
                {0x618,0x1e3ce508},{0x61c,0x20007},{0x63c,0},
                {0x644,0},{0x648,1},{0x64c,0},{0x650,1},
                {0x654,399U<<16},{0x658,399U<<16},{0x65c,MBX_FRAME_VA},
                {0x660,200},{0x674,0},{0x6d0,1},{0x6dc,0x3f800001},
                {0x860,0x180018},{0x60c,0x10000}};
            for(i=0;i<19;++i){
                unsigned value=render[i][1];
                if(render[i][0]==0x860)value=layout.isp_extent;
                if(render[i][0]==0x654)value=(gpu_wire_width-1)<<16;
                if(render[i][0]==0x658)value=(gpu_wire_height-1)<<16;
                if(render[i][0]==0x660)value=gpu_wire_width*gpu_wire_pixel_bytes/4;
                if(render[i][0]==0x650)value=gpu_wire_pixel_bytes==4?6:1;
                if(render[i][0]==0x65c)value=gpu_window_target_va?gpu_window_target_va:value+gpu_memory.frame_active*gpu_memory.frame_image_pages*4096U;
                gpu_write(cookie,render[i][0],value);++result.words_written;wmb();
            }
        }
        for(i=0;i<8;++i){
            unsigned value=setup[i][1];
            if(setup[i][0]==0x85c)value=layout.ta_extent;
            if(setup[i][0]==0x84c)value=gpu_wire_width<<16;
            if(setup[i][0]==0x850)value=gpu_wire_height<<16;
            gpu_write(cookie,setup[i][0],value);++result.words_written;wmb();
        }
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
        if(gpu_vgp_log())pr_info("n810_mbx_gpu_probe: ta-start events=%08x ctl=%08x\n",gpu_status(cookie),gpu_read(cookie,0x108));
        gpu_trace_boundary(cookie,"start",0);
        {
            const struct mbx_vgp_stream_io io={.cookie=cookie,.status=gpu_status,
                .write=gpu_stream_write,.write_barrier=gpu_stream_barrier,
                .pause=gpu_pause,.write_batch=gpu_fifo_batch?gpu_stream_write_batch:NULL,
                .spin_polls=gpu_fifo_spin_polls,.relax=gpu_stream_relax};
            struct mbx_vgp_stream_result stream={0};
            times[2]=ktime_get_ns();
            result.error=mbx_vgp_stream(&io,commands,command_count,operation_samples,&stream);
            times[3]=ktime_get_ns();
            gpu_fifo_status_reads+=stream.status_reads;gpu_fifo_pauses+=stream.pauses;
            gpu_fifo_words+=stream.written;
            gpu_fifo_spins+=stream.spins;
            result.completion_status=stream.last_status;
            result.words_written+=stream.written;result.samples+=stream.status_reads;
            if(gpu_vgp_log())pr_info("n810_mbx_gpu_probe: vgp-stream commands=%u status_reads=%u pauses=%u last_status=%08x error=%d\n",
                    stream.written,stream.status_reads,stream.pauses,stream.last_status,result.error);
            if(result.error){
                gpu_fault_command_count=command_count;
                gpu_fault_commands_written=stream.written;
                gpu_fault_free_start=gpu_read(cookie,0x828);
                gpu_fault_free_end=gpu_read(cookie,0x82c);
                gpu_fault_context=gpu_read(cookie,0x810);
                pr_err("n810_mbx_gpu_probe: fifo-fault written=%u/%u status=%08x allocator_initial=%08x/%08x allocator_fault=%08x/%08x context=%08x error=%d\n",
                    stream.written,command_count,stream.last_status,
                    gpu_fault_allocator_start,gpu_fault_allocator_end,
                    gpu_fault_free_start,gpu_fault_free_end,gpu_fault_context,result.error);
                return result;
            }
        }
        /* The availability poll belongs AFTER TA submission. The original
         * render transition801bdfbc..801be164 selects the context at80c,
         * requests its transition at808, then observes fresh event10. */
        gpu_phase=14;
        if(gpu_vgp_log())pr_info("n810_mbx_gpu_probe: ta-stream events=%08x ctl=%08x\n",gpu_status(cookie),gpu_read(cookie,0x108));
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
            gpu_control_pause(cookie,MBX_TA_COMPLETE,i);
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
        if(gpu_vgp_log())pr_info("n810_mbx_gpu_probe: triangle-ta-complete events=%08x words=%u\n",result.completion_status,result.words_written);
        /* Save post-geometry DPM state for independent list reconstruction. */
        result.error=gpu_fresh_event(cookie,MBX_CONTEXT_COMPLETE);if(result.error)return result;
        gpu_write(cookie,0x864,MBX_TA_SAVE_B_VA);++result.words_written;wmb();
        gpu_write(cookie,0x820,MBX_TA_SAVE_A_VA);++result.words_written;wmb();
        gpu_write(cookie,0x810,0);++result.words_written;wmb();
        gpu_write(cookie,0x818,1);++result.words_written;wmb();
        result.error=gpu_wait_event(cookie,&result,MBX_CONTEXT_COMPLETE);
        if(result.error)return result;
        /* The TA has generated the actual region headers and object-list
         * pointers in the owned tile allocation. Render that scene with the
         * nineteen shared ISP registers already installed above. No CPU
         * rasterization or CPU write to the render target occurs. */
        /* Observe unmodified TA geometry and GPU-generated colors. */
        result.error=gpu_fresh_event(cookie,MBX_RENDER_COMPLETE);
        if(result.error)return result;
        gpu_phase=16;gpu_rbar(cookie);gpu_wbar(cookie);
        times[4]=ktime_get_ns();
        gpu_write(cookie,0x680,1);++result.words_written;gpu_wbar(cookie);
        result.error=gpu_wait_event(cookie,&result,MBX_RENDER_COMPLETE);
        times[5]=ktime_get_ns();
        if (!result.error) {
            gpu_profile_range(&gpu_profile_fifo_min_ns,
                &gpu_profile_fifo_max_ns,times[3]-times[2]);
            gpu_profile_range(&gpu_profile_ta_finish_min_ns,
                &gpu_profile_ta_finish_max_ns,times[4]-times[3]);
            gpu_profile_range(&gpu_profile_raster_observed_min_ns,
                &gpu_profile_raster_observed_max_ns,times[5]-times[4]);
            gpu_profile_fifo_ns += times[3]-times[2];
            gpu_profile_ta_finish_ns += times[4]-times[3];
            gpu_profile_raster_observed_ns += times[5]-times[4];
            ++gpu_profile_frames;
        }
        if(gpu_vgp_log())pr_info("n810_mbx_gpu_probe: vgp-frame-profile round=%u encode_ns=%llu submit_ns=%llu ta_finish_ns=%llu raster_ns=%llu error=%d\n",
            gpu_frame_round,times[1]-times[0],times[3]-times[2],times[4]-times[3],times[5]-times[4],result.error);
    }
    return result;
}
/* Nokia801ba400..801ba498 uses16 internal reset cycles for the
 * detected core1.1.3 path, separately from the SoC PRCM reset. */
static int gpu_pipeline_initialize(void)
{
    unsigned i,mask=readl(gpu_core+0x130);int error=0;
    u64 started=ktime_get_ns();
    if(gpu_reset_pause_us<1000||gpu_reset_pause_us>500000)return -EINVAL;
    if(mask==~0U)return -EIO;
    writel(mask&~0xffffU,gpu_core+0x130);wmb();
    for(i=0;i<16;++i){
        writel(0x111,gpu_core+0x80);wmb();
        if(gpu_reset_pause_us==500000)msleep(500);
        else usleep_range(gpu_reset_pause_us,gpu_reset_pause_us+min(1000U,gpu_reset_pause_us/10));
        writel(0,gpu_core+0x80);wmb();
        if(gpu_reset_pause_us==500000)msleep(500);
        else usleep_range(gpu_reset_pause_us,gpu_reset_pause_us+min(1000U,gpu_reset_pause_us/10));
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
    gpu_startup_reset_us=div_u64(ktime_get_ns()-started,1000);
    if(readl(gpu_core+0x130)!=mask)error=-EIO;
    return error;
}
static int gpu_vgp_prepare_next(void *cookie);
#include "mbx_render_service.h"
/* Between completed frames only: reset owned control data, never pixels. */
static int gpu_vgp_prepare_next(void *cookie)
{
 unsigned events=gpu_status(cookie),control=gpu_read(cookie,0x108);int error;
 if(events==~0U||control==~0U||(events&0x2a0U)||(events&0x114U)!=0x114U||
    (events&0x00ff0000U)||(control&0x01010101U))return -EBUSY;
 mbx_dma_frame_for_cpu(&gpu_memory);
 /* The preceding completed frame already verified every guard and PTE.
  * Only this exclusive owner writes these controls, and X maps pixels read-only. */
 if(!gpu_bounds_verified)return -EILSEQ;
 gpu_bounds_verified=false;
 memset(gpu_memory.ta,0,MBX_TA_GUARD_OFFSET);
 ((__le32 *)((u8 *)gpu_memory.ta+MBX_TA_RETIRE_OFFSET))[0]=cpu_to_le32(17U|(10U<<13));
 ((__le32 *)((u8 *)gpu_memory.ta+MBX_TA_RETIRE_OFFSET))[1]=cpu_to_le32(26U);
 /* Pages17..26 are initialized once and excluded from the allocator's
  * free range27..143. Frame submissions never use the retirement scratch
  * context, so rewriting these unchanged40KiB each frame is unnecessary. */
 struct mbx_desktop_layout layout;
 error=mbx_desktop_layout(gpu_wire_width,gpu_wire_height,gpu_desktop_target,&layout);if(error)return error;
 error=mbx_tile_headers(gpu_memory.tiles,MBX_TILE_BITMAP_OFFSET/4,layout.tx,layout.ty,4,4);if(error)return error;
 ((__le32 *)gpu_memory.tiles)[layout.words-2]|=cpu_to_le32(0x80000000U);
 dma_wmb();return mbx_dma_frame_for_device(&gpu_memory);
}
static int gpu_vgp_verify_round(unsigned round)
{
 unsigned page;int error;
 mbx_dma_frame_for_cpu(&gpu_memory);error=mbx_dma_verify_bounds(&gpu_memory);
 const unsigned offset=77888+MBX_PARAMETER_BYTES+MBX_TILE_BYTES+MBX_TA_BYTES;
 if(error)return error;
 dma_rmb();
 for(page=0;page<79;++page){
  unsigned bytes=min(4096U,320000U-page*4096U),i;
  const u8 *pixels=gpu_memory.frame_pages[page];
  if(!round)memcpy(gpu_capture+offset+page*4096,pixels,bytes);
  else if(round==1){for(i=0;i<bytes;++i)if(pixels[i])return -EILSEQ;}
  else if(memcmp(gpu_capture+offset+page*4096,pixels,bytes))return -EILSEQ;
 }
 gpu_bounds_verified=true;return 0;
}
static int gpu_owned_operation(void *cookie,unsigned int *retain)
{
    struct mbx_mmu_io mmu={cookie,gpu_read,gpu_write,gpu_pause,operation_samples};
    struct mbx_gpu_result result;
    unsigned int tables[8],i,control;
    u64 startup_phase;
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
    startup_phase=ktime_get_ns();
    error=mbx_dma_allocate(gpu_device,&gpu_memory);
    gpu_startup_allocate_us=div_u64(ktime_get_ns()-startup_phase,1000);
    if(error){gpu_error=error;return error;}
    if(gpu_memory.frame_page_count!=(gpu_frame_buffers>=2?gpu_frame_buffers*80U:DIV_ROUND_UP(gpu_frame_capacity_bytes,4096U))){
        mbx_dma_release(&gpu_memory);gpu_error=-EINVAL;return gpu_error;
    }
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
    startup_phase=ktime_get_ns();
    for(gpu_frame_round=0;gpu_frame_round<3;++gpu_frame_round){
        u64 round_started=ktime_get_ns();
        if(gpu_frame_round){error=gpu_vgp_prepare_next(cookie);if(error)goto retained;}
        result=gpu_allocator_initialize(cookie);
        gpu_submitted=result.submitted;gpu_words_written+=result.words_written;
        gpu_completion_status=result.completion_status;error=result.error;
        if(error&&result.submitted)goto retained;
        if(error)break;
        error=gpu_vgp_verify_round(gpu_frame_round);if(error)goto retained;
        pr_info("n810_mbx_gpu_probe: vgp-reuse round=%u kind=%s verified=1 wall_ns=%llu\n",
            gpu_frame_round,gpu_frame_round==1?"clear":"gears",ktime_get_ns()-round_started);
    }
    gpu_startup_proof_us=div_u64(ktime_get_ns()-startup_phase,1000);
    if(probe_mode==3){
        gpu_service_baseline_verified=1;
        error=misc_register(&gpu_service_device);if(error)goto retained;
        gpu_service_registered=true;gpu_service_active=1;
        *retain=1;gpu_error=0;
        pr_info("n810_mbx_gpu_probe: VGP service ready; persistent clear/reuse verified\n");
        return 0;
    }
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
