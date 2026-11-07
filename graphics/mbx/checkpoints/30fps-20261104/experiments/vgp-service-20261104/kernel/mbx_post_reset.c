/* SPDX-License-Identifier: MIT */
#include "mbx_post_reset.h"
#ifdef __KERNEL__
#include <linux/errno.h>
#else
#include <errno.h>
#endif

static int valid_state(const struct mbx_ready_snapshot *s,
                       const struct mbx_ready_snapshot *base,
                       unsigned int control)
{
    unsigned int i;
    if (s->fclk == ~0U || s->iclk == ~0U || s->idle == ~0U ||
        s->select == ~0U || s->control == ~0U || s->status == ~0U ||
        s->power == ~0U) return -EIO;
    if (s->control != control || s->fclk != base->fclk ||
        s->iclk != base->iclk || s->select != base->select ||
        (s->power & 0x100003U)) return -EBUSY;
    for (i = 0; i < 3; ++i)
        if (!s->rates[i] || s->rates[i] == ~0UL ||
            s->rates[i] != base->rates[i]) return -EBUSY;
    return 0;
}

static int baseline_valid(const struct mbx_ready_snapshot *b, unsigned int divider)
{
    if (b->control != 1U || (b->fclk & 6U) != 6U ||
        (b->iclk & 1U) != 1U || (b->select & 7U) != divider)
        return -EBUSY;
    return valid_state(b, b, 1U);
}

static int snapshot(const struct mbx_ready_io *io,
                    struct mbx_ready_snapshot *out)
{
    int error = io->snapshot(io->reset.cookie, out);
    return error > 0 ? -EIO : error;
}

static int reassert_once(const struct mbx_reset_io *io)
{
    unsigned int before, after;
    int error = io->read(io->cookie, MBX_RESET_CONTROL, &before);
    if (error || before == ~0U) return error < 0 ? error : -EIO;
    error = io->write(io->cookie, MBX_RESET_CONTROL, before | 1U);
    if (error) return error < 0 ? error : -EIO;
    error = io->read(io->cookie, MBX_RESET_CONTROL, &after);
    if (error) return error < 0 ? error : -EIO;
    return after == (before | 1U) ? 0 : -EIO;
}

struct mbx_post_reset_result mbx_reset_then_ready_at_divider(const struct mbx_ready_io *io,
    const struct mbx_ready_snapshot *base, unsigned int expected_divider, unsigned int handshake_limit,
    unsigned int readiness_limit)
{
    struct mbx_post_reset_result result = {0};
    unsigned int i;
    int error;
    if (!io || !base || !io->snapshot || !io->reset.read ||
        !io->reset.write || !io->reset.pause ||
        (expected_divider != 1U && expected_divider != 2U) || !handshake_limit ||
        handshake_limit > MBX_READY_MAX_SAMPLES ||
        readiness_limit < MBX_READY_STABLE_SAMPLES ||
        readiness_limit > MBX_READY_MAX_SAMPLES) {
        result.handshake.operation_error = -EINVAL;
        return result;
    }
    error = baseline_valid(base, expected_divider);
    if (error) { result.handshake.operation_error = error; return result; }
    result.handshake = mbx_reset_release(&io->reset, handshake_limit);
    if (!result.handshake.operation_error) {
        result.readiness_attempted = 1;
        result.readiness_error = -ETIMEDOUT;
        for (i = 0; i < readiness_limit; ++i) {
            ++result.samples;
            error = snapshot(io, &result.last_readiness);
            if (!error) error = valid_state(&result.last_readiness, base, 0U);
            if (!error && !(result.last_readiness.status & 0x10U)) error = -EIO;
            if (error) { result.readiness_error = error; break; }
            /* Identity-only Nokia reset-completion contract. IDLEST remains
             * recorded and invalid all-ones rejected, but is not an access gate. */
            ++result.consecutive;
            if (result.consecutive == MBX_READY_STABLE_SAMPLES) {
                result.ready = 1; result.readiness_error = 0; break;
            }
            if (i + 1U < readiness_limit) io->reset.pause(io->reset.cookie);
        }
        if (result.ready && io->owned_operation) {
            unsigned int retain = 0;
            result.operation_attempted = 1;
            result.operation_error = io->owned_operation(io->reset.cookie, &retain);
            if (result.operation_error > 0) result.operation_error = -EIO;
            if (retain) {
                /* DMA may still be live. Keep reset, clocks, mappings and
                 * lifetime exactly as owned; recovery is external. */
                result.must_retain = 1;
                return result;
            }
        }
        /* Exactly one caller restoration after handshake success, including
         * timeout/invalid-readiness paths. No retry after a failed attempt. */
        result.restoration_attempts = 1;
        result.restoration_error = reassert_once(&io->reset);
    } else {
        /* The unchanged handshake owns its one error restoration. */
        result.restoration_attempts = result.handshake.wrote_register ? 1U : 0U;
        result.restoration_error = result.handshake.restoration_error;
    }
    result.final_state_attempted = 1;
    result.final_state_error = snapshot(io, &result.final);
    if (!result.final_state_error)
        result.final_state_error = valid_state(&result.final, base, 1U);
    result.reset_asserted_verified = !result.restoration_error && !result.final_state_error;
    /* If state is uncertain after any write, keep clocks/mapping/reservation
     * and module lifetime. A failed final check cannot authorize release. */
    result.must_retain = result.handshake.wrote_register && !result.reset_asserted_verified;
    return result;
}
