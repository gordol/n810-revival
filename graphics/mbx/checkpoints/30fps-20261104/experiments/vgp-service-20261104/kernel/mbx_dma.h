/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef N810_MBX_DMA_H
#define N810_MBX_DMA_H
#include <linux/device.h>
#include <linux/dma-mapping.h>
#define MBX_FRAME_PAGES 128U
#define MBX_FRAME_VA 0x100000U
#define MBX_TILE_BYTES 16384U
#define MBX_PARAMETER_BYTES 524288U
#define MBX_PARAMETER_VA 0x10000U
#define MBX_TILE_VA 0xa0000U
#define MBX_TA_VA 0xc0000U
_Static_assert(MBX_PARAMETER_VA+MBX_PARAMETER_BYTES<=MBX_TILE_VA,"parameter and tile ranges overlap");
_Static_assert(MBX_TILE_VA+MBX_TILE_BYTES<=MBX_TA_VA,"tile and TA ranges overlap");

enum mbx_dma_stage {
    MBX_DMA_EMPTY,
    MBX_DMA_ALLOCATED,
    MBX_DMA_TABLES_ATTACHED,
    MBX_DMA_SUBMITTED,
    MBX_DMA_QUIESCED,
};

struct mbx_dma_memory {
    struct device *device;
    void *tables, *guard, *target, *parameters, *tiles, *ta;
    dma_addr_t tables_dma, guard_dma, target_dma, parameters_dma, tiles_dma, ta_dma;
    void *frame_pages[MBX_FRAME_PAGES],*frame_readback;
    dma_addr_t frame_dma[MBX_FRAME_PAGES];
    unsigned frame_page_count,frame_mapped_pages;
    void *frame_block;
    dma_addr_t frame_block_dma;
    unsigned frame_block_bytes;
    bool frame_streaming,frame_device_owned;
    enum mbx_dma_stage stage;
};

/* This component is not a loaded driver. The owner establishes the device DMA
 * configuration, engine ownership and readiness. State marks must precede the
 * first table/command write. Failure to prove quiescence retains allocations. */
int mbx_dma_allocate(struct device *device, struct mbx_dma_memory *memory);
int mbx_dma_frame_for_device(struct mbx_dma_memory *);
void mbx_dma_frame_for_cpu(struct mbx_dma_memory *);
int mbx_dma_attach(struct mbx_dma_memory *memory);
int mbx_dma_submit(struct mbx_dma_memory *memory);
int mbx_dma_quiesce(struct mbx_dma_memory *memory, u32 control, u32 observed_events, u32 expected_events);
int mbx_dma_quiesce_reset(struct mbx_dma_memory *,u32 reset_complete,u32 mmu_control,u32 tables_cleared);
int mbx_dma_verify_fill8(struct mbx_dma_memory *memory, u32 expected_pixel);
int mbx_dma_verify_bounds(struct mbx_dma_memory *memory);
int mbx_dma_release(struct mbx_dma_memory *memory);

#endif
