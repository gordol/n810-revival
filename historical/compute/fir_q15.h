#ifndef N810_FIR_Q15_H
#define N810_FIR_Q15_H
/* Logical 16-bit samples, independent of sizeof(char) on C55x. */
#include <limits.h>
#if SHRT_MAX != 32767 || SHRT_MIN != (-32767 - 1)
#error Requires a signed 16-bit short
#endif
/* y[i] = sat16(floor(sum(x[i+k] * h[k]) / 32768)).
 * Caller provides count+taps-1 input samples; no implicit history or padding.
 * At most 64 taps: the accumulator needs at most 37 signed bits.
 * Disjoint input/coefficient/output ranges are required. */
void n810_fir_q15(const short *x, const short *h, short *y,
                  unsigned count, unsigned taps);
#endif
