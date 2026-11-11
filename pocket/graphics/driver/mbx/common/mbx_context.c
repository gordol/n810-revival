/* SPDX-License-Identifier: MIT */
#include "mbx_context.h"
int mbx_context_selection(unsigned status,unsigned *selection)
{
 unsigned first,second;
 if(!selection || status==0xffffffffU || (status&0x2a0U))return -5;
 if(!(status&0x01000000U))return -11;
 first=(status&0x0e000000U)>>25;
 second=(status&0x70000000U)>>28;
 *selection=second|(first<<17);
 return 0;
}

static int mbx_context_valid_io(const struct mbx_context_io *io)
{return io && io->write && io->fresh && io->wait && io->settle;}
/* Context retirement801ba9c0, called from the surface destruction loop.
 * Never use this helper to initialize a fresh TA context. */
int mbx_context_retire_loaded(const struct mbx_context_io *io)
{
 int error;
 if(!mbx_context_valid_io(io))return -22;
 error=io->write(io->cookie,0x834,1);if(error)return error;
 io->settle(io->cookie);
 return io->write(io->cookie,0x134,0xc0);
}
int mbx_context_retire_then_reload(const struct mbx_context_io *io,
                                  unsigned state_a,unsigned state_b)
{
 int error;
 if(!mbx_context_valid_io(io) || !state_a || !state_b || state_a%512U ||
    state_b%16384U || state_a>=0x02000000U || state_b>=0x02000000U)return -22;
 error=io->write(io->cookie,0x834,1);if(error)return error;
 io->settle(io->cookie);
 error=io->write(io->cookie,0x134,0xc0);if(error)return error;
 error=io->fresh(io->cookie,0x100);if(error)return error;
 error=io->write(io->cookie,0x864,state_b);if(error)return error;
 error=io->write(io->cookie,0x820,state_a);if(error)return error;
 error=io->write(io->cookie,0x814,1);if(error)return error;
 return io->wait(io->cookie,0x100);
}
int mbx_context_finish(const struct mbx_context_io *io,unsigned selection)
{
 int error;
 if(!mbx_context_valid_io(io) || (selection&~0x000e0007U))return -22;
 error=io->fresh(io->cookie,0x10);if(error)return error;
 error=io->write(io->cookie,0x80c,selection);if(error)return error;
 error=io->write(io->cookie,0x808,1);if(error)return error;
 return io->wait(io->cookie,0x10);
}
