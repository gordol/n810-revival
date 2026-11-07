/* SPDX-License-Identifier: MIT */
#include "mbx_vgp_stream.h"
int mbx_vgp_stream(const struct mbx_vgp_stream_io *io,const struct mbx_command *c,
                   unsigned count,unsigned polls,struct mbx_vgp_stream_result *r)
{
 unsigned i,at=0;
 if(!io||!io->status||!io->write||!io->write_barrier||!io->pause||!c||!r||
    !count||count>65536||!polls||polls>1000)return -22;
 for(i=0;i<count;++i)if(c[i].destination!=MBX_FIFO&&c[i].destination!=MBX_POLYGON_CONTROL)return -22;
 *r=(struct mbx_vgp_stream_result){0};
 while(at<count){
  unsigned credit=0;
  for(i=0;i<polls;++i){
   unsigned status=io->status(io->cookie),used;
   r->last_status=status;++r->status_reads;
   if(status==~0U||(status&0x2a0U))return -5;
   used=(status>>16)&255U;
   if(used>59)return -5;
   credit=59-used;
   if(credit)break;
   io->pause(io->cookie);++r->pauses;
  }
  if(!credit)return -110;
  /* Keep individual bursts at the reference's 42-word reservation size.
   * Hardware may drain concurrently; it cannot reduce our free credits. */
  if(credit>42)credit=42;
  if(credit>count-at)credit=count-at;
  for(i=0;i<credit;++i)io->write(io->cookie,c+at+i);
  io->write_barrier(io->cookie);
  at+=credit;r->written=at;
 }
 return 0;
}
