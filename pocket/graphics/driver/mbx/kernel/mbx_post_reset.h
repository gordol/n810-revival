/* SPDX-License-Identifier: MIT */
#ifndef MBX_POST_RESET_H
#define MBX_POST_RESET_H
#include "mbx_reset.h"
#define MBX_READY_MAX_SAMPLES 1000U
#define MBX_READY_STABLE_SAMPLES 2U
struct mbx_ready_snapshot {
    unsigned int fclk, iclk, idle, select, control, status, power;
    unsigned long rates[3];
};
struct mbx_ready_io {
    struct mbx_reset_io reset;
    int (*snapshot)(void *, struct mbx_ready_snapshot *);
    int (*owned_operation)(void *, unsigned int *retain);
};
struct mbx_post_reset_result {
    struct mbx_reset_result handshake;
    int readiness_error, restoration_error, final_state_error;
    int operation_error;
    unsigned int operation_attempted;
    unsigned int readiness_attempted, final_state_attempted, ready, samples, consecutive;
    unsigned int restoration_attempts, reset_asserted_verified, must_retain;
    struct mbx_ready_snapshot last_readiness, final;
};
/* Caller owns clocks/reset and has pinned module/resources through this call.
 * Baseline is the verified clocks-enabled/reset-asserted state at the
 * explicitly expected divider, one or two. The caller owns the rate claim.
 * No clock rate/divider change, core read, DMA or resource release occurs here.
 * pause belongs to the caller and must implement its validated startup limits.
 * Poll counts bound completed callback invocations, never a wedged MMIO/lock.
 */
struct mbx_post_reset_result mbx_reset_then_ready_at_divider(const struct mbx_ready_io *,
    const struct mbx_ready_snapshot *, unsigned int expected_divider, unsigned int handshake_limit,
    unsigned int readiness_limit);
#endif
