/* SPDX-License-Identifier: GPL-2.0-only */
#include <linux/errno.h>
#include <linux/string.h>
#include <linux/vmalloc.h>
#include <linux/mm.h>
#include "mbx_dma.h"
#include "mbx_parameter_data.h"
#include "mbx_parameter_data.c"

#define TABLE_BYTES (8U * 4096U)
#define PAGE_BYTES 4096U
#define CONTROL_ACTIVE 0x1010101U
#include "mbx_engine.h"
#define EVENTS_ERROR (0x20U | 0x80U | 0x200U)

static bool valid_address(dma_addr_t address, unsigned int bytes)
{
    return address && !(address & 4095U) && (u64)address <= 0xffffffffULL &&
           (u64)address + bytes <= 0x100000000ULL;
}

static bool overlaps(dma_addr_t a, unsigned int length_a,
                     dma_addr_t b, unsigned int length_b)
{
    return (u64)a < (u64)b + length_b && (u64)b < (u64)a + length_a;
}

/* Streaming targets are mapped only while GPU writes are allowed. Mapping
 * flushes CPU cache ownership; unmapping after completion invalidates for CPU/X.
 * Never expose a changed DMA bus address through the already-attached tables. */
int mbx_dma_frame_for_device(struct mbx_dma_memory *memory)
{
    dma_addr_t address;
    if(!memory->frame_streaming||memory->frame_device_owned)return 0;
    if(!memory->frame_block){
        unsigned i;int error=0;
        for(i=0;i<memory->frame_page_count;++i){
            address=dma_map_page_attrs(memory->device,virt_to_page(memory->frame_pages[i]),0,PAGE_BYTES,DMA_BIDIRECTIONAL,0);
            if(dma_mapping_error(memory->device,address)){error=-ENOMEM;break;}
            if(address!=memory->frame_dma[i]){
                dma_unmap_page_attrs(memory->device,address,PAGE_BYTES,DMA_BIDIRECTIONAL,0);error=-ERANGE;break;
            }
            ++memory->frame_mapped_pages;memory->frame_device_owned=true;
        }
        if(error)mbx_dma_frame_for_cpu(memory);
        return error;
    }
    address=dma_map_page_attrs(memory->device,virt_to_page(memory->frame_block),0,
                              memory->frame_block_bytes,DMA_BIDIRECTIONAL,0);
    if(dma_mapping_error(memory->device,address))return -ENOMEM;
    if(address!=memory->frame_block_dma){
        dma_unmap_page_attrs(memory->device,address,memory->frame_block_bytes,DMA_BIDIRECTIONAL,0);
        return -ERANGE;
    }
    memory->frame_device_owned=true;return 0;
}
void mbx_dma_frame_for_cpu(struct mbx_dma_memory *memory)
{
    if(memory->frame_streaming&&memory->frame_device_owned){
        if(memory->frame_block)dma_unmap_page_attrs(memory->device,memory->frame_block_dma,
                             memory->frame_block_bytes,DMA_BIDIRECTIONAL,0);
        else while(memory->frame_mapped_pages){
            unsigned i=--memory->frame_mapped_pages;
            dma_unmap_page_attrs(memory->device,memory->frame_dma[i],PAGE_BYTES,DMA_BIDIRECTIONAL,0);
        }
        memory->frame_device_owned=false;
    }
}
int mbx_dma_release(struct mbx_dma_memory *memory)
{
    unsigned i;
    if (!memory)
        return -EINVAL;
    if (memory->stage == MBX_DMA_TABLES_ATTACHED || memory->stage == MBX_DMA_SUBMITTED)
        return -EBUSY;
    if (memory->stage != MBX_DMA_EMPTY && memory->stage != MBX_DMA_ALLOCATED &&
        memory->stage != MBX_DMA_QUIESCED)
        return -EINVAL;
    mbx_dma_frame_for_cpu(memory);
    if(memory->frame_block){
        if(memory->frame_streaming){
            mbx_dma_frame_for_cpu(memory);
            free_pages_exact(memory->frame_block,memory->frame_block_bytes);
        }else dma_free_coherent(memory->device,memory->frame_block_bytes,
                                memory->frame_block,memory->frame_block_dma);
    }
    else if(memory->frame_streaming){
        for(i=0;i<memory->frame_page_count;i+=4)free_pages_exact(memory->frame_pages[i],4*PAGE_BYTES);
    }else for(i=0;i<memory->frame_page_count;++i)
        dma_free_coherent(memory->device,PAGE_BYTES,memory->frame_pages[i],memory->frame_dma[i]);

    if (memory->ta)
        dma_free_coherent(memory->device,36864,memory->ta,memory->ta_dma);
    if (memory->parameters)
        dma_free_coherent(memory->device, MBX_PARAMETER_BYTES, memory->parameters, memory->parameters_dma);
    if (memory->tiles)
        dma_free_coherent(memory->device, MBX_TILE_BYTES, memory->tiles, memory->tiles_dma);
    if (memory->target)
        dma_free_coherent(memory->device, PAGE_BYTES, memory->target, memory->target_dma);
    if (memory->guard)
        dma_free_coherent(memory->device, PAGE_BYTES, memory->guard, memory->guard_dma);
    if (memory->tables)
        dma_free_coherent(memory->device, TABLE_BYTES, memory->tables, memory->tables_dma);
    if (memory->device)
        put_device(memory->device);
    memset(memory, 0, sizeof(*memory));
    return 0;
}

int mbx_dma_allocate(struct device *device, struct mbx_dma_memory *memory)
{
    __le32 *tables;
    unsigned int i;
    int error;
    if (!device || !memory)
        return -EINVAL;
    if ((probe_mode==1||probe_mode==3) && (!gpu_frame_capacity_bytes ||
        gpu_frame_capacity_bytes>MBX_FRAME_PAGES*PAGE_BYTES))
        return -EINVAL;
    if (memory->stage != MBX_DMA_EMPTY || memory->device || memory->tables ||
        memory->guard || memory->target || memory->parameters || memory->tiles || memory->ta)
        return -EBUSY;
    error = dma_set_mask_and_coherent(device, DMA_BIT_MASK(32));
    if (error)
        return error;
    memory->device = get_device(device);
    memory->stage = MBX_DMA_ALLOCATED;
    memory->tables = dma_alloc_coherent(device, TABLE_BYTES, &memory->tables_dma, GFP_KERNEL);
    if (!memory->tables)
        goto no_memory;
    memory->guard = dma_alloc_coherent(device, PAGE_BYTES, &memory->guard_dma, GFP_KERNEL);
    if (!memory->guard)
        goto no_memory;
    memory->target = dma_alloc_coherent(device, PAGE_BYTES, &memory->target_dma, GFP_KERNEL);
    if (!memory->target)
        goto no_memory;
    memory->parameters=dma_alloc_coherent(device,MBX_PARAMETER_BYTES,&memory->parameters_dma,GFP_KERNEL);
    memory->tiles=dma_alloc_coherent(device,MBX_TILE_BYTES,&memory->tiles_dma,GFP_KERNEL);
    memory->ta=dma_alloc_coherent(device,36864,&memory->ta_dma,GFP_KERNEL);
    if(!memory->parameters || !memory->tiles || !memory->ta)goto no_memory;
    if(!valid_address(memory->ta_dma,36864)){error=-ERANGE;goto fail;}
    if(!valid_address(memory->parameters_dma,MBX_PARAMETER_BYTES)||!valid_address(memory->tiles_dma,MBX_TILE_BYTES)){error=-ERANGE;goto fail;}
    if (!valid_address(memory->tables_dma, TABLE_BYTES) ||
        !valid_address(memory->guard_dma, PAGE_BYTES) ||
        !valid_address(memory->target_dma, PAGE_BYTES) ||
        overlaps(memory->tables_dma, TABLE_BYTES, memory->guard_dma, PAGE_BYTES) ||
        overlaps(memory->tables_dma, TABLE_BYTES, memory->target_dma, PAGE_BYTES) ||
        overlaps(memory->guard_dma, PAGE_BYTES, memory->target_dma, PAGE_BYTES)) {
        error = -ERANGE;
        goto fail;
    }
    {
        dma_addr_t addresses[6]={memory->tables_dma,memory->guard_dma,memory->target_dma,memory->parameters_dma,memory->tiles_dma,memory->ta_dma};
        unsigned int lengths[6]={TABLE_BYTES,PAGE_BYTES,PAGE_BYTES,MBX_PARAMETER_BYTES,MBX_TILE_BYTES,36864};
        unsigned int a,b;
        for(a=0;a<6;++a)for(b=a+1;b<6;++b)
            if(overlaps(addresses[a],lengths[a],addresses[b],lengths[b])){error=-ERANGE;goto fail;}
        /* Reject every owned DMA object if it touches the physical display
         * allocation reported by FBIOGET_FSCREENINFO before insertion. This
         * check precedes table attachment and every GPU DMA command. */
        for(a=0;a<6;++a)
            if(overlaps(addresses[a],lengths[a],display_base,display_bytes)){
                error=-ERANGE;goto fail;
            }
        if((probe_mode==1||probe_mode==3)){
            memory->frame_streaming=gpu_frame_streaming;
            memory->frame_block_bytes=PAGE_ALIGN(gpu_frame_capacity_bytes);
            if(gpu_frame_contiguous){
                memory->frame_block_bytes=PAGE_ALIGN(gpu_frame_capacity_bytes);
                memory->frame_streaming=gpu_frame_streaming;
                if(memory->frame_streaming){
                    memory->frame_block=alloc_pages_exact(memory->frame_block_bytes,GFP_KERNEL);
                    /* Fragmented systems can still provide individual pages.
                     * The GPU MMU and read-only X mapping support that layout. */
                    if(memory->frame_block){
                    memset(memory->frame_block,0x3c,memory->frame_block_bytes);
                    memory->frame_block_dma=dma_map_page_attrs(device,virt_to_page(memory->frame_block),0,
                        memory->frame_block_bytes,DMA_BIDIRECTIONAL,0);
                    if(dma_mapping_error(device,memory->frame_block_dma))goto no_memory;
                    memory->frame_device_owned=true;
                    }
                }else{
                    memory->frame_block=dma_alloc_coherent(device,memory->frame_block_bytes,
                                                           &memory->frame_block_dma,GFP_KERNEL);
                    if(!memory->frame_block)goto no_memory;
                }
                if(memory->frame_block&&!valid_address(memory->frame_block_dma,memory->frame_block_bytes)){
                    error=-ERANGE;goto fail;
                }
            }
            /* ARM shared mappings are colour-aligned to SHMLBA=16KiB.
             * Preserve that colour in each kernel alias without requiring
             * one large contiguous allocation. */
            void *chunk=NULL;
            for(i=0;i<DIV_ROUND_UP(gpu_frame_capacity_bytes,PAGE_BYTES);++i){
                void *page;
                if(memory->frame_block){
                    page=(u8 *)memory->frame_block+i*PAGE_BYTES;
                    memory->frame_dma[i]=memory->frame_block_dma+i*PAGE_BYTES;
                }else if(memory->frame_streaming){
                    if(!(i%4)){
                        chunk=alloc_pages_exact(4*PAGE_BYTES,GFP_KERNEL);
                        if(!chunk)goto no_memory;
                        memset(chunk,0x3c,4*PAGE_BYTES);
                    }
                    page=(u8 *)chunk+(i%4)*PAGE_BYTES;
                    memory->frame_pages[i]=page;memory->frame_page_count=i+1;
                    memory->frame_dma[i]=dma_map_page_attrs(device,virt_to_page(page),0,PAGE_BYTES,DMA_BIDIRECTIONAL,0);
                    if(dma_mapping_error(device,memory->frame_dma[i]))goto no_memory;
                    ++memory->frame_mapped_pages;memory->frame_device_owned=true;
                }else page=dma_alloc_coherent(device,PAGE_BYTES,&memory->frame_dma[i],GFP_KERNEL);
                if(!page)goto no_memory;
                memory->frame_pages[i]=page;memory->frame_page_count=i+1;
                if(!valid_address(memory->frame_dma[i],PAGE_BYTES)||
                   overlaps(memory->frame_dma[i],PAGE_BYTES,display_base,display_bytes)){error=-ERANGE;goto fail;}
                for(a=0;a<6;++a)if(overlaps(memory->frame_dma[i],PAGE_BYTES,addresses[a],lengths[a])){error=-ERANGE;goto fail;}
                for(a=0;a<i;++a)if(memory->frame_dma[a]==memory->frame_dma[i]){error=-ERANGE;goto fail;}
                if(!memory->frame_streaming)memset(page,0x3c,PAGE_BYTES);
            }
        }
    }
    memset(memory->guard, 0xa5, PAGE_BYTES);
    memset(memory->target, 0x3c, PAGE_BYTES);
    tables = memory->tables;
    for (i = 0; i < TABLE_BYTES / 4; ++i)
        tables[i] = cpu_to_le32((u32)memory->guard_dma);
    /* GPU virtual page 0x1000 is the only non-guard data mapping. */
    tables[1] = cpu_to_le32((u32)memory->target_dma);
    memset(memory->parameters,0,MBX_PARAMETER_BYTES);memset(memory->tiles,0,MBX_TILE_BYTES);
    mbx_background32(memory->parameters,MBX_PARAMETER_BYTES/4);
    /* Immutable black background bitmap lives in the second half of the
     * tile page, outside the128-byte padded region list. */
    ((__le32 *)memory->parameters)[1]=cpu_to_le32(0xa8804000U);
    ((__le32 *)memory->parameters)[2]=cpu_to_le32(0x0e080000U|((MBX_TILE_VA+0x3000U)>>7));
    mbx_tile_headers(memory->tiles,MBX_TILE_BYTES/4,25,25,4,4);
    ((__le32 *)memory->parameters)[7]=cpu_to_le32(0x44600000);
    ((__le32 *)memory->parameters)[10]=cpu_to_le32(0x44600000);
    ((__le32 *)memory->parameters)[21]=cpu_to_le32(0x3ee00000);
    ((__le32 *)memory->parameters)[25]=cpu_to_le32(0x3ee00000);
    ((__le32 *)memory->tiles)[1566]|=cpu_to_le32(0x80000000U);
    memset(memory->ta,0,36864);
    /* Separate allocator seed context; surface stateB stays zero.
     * Original reserved DPM pages17..26; parameter pages27..31 are distinct. */
    ((__le32 *)((u8 *)memory->ta+28672))[0]=cpu_to_le32(17U|(10U<<13));
    ((__le32 *)((u8 *)memory->ta+28672))[1]=cpu_to_le32(26U);
    memset((u8 *)memory->ta+32768,0x5a,4096);
    for(i=0;i<MBX_PARAMETER_BYTES/PAGE_BYTES;++i)tables[MBX_PARAMETER_VA/PAGE_BYTES+i]=cpu_to_le32((u32)memory->parameters_dma+4096*i);
    for(i=0;i<MBX_TILE_BYTES/PAGE_BYTES;++i)tables[MBX_TILE_VA/PAGE_BYTES+i]=cpu_to_le32((u32)memory->tiles_dma+PAGE_BYTES*i);
    for(i=0;i<memory->frame_page_count;++i)tables[MBX_FRAME_VA/PAGE_BYTES+i]=cpu_to_le32((u32)memory->frame_dma[i]);
    for(i=0;i<4;++i)tables[MBX_TA_VA/PAGE_BYTES+i]=cpu_to_le32((u32)memory->ta_dma+4096*i);
    tables[208]=cpu_to_le32((u32)memory->ta_dma+16384);
    tables[210]=cpu_to_le32((u32)memory->ta_dma+20480);
    tables[212]=cpu_to_le32((u32)memory->ta_dma+24576);
    tables[216]=cpu_to_le32((u32)memory->ta_dma+28672);
    dma_wmb();
    return 0;

no_memory:
    error = -ENOMEM;
fail:
    mbx_dma_release(memory);
    return error;
}

int mbx_dma_attach(struct mbx_dma_memory *memory)
{
    if (!memory || memory->stage != MBX_DMA_ALLOCATED)
        return -EINVAL;
    /* Caller invokes this BEFORE installing any table register. */
    memory->stage = MBX_DMA_TABLES_ATTACHED;
    dma_wmb();
    return 0;
}

int mbx_dma_submit(struct mbx_dma_memory *memory)
{
    if (!memory || memory->stage != MBX_DMA_TABLES_ATTACHED)
        return -EINVAL;
    /* Caller invokes this BEFORE the first command word. */
    memory->stage = MBX_DMA_SUBMITTED;
    dma_wmb();
    return 0;
}

int mbx_dma_quiesce(struct mbx_dma_memory *memory, u32 control, u32 events,u32 expected_events)
{
    if (!memory || (memory->stage != MBX_DMA_TABLES_ATTACHED &&
                    memory->stage != MBX_DMA_SUBMITTED))
        return -EINVAL;
    if(expected_events!=MBX_RENDER_COMPLETE && expected_events!=MBX_TA_COMPLETE &&
       expected_events!=MBX_ALLOC_COMPLETE && expected_events!=MBX_CONTEXT_COMPLETE)return -EINVAL;
    if (control == 0xffffffffU || events == 0xffffffffU)
        return -EIO;
    if (control & CONTROL_ACTIVE)
        return -EBUSY;
    if (memory->stage == MBX_DMA_SUBMITTED) {
        if (events & EVENTS_ERROR)
            return -EIO;
        if (!(events & expected_events))
            return -EBUSY;
    }
    /* These values must be actual ordered observations made by the owner after
     * the bounded completion wait and successful MMU disable handshake. Reset
     * or clock disable alone is never supplied as completion evidence. */
    dma_rmb();
    memory->stage = MBX_DMA_QUIESCED;
    return 0;
}

/* Recovery requires a fresh whole-GFX reset AND observed cleared MMU/table
 * state, the combination verified on this Nokia. No old completion is used. */
int mbx_dma_quiesce_reset(struct mbx_dma_memory *memory,u32 reset_complete,u32 control,u32 tables_cleared)
{
    if(!memory || (memory->stage!=MBX_DMA_SUBMITTED && memory->stage!=MBX_DMA_TABLES_ATTACHED))return -EINVAL;
    if(reset_complete!=1 || tables_cleared!=1 || control==~0U || (control&CONTROL_ACTIVE))return -EBUSY;
    dma_rmb();memory->stage=MBX_DMA_QUIESCED;return 0;
}

int mbx_dma_verify_fill8(struct mbx_dma_memory *memory, u32 expected_pixel)
{
    (void)expected_pixel;
    if(!memory || memory->stage!=MBX_DMA_QUIESCED)return -EBUSY;
    return mbx_dma_verify_bounds(memory);
}
/* Check every word, using four independent loads per loop so uncached DMA
 * reads do not pay the mapping-selection branch chain for each PTE. */
static bool mbx_words_equal(const __le32 *p,unsigned count,u32 expected,u32 step)
{
    while(count>=4){
        u32 mismatch=(le32_to_cpu(p[0])^expected)|
            (le32_to_cpu(p[1])^(expected+step))|
            (le32_to_cpu(p[2])^(expected+2*step))|
            (le32_to_cpu(p[3])^(expected+3*step));
        if(mismatch)return false;
        p+=4;count-=4;expected+=4*step;
    }
    while(count--){if(le32_to_cpu(*p++)!=expected)return false;expected+=step;}
    return true;
}
int mbx_dma_verify_bounds(struct mbx_dma_memory *memory)
{
    const __le32 *tables;
    unsigned i,cursor=0;
    struct {unsigned first,count;dma_addr_t address;unsigned step;} ranges[8];
    if (!memory || (memory->stage != MBX_DMA_QUIESCED && memory->stage != MBX_DMA_SUBMITTED))
        return -EBUSY;
    dma_rmb();tables=memory->tables;
    if(!mbx_words_equal((const __le32 *)memory->target+2048/4,2048/4,0x3c3c3c3c,0))return -EILSEQ;
    if(!mbx_words_equal(memory->guard,PAGE_BYTES/4,0xa5a5a5a5,0))return -EOVERFLOW;
    if(!mbx_words_equal((const __le32 *)((const u8 *)memory->ta+32768),4096/4,0x5a5a5a5a,0))return -EOVERFLOW;
    if(memory->frame_page_count!=79)return -EILSEQ;
    if(!mbx_words_equal((const __le32 *)memory->frame_pages[78]+512/4,(4096-512)/4,0x3c3c3c3c,0))return -EOVERFLOW;
    ranges[0]=(typeof(ranges[0])){1,1,memory->target_dma,0};
    ranges[1]=(typeof(ranges[0])){MBX_PARAMETER_VA/PAGE_BYTES,MBX_PARAMETER_BYTES/PAGE_BYTES,memory->parameters_dma,PAGE_BYTES};
    ranges[2]=(typeof(ranges[0])){MBX_TILE_VA/PAGE_BYTES,MBX_TILE_BYTES/PAGE_BYTES,memory->tiles_dma,PAGE_BYTES};
    ranges[3]=(typeof(ranges[0])){MBX_TA_VA/PAGE_BYTES,4,memory->ta_dma,PAGE_BYTES};
    ranges[4]=(typeof(ranges[0])){208,1,memory->ta_dma+16384,0};
    ranges[5]=(typeof(ranges[0])){210,1,memory->ta_dma+20480,0};
    ranges[6]=(typeof(ranges[0])){212,1,memory->ta_dma+24576,0};
    ranges[7]=(typeof(ranges[0])){216,1,memory->ta_dma+28672,0};
    for(i=0;i<8;++i){
        if(!mbx_words_equal(tables+cursor,ranges[i].first-cursor,memory->guard_dma,0)||
           !mbx_words_equal(tables+ranges[i].first,ranges[i].count,ranges[i].address,ranges[i].step))return -EOVERFLOW;
        cursor=ranges[i].first+ranges[i].count;
    }
    if(!mbx_words_equal(tables+cursor,MBX_FRAME_VA/PAGE_BYTES-cursor,memory->guard_dma,0))return -EOVERFLOW;
    cursor=MBX_FRAME_VA/PAGE_BYTES;
    for(i=0;i<memory->frame_page_count;++i)
        if(le32_to_cpu(tables[cursor++])!=memory->frame_dma[i])return -EOVERFLOW;
    if(!mbx_words_equal(tables+cursor,TABLE_BYTES/4-cursor,memory->guard_dma,0))return -EOVERFLOW;
    return 0;
}
