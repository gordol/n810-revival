/* SPDX-License-Identifier: MIT
 * Exact last-value memoization of packed vertex color. Bitwise keys preserve
 * signed zero and all original rounding; no tolerance or quantization added.
 */
#ifndef MBX_COLOR_CACHE_H
#define MBX_COLOR_CACHE_H
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
struct mbx_color_cache { uint32_t bits[4],packed; bool valid; };
static unsigned mbx_byte(float f)
{ return f<0 ? 0 : f>1 ? 255 : (unsigned)(f*255.0f+0.5f); }
static uint32_t mbx_color(const float *color)
{ return mbx_byte(color[0])|mbx_byte(color[1])<<8|mbx_byte(color[2])<<16|mbx_byte(color[3])<<24; }
static uint32_t mbx_cached_color(struct mbx_color_cache *cache,const float *color)
{
 uint32_t bits[4];memcpy(bits,color,sizeof(bits));
 if(cache->valid&&bits[0]==cache->bits[0]&&bits[1]==cache->bits[1]&&
    bits[2]==cache->bits[2]&&bits[3]==cache->bits[3])return cache->packed;
 cache->packed=mbx_color(color);memcpy(cache->bits,bits,sizeof(bits));cache->valid=true;
 return cache->packed;
}
#endif
