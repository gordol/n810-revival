/* SPDX-License-Identifier: MIT */
#include <assert.h>
#include <stdio.h>
#include "mbx_surface_lease.h"
int main(void){
 struct mbx_surface_lease s={.image={.version=1,.session=2,.generation=7,.format=MBX_SURFACE_RGB565,.width=400,.height=256,.stride=800,.bytes=204800,.flags=MBX_SURFACE_COMPLETE},.held=1};
 struct mbx_surface_sink p={.surface=s.image,.address=4096,.capacity=768000,.stride=1600,.width=400,.height=224,.reverse_rows=1};
 assert(mbx_lease_sink_valid(&s,&p));
 s.held=0;assert(!mbx_lease_sink_valid(&s,&p));s.held=1;
 p.surface.generation--;assert(!mbx_lease_sink_valid(&s,&p));p.surface=s.image;
 p.surface.session++;assert(!mbx_lease_sink_valid(&s,&p));p.surface=s.image;
 p.surface.stride=801;assert(!mbx_lease_sink_valid(&s,&p));p.surface=s.image;
 p.height=257;assert(!mbx_lease_sink_valid(&s,&p));p.height=224;
 p.x=1;assert(!mbx_lease_sink_valid(&s,&p));p.x=0;
 p.capacity=357599;assert(!mbx_lease_sink_valid(&s,&p));p.capacity=357600;assert(mbx_lease_sink_valid(&s,&p));
 p.address=~(__u64)0-100;assert(!mbx_lease_sink_valid(&s,&p));p.address=4096;
 p.width=~0U;assert(!mbx_lease_sink_valid(&s,&p));p.width=400;
 p.reverse_rows=2;assert(!mbx_lease_sink_valid(&s,&p));p.reverse_rows=1;
 p.reserved[0]=1;assert(!mbx_lease_sink_valid(&s,&p));
 struct mbx_surface_dma_sink d={.surface=s.image,.version=1,.fb_fd=3,.canvas_width=800,.canvas_height=480,.stride=1600,.destination_x=400,.destination_y=256,.width=400,.height=224,.reverse_rows=1};
 assert(mbx_lease_dma_valid(&s,&d));
 d.destination_x++;assert(!mbx_lease_dma_valid(&s,&d));d.destination_x--;
 d.destination_y++;assert(!mbx_lease_dma_valid(&s,&d));d.destination_y--;
 d.stride=1599;assert(!mbx_lease_dma_valid(&s,&d));d.stride=1600;
 d.fb_fd=-1;assert(!mbx_lease_dma_valid(&s,&d));d.fb_fd=3;
 d.surface.generation++;assert(!mbx_lease_dma_valid(&s,&d));d.surface=s.image;
 d.reverse_rows=2;assert(!mbx_lease_dma_valid(&s,&d));d.reverse_rows=1;
 d.canvas_width=~0U;assert(!mbx_lease_dma_valid(&s,&d));d.canvas_width=800;
 d.reserved=1;assert(!mbx_lease_dma_valid(&s,&d));
 puts("surface lease: stale generations, bounds, stride, overflow and reserved fields rejected");
}
