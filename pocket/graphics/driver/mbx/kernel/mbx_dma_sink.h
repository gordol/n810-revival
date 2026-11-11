/* SPDX-License-Identifier: GPL-2.0-only
 * Pinned OMAP fbdev synchronous DMA sink. No locks survive this ioctl.
 * Platform device lock excludes remove; fb_info/region locks exclude mode,
 * plane and allocation changes. The caller still owns presentation after return.
 */
#include <linux/dmaengine.h>
#include <linux/file.h>
#include <linux/fb.h>
#include <linux/vmalloc.h>
#include <linux/completion.h>
#include <linux/omapfb.h>
#include <video/omapvrfb.h>
#include "omapfb_pinned.h"
#include "omap_dma_pinned.h"
static unsigned gpu_dma_sink_stage,gpu_dma_sink_admission;
static int gpu_dma_sink_errno;
module_param(gpu_dma_sink_stage,uint,0400);
module_param(gpu_dma_sink_admission,uint,0400);
module_param(gpu_dma_sink_errno,int,0400);
static unsigned long long gpu_dma_sink_bytes,gpu_dma_sink_jobs,gpu_dma_sink_ns,gpu_dma_sink_failures;
module_param(gpu_dma_sink_bytes,ullong,0400);
module_param(gpu_dma_sink_jobs,ullong,0400);
module_param(gpu_dma_sink_ns,ullong,0400);
module_param(gpu_dma_sink_failures,ullong,0400);
static int mbx_fb_match(struct device *dev,const void *unused){(void)unused;return !strcmp(dev_name(dev),"omapfb");}
static bool mbx_dma_filter(struct dma_chan *chan,void *unused){(void)unused;return !strcmp(dev_driver_string(chan->device->dev),"omap-dma-engine");}
static void mbx_dma_done(void *arg){complete(arg);}
static bool gpu_dma_reuse_channel;
module_param(gpu_dma_reuse_channel,bool,0400);
static struct dma_chan *gpu_dma_sink_channel;
static unsigned long long gpu_dma_channel_requests;
module_param(gpu_dma_channel_requests,ullong,0400);
/* Service mutex serializes copies and close. Every copy drains/terminates
 * its descriptors before returning, so close never releases active DMA. */
static void mbx_dma_sink_release_channel(void){
 if(gpu_dma_sink_channel){dma_release_channel(gpu_dma_sink_channel);gpu_dma_sink_channel=NULL;}
}
static bool gpu_dma_damage_mapping;
module_param(gpu_dma_damage_mapping,bool,0400);
static unsigned long long gpu_dma_mapped_pages;
module_param(gpu_dma_mapped_pages,ullong,0400);
struct mbx_dma_page { dma_addr_t address; bool mapped; };
/* Adjacent independently mapped pages can share a descriptor only when
 * their DMA addresses are contiguous in this consuming device's domain. */
static size_t mbx_dma_span(const struct mbx_dma_page *pages,unsigned count,size_t offset,size_t limit){
 size_t bytes=min_t(size_t,limit,PAGE_SIZE-offset%PAGE_SIZE);
 while(bytes<limit){
  unsigned next=(offset+bytes)/PAGE_SIZE;
  if(next>=count||pages[next].address!=pages[next-1].address+PAGE_SIZE)break;
  bytes+=min_t(size_t,limit-bytes,PAGE_SIZE);
 }
 return bytes;
}
static struct page *mbx_cpu_page(void *ptr){
 if(is_vmalloc_addr(ptr))return vmalloc_to_page(ptr);
 /* Only allocation-owned addresses reach here: alloc_pages_exact source
  * or the locked omapfb dma_alloc_attrs allocation, never user pointers. */
 return virt_to_page(ptr);
}
static int mbx_surface_dma_copy(struct file *gpu_file,const struct mbx_surface_dma_sink *q){
 struct file *fb=NULL;struct device *dev=NULL,*dma_dev=NULL;struct dma_chan *chan=NULL;
 struct omapfb2_device *fbdev;struct fb_info *info=NULL;struct omapfb2_mem_region *rg=NULL;
 struct mbx_dma_page *src=NULL,*dst=NULL;unsigned ns=0,nd=0,row,i,jobs=0,sfirst=0,slast=0,dfirst=0,dlast=0;
 bool dev_locked=false,info_locked=false,region_locked=false,queued=false;int error=-EINVAL;
 unsigned long src_attrs=gpu_memory.frame_cpu_reads_only?DMA_ATTR_SKIP_CPU_SYNC:0;
 dma_cookie_t last_cookie=0;dma_cap_mask_t mask;struct completion done;u64 started=ktime_get_ns();
 (void)gpu_file;gpu_dma_sink_stage=1;gpu_dma_sink_errno=0;
 if(!mbx_lease_dma_valid(&gpu_surface_lease,q)||
    gpu_memory.frame_device_owned||!gpu_memory.frame_streaming||gpu_frame_shared)return -EINVAL;
 gpu_dma_sink_stage=2;dma_cap_zero(mask);dma_cap_set(DMA_MEMCPY,mask);
 chan=gpu_dma_reuse_channel?gpu_dma_sink_channel:NULL;
 if(!chan){chan=dma_request_channel(mask,mbx_dma_filter,NULL);if(!chan)return -ENODEV;
  ++gpu_dma_channel_requests;if(gpu_dma_reuse_channel)gpu_dma_sink_channel=chan;
 }
 dma_dev=chan->device->dev;
 gpu_dma_sink_stage=3;fb=fget(q->fb_fd);if(!fb){error=-EBADF;goto out;}
 if(!(fb->f_mode&FMODE_WRITE)||!S_ISCHR(file_inode(fb)->i_mode)||imajor(file_inode(fb))!=FB_MAJOR){error=-EINVAL;goto out;}
 gpu_dma_sink_stage=4;dev=bus_find_device(&platform_bus_type,NULL,NULL,mbx_fb_match);if(!dev){error=-ENODEV;goto out;}
 device_lock(dev);dev_locked=true;
 gpu_dma_sink_stage=5;
 if(!dev->driver||strcmp(dev->driver->name,"omapfb")||!(fbdev=dev_get_drvdata(dev))){error=-ENODEV;goto out;}
 gpu_dma_sink_stage=6;
 gpu_dma_sink_admission=(dma_dev->dma_ops==fbdev->dev->dma_ops?1:0)|(dma_dev->dma_range_map?2:0)|(fbdev->dev->dma_range_map?4:0)|(dma_dev->archdata.dma_coherent?8:0)|(fbdev->dev->archdata.dma_coherent?16:0)|(dma_dev->dma_mask?32:0)|(!dma_dev->dma_ops?64:0)|(!fbdev->dev->dma_ops?128:0);
 /* Pinned legacy omapfb lacks of_node and retains raw NULL DMA ops;
  * ARM's get_arch_dma_ops resolves that to arm_dma_ops. The DT OMAP DMA
  * provider records that same default explicitly in arch_setup_dma_ops. */
 if(!dma_dev->dma_ops||!dma_dev->archdata.dma_ops_setup||!dma_dev->of_node||
    fbdev->dev->dma_ops||fbdev->dev->archdata.dma_ops_setup||fbdev->dev->of_node||
    dma_dev->dma_range_map||fbdev->dev->dma_range_map||
    dma_dev->archdata.dma_coherent||fbdev->dev->archdata.dma_coherent||!dma_dev->dma_mask){error=-ENODEV;goto out;}
 gpu_dma_sink_stage=7;for(i=0;i<fbdev->num_fbs;i++)if(fbdev->fbs[i]==fb->private_data){info=fbdev->fbs[i];break;}
 if(!info||info->node!=0){error=-ENODEV;goto out;}
 mutex_lock(&info->lock);info_locked=true;
 gpu_dma_sink_stage=8;
 if(FB2OFB(info)->fbdev!=fbdev||FB2OFB(info)->rotation_type!=OMAP_DSS_ROT_DMA||FB2OFB(info)->mirror||
    info->var.rotate||info->var.xoffset||info->var.yoffset||info->var.bits_per_pixel!=16||
    info->var.red.offset!=11||info->var.red.length!=5||info->var.green.offset!=5||info->var.green.length!=6||
    info->var.red.msb_right||info->var.green.msb_right||info->var.blue.msb_right||info->var.blue.offset||info->var.blue.length!=5||info->var.transp.length||
    q->canvas_width!=info->var.xres||q->canvas_height!=info->var.yres||q->stride!=info->fix.line_length||
    q->destination_x>=q->canvas_width||q->destination_y>=q->canvas_height||
    q->width>q->canvas_width-q->destination_x||q->height>q->canvas_height-q->destination_y){error=-EINVAL;goto out;}
 for(i=0;i<OMAPFB_MAX_OVL_PER_FB;i++)if(FB2OFB(info)->rotation[i]){error=-EINVAL;goto out;}
 gpu_dma_sink_stage=9;rg=FB2OFB(info)->region;down_read(&rg->lock);region_locked=true;
 if(!rg->alloc||!rg->vaddr||rg->token!=(void __force *)rg->vaddr||
    ((unsigned long)rg->vaddr&(PAGE_SIZE-1))||(rg->dma_handle&(PAGE_SIZE-1))||
    !(rg->attrs&DMA_ATTR_WRITE_COMBINE)||rg->attrs&DMA_ATTR_NO_KERNEL_MAPPING||
    (u64)q->stride*q->canvas_height>rg->size||info->screen_base!=rg->vaddr){error=-EINVAL;goto out;}
 /* Synchronize the previous RFBI read inside this bounded transaction too. */
 gpu_dma_sink_stage=10;
 {struct omap_dss_device *display=fb2display(info);
  if(!display||!display->driver||!display->driver->sync){error=-ENODEV;goto out;}
  error=display->driver->sync(display);if(error)goto out;}
 ns=DIV_ROUND_UP(q->surface.bytes,PAGE_SIZE);nd=DIV_ROUND_UP((size_t)q->stride*q->canvas_height,PAGE_SIZE);
 if(ns>256||nd>1024){error=-E2BIG;goto out;}
 src=kcalloc(ns,sizeof(*src),GFP_KERNEL);dst=kcalloc(nd,sizeof(*dst),GFP_KERNEL);
 if(!src||!dst){error=-ENOMEM;goto out;}
 slast=ns;dlast=nd;
 if(gpu_dma_damage_mapping){
  sfirst=((size_t)q->y*q->surface.stride+(size_t)q->x*2)/PAGE_SIZE;
  slast=DIV_ROUND_UP((size_t)(q->y+q->height-1)*q->surface.stride+(size_t)(q->x+q->width)*2,PAGE_SIZE);
  dfirst=((size_t)q->destination_y*q->stride+(size_t)q->destination_x*2)/PAGE_SIZE;
  dlast=DIV_ROUND_UP((size_t)(q->destination_y+q->height-1)*q->stride+(size_t)(q->destination_x+q->width)*2,PAGE_SIZE);
  if(sfirst>=slast||slast>ns||dfirst>=dlast||dlast>nd){error=-EINVAL;goto out;}
 }
 gpu_dma_sink_stage=11;for(i=sfirst;i<slast;i++){
  void *ptr=gpu_memory.frame_block?(u8 *)gpu_memory.frame_block+(q->surface.slot*gpu_memory.frame_image_pages+i)*PAGE_SIZE:
      gpu_memory.frame_pages[q->surface.slot*gpu_memory.frame_image_pages+i];
  struct page *page=mbx_cpu_page(ptr);if(!page){error=-ENXIO;goto out;}
  src[i].address=dma_map_page_attrs(dma_dev,page,0,PAGE_SIZE,DMA_TO_DEVICE,src_attrs);
  if(dma_mapping_error(dma_dev,src[i].address)){error=-EIO;goto out;}src[i].mapped=true;++gpu_dma_mapped_pages;
 }
 wmb();
 gpu_dma_sink_stage=12;for(i=dfirst;i<dlast;i++){
  struct page *page=mbx_cpu_page((u8 __force *)rg->vaddr+i*PAGE_SIZE);if(!page){error=-ENXIO;goto out;}
  /* This is allocator-owned coherent WC memory. Never perform cached-alias
   * maintenance on it. Map into this DMA device's domain without CPU sync. */
  dst[i].address=dma_map_page_attrs(dma_dev,page,0,PAGE_SIZE,DMA_FROM_DEVICE,DMA_ATTR_SKIP_CPU_SYNC);
  if(dma_mapping_error(dma_dev,dst[i].address)){error=-EIO;goto out;}dst[i].mapped=true;++gpu_dma_mapped_pages;
  /* Exact pinned OMAP devices use the same non-bouncing ARM DMA ops with
   * no range translation. Verify page discovery against allocator handle. */
  if(dst[i].address!=rg->dma_handle+(dma_addr_t)i*PAGE_SIZE||
     (u64)dst[i].address+PAGE_SIZE-1>*dma_dev->dma_mask){error=-ENXIO;goto out;}
 }
 gpu_dma_sink_stage=13;init_completion(&done);
 for(row=0;row<q->height;row++){
  size_t so=(q->y+(q->reverse_rows?q->height-1-row:row))*q->surface.stride+q->x*2;
  size_t to=(q->destination_y+row)*q->stride+q->destination_x*2,left=q->width*2;
  /* One interleaved descriptor per contiguous run of forward rows. The
   * consuming device mappings, not CPU virtual adjacency, prove contiguity. */
  if(!q->reverse_rows&&row+1<q->height){
   size_t ss=q->surface.stride,ds=q->stride;
   size_t sn=mbx_dma_span(src,ns,so,(q->height-1-row)*ss+left);
   size_t dn=mbx_dma_span(dst,nd,to,(q->height-1-row)*ds+left);
   unsigned rows=min_t(size_t,sn<left?0:1+(sn-left)/ss,dn<left?0:1+(dn-left)/ds);
   if(rows>1){
    struct dma_interleaved_template *xt=kzalloc(sizeof(*xt)+sizeof(xt->sgl[0]),GFP_KERNEL);
    struct dma_async_tx_descriptor *tx;dma_cookie_t cookie;
    if(!xt){error=-ENOMEM;goto out;}
    xt->src_start=src[so/PAGE_SIZE].address+so%PAGE_SIZE;xt->dst_start=dst[to/PAGE_SIZE].address+to%PAGE_SIZE;
    xt->dir=DMA_MEM_TO_MEM;xt->src_inc=xt->dst_inc=true;xt->src_sgl=xt->dst_sgl=true;
    xt->numf=rows;xt->frame_size=1;xt->sgl[0].size=left;xt->sgl[0].src_icg=ss-left;xt->sgl[0].dst_icg=ds-left;
    tx=dmaengine_prep_interleaved_dma(chan,xt,DMA_CTRL_ACK|DMA_PREP_INTERRUPT);kfree(xt);
    if(!tx){error=-ENOMEM;goto out;}
    if(mbx_omap_block_completion(tx,chan,src[so/PAGE_SIZE].address+so%PAGE_SIZE,dst[to/PAGE_SIZE].address+to%PAGE_SIZE,left,rows,ss,ds)){error=-EINVAL;goto out;}
    if(row+rows==q->height){tx->callback=mbx_dma_done;tx->callback_param=&done;}
    cookie=dmaengine_submit(tx);if(dma_submit_error(cookie)){error=cookie;goto out;}
    last_cookie=cookie;queued=true;++jobs;row+=rows-1;continue;
   }
  }
  while(left){
   size_t bytes=min(mbx_dma_span(src,ns,so,left),mbx_dma_span(dst,nd,to,left));
   struct dma_async_tx_descriptor *tx=dmaengine_prep_dma_memcpy(chan,dst[to/PAGE_SIZE].address+to%PAGE_SIZE,
       src[so/PAGE_SIZE].address+so%PAGE_SIZE,bytes,DMA_CTRL_ACK|DMA_PREP_INTERRUPT);
   dma_cookie_t cookie;
   if(!tx){error=-ENOMEM;goto out;}
   if(row==q->height-1&&bytes==left){tx->callback=mbx_dma_done;tx->callback_param=&done;}
   cookie=dmaengine_submit(tx);if(dma_submit_error(cookie)){error=cookie;goto out;}
   last_cookie=cookie;queued=true;++jobs;so+=bytes;to+=bytes;left-=bytes;
  }
 }
 gpu_dma_sink_stage=14;dma_async_issue_pending(chan);
 if(!wait_for_completion_timeout(&done,msecs_to_jiffies(2000))){error=-ETIMEDOUT;goto out;}
 gpu_dma_sink_stage=15;
 if(dma_async_is_tx_complete(chan,last_cookie,NULL,NULL)!=DMA_COMPLETE){error=-EIO;goto out;}
 dma_rmb();gpu_dma_sink_stage=16;error=0;gpu_dma_sink_bytes+=(u64)q->width*q->height*2;gpu_dma_sink_jobs+=jobs;
out:
 if(queued){
  /* Pinned OMAP provider terminate_all returns0; never free DMA-owned pages
   * if a future provider violates that contract. No forced recovery here. */
  if(dmaengine_terminate_sync(chan)){pr_err("MBX DMA termination failed; retaining transaction until completion\n");wait_for_completion(&done);dmaengine_synchronize(chan);}
 }
 for(i=0;dst&&i<nd;i++)if(dst[i].mapped)dma_unmap_page_attrs(dma_dev,dst[i].address,PAGE_SIZE,DMA_FROM_DEVICE,DMA_ATTR_SKIP_CPU_SYNC);
 for(i=0;src&&i<ns;i++)if(src[i].mapped)dma_unmap_page_attrs(dma_dev,src[i].address,PAGE_SIZE,DMA_TO_DEVICE,src_attrs);
 kfree(dst);kfree(src);
 if(region_locked)up_read(&rg->lock);
 if(info_locked)mutex_unlock(&info->lock);
 if(dev_locked)device_unlock(dev);
 if(dev)put_device(dev);
 if(fb)fput(fb);
 if(chan&&!gpu_dma_reuse_channel)dma_release_channel(chan);
 gpu_dma_sink_errno=error;
 if(error)++gpu_dma_sink_failures;
 gpu_dma_sink_ns+=ktime_get_ns()-started;return error;
}
