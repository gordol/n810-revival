/* SPDX-License-Identifier: MIT */
#ifndef MBX_NATIVE_PRESENT_H
#define MBX_NATIVE_PRESENT_H
#include <stddef.h>
#include <stdint.h>

/* RGB565 byte surfaces. The caller owns both mappings for the entire call.
 * Source must be GPU-complete and CPU-readable under the driver's DMA contract.
 * This presenter never starts a GPU job or accepts physical addresses. */
struct mbx_surface { void *pixels; size_t bytes, stride; unsigned width, height; };
struct mbx_rect { unsigned x, y, width, height; };
struct mbx_present_ops {
    /* Wait for the prior display read; failure forbids writes and reuse. */
    int (*wait)(void *context);
    /* Submit the composed framebuffer. The submitted_region records the exact destination damage.
     * The implementation must publish CPU writes before triggering DMA. */
    int (*submit)(void *context);
};
struct mbx_presenter {
    struct mbx_surface framebuffer;
    struct mbx_present_ops ops;
    void *context;
    uint64_t submitted, completed, copied_bytes;
    int pending, faulted, writing;
    struct mbx_rect submitted_region;
};
int mbx_present_drain(struct mbx_presenter *p);
/* Borrow the destination only after its previous display transfer completes.
 * One owner must submit or cancel before any other presentation/close. */
int mbx_present_acquire(struct mbx_presenter *,struct mbx_surface *);
int mbx_present_submit(struct mbx_presenter *,struct mbx_rect);
int mbx_present_cancel(struct mbx_presenter *);
/* Single owner, no allocation, no X, no format conversion or scaling.
 * All bounds are validated before waiting or touching the framebuffer.
 * A transfer failure latches faulted; recovery belongs to the display owner. */
int mbx_present_rgb565(struct mbx_presenter *p, const struct mbx_surface *source,
                      struct mbx_rect source_rect, unsigned destination_x,
                      unsigned destination_y);
/* Exact bounding rectangle of changed pixels; 0 means unchanged, 1 changed. */
int mbx_surface_damage(const struct mbx_surface *a,const struct mbx_surface *b,struct mbx_rect *r);
#endif
