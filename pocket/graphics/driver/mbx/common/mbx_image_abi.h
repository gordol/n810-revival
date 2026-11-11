/* SPDX-License-Identifier: MIT */
#ifndef MBX_IMAGE_ABI_H
#define MBX_IMAGE_ABI_H
#ifdef __KERNEL__
#include <linux/ioctl.h>
#else
#include <sys/ioctl.h>
#endif
#include "mbx_window_images.h"
#define MBX_WINDOW_BIND _IOW('M',0x56,struct mbx_window_request)
#define MBX_WINDOW_LAYOUT _IOR('M',0x58,struct mbx_window_layout)
#define MBX_WINDOW_QUERY _IOR('M',0x57,struct mbx_window_token)
/* Owned read-only images in one mapping. Selection never accepts an address.
 * The exclusive client must fence X consumption before selecting an image
 * for another GPU write. All offsets are page and ARM alias-colour aligned. */
struct mbx_image_layout {
 unsigned version,images,stride_bytes,image_bytes;
};
_Static_assert(sizeof(struct mbx_image_layout)==16,"image layout ABI");
#define MBX_IMAGE_LAYOUT _IOR('M',0x41,struct mbx_image_layout)
#define MBX_IMAGE_SELECT _IOW('M',0x40,unsigned)
/* Valid only while this exclusive file owns the validated command template.
 * Generation changes on every full upload and is never reused within a module
 * lifetime. Query after a successful full upload, never after a failed write. */
struct mbx_template_info { unsigned version,generation,bytes,draws; };
_Static_assert(sizeof(struct mbx_template_info)==16,"template info ABI");
#define MBX_TEMPLATE_INFO _IOR('M',0x42,struct mbx_template_info)
/* Private experiment. No arbitrary GPU addresses or cross-session handles. */
struct mbx_resident_token { unsigned session,generation,slot; };
struct mbx_resident_bind { unsigned version,destination; struct mbx_resident_token source; };
#define MBX_RESIDENT_QUERY _IOR('M',0x43,struct mbx_resident_token)
#define MBX_RESIDENT_BIND _IOW('M',0x44,struct mbx_resident_bind)

struct mbx_resident_merge { unsigned version,destination; struct mbx_resident_token rgb,alpha; };
#define MBX_RESIDENT_MERGE _IOW('M',0x45,struct mbx_resident_merge)

#endif
