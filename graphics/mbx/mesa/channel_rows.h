/* SPDX-License-Identifier: MIT */
#ifndef MBX_CHANNEL_ROWS_H
#define MBX_CHANNEL_ROWS_H
/* Final chunk overlaps prior rows to keep the proven 16-row hardware shape.
 * Alpha channel replacement is idempotent; RGB bytes remain untouched. */
static inline int mbx_channel_rows(unsigned height,unsigned next,unsigned *start,unsigned *rows)
{
 if(!start||!rows||height<16||height>400||next>=height)return -22;
 unsigned remaining=height-next;
 *rows=remaining>192?192:(remaining+15U)&~15U;
 if(*rows>height)return -22;
 *start=*rows>remaining?height-*rows:next;
 return 0;
}
#endif
