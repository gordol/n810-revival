/* SPDX-License-Identifier: MIT */
#ifndef MBX_GL_STATE_H
#define MBX_GL_STATE_H
/* Gallium PIPE_FUNC_* order matches GL comparison enum low three bits. */
struct mbx_gl_state {
    unsigned depth_enabled, depth_write, depth_func;
    unsigned smooth_color, blend_enabled, color_mask;
};
/* N95-derived fixed-function state subset. Unsupported state is rejected,
 * never silently approximated. Device acceptance is a separate requirement. */
int mbx_gl_state_words(const struct mbx_gl_state *, unsigned words[2]);
unsigned mbx_gl_pack_rgba(unsigned r, unsigned g, unsigned b, unsigned a);
#endif
