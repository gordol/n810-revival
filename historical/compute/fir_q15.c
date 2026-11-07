#include "fir_q15.h"

void n810_fir_q15(const short *x, const short *h, short *y,
                  unsigned count, unsigned taps)
{
    unsigned i, k;
    for (i = 0; i < count; ++i) {
        long long sum = 0, q;
        for (k = 0; k < taps; ++k)
            sum += (long long)x[i+k] * h[k];
        /* C division truncates toward zero. Make negative rounding explicit. */
        q = sum >= 0 ? sum / 32768 : -((-sum + 32767) / 32768);
        y[i] = q > 32767 ? 32767 : q < -32768 ? -32768 : (short)q;
    }
}
