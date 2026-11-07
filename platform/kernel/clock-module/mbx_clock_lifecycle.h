/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef MBX_CLOCK_LIFECYCLE_H
#define MBX_CLOCK_LIFECYCLE_H

enum mbx_clock_resource {
    MBX_CLOCK_REGION, MBX_CLOCK_SHARED_HANDLE, MBX_CLOCK_RATE_CLAIM,
    MBX_CLOCK_INTERFACE_HANDLE, MBX_CLOCK_2D_HANDLE, MBX_CLOCK_3D_HANDLE,
    MBX_CLOCK_RESOURCE_COUNT
};
enum mbx_clock_phase {
    MBX_CLOCK_ACQUIRE, MBX_CLOCK_INITIAL, MBX_CLOCK_PIN, MBX_CLOCK_RATE,
    MBX_CLOCK_ENABLE, MBX_CLOCK_RESET, MBX_CLOCK_READY,
    MBX_CLOCK_RESTORE_RESET, MBX_CLOCK_DISABLE_FUNCTIONAL,
    MBX_CLOCK_RESTORE_RATE, MBX_CLOCK_DISABLE_INTERFACE,
    MBX_CLOCK_RELEASE, MBX_CLOCK_COMPLETE
};
enum mbx_clock_state { MBX_CLOCK_RELEASED, MBX_CLOCK_FAULT_PINNED };

struct mbx_clock_observation {
    unsigned int reset_control, gates, divider, power_on;
    unsigned long parent_rate, rate_2d, rate_3d;
};
struct mbx_clock_reset_report {
    int operation_error, restoration_error;
    unsigned int wrote_register, completion_observed, reset_restored;
};
struct mbx_clock_result {
    enum mbx_clock_state state;
    enum mbx_clock_phase last_phase;
    int operation_error, reset_restoration_error, clock_restoration_error;
    int observation_error, quiescence_error, kernel_init_error;
    unsigned int held_resources, enabled_refs, module_pinned;
    unsigned int rate_attempted, reset_called, reset_restore_attempts;
    unsigned int rate_restore_attempts, last_observation_valid;
    unsigned long original_parent_rate;
    struct mbx_clock_observation last_observation;
};
struct mbx_clock_io {
    void *cookie;
    int (*acquire)(void *, enum mbx_clock_resource);
    void (*release)(void *, enum mbx_clock_resource);
    int (*pin_lifetime)(void *);
    void (*unpin_lifetime)(void *);
    int (*sample)(void *, struct mbx_clock_observation *);
    int (*set_divider)(void *, unsigned int);
    int (*enable)(void *, unsigned int);
    void (*disable)(void *, unsigned int);
    void (*reset)(void *, struct mbx_clock_reset_report *);
    int (*ready)(void *);
    int (*restore_reset)(void *);
};

/*
 * Original abstract policy only: no kernel module, register mapping or hardware.
 * acquire failures must transfer no ownership. enable failures transfer no API
 * reference, but may leave hardware uncertain; successful references alone may
 * be disabled. sample rejects invalid/all-ones raw words before deriving fields.
 * set_divider operates through the exclusively owned shared CCF handle, never
 * a raw fallback; 1/2 are the only requested divisors. All callbacks must return
 * in bounded time. reset binds the already reviewed helper report unchanged.
 * No other gate consumer/writer may exist throughout this whole transaction.
 *
 * pin_lifetime must establish an actual resident module/device lifetime BEFORE
 * any hardware-changing callback. On FAULT_PINNED the future binding must retain
 * all indicated valid handles, clock references, rate claim, mapping/reservation
 * and bound device, expose cached errors, suppress manual unbind, and RETURN
 * SUCCESS from module init to avoid freeing live unresolved state. That init
 * success is not operation success. No automatic unpin/repair path is supplied.
 * On RELEASED all references are balanced; module init may return its operation
 * error. Force removal and a callback that never returns are outside guarantees.
 */
struct mbx_clock_result mbx_clock_transaction(const struct mbx_clock_io *);
#endif
