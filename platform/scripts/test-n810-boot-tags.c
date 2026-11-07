/* SPDX-License-Identifier: GPL-2.0 */
/* Exercise the actual compressed-kernel converter with synthetic NOLO tags. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <asm/setup.h>
#include <libfdt.h>

int atags_to_fdt(void *, void *, int);

static void put16(unsigned char *p, unsigned value)
{
 p[0] = value; p[1] = value >> 8;
}

int main(void)
{
 uint32_t words[128] = {0};
 unsigned char config[72] = {0};
 char tree[16384];
 struct tag *core = (void *)words, *memory, *board, *end;
 const void *value;
 int chosen, length;
 core->hdr.tag = ATAG_CORE; core->hdr.size = tag_size(tag_core);
 memory = tag_next(core);
 memory->hdr.tag = ATAG_MEM; memory->hdr.size = tag_size(tag_mem32);
 memory->u.mem.start = 0x80000000; memory->u.mem.size = 0x08000000;
 board = tag_next(memory);
 board->hdr.tag = 0x414f4d50; board->hdr.size = 2 + sizeof(config) / 4;
 /* Unknown records before and after a boot reason must be preserved. */
 put16(config, 0x4f0c); put16(config + 2, 32);
 memset(config + 4, 0xa5, 32);
 put16(config + 36, 0x4f80); put16(config + 38, 12);
 memcpy(config + 40, "charger", 8);
 put16(config + 52, 0x4f82); put16(config + 54, 16);
 memset(config + 56, 0x5a, 16);
 memcpy(&board->u, config, sizeof(config));
 end = tag_next(board); end->hdr.size = 0; end->hdr.tag = ATAG_NONE;
 assert(fdt_create_empty_tree(tree, sizeof(tree)) == 0);
 assert(atags_to_fdt(words, tree, sizeof(tree)) == 0);
 chosen = fdt_path_offset(tree, "/chosen"); assert(chosen >= 0);
 value = fdt_getprop(tree, chosen, "omap-config", &length);
 assert(value && length == sizeof(config));
 assert(memcmp(value, config, sizeof(config)) == 0);
 value = fdt_getprop(tree, chosen, "atag-00000002", &length);
 assert(value && length == (int)board->hdr.size * 4);
 assert(memcmp(value, board, length) == 0);
 value = fdt_getprop(tree, fdt_path_offset(tree, "/memory"), "reg", &length);
 assert(value && length == 8);
 assert(fdt32_to_cpu(((const fdt32_t *)value)[0]) == 0x80000000);
 assert(fdt32_to_cpu(((const fdt32_t *)value)[1]) == 0x08000000);
 /* Malformed size must fail before advancing the ATAG pointer. */
 board->hdr.size = 1;
 assert(fdt_create_empty_tree(tree, sizeof(tree)) == 0);
 assert(atags_to_fdt(words, tree, sizeof(tree)) == 1);
 board->hdr.size = sizeof(tree) / 4 + 1;
 assert(fdt_create_empty_tree(tree, sizeof(tree)) == 0);
 assert(atags_to_fdt(words, tree, sizeof(tree)) == 1);
 puts("Boot tags: complete OMAP/raw copies, memory and malformed-size checks passed");
 return 0;
}
