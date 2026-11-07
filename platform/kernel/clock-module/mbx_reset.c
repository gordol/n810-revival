/* SPDX-License-Identifier: MIT */
#include "mbx_reset.h"
#ifdef __KERNEL__
#include <linux/errno.h>
#else
#include <errno.h>
#endif

#define RESET_BIT 1U
#define COMPLETION_BIT 0x10U

static int read_word(const struct mbx_reset_io *io,
                     enum mbx_reset_register reg, unsigned int *value)
{
    int error = io->read(io->cookie, reg, value);
    if (error) return error < 0 ? error : -EIO;
    return *value == ~0U ? -EIO : 0;
}

static int write_word(const struct mbx_reset_io *io,
                      enum mbx_reset_register reg, unsigned int value,
                      struct mbx_reset_result *result)
{
    int error;
    /* A failed access may have reached hardware, so mark before the call. */
    result->wrote_register = 1;
    error = io->write(io->cookie, reg, value);
    return error > 0 ? -EIO : error;
}

static int poll(const struct mbx_reset_io *io, enum mbx_reset_register reg,
                unsigned int mask, unsigned int expected,
                unsigned int maximum_samples, struct mbx_reset_result *result)
{
    unsigned int value, i;
    for (i = 0; i < maximum_samples; ++i) {
        int error = read_word(io, reg, &value);
        ++result->samples;
        if (error) return error;
        if ((value & mask) == expected) return 0;
        if (i + 1 < maximum_samples) io->pause(io->cookie);
    }
    return -ETIMEDOUT;
}

static int update_control(const struct mbx_reset_io *io, unsigned int asserted,
                          struct mbx_reset_result *result)
{
    unsigned int before, after, requested;
    int error = read_word(io, MBX_RESET_CONTROL, &before);
    if (error) return error;
    requested = (before & ~RESET_BIT) | asserted;
    error = write_word(io, MBX_RESET_CONTROL, requested, result);
    if (error) return error;
    error = read_word(io, MBX_RESET_CONTROL, &after);
    if (error) return error;
    /* Check both the target bit and unrelated bits preserved by this update. */
    return after == requested ? 0 : -EIO;
}

struct mbx_reset_result mbx_reset_release(const struct mbx_reset_io *io,
                                         unsigned int maximum_samples)
{
    struct mbx_reset_result result = {0};
    unsigned int initial_control, initial_status;
    result.failed_phase = MBX_RESET_PREFLIGHT;
    if (!io || !io->read || !io->write || !io->pause ||
        maximum_samples == 0 || maximum_samples > 100000) {
        result.operation_error = -EINVAL;
        return result;
    }
    result.operation_error = read_word(io, MBX_RESET_CONTROL, &initial_control);
    if (result.operation_error) return result;
    if (!(initial_control & RESET_BIT)) {
        result.operation_error = -EBUSY;
        return result;
    }
    result.operation_error = read_word(io, MBX_RESET_STATUS, &initial_status);
    if (result.operation_error) return result;

    result.failed_phase = MBX_RESET_ACK;
    /* Acknowledge only the observed completion bit; never echo W1C history. */
    result.operation_error = write_word(io, MBX_RESET_STATUS, COMPLETION_BIT, &result);
    if (result.operation_error) goto failed;
    result.operation_error = poll(io, MBX_RESET_STATUS, COMPLETION_BIT, 0,
                                  maximum_samples, &result);
    if (result.operation_error) goto failed;

    result.failed_phase = MBX_RESET_ASSERT;
    result.operation_error = update_control(io, RESET_BIT, &result);
    if (result.operation_error) goto failed;
    result.failed_phase = MBX_RESET_RELEASE;
    result.operation_error = update_control(io, 0, &result);
    if (result.operation_error) goto failed;
    result.failed_phase = MBX_RESET_COMPLETE;
    result.operation_error = poll(io, MBX_RESET_STATUS, COMPLETION_BIT,
                                  COMPLETION_BIT, maximum_samples, &result);
    if (result.operation_error) goto failed;
    result.completion_observed = 1;
    return result;

failed:
    if (result.wrote_register) {
        result.restoration_error = update_control(io, RESET_BIT, &result);
        result.reset_restored = result.restoration_error == 0;
    }
    return result;
}
