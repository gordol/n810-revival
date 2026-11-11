/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef MBX_TEXTURE_EQUAL_H
#define MBX_TEXTURE_EQUAL_H
/* Exact comparison of CPU-owned immutable texture storage. No sampling,
 * checksums, speculative reads past length, or change to DMA ownership.
 * ARM kernel get_unaligned() can emit byte loads with -mno-unaligned-access;
 * explicitly aligned pointers permit word loads without that assumption.
 */
typedef unsigned int mbx_verify_word __attribute__((__may_alias__));
static int mbx_texture_equal(const void *left, const void *right, unsigned long bytes)
{
    const unsigned char *a=left,*b=right;
    if(sizeof(mbx_verify_word)==4 && !(((unsigned long)a|(unsigned long)b)&3UL)) {
        const mbx_verify_word *x=(const mbx_verify_word *)a;
        const mbx_verify_word *y=(const mbx_verify_word *)b;
        while(bytes>=16) {
            unsigned int different=(x[0]^y[0])|(x[1]^y[1])|(x[2]^y[2])|(x[3]^y[3]);
            if(different)return 0;
            x+=4;y+=4;bytes-=16;
        }
        while(bytes>=4) {
            if(*x++!=*y++)return 0;
            bytes-=4;
        }
        a=(const unsigned char *)x;b=(const unsigned char *)y;
    }
    while(bytes--)if(*a++!=*b++)return 0;
    return 1;
}
#endif
