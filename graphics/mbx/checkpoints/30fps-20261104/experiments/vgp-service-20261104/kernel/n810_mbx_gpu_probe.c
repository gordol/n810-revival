// SPDX-License-Identifier: GPL-2.0-only
/* Original probe candidate; requires the corrected shared-divider topology.
 * Identity mode precedes any separately selected offscreen fill. */
#include <linux/clk.h>
#include <linux/delay.h>
#include <linux/err.h>
#include <linux/io.h>
#include <linux/ioport.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include "mbx_post_reset.h"
#include <linux/irqflags.h>
#include <linux/preempt.h>
#include "clock_commit.h"
#include "clock_commit.c"
#include "mbx_gpu_operation.h"
#define MBX_BASE 0x50000000UL
#define MBX_SIZE 0x4000UL
#define PRCM_BASE 0x48008300UL
#define PRCM_SIZE 0x100UL
#define FCLK 0x00
#define ICLK 0x10
#define IDLE 0x20
#define SELECT 0x40
#define CONTROL 0x50
#define STATUS 0x58
#define POWER 0xe4
#define PAUSE_BASELINE_MIN_US 100U
#define PAUSE_BASELINE_MAX_US 200U
#define DIVIDER_BASELINE 1U
#define DIVIDER_HYPOTHESIS 2U

enum cleanup_step {
    CLEANUP_CHECK=1, CLEANUP_BEFORE_3D, CLEANUP_AFTER_3D,
    CLEANUP_BEFORE_2D, CLEANUP_AFTER_2D, CLEANUP_BEFORE_RATE,
    CLEANUP_AFTER_RATE, CLEANUP_BEFORE_INTERFACE, CLEANUP_AFTER_INTERFACE,
    CLEANUP_FINAL, CLEANUP_COMPLETE
};

static unsigned int permit_gpu_probe;
static unsigned int permit_global_commit;
static unsigned int commit_samples=32;
static unsigned int commit_pause_us=100;
module_param(permit_global_commit,uint,0400);
module_param(commit_samples,uint,0400);
module_param(commit_pause_us,uint,0400);

static unsigned int handshake_samples = MBX_READY_MAX_SAMPLES;
static unsigned int readiness_limit = MBX_READY_MAX_SAMPLES;
static unsigned int pause_min_us = PAUSE_BASELINE_MIN_US;
static unsigned int pause_max_us = PAUSE_BASELINE_MAX_US;
static unsigned int target_divider = DIVIDER_HYPOTHESIS;
static int handshake_error, readiness_error, restoration_error, final_state_error;
static unsigned int handshake_complete, readiness_attempted, ready, readiness_samples;
static unsigned int reset_asserted_verified, restoration_attempts, resident_fault;
static unsigned int lifetime_pinned, enabled_references, held_clock_handles;
static int clock_operation_error, cleanup_error;
static unsigned int cleanup_phase, cleanup_checks, clock_attempted;
static unsigned int observed_fclk, observed_iclk, observed_select, observed_control, observed_power;
static int divider_operation_error, divider_restoration_error;
static unsigned int shared_handle_held, rate_claimed, sibling_rate_claimed, divider_change_attempted;
static unsigned int divider_restore_attempts, active_divider;
static unsigned long observed_shared_rate;
module_param(permit_gpu_probe,uint,0400);
module_param(handshake_samples,uint,0400);
module_param(readiness_limit,uint,0400);
module_param(pause_min_us,uint,0400);
module_param(pause_max_us,uint,0400);
module_param(target_divider,uint,0400);
module_param(handshake_error,int,0400);
module_param(readiness_error,int,0400);
module_param(restoration_error,int,0400);
module_param(final_state_error,int,0400);
module_param(handshake_complete,uint,0400);
module_param(readiness_attempted,uint,0400);
module_param(ready,uint,0400);
module_param(readiness_samples,uint,0400);
module_param(reset_asserted_verified,uint,0400);
module_param(restoration_attempts,uint,0400);
module_param(resident_fault,uint,0400);
module_param(lifetime_pinned,uint,0400);
module_param(enabled_references,uint,0400);
module_param(held_clock_handles,uint,0400);

module_param(clock_operation_error,int,0400);
module_param(cleanup_error,int,0400);
module_param(cleanup_phase,uint,0400);
module_param(cleanup_checks,uint,0400);
module_param(clock_attempted,uint,0400);
module_param(observed_fclk,uint,0400);
module_param(observed_iclk,uint,0400);
module_param(observed_select,uint,0400);
module_param(observed_control,uint,0400);
module_param(observed_power,uint,0400);
module_param(divider_operation_error,int,0400);
module_param(divider_restoration_error,int,0400);
module_param(shared_handle_held,uint,0400);
module_param(rate_claimed,uint,0400);
module_param(sibling_rate_claimed,uint,0400);
module_param(divider_change_attempted,uint,0400);
module_param(divider_restore_attempts,uint,0400);
module_param(active_divider,uint,0400);
module_param(observed_shared_rate,ulong,0400);

static unsigned int recovery_attempted,recovery_complete,recovery_tables_cleared,recovery_mmu_control;
static int recovery_error;
static int recover_set(const char *,const struct kernel_param *);
static const struct kernel_param_ops recover_ops={.set=recover_set};
module_param_cb(recover,&recover_ops,NULL,0200);
module_param(recovery_attempted,uint,0400);module_param(recovery_complete,uint,0400);
module_param(recovery_tables_cleared,uint,0400);module_param(recovery_mmu_control,uint,0400);
module_param(recovery_error,int,0400);

struct context {
    void __iomem *commit_map;
    unsigned long commit_irq_flags;
    struct platform_device *device;
    void __iomem *reservation, *prcm;
    struct clk *clocks[3];
    struct clk *shared;
    struct mbx_ready_snapshot initial,baseline;
};
static struct context context;
static struct platform_device *ready_device;
static int probe_result = -ENXIO;

static int take_snapshot(void *cookie,struct mbx_ready_snapshot *s)
{
    struct context *c=cookie;
    unsigned int i;
    s->fclk=readl(c->prcm+FCLK);s->iclk=readl(c->prcm+ICLK);
    s->idle=readl(c->prcm+IDLE);s->select=readl(c->prcm+SELECT);
    s->control=readl(c->prcm+CONTROL);s->status=readl(c->prcm+STATUS);
    s->power=readl(c->prcm+POWER);
    for(i=0;i<3;++i)s->rates[i]=c->clocks[i]?clk_get_rate(c->clocks[i]):0;
    if(shared_handle_held){
        observed_shared_rate=clk_get_rate(c->shared);
        if(!observed_shared_rate||observed_shared_rate==~0UL||
           observed_shared_rate!=s->rates[1]||observed_shared_rate!=s->rates[2])return -EIO;
    }
    return (s->fclk==~0U || s->iclk==~0U || s->idle==~0U || s->select==~0U ||
        s->control==~0U || s->status==~0U || s->power==~0U)?-EIO:0;
}
static void log_snapshot(const char *phase,const struct mbx_ready_snapshot *s)
{
    pr_info("n810_mbx_gpu_probe: %s fclk=%08x iclk=%08x idle=%08x select=%08x control=%08x status=%08x power=%08x rates=%lu/%lu/%lu\n",
        phase,s->fclk,s->iclk,s->idle,s->select,s->control,s->status,s->power,
        s->rates[0],s->rates[1],s->rates[2]);
}
static int reset_read(void *cookie,enum mbx_reset_register reg,unsigned int *value)
{
    struct context *c=cookie;
    if(reg!=MBX_RESET_CONTROL && reg!=MBX_RESET_STATUS)return -EINVAL;
    *value=readl(c->prcm+(reg==MBX_RESET_CONTROL?CONTROL:STATUS));return 0;
}
static int reset_write(void *cookie,enum mbx_reset_register reg,unsigned int value)
{
    struct context *c=cookie;
    if(reg==MBX_RESET_STATUS){if(value!=0x10U)return -EINVAL;writel(value,c->prcm+STATUS);}
    else if(reg==MBX_RESET_CONTROL && value!=~0U)writel(value,c->prcm+CONTROL);
    else return -EINVAL;
    return 0;
}
static void reset_pause(void *cookie)
{
    (void)cookie;usleep_range(pause_min_us,pause_max_us);
}
static unsigned long divider_rate(unsigned long parent,unsigned int divider)
{
    return parent/divider+!!(parent%divider);
}
/* Prefix count denotes remaining successful CCF enable references, not
 * inferred hardware gates. It is never increased to repair an observation. */
static int verify_owned_state(struct context *c,unsigned int owned,unsigned int divider)
{
    struct mbx_ready_snapshot sample;
    unsigned int i,expected_fclk,expected_iclk,expected_power;
    int error=take_snapshot(c,&sample);
    ++cleanup_checks;
    observed_fclk=sample.fclk;observed_iclk=sample.iclk;
    observed_select=sample.select;observed_control=sample.control;
    observed_power=sample.power;
    if(error)return error;
    expected_fclk=(c->initial.fclk&~6U)|(owned>=2?2U:0U)|(owned>=3?4U:0U);
    expected_iclk=(c->initial.iclk&~1U)|(owned?1U:0U);
    /* With interface owned the GFX domain must be stably ON. After its
     * release require the original observed power-state bits, no transition.
     * No extra wait/repair is attempted if this strict check does not hold. */
    expected_power=owned?0U:(c->initial.power&3U);
    if(sample.fclk!=expected_fclk||sample.iclk!=expected_iclk||
       sample.control!=1U||sample.select!=((c->initial.select&~7U)|divider)||
       (sample.power&0x100003U)!=expected_power)return -EBUSY;
    for(i=0;i<3;++i)if(!sample.rates[i]||sample.rates[i]==~0UL||
        sample.rates[i]!=c->initial.rates[i])return -EIO;
    if(!observed_shared_rate||observed_shared_rate==~0UL||
       observed_shared_rate!=c->initial.rates[2])return -EIO;
    return 0;
}
static void put_handles(struct context *c)
{
    if(sibling_rate_claimed){clk_rate_exclusive_put(c->clocks[1]);sibling_rate_claimed=0;}
    if(rate_claimed){clk_rate_exclusive_put(c->shared);rate_claimed=0;}
    if(shared_handle_held){clk_put(c->shared);c->shared=NULL;shared_handle_held=0;}
    while(held_clock_handles){unsigned int i=--held_clock_handles;clk_put(c->clocks[i]);c->clocks[i]=NULL;}
}
static int set_committed_rate(struct context *,unsigned int,unsigned int);
static int cleanup_owned_clocks(struct context *c)
{
    unsigned int index;
    int error;
    cleanup_phase=CLEANUP_CHECK;
    error=verify_owned_state(c,enabled_references,active_divider);
    if(error)return error;
    if(active_divider!=DIVIDER_BASELINE){
        /* Keep interface access and the exclusive shared claim until both
         * sibling caches and the complete original divider word are verified. */
        cleanup_phase=CLEANUP_BEFORE_RATE;
        error=verify_owned_state(c,enabled_references,active_divider);
        if(error)return error;
        divider_restore_attempts=1;
        divider_restoration_error=set_committed_rate(c,active_divider,DIVIDER_BASELINE);
        if(divider_restoration_error>0)divider_restoration_error=-EIO;
        cleanup_phase=CLEANUP_AFTER_RATE;
        error=verify_owned_state(c,enabled_references,DIVIDER_BASELINE);
        if(divider_restoration_error)return divider_restoration_error;
        if(error){divider_restoration_error=error;return error;}
        active_divider=DIVIDER_BASELINE;
    }
    while(enabled_references>1U){
        index=enabled_references-1U;
        cleanup_phase=index==2U?CLEANUP_BEFORE_3D:CLEANUP_BEFORE_2D;
        error=verify_owned_state(c,enabled_references,active_divider);
        if(error)return error;
        /* A void disable consumes this successful reference. A later bad
         * readback must not reacquire it or claim it still exists. */
        --enabled_references;
        clk_disable_unprepare(c->clocks[index]);
        ++cleanup_phase;
        error=verify_owned_state(c,enabled_references,active_divider);
        if(error)return error;
    }

    if(enabled_references){
        cleanup_phase=CLEANUP_BEFORE_INTERFACE;
        error=verify_owned_state(c,enabled_references,DIVIDER_BASELINE);
        if(error)return error;
        --enabled_references;
        clk_disable_unprepare(c->clocks[0]);
        cleanup_phase=CLEANUP_AFTER_INTERFACE;
        error=verify_owned_state(c,0,DIVIDER_BASELINE);
        if(error)return error;
    }
    cleanup_phase=CLEANUP_FINAL;
    error=verify_owned_state(c,0,DIVIDER_BASELINE);
    if(error)return error;
    put_handles(c);
    cleanup_phase=CLEANUP_COMPLETE;
    return 0;
}
static void retain_fault(int error)
{
    resident_fault=1;cleanup_error=error;
    pr_info("n810_mbx_gpu_probe: resident cleanup fault=%d phase=%u checks=%u owned_refs=%u handles=%u observed=%08x/%08x/%08x/%08x/%08x divider_error=%d divider_restore=%d active_divider=%u rate_claim=%u shared_handle=%u shared_rate=%lu; no retry or forced unload\n",
        error,cleanup_phase,cleanup_checks,enabled_references,held_clock_handles,
        observed_fclk,observed_iclk,observed_select,observed_control,observed_power,
        divider_operation_error,divider_restoration_error,active_divider,rate_claimed,
        shared_handle_held,observed_shared_rate);
}
static unsigned int commit_read(void *cookie,unsigned int offset)
{struct context *c=cookie;return readl(c->commit_map+offset);}
static void commit_write(void *cookie,unsigned int offset,unsigned int value)
{struct context *c=cookie;writel(value,c->commit_map+offset);}
static void commit_pause(void *cookie,unsigned int us)
{(void)cookie;udelay(us);}
static void commit_lock(void *cookie)
{struct context *c=cookie;preempt_disable();local_irq_save(c->commit_irq_flags);}
static void commit_unlock(void *cookie)
{struct context *c=cookie;local_irq_restore(c->commit_irq_flags);preempt_enable();}
static int set_committed_rate(struct context *c,unsigned int from,unsigned int to)
{
    struct commit_io transaction={c,commit_read,commit_write,commit_pause,commit_lock,commit_unlock};
    struct commit_result r=clock_commit_apply(&transaction,(c->initial.select&~7U)|from,
        (c->initial.select&~7U)|to,commit_samples,commit_pause_us);
    int error;unsigned int i;
    pr_info("n810_mbx_gpu_probe: committed-rate from=%u to=%u raw=%08x samples=%u error=%d guard_error=%d\n",
        from,to,r.target,r.target_samples,r.error,r.restoration_error);
    for(i=0;i<COMMIT_GUARDS;++i)
        pr_info("n810_mbx_gpu_probe: rate-guard index=%u before=%08x after=%08x\n",i,r.guards_before[i],r.guards_after[i]);
    if(r.error||r.restoration_error)return r.restoration_error?r.restoration_error:r.error;
    /* Both composite clock handles are exclusively owned. This kernel's
     * round-rate op rejects this valid divider. Keep its nominal caches
     * unchanged during this bounded diagnostic, then restore raw divider1
     * before releasing either handle. No other GPU consumer may run. */
    error=readl(c->prcm+SELECT)==((c->initial.select&~7U)|to)?0:-EIO;
    return error;
}
static int observe(struct platform_device *device)
{
    static const char *const names[]={"gfx_ick","gfx_2d_fck","gfx_3d_fck"};
    struct context *c=&context;
    struct mbx_ready_io io = {0};
    struct mbx_post_reset_result r;
    unsigned int i;
    int error;
    c->device=device;
    /* Reserve the full core/MMU aperture; operation reads only after readiness. */
    c->reservation=devm_platform_ioremap_resource(device,0);
    if(IS_ERR(c->reservation))return PTR_ERR(c->reservation);
    gpu_port=devm_platform_ioremap_resource(device,1);
    if(IS_ERR(gpu_port))return PTR_ERR(gpu_port);
    gpu_2d_port=devm_platform_ioremap_resource(device,3);
    if(IS_ERR(gpu_2d_port))return PTR_ERR(gpu_2d_port);
    gpu_ta_control=devm_platform_ioremap_resource(device,2);
    if(IS_ERR(gpu_ta_control))return PTR_ERR(gpu_ta_control);
    c->prcm=devm_ioremap(&device->dev,PRCM_BASE,PRCM_SIZE);
    if(!c->prcm)return -ENOMEM;
    c->commit_map=devm_ioremap(&device->dev,0x48008000UL,0x1000);
    if(!c->commit_map)return -ENOMEM;
    error=take_snapshot(c,&c->initial);if(error)return error;
    log_snapshot("initial",&c->initial);
    if((c->initial.fclk&6U)||(c->initial.iclk&1U)||c->initial.control!=1U||
       (c->initial.select&7U)!=DIVIDER_BASELINE||(c->initial.power&0x100000U)||
       (c->initial.power&3U)==2U)return -EBUSY;
    for(i=0;i<3;++i){
        struct clk *clock=clk_get(NULL,names[i]);
        if(IS_ERR(clock)){error=PTR_ERR(clock);goto before_mutation;}
        c->clocks[i]=clock;++held_clock_handles;
    }
    c->shared=clk_get(NULL,"gfx_3d_fck");
    if(IS_ERR(c->shared)){error=PTR_ERR(c->shared);c->shared=NULL;goto before_mutation;}
    shared_handle_held=1;
    /* Read cached rate baseline before changing any clock. Gate/reset/power
     * verification follows while the explicit lifetime is already held. */
    for(i=0;i<3;++i)c->initial.rates[i]=clk_get_rate(c->clocks[i]);
    __module_get(THIS_MODULE);lifetime_pinned=1;
    error=clk_rate_exclusive_get(c->shared);
    if(error)goto before_mutation;
    rate_claimed=1;
    error=clk_rate_exclusive_get(c->clocks[1]);
    if(error)goto before_mutation;
    sibling_rate_claimed=1;
    error=verify_owned_state(c,0,DIVIDER_BASELINE);
    if(error)goto before_mutation;
    /* Nokia startup order: commit divider while all GFX gates are off. */
    divider_change_attempted=1;
    divider_operation_error=set_committed_rate(c,DIVIDER_BASELINE,target_divider);
    if(divider_operation_error){retain_fault(divider_operation_error);return 0;}
    error=verify_owned_state(c,enabled_references,target_divider);
    if(error){retain_fault(error);return 0;}
    active_divider=target_divider;
    pr_info("n810_mbx_gpu_probe: divider-before-gates verified refs=%u divider=%u\n",enabled_references,active_divider);
    for(i=0;i<3;++i){

        clock_attempted=1;
        error=clk_prepare_enable(c->clocks[i]);
        if(error){
            clock_operation_error=error;
            /* No successful reference was acquired for this call. Check
             * hardware against only the earlier successful references. */
            error=verify_owned_state(c,enabled_references,active_divider);
            if(error){retain_fault(error);return 0;}
            goto cleanup;
        }
        ++enabled_references;
        error=verify_owned_state(c,enabled_references,active_divider);
        if(error){clock_operation_error=error;retain_fault(error);return 0;}
    }
    /* Verified coherent divider is now required before reset/readiness. */
    error=take_snapshot(c,&c->baseline);
    if(error){clock_operation_error=error;retain_fault(error);return 0;}
    log_snapshot("baseline-enabled",&c->baseline);
    gpu_core=c->reservation;
    gpu_device=&device->dev;
    io.owned_operation=gpu_owned_operation;
    io.reset.cookie=c;io.reset.read=reset_read;io.reset.write=reset_write;
    io.reset.pause=reset_pause;io.snapshot=take_snapshot;
    r=mbx_reset_then_ready_at_divider(&io,&c->baseline,active_divider,handshake_samples,readiness_limit);
    if(r.readiness_attempted)log_snapshot("last-readiness-raw",&r.last_readiness);
    if(r.final_state_attempted)log_snapshot("restoration-raw",&r.final);
    handshake_error=r.handshake.operation_error;readiness_error=r.readiness_error;
    restoration_error=r.restoration_error;final_state_error=r.final_state_error;
    handshake_complete=r.handshake.completion_observed;readiness_attempted=r.readiness_attempted;
    ready=r.ready;readiness_samples=r.samples;restoration_attempts=r.restoration_attempts;
    reset_asserted_verified=r.reset_asserted_verified;resident_fault=r.must_retain&&!gpu_service_active;
    pr_info("n810_mbx_gpu_probe: handshake=%d completion=%u readiness_attempted=%u readiness=%d ready=%u samples=%u restore=%d final=%d asserted=%u restore_attempts=%u resident=%u limits=%u/%u pause_us=%u-%u target_divider=%u; bounded owned GPU operation\n",
        handshake_error,handshake_complete,readiness_attempted,readiness_error,ready,
        readiness_samples,restoration_error,final_state_error,reset_asserted_verified,
        restoration_attempts,resident_fault,handshake_samples,readiness_limit,pause_min_us,pause_max_us,target_divider);
    if(r.must_retain){
        /* Return success so module text, driver binding and devres survive.
         * Normal unload is pinned. Force unload/raw writers remain outside
         * the guarantee and must be excluded by the reviewed operator scope. */
        return 0;
    }
cleanup:
    cleanup_error=cleanup_owned_clocks(c);
    if(cleanup_error){retain_fault(cleanup_error);return 0;}
    /* Caller init keeps its lifetime pin through driver/devres/device teardown. */
    return clock_operation_error?clock_operation_error:divider_operation_error;
before_mutation:
    /* No clock-enable operation was attempted, so there are no successful
     * enable references to unwind. Init still holds any lifetime pin until
     * actual managed mapping and reservation teardown finishes. */
    put_handles(c);return error;
}
#include "mbx_reset.c"
#include "mbx_post_reset.c"
static int ready_probe(struct platform_device *device)
{
    if(device!=ready_device)return -ENODEV;
    probe_result=observe(device);return probe_result;
}
static struct platform_driver ready_driver={
    .probe=ready_probe,.prevent_deferred_probe=true,
    .driver={.name="n810-mbx-gpu-probe",.probe_type=PROBE_FORCE_SYNCHRONOUS,
             .suppress_bind_attrs=true},
};
/* Explicit attended recovery, serialized by the kernel parameter lock.
 * Retain all buffers until fresh reset has cleared every GPU table pointer.
 * This replaces the separate reset+kexec recovery for future probe faults. */
static int recover_locked(const char *value,const struct kernel_param *unused)
{
    struct context *c=&context;unsigned requested,i;
    struct mbx_ready_snapshot before;
    struct mbx_reset_io rio={c,reset_read,reset_write,reset_pause};
    struct mbx_reset_result reset;int e;
    (void)unused;
    e=kstrtouint(value,0,&requested);if(e || requested!=1)return -EINVAL;
    if((!resident_fault&&!gpu_service_active&&!gpu_service_failed) || !lifetime_pinned || enabled_references!=3 ||
       held_clock_handles!=3 || active_divider!=2 ||
       (gpu_memory.stage!=MBX_DMA_SUBMITTED && gpu_memory.stage!=MBX_DMA_TABLES_ATTACHED) ||
       !ready_device || recovery_attempted)return -EBUSY;
    e=take_snapshot(c,&before);if(e)return e;
    if(before.fclk!=c->baseline.fclk || before.iclk!=c->baseline.iclk ||
       before.select!=c->baseline.select || before.control!=0 ||
       (before.power&0x100003U))return -EBUSY;
    recovery_attempted=1;
    gpu_service_active=0;
    e=reassert_once(&rio);if(e)goto fail;
    usleep_range(10000,11000);
    e=verify_owned_state(c,3,2);if(e)goto fail;
    reset=mbx_reset_release(&rio,handshake_samples);
    if(reset.operation_error || reset.restoration_error){e=reset.operation_error?reset.operation_error:reset.restoration_error;goto fail;}
    if(!reset.completion_observed || readl(gpu_core+0xf00)!=observed_core_id ||
       readl(gpu_core+0xf10)!=observed_revision){e=-EIO;goto fail;}
    recovery_mmu_control=readl(gpu_core+0x1020);
    if(recovery_mmu_control==~0U || (recovery_mmu_control&0x01010101U)){e=-EIO;goto fail;}
    for(i=0;i<8;++i)if(readl(gpu_core+0x1000+i*4)){e=-EIO;goto fail;}
    recovery_tables_cleared=1;
    e=mbx_dma_quiesce_reset(&gpu_memory,reset.completion_observed,recovery_mmu_control,recovery_tables_cleared);if(e)goto fail;
    gpu_quiesced=1;gpu_dma_stage=gpu_memory.stage;
    /* Stable failed-command evidence, explicitly still carrying its old
     * error/phase/write count. This is not a successful-render receipt. */
    gpu_capture_finish();
    writel(gpu_interrupt_mask,gpu_core+0x130);wmb();
    if(readl(gpu_core+0x130)!=gpu_interrupt_mask){e=-EIO;goto fail;}
    gpu_mask_changed=0;
    e=reassert_once(&rio);if(e)goto fail;
    reset_asserted_verified=1;
    usleep_range(10000,11000);
    e=mbx_dma_release(&gpu_memory);gpu_dma_stage=gpu_memory.stage;if(e)goto fail;
    e=cleanup_owned_clocks(c);if(e)goto fail;
    if(gpu_service_registered){misc_deregister(&gpu_service_device);gpu_service_registered=false;}
    platform_driver_unregister(&ready_driver);
    platform_device_unregister(ready_device);ready_device=NULL;
    gpu_core=gpu_port=gpu_ta_control=gpu_2d_port=NULL;gpu_device=NULL;
    resident_fault=0;recovery_complete=1;
    restoration_attempts=1;restoration_error=final_state_error=cleanup_error=0;
    lifetime_pinned=0;module_put(THIS_MODULE);
    pr_info("n810_mbx_gpu_probe: recovery COMPLETE fresh reset, MMU off, tables cleared, owned DMA freed, divider1/clocks restored, binding removed; normal unload supported\n");
    return 0;
fail:
    recovery_error=e;reassert_once(&rio);
    pr_err("n810_mbx_gpu_probe: recovery retained error=%d; no forced unload or reboot\n",e);
    return e;
}
static int recover_set(const char *value,const struct kernel_param *unused)
{
    int e;
    mutex_lock(&gpu_service_mutex);
    if(gpu_service_opened)e=-EBUSY;
    else e=recover_locked(value,unused);
    mutex_unlock(&gpu_service_mutex);
    return e;
}
static int __init ready_init(void)
{
    struct resource res[4]={{.start=MBX_BASE,.end=MBX_BASE+MBX_SIZE-1,.flags=IORESOURCE_MEM},{.start=0x50008000,.end=0x50009fff,.flags=IORESOURCE_MEM},{.start=0x5000c000,.end=0x5000cfff,.flags=IORESOURCE_MEM},{.start=0x5000a000,.end=0x5000bfff,.flags=IORESOURCE_MEM}};
    struct platform_device_info info={.name="n810-mbx-gpu-probe",.id=PLATFORM_DEVID_NONE,.res=res,.num_res=4,.dma_mask=DMA_BIT_MASK(32)};
    int error;
    pr_info("n810_mbx_gpu_probe: reset-completion contract; IDLEST diagnostic\n");
#ifdef CONFIG_SMP
    return -EOPNOTSUPP;
#endif
    if(permit_gpu_probe!=1||permit_global_commit!=1)return -EPERM;
    if(target_divider!=2||!commit_samples||commit_samples>32||!commit_pause_us||commit_pause_us>100)return -EINVAL;
    error=gpu_validate_settings();if(error)return error;
    if(!handshake_samples||handshake_samples>MBX_READY_MAX_SAMPLES||
       (target_divider!=DIVIDER_BASELINE&&target_divider!=DIVIDER_HYPOTHESIS)||
       readiness_limit<MBX_READY_STABLE_SAMPLES||readiness_limit>MBX_READY_MAX_SAMPLES||
       pause_min_us<PAUSE_BASELINE_MIN_US||pause_max_us>PAUSE_BASELINE_MAX_US||
       pause_max_us<pause_min_us)return -EINVAL;
    if(!of_machine_is_compatible("nokia,n810"))return -ENODEV;
    error=gpu_capture_create();if(error)return error;
    /* Supplied result params cannot spoof an observation. */
    handshake_error=readiness_error=restoration_error=final_state_error=0;
    handshake_complete=readiness_attempted=ready=readiness_samples=0;
    reset_asserted_verified=restoration_attempts=resident_fault=0;
    lifetime_pinned=enabled_references=held_clock_handles=0;
    clock_operation_error=cleanup_error=0;cleanup_phase=cleanup_checks=clock_attempted=0;
    observed_fclk=observed_iclk=observed_select=observed_control=observed_power=0;
    divider_operation_error=divider_restoration_error=0;
    shared_handle_held=rate_claimed=sibling_rate_claimed=divider_change_attempted=divider_restore_attempts=0;
    active_divider=DIVIDER_BASELINE;observed_shared_rate=0;
    ready_device=platform_device_register_full(&info);
    if(IS_ERR(ready_device)){gpu_capture_remove();return PTR_ERR(ready_device);}
    error=platform_driver_register(&ready_driver);
    if(!error){
        error=probe_result;
        if(resident_fault||gpu_service_active)return 0; /* keep owned binding and buffers */
        platform_driver_unregister(&ready_driver);
    }
    platform_device_unregister(ready_device);ready_device=NULL;
    /* Pin spans all mapping/reservation and platform-device teardown. */
    if(lifetime_pinned){lifetime_pinned=0;module_put(THIS_MODULE);}
    if(error)gpu_capture_remove();
    if(error && cleanup_phase==CLEANUP_COMPLETE && !gpu_attempted)
        pr_info("n810_mbx_gpu_probe: released-before-gpu error=%d refs=%u handles=%u shared=%u claim=%u pin=%u resident=%u reset_attempted=%u gpu_attempted=%u gpu_submitted=%u gates_match=%u selector_match=%u\n",
            error,enabled_references,held_clock_handles,shared_handle_held,rate_claimed,
            lifetime_pinned,resident_fault,handshake_complete|readiness_attempted,
            gpu_attempted,gpu_submitted,
            observed_fclk==context.initial.fclk && observed_iclk==context.initial.iclk,
            observed_select==context.initial.select);
    return error;
}
static void __exit ready_exit(void)
{
    gpu_capture_remove();
    /* Normal unload cannot enter with a retained lifetime reference. The
     * accepted kernel permits force unload; this code cannot make it safe. */
}
module_init(ready_init);module_exit(ready_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Original shared CCF divider 1/2 comparison with V2 reset, readiness and verified cleanup; bounded owned GPU operation");
