#pragma once
// This port has no OS sockets. Avoid upstream includes.h pulling lwIP/FreeRTOS
// into the protocol core (FreeRTOS and WPA both use the LIST_H include guard).
#define INCLUDES_H
#include <stdlib.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>
#include <errno.h>
#include <ctype.h>
#include <unistd.h>
#include <sys/types.h>
#include <sys/time.h>
#define __BYTE_ORDER __BYTE_ORDER__
#define __LITTLE_ENDIAN __ORDER_LITTLE_ENDIAN__
#define __BIG_ENDIAN __ORDER_BIG_ENDIAN__
#define bswap_16 __builtin_bswap16
#define bswap_32 __builtin_bswap32
#define bswap_64 __builtin_bswap64
// Configuration-only IPv4 storage in disabled RADIUS/AP features, no socket ABI.
struct in_addr { uint32_t s_addr; };
#define htonl __builtin_bswap32
#define ntohl __builtin_bswap32
#define htons __builtin_bswap16
#define ntohs __builtin_bswap16

// Protocol objects are task-owned and may use PSRAM. Keep SDK/DMA/ISR storage
// under its existing allocator; these wrappers affect only this RSN archive.
void* pocket_rsn_malloc(size_t);
void* pocket_rsn_realloc(void*,size_t);
void pocket_rsn_free(void*);
char* pocket_rsn_strdup(const char*);
#define os_malloc(n) pocket_rsn_malloc(n)
#define os_realloc(p,n) pocket_rsn_realloc(p,n)
#define os_free(p) pocket_rsn_free(p)
#define os_strdup(p) pocket_rsn_strdup(p)
