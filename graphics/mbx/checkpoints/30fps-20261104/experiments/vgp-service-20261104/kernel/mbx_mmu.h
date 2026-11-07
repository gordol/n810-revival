/* SPDX-License-Identifier: MIT */
#ifndef N810_MBX_MMU_H
#define N810_MBX_MMU_H

/* The owner must establish accessible hardware, exclusive engine ownership and
 * DMA memory lifetime. This helper does not acquire or release any resource.
 * A timeout never authorizes freeing memory referenced by the GPU. */
typedef unsigned int mbx_word;
_Static_assert(sizeof(mbx_word) == 4, "MBX words must be 32 bits");

struct mbx_mmu_io {
    void *context;
    mbx_word (*read)(void *context, unsigned int core_offset);
    void (*write)(void *context, unsigned int core_offset, mbx_word value);
    void (*pause)(void *context);
    unsigned int maximum_samples;
};

enum mbx_mmu_result {
    MBX_MMU_OK = 0,
    MBX_MMU_BUSY = -16,
    MBX_MMU_INVALID = -22,
    MBX_MMU_TIMEOUT = -110,
    MBX_MMU_IO_INVALID = -5,
};

int mbx_mmu_enable(const struct mbx_mmu_io *io, const mbx_word table_addresses[8]);
int mbx_mmu_disable(const struct mbx_mmu_io *io);
int mbx_mmu_reload(const struct mbx_mmu_io *io, mbx_word virtual_page, mbx_word device_page);

#endif
