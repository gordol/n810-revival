/* SPDX-License-Identifier: MIT */
#ifndef MBX_SERVICE_ABI_H
#define MBX_SERVICE_ABI_H
#ifdef __KERNEL__
#include <linux/ioctl.h>
#else
#include <sys/ioctl.h>
#endif
struct mbx_texture_resident_info { unsigned version,session,generation,bytes; };
#define MBX_TEXTURE_RESIDENT_INFO _IOR('M',0x55,struct mbx_texture_resident_info)
/* Read-only readiness on an already-authorized exclusive device file. */
struct mbx_service_info { unsigned version,active,baseline_verified,reserved; };
_Static_assert(sizeof(struct mbx_service_info)==16,"service info ABI");
#define MBX_SERVICE_INFO _IOR('M',0x43,struct mbx_service_info)
#endif
