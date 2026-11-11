/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef POCKET_PIXEL_TARGET_H
#define POCKET_PIXEL_TARGET_H
#include <stddef.h>
#include <stdint.h>
/* Native GL-owner-thread API. Drawing uses standard GL between begin/end.
 * The current frontend context is borrowed, never created or replaced here.
 * Output is top-down RGB565, stride in pixels, capacity in bytes.
 * begin rejects nesting/context mismatch; read rejects invalid spans before GL.
 * Always end a successful begin, including failed draws/readbacks.
 */
int pocket_target_begin(void);
int pocket_target_read(uint16_t *,size_t,unsigned stride,unsigned width,unsigned height);
void pocket_target_end(void);
#endif
