#include <stddef.h>
#ifndef ADD_NAME
#error ADD_NAME must name this build variant
#endif

void ADD_NAME(const float *a, const float *b, float *out, size_t blocks)
{
    size_t i;
    for (i = 0; i < blocks * 8; ++i)
        out[i] = a[i] + b[i];
}
