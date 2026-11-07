/* SPDX-License-Identifier: GPL-2.0-only */
#include "clock_commit.h"
#ifdef __KERNEL__
#include <linux/errno.h>
#else
#include <errno.h>
#endif
/* OMAP2420: MPU, CORE1/2, PLL control/dividers, DSP. Read-only guards. */
static const unsigned int guard_offsets[COMMIT_GUARDS]={0x140,0x240,0x244,0x500,0x520,0x540,0x544,0x840};
struct commit_result clock_commit_apply(const struct commit_io *io,unsigned int baseline,
 unsigned int target,unsigned int samples,unsigned int pause_us)
{
 struct commit_result r={0};unsigned int i;
 if(!io||!io->read||!io->write||!io->pause||!io->lock||!io->unlock||
    ((baseline&7U)!=1U&&(baseline&7U)!=2U)||
    ((target&7U)!=1U&&(target&7U)!=2U)||((baseline^target)&~7U)||!samples||samples>32U||
    !pause_us||pause_us>100U){r.error=-EINVAL;return r;}
 io->lock(io->cookie);
 r.initial_config=io->read(io->cookie,0x80);
 r.initial_status=io->read(io->cookie,0x84);
 if(r.initial_config!=0||r.initial_status!=0||io->read(io->cookie,0x340)!=baseline){r.error=-EBUSY;goto out;}
 for(i=0;i<COMMIT_GUARDS;++i){
  r.guards_before[i]=io->read(io->cookie,guard_offsets[i]);
  if(r.guards_before[i]==~0U){r.error=-EIO;goto out;}
 }
 /* The existing OMAP242x SRAM path defines DPLL lock as IDLEST&3==2. */
 if((r.guards_before[4]&3U)!=2U){r.error=-EBUSY;goto out;}
 r.attempted=1;
 io->write(io->cookie,0x340,target);
 io->write(io->cookie,0x80,1);++r.commits;
 for(r.target_samples=1;;++r.target_samples){
  r.target=io->read(io->cookie,0x340);
  if(r.target==target||r.target_samples==samples)break;
  io->pause(io->cookie,pause_us);
 }
 if(r.target!=target)r.error=-ETIMEDOUT;
 r.final_config=io->read(io->cookie,0x80);r.final_status=io->read(io->cookie,0x84);
 if(r.final_config!=r.initial_config||r.final_status!=r.initial_status)r.restoration_error=-EIO;
 for(i=0;i<COMMIT_GUARDS;++i){
  r.guards_after[i]=io->read(io->cookie,guard_offsets[i]);
  if(r.guards_after[i]!=r.guards_before[i])r.restoration_error=-EIO;
 }
out:
 io->unlock(io->cookie);return r;
}
