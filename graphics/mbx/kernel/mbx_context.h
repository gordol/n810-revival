/* SPDX-License-Identifier: MIT */
#ifndef N810_MBX_CONTEXT_H
#define N810_MBX_CONTEXT_H
/* Decode only the post-submission context availability fields used by the original
 * Nokia driver at801bdfbc..801bdff0. Does not assert geometry completion. */
int mbx_context_selection(unsigned status,unsigned *selection);
struct mbx_context_io {
 void *cookie;
 int (*write)(void *,unsigned,unsigned);
 int (*fresh)(void *,unsigned);
 int (*wait)(void *,unsigned);
 void (*settle)(void *);
};
/* Retirement and retirement/reload transitions, not fresh initialization.
 * The834 helper is reached during surface destruction at801bab3c. */
int mbx_context_retire_loaded(const struct mbx_context_io *io);
int mbx_context_retire_then_reload(const struct mbx_context_io *io,
                                  unsigned state_a,unsigned state_b);
/* Caller first observes an available post-submission context and decodes it.
 * Request the original80c/808 transition, observing a fresh event10. */
int mbx_context_finish(const struct mbx_context_io *io,unsigned selection);
#endif
