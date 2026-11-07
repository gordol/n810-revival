/* SPDX-License-Identifier: MIT */
#include "mbx_gl_state.h"
int mbx_gl_state_words(const struct mbx_gl_state *s, unsigned words[2])
{
    unsigned state;
    if (!s || !words || s->depth_enabled>1 || s->depth_write>1 ||
        s->depth_func>7 || s->smooth_color>1 || s->blend_enabled ||
        s->color_mask!=15) return -22;
    /* 804b60bc: normal unblended color state, no fog or alpha test.
     * 804a899c..89b0: depth comparison occupies bits9..11, with bit7
     * preserving disabled depth writes. This is NOT the fog state14202f80.
     * Bit22 is the smooth-color state from context2bc; flat clears omit it.
     */
    state=0x22200000U | (s->smooth_color ? 0x00400000U : 0);
    if (s->depth_enabled)
        state |= s->depth_func<<9 | (s->depth_write ? 0 : 0x80U);
    else state |= 0xe80U;
    words[0]=0xe0000000U; /* alpha comparison always, reference0 */
    words[1]=state;
    return 0;
}
unsigned mbx_gl_pack_rgba(unsigned r,unsigned g,unsigned b,unsigned a)
{
    return (r&255U) | ((g&255U)<<8) | ((b&255U)<<16) | ((a&255U)<<24);
}
