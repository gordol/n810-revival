/* SPDX-License-Identifier: MIT */
#ifndef N810_MBX_RESET_H
#define N810_MBX_RESET_H

/* Abstract PRCM registers. This component has no MMIO mapping or device entry. */
enum mbx_reset_register { MBX_RESET_CONTROL, MBX_RESET_STATUS };
enum mbx_reset_phase {
    MBX_RESET_PREFLIGHT, MBX_RESET_ACK, MBX_RESET_ASSERT,
    MBX_RESET_RELEASE, MBX_RESET_COMPLETE, MBX_RESET_RESTORE
};
struct mbx_reset_io {
    void *cookie;
    int (*read)(void *, enum mbx_reset_register, unsigned int *);
    int (*write)(void *, enum mbx_reset_register, unsigned int);
    void (*pause)(void *);
};
struct mbx_reset_result {
    int operation_error;
    int restoration_error;
    enum mbx_reset_phase failed_phase;
    unsigned int wrote_register;
    unsigned int completion_observed;
    unsigned int reset_restored;
    unsigned int samples;
};

/*
 * Caller must own and serialize the reset registers, hold power/clocks, and
 * provide ordered register access. Initially reset must be asserted. Status
 * bit 4 is a firmware-observed completion poll, not a public specification.
 * Success leaves reset released; caller retains ownership until reassertion.
 * Errors after any attempted write attempt to restore reset assertion, but
 * restoration can fail. No error authorizes freeing device-visible memory.
 * Divider changes, power policy, readiness and identity are outside this API.
 * maximum_samples bounds each poll; pause must itself return in bounded time.
 */
struct mbx_reset_result mbx_reset_release(const struct mbx_reset_io *,
                                         unsigned int maximum_samples);
#endif
