#include <asm/hwcap.h>
#include <float.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/auxv.h>

/* Both objects use the base AAPCS, including float arguments and returns. */
float affine_soft(float, float, float);
float affine_vfp(float, float, float);
double affine64_soft(double, double, double);
double affine64_vfp(double, double, double);
void transform_soft(const float *, const float *, float *, size_t);
void transform_vfp(const float *, const float *, float *, size_t);

_Static_assert(sizeof(float) == 4 && FLT_RADIX == 2 && FLT_MANT_DIG == 24,
               "binary32 float required");
_Static_assert(sizeof(double) == 8 && DBL_MANT_DIG == 53, "binary64 double required");

enum { MAX_POINTS = 1024, ROUNDS = 64 };
static float input[MAX_POINTS * 4];
static float soft_output[MAX_POINTS * 4 + 2];
static float vfp_output[MAX_POINTS * 4 + 2];
static uint32_t random_state = 0x24201136;

static float sample(void)
{
    random_state ^= random_state << 13;
    random_state ^= random_state >> 17;
    random_state ^= random_state << 5;
    return ((int32_t)(random_state % 20001) - 10000) / 997.0f;
}

static double absolute(double x)
{
    return x < 0 ? -x : x;
}

static uint32_t bits(float x)
{
    uint32_t result;
    memcpy(&result, &x, sizeof result);
    return result;
}

static uint64_t bits64(double x)
{
    uint64_t result;
    memcpy(&result, &x, sizeof result);
    return result;
}

int main(int argc, char **argv)
{
    const size_t sizes[] = { 0, 1, 7, 64, 257, MAX_POINTS };
    unsigned long hwcap = getauxval(AT_HWCAP);
    int force_soft = argc == 2 && strcmp(argv[1], "--force-soft") == 0;
    uint32_t checksum = 2166136261u;
    size_t scalar_cases = 0, output_words = 0, frames = 0;
    size_t round, k, i, row;
    if (argc > 2 || (argc == 2 && !force_soft)) {
        fputs("usage: vfp-probe [--force-soft]\n", stderr);
        return 2;
    }
    if (affine_soft(1.5f, 2.25f, -0.5f) != 2.875f)
        return 3;
    if (affine64_soft(1.5, 2.25, -0.5) != 2.875)
        return 3;
    if (force_soft || !(hwcap & HWCAP_VFP)) {
        printf("{\"status\":\"SOFT_ONLY\",\"hwcap_vfp\":%s,"
               "\"forced_soft\":%s,\"vfp_functions_called\":false}\n",
               hwcap & HWCAP_VFP ? "true" : "false",
               force_soft ? "true" : "false");
        return 0;
    }
    for (round = 0; round < ROUNDS; ++round) {
        float matrix[16];
        for (i = 0; i < 16; ++i)
            matrix[i] = sample();
        for (i = 0; i < MAX_POINTS * 4; ++i)
            input[i] = sample();
        for (i = 0; i < 256; ++i) {
            float x = sample(), scale = sample(), bias = sample();
            if (bits(affine_soft(x, scale, bias)) != bits(affine_vfp(x, scale, bias)))
                return 4;
            {
                double dx = (double)x / 991.0;
                double ds = (double)scale / 983.0;
                double db = (double)bias / 977.0;
                if (bits64(affine64_soft(dx, ds, db)) != bits64(affine64_vfp(dx, ds, db)))
                    return 4;
            }
            ++scalar_cases;
        }
        for (k = 0; k < sizeof sizes / sizeof sizes[0]; ++k) {
            size_t count = sizes[k];
            for (i = 0; i < MAX_POINTS * 4 + 2; ++i)
                soft_output[i] = vfp_output[i] = 12345.0f;
            transform_soft(matrix, input, soft_output + 1, count);
            transform_vfp(matrix, input, vfp_output + 1, count);
            if (memcmp(soft_output, vfp_output, sizeof soft_output))
                return 5;
            if (soft_output[0] != 12345.0f)
                return 6;
            for (i = count * 4 + 1; i < MAX_POINTS * 4 + 2; ++i)
                if (soft_output[i] != 12345.0f)
                    return 7;
            for (i = 0; i < count; ++i) {
                for (row = 0; row < 4; ++row) {
                    double expected = 0, magnitude = 0;
                    size_t col;
                    for (col = 0; col < 4; ++col) {
                        double product = (double)matrix[row * 4 + col] * input[i * 4 + col];
                        expected += product;
                        magnitude += absolute(product);
                    }
                    if (absolute((double)soft_output[1 + i * 4 + row] - expected) >
                        8 * FLT_EPSILON * magnitude + FLT_MIN)
                        return 8;
                    checksum = (checksum ^ bits(soft_output[1 + i * 4 + row])) * 16777619u;
                    ++output_words;
                }
            }
            ++frames;
        }
    }
    printf("{\"status\":\"PASS\",\"hwcap_vfp\":true,"
           "\"soft_caller_float_argument_return_cases\":%lu,"
           "\"soft_caller_double_argument_return_cases\":%lu,"
           "\"transform_frames\":%lu,\"output_words\":%lu,"
           "\"checksum\":\"%08lx\",\"performance_measured\":false}\n",
           (unsigned long)scalar_cases, (unsigned long)scalar_cases, (unsigned long)frames,
           (unsigned long)output_words, (unsigned long)checksum);
    return 0;
}
