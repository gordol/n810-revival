/* SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
 * SPDX-License-Identifier: GPL-2.0-or-later */
/* OSMesa owns CPU-readable output after the synchronous MBX write/read returns.
 * X shared-image/async modes have no owner here and are explicitly rejected.
 * These symbols belong only to the OSMesa target; GLX keeps its X owner. */
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
struct sw_displaytarget;
void n810_mbx_async_drain(void);
int n810_mbx_async_submit(struct sw_displaytarget *,int,const void *,size_t,size_t);
int n810_mbx_shared_bind(struct sw_displaytarget *,int,size_t);
void *n810_mbx_fence_create(void);
void *n810_mbx_fence_reference(void *,void *);
bool n810_mbx_fence_finish(void *,uint64_t);
void n810_mbx_async_drain(void) {}
int n810_mbx_async_submit(struct sw_displaytarget *target,int fd,
                         const void *packet,size_t bytes,size_t image_bytes)
{
    (void)target;(void)fd;(void)packet;(void)bytes;(void)image_bytes;
    return -1;
}
int n810_mbx_shared_bind(struct sw_displaytarget *target,int fd,size_t bytes)
{
    (void)target;(void)fd;(void)bytes;
    return -1;
}
void *n810_mbx_fence_create(void) { return (void *)(uintptr_t)1; }
void *n810_mbx_fence_reference(void *previous,void *next)
{
    (void)previous;
    return next;
}
bool n810_mbx_fence_finish(void *fence,uint64_t timeout)
{
    (void)timeout;
    return (uintptr_t)fence<=1;
}
