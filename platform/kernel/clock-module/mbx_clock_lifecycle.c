/* SPDX-License-Identifier: GPL-2.0-only */
#include "mbx_clock_lifecycle.h"
#ifdef __KERNEL__
#include <linux/errno.h>
#else
#include <errno.h>
#endif

static int error_code(int error) { return error > 0 ? -EIO : error; }

static int observe(const struct mbx_clock_io *io, struct mbx_clock_result *r)
{
    struct mbx_clock_observation *s = &r->last_observation;
    int error;
    r->last_observation_valid = 0;
    error = error_code(io->sample(io->cookie, s));
    if (error) { r->observation_error = error; return error; }
    if (s->gates > 7 || s->divider < 1 || s->divider > 4 || s->power_on > 1 ||
        !s->parent_rate || s->parent_rate == ~0UL ||
        !s->rate_2d || s->rate_2d == ~0UL || !s->rate_3d || s->rate_3d == ~0UL) {
        r->observation_error = -EIO;
        return -EIO;
    }
    r->last_observation_valid = 1;
    return 0;
}

static int expected(const struct mbx_clock_result *r, unsigned int gates,
                    unsigned int reset, unsigned int divider, int rates)
{
    const struct mbx_clock_observation *s = &r->last_observation;
    unsigned long rate = r->original_parent_rate / divider +
                         !!(r->original_parent_rate % divider);
    return r->last_observation_valid && s->gates == gates &&
           s->reset_control == reset && s->parent_rate == r->original_parent_rate &&
           (!(gates & 1U) || s->power_on) &&
           (!rates || (s->divider == divider && s->rate_2d == rate && s->rate_3d == rate));
}

static void release_all(const struct mbx_clock_io *io, struct mbx_clock_result *r)
{
    unsigned int i;
    r->last_phase = MBX_CLOCK_RELEASE;
    for (i = MBX_CLOCK_RESOURCE_COUNT; i > 0; --i) {
        unsigned int bit = 1U << (i - 1);
        if (r->held_resources & bit) {
            io->release(io->cookie, (enum mbx_clock_resource)(i - 1));
            r->held_resources &= ~bit;
        }
    }
    if (r->module_pinned) {
        io->unpin_lifetime(io->cookie);
        r->module_pinned = 0;
    }
    r->state = MBX_CLOCK_RELEASED;
    r->kernel_init_error = r->operation_error;
}

struct mbx_clock_result mbx_clock_transaction(const struct mbx_clock_io *io)
{
    struct mbx_clock_result r = {0};
    struct mbx_clock_reset_report reset = {0};
    unsigned int i;
    int error;
    r.last_phase = MBX_CLOCK_ACQUIRE;
    if (!io || !io->acquire || !io->release || !io->pin_lifetime ||
        !io->unpin_lifetime || !io->sample || !io->set_divider ||
        !io->enable || !io->disable || !io->reset || !io->ready ||
        !io->restore_reset) {
        r.operation_error = r.kernel_init_error = -EINVAL;
        return r;
    }
    for (i = 0; i < MBX_CLOCK_RESOURCE_COUNT; ++i) {
        r.operation_error = error_code(io->acquire(io->cookie, (enum mbx_clock_resource)i));
        if (r.operation_error) goto safe;
        r.held_resources |= 1U << i;
    }
    r.last_phase = MBX_CLOCK_INITIAL;
    error = observe(io, &r);
    if (error) { r.operation_error = error; goto safe; }
    r.original_parent_rate = r.last_observation.parent_rate;
    if (!expected(&r, 0, 1, 1, 1)) { r.operation_error = -EBUSY; goto safe; }
    r.last_phase = MBX_CLOCK_PIN;
    r.operation_error = error_code(io->pin_lifetime(io->cookie));
    if (r.operation_error) goto safe;
    r.module_pinned = 1;
    r.last_phase = MBX_CLOCK_RATE;
    r.rate_attempted = 1; /* A failed API operation may have reached hardware. */
    r.operation_error = error_code(io->set_divider(io->cookie, 2));
    if (r.operation_error) goto cleanup;
    error = observe(io, &r);
    if (error || !expected(&r, 0, 1, 2, 1)) {
        r.operation_error = error ? error : -EIO; goto cleanup;
    }
    r.last_phase = MBX_CLOCK_ENABLE;
    for (i = 1; i <= 4; i <<= 1) {
        r.operation_error = error_code(io->enable(io->cookie, i));
        if (r.operation_error) goto cleanup;
        r.enabled_refs |= i;
    }
    error = observe(io, &r);
    if (error || !expected(&r, 7, 1, 2, 1)) {
        r.operation_error = error ? error : -EIO; goto cleanup;
    }
    r.last_phase = MBX_CLOCK_RESET;
    r.reset_called = 1;
    io->reset(io->cookie, &reset);
    r.operation_error = error_code(reset.operation_error);
    r.reset_restoration_error = error_code(reset.restoration_error);
    if (reset.operation_error && reset.wrote_register) {
        r.reset_restore_attempts = 1; /* Already attempted inside the helper. */
        if (!reset.reset_restored && !r.reset_restoration_error)
            r.reset_restoration_error = -EIO;
    }
    if (r.reset_restoration_error) goto fault;
    if (r.operation_error) goto cleanup;
    if (!reset.completion_observed || !reset.wrote_register) {
        r.operation_error = -EIO; goto cleanup;
    }
    error = observe(io, &r);
    if (error || !expected(&r, 7, 0, 2, 1)) {
        r.operation_error = error ? error : -EIO; goto cleanup;
    }
    r.last_phase = MBX_CLOCK_READY;
    r.operation_error = error_code(io->ready(io->cookie));

cleanup:
    r.last_phase = MBX_CLOCK_RESTORE_RESET;
    if (r.reset_called && reset.wrote_register && !r.reset_restore_attempts) {
        r.reset_restore_attempts = 1;
        r.reset_restoration_error = error_code(io->restore_reset(io->cookie));
        if (r.reset_restoration_error) goto fault;
    }
    error = observe(io, &r);
    if (error) { r.quiescence_error = error; goto fault; }
    if (r.last_observation.reset_control != 1) {
        r.reset_restoration_error = -EIO; goto fault;
    }
    if (!expected(&r, r.enabled_refs, 1, 1, 0) ||
        (r.last_observation.divider != 1 && r.last_observation.divider != 2)) {
        r.clock_restoration_error = -EIO; goto fault;
    }
    r.last_phase = MBX_CLOCK_DISABLE_FUNCTIONAL;
    for (i = 4; i >= 2; i >>= 1) {
        if (r.enabled_refs & i) { io->disable(io->cookie, i); r.enabled_refs &= ~i; }
    }
    error = observe(io, &r);
    if (error || !expected(&r, r.enabled_refs, 1, 1, 0)) {
        r.clock_restoration_error = error ? error : -EIO; goto fault;
    }
    r.last_phase = MBX_CLOCK_RESTORE_RATE;
    r.rate_restore_attempts = 1;
    r.clock_restoration_error = error_code(io->set_divider(io->cookie, 1));
    if (r.clock_restoration_error) goto fault;
    error = observe(io, &r);
    if (error || !expected(&r, r.enabled_refs, 1, 1, 1)) {
        r.clock_restoration_error = error ? error : -EIO; goto fault;
    }
    r.last_phase = MBX_CLOCK_DISABLE_INTERFACE;
    if (r.enabled_refs & 1U) { io->disable(io->cookie, 1); r.enabled_refs &= ~1U; }
    error = observe(io, &r);
    if (error || !expected(&r, 0, 1, 1, 1)) {
        r.clock_restoration_error = error ? error : -EIO; goto fault;
    }
safe:
    release_all(io, &r);
    r.last_phase = MBX_CLOCK_COMPLETE;
    return r;
fault:
    r.state = MBX_CLOCK_FAULT_PINNED;
    /* Keep all still-valid ownership and the binding alive; never fail init. */
    r.kernel_init_error = 0;
    return r;
}
