// SPDX-License-Identifier: GPL-2.0-only
/* Original PRCM-only binding candidate. Not cleared for loading or boot. */
#include <linux/clk.h>
#include <linux/delay.h>
#include <linux/err.h>
#include <linux/io.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/slab.h>
#include "mbx_clock_lifecycle.h"
#include "mbx_reset.h"

#define MBX_BASE 0x50000000UL
#define MBX_SIZE 0x1000UL
#define PRCM_BASE 0x48008300UL
#define PRCM_SIZE 0x100UL
#define FCLKEN 0x00
#define ICLKEN 0x10
#define IDLEST 0x20
#define CLKSEL 0x40
#define RSTCTRL 0x50
#define RSTST 0x58
#define PWSTST 0xe4
#define TRIAL_SAMPLES 1000U

struct trial_context {
    struct platform_device *device;
    struct clk *shared, *interface, *graphics_2d, *graphics_3d;
    void __iomem *prcm, *reserved_mapping;
    unsigned int group_open, actual_pin, initial_select, have_select;
    unsigned int snapshot_count, readiness_samples, ready_idle;
};
static struct trial_context context;
static struct mbx_clock_result final_result;
static struct platform_device *trial_device;
static int probe_result = -ENXIO;
static unsigned int permit_clock_reset_trial;
static int operation_result, reset_restoration_result, clock_restoration_result;
static int observation_result, quiescence_result;
static unsigned int resident_fault, lifetime_pinned, held_resources, enabled_refs;
static unsigned int last_phase, readiness_samples, ready_idlest;
module_param(permit_clock_reset_trial, uint, 0400);
module_param(operation_result, int, 0400);
module_param(reset_restoration_result, int, 0400);
module_param(clock_restoration_result, int, 0400);
module_param(observation_result, int, 0400);
module_param(quiescence_result, int, 0400);
module_param(resident_fault, uint, 0400);
module_param(lifetime_pinned, uint, 0400);
module_param(held_resources, uint, 0400);
module_param(enabled_refs, uint, 0400);
module_param(last_phase, uint, 0400);
module_param(readiness_samples, uint, 0400);
module_param(ready_idlest, uint, 0400);

static void trial_release_region(struct trial_context *c)
{
    if (c->group_open) {
        devres_release_group(&c->device->dev, c);
        c->group_open = 0;
    }
    c->prcm = NULL;
    c->reserved_mapping = NULL;
}

static int get_clock(struct clk **destination, const char *name)
{
    struct clk *clock = clk_get(NULL, name);
    if (IS_ERR(clock)) return PTR_ERR(clock);
    *destination = clock;
    return 0;
}

static int acquire_resource(void *cookie, enum mbx_clock_resource resource)
{
    struct trial_context *c = cookie;
    int error;
    switch (resource) {
    case MBX_CLOCK_REGION:
        if (!devres_open_group(&c->device->dev, c, GFP_KERNEL)) return -ENOMEM;
        c->group_open = 1;
        c->reserved_mapping = devm_platform_ioremap_resource(c->device, 0);
        if (IS_ERR(c->reserved_mapping)) {
            error = PTR_ERR(c->reserved_mapping);
            trial_release_region(c);
            return error;
        }
        c->prcm = devm_ioremap(&c->device->dev, PRCM_BASE, PRCM_SIZE);
        if (!c->prcm) { trial_release_region(c); return -ENOMEM; }
        devres_close_group(&c->device->dev, c);
        return 0;
    case MBX_CLOCK_SHARED_HANDLE:
        return get_clock(&c->shared, "gfx_3d_div_fck");
    case MBX_CLOCK_RATE_CLAIM:
        return clk_rate_exclusive_get(c->shared);
    case MBX_CLOCK_INTERFACE_HANDLE:
        return get_clock(&c->interface, "gfx_ick");
    case MBX_CLOCK_2D_HANDLE:
        return get_clock(&c->graphics_2d, "gfx_2d_fck");
    case MBX_CLOCK_3D_HANDLE:
        return get_clock(&c->graphics_3d, "gfx_3d_fck");
    default: return -EINVAL;
    }
}

static void trial_release_resource(void *cookie, enum mbx_clock_resource resource)
{
    struct trial_context *c = cookie;
    switch (resource) {
    case MBX_CLOCK_REGION: trial_release_region(c); break;
    case MBX_CLOCK_SHARED_HANDLE: clk_put(c->shared); c->shared = NULL; break;
    case MBX_CLOCK_RATE_CLAIM: clk_rate_exclusive_put(c->shared); break;
    case MBX_CLOCK_INTERFACE_HANDLE: clk_put(c->interface); c->interface = NULL; break;
    case MBX_CLOCK_2D_HANDLE: clk_put(c->graphics_2d); c->graphics_2d = NULL; break;
    case MBX_CLOCK_3D_HANDLE: clk_put(c->graphics_3d); c->graphics_3d = NULL; break;
    default: break;
    }
}

static int pin_lifetime(void *cookie)
{
    struct trial_context *c = cookie;
    if (c->actual_pin) return -EINVAL;
    /* We are executing our own synchronous init under the loader's existing
     * reference. __module_get takes a direct additional reference; it has no
     * fallible transition after acquisition. Do not assume try_module_get's
     * COMING behavior. delete_module rejects non-LIVE modules during init. */
    __module_get(THIS_MODULE);
    c->actual_pin = 1;
    return 0;
}

static void unpin_lifetime(void *cookie)
{
    struct trial_context *c = cookie;
    if (WARN_ON(!c->actual_pin)) return;
    c->actual_pin = 0;
    module_put(THIS_MODULE);
}

static int sample_state(void *cookie, struct mbx_clock_observation *s)
{
    struct trial_context *c = cookie;
    unsigned int fclk = readl(c->prcm + FCLKEN);
    unsigned int iclk = readl(c->prcm + ICLKEN);
    unsigned int idle = readl(c->prcm + IDLEST);
    unsigned int select = readl(c->prcm + CLKSEL);
    unsigned int reset_control = readl(c->prcm + RSTCTRL);
    unsigned int reset_status = readl(c->prcm + RSTST);
    unsigned int power = readl(c->prcm + PWSTST);
    unsigned long shared_rate;
    ++c->snapshot_count;
    if (fclk == ~0U || iclk == ~0U || idle == ~0U || select == ~0U ||
        reset_control == ~0U || reset_status == ~0U || power == ~0U) return -EIO;
    if (!c->have_select) { c->initial_select = select; c->have_select = 1; }
    if ((select & ~7U) != (c->initial_select & ~7U)) return -EIO;
    s->reset_control = reset_control;
    s->gates = (iclk & 1U) | (fclk & 6U);
    s->divider = select & 7U;
    s->power_on = (power & 0x100003U) == 0;
    s->parent_rate = clk_get_rate(c->interface);
    s->rate_2d = clk_get_rate(c->graphics_2d);
    s->rate_3d = clk_get_rate(c->graphics_3d);
    shared_rate = clk_get_rate(c->shared);
    pr_info("n810_mbx_clock_trial: sample=%u fclk=%08x iclk=%08x idle=%08x select=%08x control=%08x status=%08x power=%08x rates=%lu/%lu/%lu/%lu\n",
        c->snapshot_count, fclk, iclk, idle, select, reset_control, reset_status,
        power, s->parent_rate, shared_rate, s->rate_2d, s->rate_3d);
    return shared_rate == s->rate_2d && shared_rate == s->rate_3d ? 0 : -EIO;
}

static int set_divider(void *cookie, unsigned int divisor)
{
    struct trial_context *c = cookie;
    unsigned long parent, requested;
    if (divisor != 1 && divisor != 2) return -EINVAL;
    parent = clk_get_rate(c->interface);
    if (!parent || parent == ~0UL) return -EIO;
    requested = parent / divisor + !!(parent % divisor);
    return clk_set_rate(c->shared, requested);
}

static struct clk *clock_for(struct trial_context *c, unsigned int bit)
{
    return bit == 1 ? c->interface : bit == 2 ? c->graphics_2d : c->graphics_3d;
}
static int enable_clock(void *cookie, unsigned int bit)
{
    if (bit != 1 && bit != 2 && bit != 4) return -EINVAL;
    return clk_prepare_enable(clock_for(cookie, bit));
}
static void disable_clock(void *cookie, unsigned int bit)
{
    clk_disable_unprepare(clock_for(cookie, bit));
}

static int reset_read(void *cookie, enum mbx_reset_register reg, unsigned int *value)
{
    struct trial_context *c = cookie;
    if (reg != MBX_RESET_CONTROL && reg != MBX_RESET_STATUS) return -EINVAL;
    *value = readl(c->prcm + (reg == MBX_RESET_CONTROL ? RSTCTRL : RSTST));
    return 0;
}
static int reset_write(void *cookie, enum mbx_reset_register reg, unsigned int value)
{
    struct trial_context *c = cookie;
    if (reg == MBX_RESET_STATUS && value == 0x10U) writel(value, c->prcm + RSTST);
    else if (reg == MBX_RESET_CONTROL && value != ~0U) writel(value, c->prcm + RSTCTRL);
    else return -EINVAL;
    return 0;
}
static void reset_pause(void *cookie) { (void)cookie; usleep_range(100, 200); }
static void run_reset(void *cookie, struct mbx_clock_reset_report *report)
{
    const struct mbx_reset_io io = {cookie, reset_read, reset_write, reset_pause};
    struct mbx_reset_result r = mbx_reset_release(&io, TRIAL_SAMPLES);
    report->operation_error = r.operation_error;
    report->restoration_error = r.restoration_error;
    report->wrote_register = r.wrote_register;
    report->completion_observed = r.completion_observed;
    report->reset_restored = r.reset_restored;
}
static int restore_reset(void *cookie)
{
    unsigned int before_reset, after;
    int error = reset_read(cookie, MBX_RESET_CONTROL, &before_reset);
    if (error || before_reset == ~0U) return error ? error : -EIO;
    error = reset_write(cookie, MBX_RESET_CONTROL, before_reset | 1U);
    if (error) return error;
    error = reset_read(cookie, MBX_RESET_CONTROL, &after);
    return error ? error : after == (before_reset | 1U) ? 0 : -EIO;
}
static int wait_ready(void *cookie)
{
    struct trial_context *c = cookie;
    unsigned int i, consecutive = 0;
    for (i = 0; i < TRIAL_SAMPLES; ++i) {
        unsigned int fclk = readl(c->prcm + FCLKEN);
        unsigned int iclk = readl(c->prcm + ICLKEN);
        unsigned int idle = readl(c->prcm + IDLEST);
        unsigned int power = readl(c->prcm + PWSTST);
        unsigned int control = readl(c->prcm + RSTCTRL);
        unsigned int select = readl(c->prcm + CLKSEL);
        c->readiness_samples = i + 1; c->ready_idle = idle;
        if (fclk == ~0U || iclk == ~0U || idle == ~0U || power == ~0U ||
            control == ~0U || select == ~0U) return -EIO;
        if ((fclk & 6U) == 6U && (iclk & 1U) && (idle & 1U) &&
            !(power & 0x100003U) && control == 0 &&
            select == ((c->initial_select & ~7U) | 2U)) {
            if (++consecutive == 2) return 0;
        } else consecutive = 0;
        if (i + 1 < TRIAL_SAMPLES) usleep_range(100, 200);
    }
    return -ETIMEDOUT;
}

#include "mbx_reset.c"
#include "mbx_clock_lifecycle.c"

static int trial_probe(struct platform_device *device)
{
    const struct mbx_clock_io io = {&context, acquire_resource, trial_release_resource,
        pin_lifetime, unpin_lifetime, sample_state, set_divider, enable_clock,
        disable_clock, run_reset, wait_ready, restore_reset};
    if (device != trial_device) return -ENODEV;
    context.device = device;
    final_result = mbx_clock_transaction(&io);
    operation_result = final_result.operation_error;
    reset_restoration_result = final_result.reset_restoration_error;
    clock_restoration_result = final_result.clock_restoration_error;
    observation_result = final_result.observation_error;
    quiescence_result = final_result.quiescence_error;
    resident_fault = final_result.state == MBX_CLOCK_FAULT_PINNED;
    lifetime_pinned = context.actual_pin;
    held_resources = final_result.held_resources;
    enabled_refs = final_result.enabled_refs;
    last_phase = final_result.last_phase;
    readiness_samples = context.readiness_samples; ready_idlest = context.ready_idle;
    probe_result = final_result.kernel_init_error;
    pr_info("n810_mbx_clock_trial: operation=%d reset_restore=%d clock_restore=%d observation=%d quiescence=%d resident_fault=%u pinned=%u held=%x enabled=%x phase=%u readiness_samples=%u idle=%08x; no MBX access, commands or DMA\n",
        operation_result, reset_restoration_result, clock_restoration_result,
        observation_result, quiescence_result, resident_fault, lifetime_pinned,
        held_resources, enabled_refs, last_phase, readiness_samples, ready_idlest);
    return probe_result;
}
static struct platform_driver trial_driver = {
    .probe = trial_probe, .prevent_deferred_probe = true,
    .driver = {.name = "n810-mbx-clock-trial", .probe_type = PROBE_FORCE_SYNCHRONOUS,
               .suppress_bind_attrs = true},
};
static int __init clock_trial_init(void)
{
    struct resource resource = {.start = MBX_BASE, .end = MBX_BASE + MBX_SIZE - 1,
                                .flags = IORESOURCE_MEM};
    struct platform_device_info info = {.name = "n810-mbx-clock-trial",
        .id = PLATFORM_DEVID_NONE, .res = &resource, .num_res = 1};
    int error;
    if (permit_clock_reset_trial != 1) return -EPERM;
    if (!of_machine_is_compatible("nokia,n810")) return -ENODEV;
    trial_device = platform_device_register_full(&info);
    if (IS_ERR(trial_device)) return PTR_ERR(trial_device);
    error = platform_driver_register(&trial_driver);
    if (!error) {
        error = probe_result;
        /* Fault success keeps the bound device, devres and direct module pin. */
        if (final_result.state == MBX_CLOCK_FAULT_PINNED) return 0;
        platform_driver_unregister(&trial_driver);
    }
    platform_device_unregister(trial_device); trial_device = NULL;
    return error;
}
static void __exit clock_trial_exit(void)
{
    /* Normal successful completion already released/unregistered everything.
     * An unresolved binding is pinned and cannot reach ordinary module exit. */
    WARN_ON(context.actual_pin || trial_device);
}
module_init(clock_trial_init);
module_exit(clock_trial_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Original bounded shared-GFX divider/reset/readiness trial; no core access");
