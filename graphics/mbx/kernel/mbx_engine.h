/* SPDX-License-Identifier: MIT */
#ifndef N810_MBX_ENGINE_H
#define N810_MBX_ENGINE_H
#define MBX_EVENT_STATUS 0x12cU
#define MBX_EVENT_CLEAR 0x134U
#define MBX_RENDER_COMPLETE 0x4U
#define MBX_TA_COMPLETE 0x10U
#define MBX_ALLOC_COMPLETE 0x40U
#define MBX_CONTEXT_COMPLETE 0x100U
#define MBX_COPY_COMPLETE 0x400U
struct mbx_gpu_result { int error; unsigned words_written,samples,completion_status,submitted; };
#endif
