"""Compile the actual patched crop helpers against hardware/lock test doubles.
No device access. Supply the clean maintained Linux source tree.
"""
from pathlib import Path
import argparse,subprocess,tempfile,shutil
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--kernel-tree',type=Path,required=True)
a=parser.parse_args();patch=Path(__file__).with_name('n810-partial-rfbi.patch')
with tempfile.TemporaryDirectory() as directory:
 root=Path(directory)
 for line in patch.read_text().splitlines():
  if line.startswith('--- a/'):
   name=line[6:];target=root/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(a.kernel_tree/name,target)
 subprocess.run(['patch','--batch','-p1','-i',str(patch.resolve())],cwd=root,check=True,stdout=subprocess.DEVNULL)
 source=(root/'drivers/video/fbdev/omap2/omapfb/dss/apply.c').read_text()
 helpers=source[source.index('static int dss_update_region_check_locked'):source.index('static void dss_mgr_start_update_compat')]
pre=r'''
#include <stdint.h>
#include <stdbool.h>
#include <errno.h>
#include <assert.h>
#include <string.h>
#include <stdio.h>
typedef uint16_t u16;typedef uint32_t u32;typedef uint64_t u64;
#define U32_MAX UINT32_MAX
#define OMAP_DSS_GFX 0
#define OMAP_DSS_COLOR_RGB16 1
#define OMAP_DSS_ROT_DMA 0
struct omap_video_timings {u16 x_res,y_res;};
struct omap_overlay_info {uint32_t paddr;u16 screen_width,width,height;int color_mode,rotation,mirror,rotation_type,pos_x,pos_y,out_width,out_height;};
struct ovl_priv_data {bool enabled,info_dirty;struct omap_overlay_info info;};
struct omap_overlay {int id;struct ovl_priv_data p;struct omap_overlay *next;};
struct mgr_priv_data {bool update_region_active,updating;struct omap_video_timings timings;int lcd_config;};
struct omap_overlay_manager {int id,manual;struct mgr_priv_data p;struct omap_overlay *overlays;};
static struct {int irq_enabled;} dss_data;
static int data_lock,locks,starts,fail_setup,fail_settings;
static struct omap_overlay_info hw;
static struct omap_video_timings timing;
#define get_mgr_priv(m) (&(m)->p)
#define get_ovl_priv(o) (&(o)->p)
#define mgr_manual_update(m) ((m)->manual)
#define list_for_each_entry(o,head,member) for(o=*(head);o;o=o->next)
#define spin_lock_irqsave(lock,flags) do{(void)(lock);flags=0;assert(!locks);locks++;}while(0)
#define spin_unlock_irqrestore(lock,flags) do{(void)(lock);(void)(flags);assert(locks==1);locks--;}while(0)
static void dss_mgr_write_regs(struct omap_overlay_manager *m){if(m->overlays)hw=m->overlays->p.info;}
static void dispc_mgr_set_timings(int id,const struct omap_video_timings *t){(void)id;timing=*t;}
static void dss_mgr_write_regs_extra(struct omap_overlay_manager *m){(void)m;}
static int dss_check_settings(struct omap_overlay_manager *m){(void)m;return fail_settings;}
static int dss_ovl_use_replication(int c,int f){(void)c;(void)f;return 0;}
static int dispc_ovl_setup(int id,struct omap_overlay_info *i,int r,struct omap_video_timings *t,bool b){(void)id;(void)r;(void)t;(void)b;hw=*i;return fail_setup;}
static int need_isr(void){return 0;}
static void dss_register_vsync_isr(void){}
static void dispc_mgr_enable_sync(int id){(void)id;starts++;}
'''
main=r'''
int main(void){
 struct omap_overlay o={.id=0,.p={.enabled=true,.info={.paddr=0x81000000,.screen_width=800,.width=800,.height=480,.color_mode=1}}};
 struct omap_overlay_manager m={.manual=1,.overlays=&o,.p={.timings={800,480}}};
 struct omap_overlay_info original=o.p.info;
 assert(!dss_mgr_check_update_region_compat(&m,16,32,120,80));
 assert(!dss_mgr_start_update_region_compat(&m,16,32,120,80));
 assert(starts==1&&hw.paddr==original.paddr+(32*800+16)*2&&hw.screen_width==800&&hw.width==120&&hw.height==80);
 assert(timing.x_res==120&&timing.y_res==80&&!memcmp(&o.p.info,&original,sizeof(original)));
 assert(dss_mgr_start_update_region_compat(&m,0,0,800,480)==-EBUSY);
 m.p.updating=false;dss_restore_update_region_locked(&m);
 assert(!memcmp(&hw,&original,sizeof(original))&&timing.x_res==800&&timing.y_res==480&&!m.p.update_region_active);
 assert(dss_mgr_check_update_region_compat(&m,799,0,2,1)==-EINVAL);
 assert(dss_mgr_check_update_region_compat(&m,0,0,0,1)==-EINVAL);
 assert(dss_mgr_check_update_region_compat(&m,1,0,8,8)==-EOPNOTSUPP);
 o.p.info.rotation=1;assert(dss_mgr_check_update_region_compat(&m,0,0,8,8)==-EOPNOTSUPP);o.p.info=original;
 o.p.info.out_width=400;assert(dss_mgr_check_update_region_compat(&m,0,0,8,8)==-EOPNOTSUPP);o.p.info=original;
 o.p.info.paddr=UINT32_MAX-100;assert(dss_mgr_check_update_region_compat(&m,0,0,8,8)==-EOPNOTSUPP);o.p.info=original;
 struct omap_overlay other=o;o.next=&other;assert(dss_mgr_check_update_region_compat(&m,0,0,8,8)==-EOPNOTSUPP);o.next=NULL;
 fail_setup=-EINVAL;assert(dss_mgr_start_update_region_compat(&m,0,0,8,8)==-EINVAL);assert(starts==1&&!m.p.updating&&!m.p.update_region_active&&!memcmp(&hw,&original,sizeof(hw)));fail_setup=0;
 fail_settings=-EINVAL;assert(dss_mgr_start_update_region_compat(&m,0,0,8,8)==-EINVAL);assert(starts==1);fail_settings=0;
 assert(!dss_mgr_start_update_region_compat(&m,0,0,800,480));assert(starts==2&&!m.p.update_region_active);
 puts("PASS actual region helper: crop address/stride/dimensions, full-state restoration, busy/bounds/alignment/scaling/rotation/overlay/overflow rejection, no start on failure");
}
'''
with tempfile.TemporaryDirectory() as directory:
 p=Path(directory);(p/'test.c').write_text(pre+helpers+main)
 subprocess.run(['cc','-std=c99','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
