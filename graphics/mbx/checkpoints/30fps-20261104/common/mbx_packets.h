/* SPDX-License-Identifier: MIT */
#ifndef N810_MBX_PACKETS_H
#define N810_MBX_PACKETS_H
#define MBX_TRIANGLE_WORDS 19U
/* IEEE754 words are checked as integers; this code also builds in the kernel.
 * z is the original packet parameter, not an advertised GL depth convention.
 * Only the statically recovered opaque, untextured state is encoded here. */
/* argb is conventional opaqueffRRGGBB; the encoder constructs the distinct
 * positive packed-color float container required by special attribute11. */
struct mbx_vertex { unsigned x, y, z, argb; };
int mbx_encode_triangle(unsigned width,unsigned height,
                        const struct mbx_vertex vertices[3],
                        unsigned *words,unsigned capacity);
#define MBX_TRIANGLE_FRAME_COMMANDS 23U
enum mbx_destination { MBX_FIFO, MBX_POLYGON_CONTROL };
struct mbx_command { enum mbx_destination destination; unsigned value; };
/* A complete one-polygon frame: preamble, state/vertices, sideband, frame end. */
int mbx_encode_triangle_frame(unsigned width,unsigned height,
                             const struct mbx_vertex vertices[3],
                             struct mbx_command *commands,unsigned capacity);
/* Bounded command batches reuse caller-owned storage. No allocation, MMIO or
 * completion wait occurs here. Hardware validation is still pending. */
#define MBX_MAX_BATCH_TRIANGLES 256U
#define MBX_MAX_BATCH_COMMANDS (20U*MBX_MAX_BATCH_TRIANGLES+3U)
int mbx_encode_triangle_batch(unsigned width,unsigned height,
                             const struct mbx_vertex *vertices,unsigned triangles,
                             struct mbx_command *commands,unsigned capacity,
                             unsigned *written);
#endif
