/* SPDX-License-Identifier: MIT */
#include "mbx_mmu.h"

#define MMU_CONTROL 0x1020U
#define REQUEST 1U
#define ENABLED (1U << 16)
#define RELOAD (1U << 8)
#define RELOAD_BUSY (1U << 24)

static int valid_io(const struct mbx_mmu_io *io)
{
    return io && io->read && io->write && io->pause &&
           io->maximum_samples > 0 && io->maximum_samples <= 100000;
}

static int wait_control(const struct mbx_mmu_io *io, mbx_word mask, mbx_word expected)
{
    unsigned int sample;
    for (sample = 0; sample < io->maximum_samples; ++sample) {
        mbx_word control = io->read(io->context, MMU_CONTROL);
        if (control == 0xffffffffU)
            return MBX_MMU_IO_INVALID;
        if ((control & mask) == expected)
            return MBX_MMU_OK;
        if (sample + 1 < io->maximum_samples)
            io->pause(io->context);
    }
    return MBX_MMU_TIMEOUT;
}

int mbx_mmu_enable(const struct mbx_mmu_io *io, const mbx_word tables[8])
{
    unsigned int i, j;
    mbx_word control;
    int result;
    if (!valid_io(io) || !tables)
        return MBX_MMU_INVALID;
    /* Validate every address before the first callback or register write. */
    for (i = 0; i < 8; ++i) {
        if (!tables[i] || (tables[i] & 4095U))
            return MBX_MMU_INVALID;
        for (j = 0; j < i; ++j)
            if (tables[i] == tables[j])
                return MBX_MMU_INVALID;
    }
    control = io->read(io->context, MMU_CONTROL);
    if (control == 0xffffffffU)
        return MBX_MMU_IO_INVALID;
    if (control & (REQUEST | ENABLED | RELOAD | RELOAD_BUSY))
        return MBX_MMU_BUSY;
    for (i = 0; i < 8; ++i)
        io->write(io->context, 0x1000U + 4 * i, tables[i]);
    io->write(io->context, MMU_CONTROL, control & ~REQUEST);
    result = wait_control(io, ENABLED, 0);
    if (result)
        return result;
    /* Preserve observed configuration rather than inventing default bits. */
    control = io->read(io->context, MMU_CONTROL);
    if (control == 0xffffffffU)
        return MBX_MMU_IO_INVALID;
    if (control & (REQUEST | ENABLED | RELOAD | RELOAD_BUSY))
        return MBX_MMU_BUSY;
    io->write(io->context, MMU_CONTROL, control | REQUEST);
    return wait_control(io, ENABLED, ENABLED);
}

int mbx_mmu_disable(const struct mbx_mmu_io *io)
{
    mbx_word control;
    if (!valid_io(io))
        return MBX_MMU_INVALID;
    control = io->read(io->context, MMU_CONTROL);
    if (control == 0xffffffffU)
        return MBX_MMU_IO_INVALID;
    if (control & (RELOAD | RELOAD_BUSY))
        return MBX_MMU_BUSY;
    io->write(io->context, MMU_CONTROL, control & ~REQUEST);
    return wait_control(io, REQUEST | ENABLED, 0);
}

int mbx_mmu_reload(const struct mbx_mmu_io *io, mbx_word virtual_page, mbx_word device_page)
{
    mbx_word control;
    if (!valid_io(io) || (virtual_page & 4095U) || virtual_page >= 0x2000000U ||
        !device_page || (device_page & 4095U))
        return MBX_MMU_INVALID;
    control = io->read(io->context, MMU_CONTROL);
    if (control == 0xffffffffU)
        return MBX_MMU_IO_INVALID;
    if ((control & (REQUEST | ENABLED | RELOAD | RELOAD_BUSY)) != (REQUEST | ENABLED))
        return MBX_MMU_BUSY;
    io->write(io->context, 0x1024U, device_page);
    io->write(io->context, 0x1028U, virtual_page >> 12);
    io->write(io->context, MMU_CONTROL, control | RELOAD);
    return wait_control(io, RELOAD | RELOAD_BUSY, 0);
}
