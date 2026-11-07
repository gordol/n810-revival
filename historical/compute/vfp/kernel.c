/* Finite, normal-range floating-point workload for an isolated ABI probe. */
#include <stddef.h>

#ifndef TRANSFORM_NAME
#error TRANSFORM_NAME must name this build variant
#endif
#ifndef AFFINE_NAME
#error AFFINE_NAME must name this build variant
#endif
#ifndef DOUBLE_AFFINE_NAME
#error DOUBLE_AFFINE_NAME must name this build variant
#endif

float AFFINE_NAME(float x, float scale, float bias)
{
    return x * scale + bias;
}

double DOUBLE_AFFINE_NAME(double x, double scale, double bias)
{
    return x * scale + bias;
}

void TRANSFORM_NAME(const float *matrix, const float *input,
                    float *output, size_t count)
{
    size_t i, row;
    for (i = 0; i < count; ++i) {
        for (row = 0; row < 4; ++row) {
            const float *m = matrix + row * 4;
            const float *p = input + i * 4;
            float sum = m[0] * p[0];
            sum += m[1] * p[1];
            sum += m[2] * p[2];
            sum += m[3] * p[3];
            output[i * 4 + row] = sum;
        }
    }
}
