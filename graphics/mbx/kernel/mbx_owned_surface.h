/* SPDX-License-Identifier: MIT */
#ifndef MBX_OWNED_SURFACE_H
#define MBX_OWNED_SURFACE_H
#include <linux/types.h>
#include <linux/ioctl.h>
/* Private synchronous service ABI. Handles are not DMA/physical addresses.
 * Acquire pins the completed image against every subsequent GPU submission.
 * Release returns ownership; close invalidates all handles. No implicit copy.
 */
#define MBX_SURFACE_RGB565 1U
#define MBX_SURFACE_COMPLETE 1U
struct mbx_owned_surface {
 __u32 version,session,generation,slot;
 __u32 format,width,height,stride;
 __u32 bytes,flags,reserved[2];
};
/* Explicit final CPU sink, not a claim of DMA scanout. A partial copy failure
 * leaves the lease held and must never be followed by display submission.
 * Source rows can be reversed to preserve GL/display coordinate conventions.
 */
struct mbx_surface_sink {
 struct mbx_owned_surface surface;
 __u64 address,capacity;
 __u32 stride,x,y,width,height,reverse_rows,reserved[2];
};
/* Synchronous DMA sink. The framebuffer fd names the destination allocation;
 * no userspace physical addresses are accepted. */
struct mbx_surface_dma_sink {
 struct mbx_owned_surface surface;
 __u32 version;
 __s32 fb_fd;
 __u32 canvas_width,canvas_height,stride,destination_x,destination_y;
 __u32 x,y,width,height,reverse_rows,reserved;
};
_Static_assert(sizeof(struct mbx_surface_dma_sink)==100,"DMA sink ABI");
_Static_assert(sizeof(struct mbx_owned_surface)==48,"surface ABI");
_Static_assert(sizeof(struct mbx_surface_sink)==96,"surface sink ABI");
#define MBX_SURFACE_ACQUIRE _IOR('M',0x50,struct mbx_owned_surface)
#define MBX_SURFACE_RELEASE _IOW('M',0x51,struct mbx_owned_surface)
#define MBX_SURFACE_COPY_SINK _IOW('M',0x52,struct mbx_surface_sink)
#define MBX_SURFACE_DMA_SINK _IOW('M',0x53,struct mbx_surface_dma_sink)
#endif
