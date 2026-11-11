/* SPDX-License-Identifier: MIT */
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
struct context {
 struct {unsigned fclk,iclk,select,control,power;} initial;
 void *clocks[3];
};
enum {CLEANUP_CHECK=1,CLEANUP_BEFORE_3D,CLEANUP_AFTER_3D,
 CLEANUP_BEFORE_2D,CLEANUP_AFTER_2D,CLEANUP_BEFORE_RATE,CLEANUP_AFTER_RATE,
 CLEANUP_BEFORE_INTERFACE,CLEANUP_AFTER_INTERFACE,CLEANUP_FINAL,CLEANUP_COMPLETE};
#define DIVIDER_BASELINE 1U
#define DIVIDER_HYPOTHESIS 2U
static unsigned cleanup_phase,enabled_references,active_divider,divider_restore_attempts;
static int divider_restoration_error,commit_error;
static unsigned raw_divider,hardware_refs,checks,fail_check,commits,releases,disables;
static int verify_owned_state(struct context *c,unsigned refs,unsigned divider){
 (void)c;++checks;if(checks==fail_check)return -EBUSY;
 return refs==hardware_refs&&divider==raw_divider?0:-EIO;
}
static int set_committed_rate(struct context *c,unsigned from,unsigned to){
 (void)c;assert(raw_divider==from);++commits;
 if(commit_error)return commit_error;
 raw_divider=to;return 0;
}
static void clk_disable_unprepare(void *p){
 assert((unsigned long)p==hardware_refs);assert(hardware_refs);--hardware_refs;++disables;
}
static void put_handles(struct context *c){(void)c;assert(!hardware_refs);++releases;}
#include "clock_cleanup.inc"
static int admit(struct context *c){
#include "clock_admission.inc"
 return 0;
}
static void reset(struct context *c,unsigned initial,unsigned refs){
 memset(c,0,sizeof(*c));c->initial.select=initial;c->initial.control=1;
 for(unsigned i=0;i<3;i++)c->clocks[i]=(void*)(unsigned long)(i+1);
 cleanup_phase=0;enabled_references=hardware_refs=refs;active_divider=raw_divider=2;
 divider_restore_attempts=0;divider_restoration_error=commit_error=0;
 checks=fail_check=commits=releases=disables=0;
}
int main(void){
 struct context c;
 for(unsigned initial=1;initial<=2;initial++){
  reset(&c,initial,3);assert(!admit(&c)&&active_divider==initial);
  active_divider=2;
  assert(!cleanup_owned_clocks(&c));unsigned total_checks=checks;
  assert(raw_divider==initial&&active_divider==initial&&cleanup_phase==CLEANUP_COMPLETE);
  assert(commits==(initial!=2)&&divider_restore_attempts==(initial!=2));
  assert(!hardware_refs&&!enabled_references&&disables==3&&releases==1);
  for(unsigned fail=1;fail<=total_checks;fail++){
   reset(&c,initial,3);fail_check=fail;
   assert(cleanup_owned_clocks(&c)==-EBUSY&&!releases&&cleanup_phase!=CLEANUP_COMPLETE);
   assert(enabled_references==hardware_refs&&disables<=3);
  }
  for(unsigned refs=0;refs<=3;refs++){
   reset(&c,initial,refs);assert(!cleanup_owned_clocks(&c));
   assert(raw_divider==initial&&disables==refs&&releases==1);
  }
 }
 reset(&c,1,3);commit_error=-EIO;
 assert(cleanup_owned_clocks(&c)==-EIO&&!releases&&!disables&&hardware_refs==3);
 for(unsigned initial=0;initial<8;initial++){
  reset(&c,initial,0);assert((admit(&c)==0)==(initial==1||initial==2));
 }
 reset(&c,2,0);c.initial.fclk=2;assert(admit(&c)==-EBUSY);
 reset(&c,2,0);c.initial.iclk=1;assert(admit(&c)==-EBUSY);
 reset(&c,2,0);c.initial.control=0;assert(admit(&c)==-EBUSY);
 reset(&c,2,0);c.initial.power=0x100000;assert(admit(&c)==-EBUSY);
 reset(&c,2,0);c.initial.power=2;assert(admit(&c)==-EBUSY);
 puts("clock lifecycle: initial1/2 admitted only idle; exact original divider restored; initial2 uses no commit; every cleanup readback failure retains ownership; partial enables and commit failure checked");
}
