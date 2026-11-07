#include <stddef.h>
#if !defined(BATCH_NAME) || !defined(REAL_TYPE)
#error BATCH_NAME and REAL_TYPE must select this build variant
#endif

void BATCH_NAME(const REAL_TYPE *m, const REAL_TYPE *in, REAL_TYPE *out, size_t count)
{
    size_t i, row;
    for (i = 0; i < count; ++i) {
        for (row = 0; row < 4; ++row) {
            REAL_TYPE value = m[row * 4] * in[i * 4];
            value += m[row * 4 + 1] * in[i * 4 + 1];
            value += m[row * 4 + 2] * in[i * 4 + 2];
            value += m[row * 4 + 3] * in[i * 4 + 3];
            out[i * 4 + row] = value;
        }
    }
}
