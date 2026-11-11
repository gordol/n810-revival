/* SPDX-License-Identifier: MIT. Private cooperative Mesa API, not a GL extension.
 * Descriptors name completed small/native logical RGBA8 images, never addresses.
 * The broker owns slot allocation and publish/consume acknowledgements.
 */
#ifndef MBX_WINDOW_EXPORT_H
#define MBX_WINDOW_EXPORT_H
#include "mbx_window_images.h"
#define MBX_WINDOW_EXPORT_VERSION 1U
#define MBX_WINDOW_EXPORT_NATIVE_VERSION 2U
#define MBX_WINDOW_LOGICAL_RGBA8 1U
#define MBX_WINDOW_CLIENT_SLOTS 14U
struct mbx_window_image {
 unsigned version,width,height,format;
 struct mbx_window_token token;
 union {unsigned reserved;unsigned stride_bytes;};
};
#ifdef __cplusplus
static_assert(sizeof(struct mbx_window_image)==32,"window export ABI");
#else
_Static_assert(sizeof(struct mbx_window_image)==32,"window export ABI");
#endif
static inline int mbx_window_range_valid(unsigned first,unsigned count){
 return count&&first<MBX_WINDOW_CLIENT_SLOTS&&count<=MBX_WINDOW_CLIENT_SLOTS-first;
}
static inline int mbx_window_image_valid(const struct mbx_window_image *p){
 if(!p||p->format!=MBX_WINDOW_LOGICAL_RGBA8||!p->token.session||!p->token.generation||p->token.slot>=14)return 0;
 if(p->version==1)return p->width==128&&p->height==128&&!p->reserved;
 return p->version==2&&mbx_window_shape(2,p->token.slot,p->width,p->height)&&p->stride_bytes==p->width*4U;
}
/* Nested transactions serialize all jobs, scratch slots and the final sink.
 * An export needs glFinish first. Import requires allocated, level-zero,
 * non-mipmapped GL_TEXTURE_2D RGBA8 storage of matching dimensions. No CPU access is allowed afterward.
 * Import/forget must happen between draws; imported textures are read-only.
 * Keep a producer slot immutable until the compositor's completion ACK, then
 * call export_release. Retain the GL texture name until that release succeeds.
 */
#ifdef __cplusplus
extern "C" {
#endif
int n810_mbx_transaction_begin(void);
int n810_mbx_transaction_end(void);
/* Pointwise RGB(source), alpha(mask) replacement; not blending. Inputs may be
 * uploaded images or completed resident images. RED modes require an uploaded
 * canonical mask; no GPU readback is permitted. Target is allocated128x128 for
 * input1..128 each axis, or240x320 for native inputs. Sample only the returned
 * logical rectangle (UVmax=width/storage_width,height/storage_height).
 * Caller glFinish'es pending GL work first, allocates target storage without
 * pixels, and retains/deletes it normally. Output pixels remain GPU-only. */
#define MBX_WINDOW_ALPHA 0U
#define MBX_WINDOW_RED_ALPHA 1U
#define MBX_WINDOW_BINARY_RED_ALPHA 2U
struct mbx_window_view {unsigned width,height,storage_width,storage_height;};
int n810_mbx_window_channels(unsigned source,unsigned mask,unsigned target,
 unsigned mode,struct mbx_window_view *view);
/* Rect coordinates address level-zero canonical upload rows directly.
 * Equal-size uploaded source/mask images may be up to1024x1024. Only the
 * selected1..128 rectangle is packed; target storage is128x128. Cropped
 * resident inputs are rejected, with no implicit readback. */
struct mbx_window_rect {unsigned x,y,width,height;};
int n810_mbx_window_channels_region(unsigned source,unsigned mask,unsigned target,
 const struct mbx_window_rect *rect,unsigned mode,struct mbx_window_view *view);
/* One synchronous GPU merge for a zero-padded128x128 atlas. All inputs must
 * have canonical CPU upload storage; source/mask sizes match per item and
 * are at most1024x1024. sx/sy address both inputs. Destination rectangles
 * must be disjoint and fit128x128. Modes match the single-region operation.
 * Finish pending GL work and prior target consumers before calling. Pinned,
 * imported, active-target and feedback aliases are rejected. No GL state is
 * changed. On admission failure, view and target remain unchanged and no job
 * is submitted. Device errors after submission are not an admission fallback.
 * Returned view bounds the used atlas area; storage dimensions are128x128. */
#define MBX_WINDOW_CHANNEL_BATCH_MAX 64U
struct mbx_window_channel_item {unsigned source,mask,sx,sy,width,height,dx,dy,mode;};
int n810_mbx_window_channels_batch(unsigned target,
 const struct mbx_window_channel_item *items,unsigned count,struct mbx_window_view *view);
int n810_mbx_window_get_layout(struct mbx_window_layout *out);
int n810_mbx_window_export(unsigned texture,struct mbx_window_image *out);
int n810_mbx_window_export_release(unsigned texture,const struct mbx_window_image *image);
int n810_mbx_window_import(unsigned texture,const struct mbx_window_image *image);
int n810_mbx_window_forget(unsigned texture);
#ifdef __cplusplus
}
#endif
#endif
