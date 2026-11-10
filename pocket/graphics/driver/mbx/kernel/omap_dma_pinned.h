/* SPDX-License-Identifier: GPL-2.0-only
 * Descriptor ABI pinned to Linux 6bd43ee8d27b207c958808368251d55ec0475f9e:
 * drivers/dma/virt-dma.h and drivers/dma/ti/omap-dma.c. This only changes our
 * newly prepared, not-yet-submitted MEM_TO_MEM descriptor. No live code patch.
 * The provider's interleaved FRAME interrupt completes at the first row;
 * BLOCK is the completion event for numf rows. Keep all error interrupts.
 */
struct mbx_omap_vdesc {struct dma_async_tx_descriptor tx;struct dmaengine_result tx_result;struct list_head node;};
struct mbx_omap_sg {dma_addr_t addr;u32 en,fn;s32 fi;s16 ei;void *t2_desc;dma_addr_t t2_desc_paddr;};
struct mbx_omap_desc {
 struct mbx_omap_vdesc vd;bool using_ll;enum dma_transfer_direction dir;dma_addr_t dev_addr;bool polled;
 s32 fi;s16 ei;u8 es;u32 ccr;u16 clnk_ctrl,cicr;u32 csdp;unsigned sglen;struct mbx_omap_sg sg[];
};
static int mbx_omap_block_completion(struct dma_async_tx_descriptor *tx,struct dma_chan *chan,
 dma_addr_t src,dma_addr_t dst,unsigned width,unsigned rows,unsigned src_stride,unsigned dst_stride){
 struct mbx_omap_desc *d=(void *)tx;
 const unsigned errors=BIT(1)|BIT(8)|BIT(11);
 if(tx->chan!=chan||d->using_ll||d->polled||d->dir!=DMA_MEM_TO_MEM||d->sglen!=1||d->es>2||
    d->dev_addr!=src||d->sg[0].addr!=dst||d->sg[0].fn!=rows||d->sg[0].en!=(width>>d->es)||
    d->fi!=(src_stride==width?0:src_stride-width+1)||d->sg[0].fi!=(dst_stride==width?0:dst_stride-width+1)||
    d->sg[0].t2_desc||d->sg[0].t2_desc_paddr||
    (d->cicr!=(errors|BIT(3))&&d->cicr!=(errors|BIT(5))))return -EINVAL;
 d->cicr=errors|BIT(5);return 0;
}
