#define _POSIX_C_SOURCE 200809L
#include <asm/hwcap.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/auxv.h>
#include <time.h>

typedef void (*add_function)(const float *, const float *, float *, size_t);
typedef void (*f32_function)(const float *, const float *, float *, size_t);
typedef void (*f64_function)(const double *, const double *, double *, size_t);
void add_soft(const float *, const float *, float *, size_t);
void add_vfp(const float *, const float *, float *, size_t);
void shortvec_add(const float *, const float *, float *, size_t);
void batch_f32_soft(const float *, const float *, float *, size_t);
void batch_f32_vfp(const float *, const float *, float *, size_t);
void batch_f64_soft(const double *, const double *, double *, size_t);
void batch_f64_vfp(const double *, const double *, double *, size_t);
uint32_t shortvec_get_fpscr(void);

enum { MAX_WORDS = 8192 };
static float fa[MAX_WORDS], fb[MAX_WORDS], fo[MAX_WORDS], fm[16];
static double da[MAX_WORDS], dout[MAX_WORDS], dm[16];

static uint64_t now(void)
{
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts))
        return 0;
    return (uint64_t)ts.tv_sec * 1000000000u + (uint64_t)ts.tv_nsec;
}

static uint32_t hash(const void *p, size_t size)
{
    const unsigned char *data = p;
    uint32_t h = 2166136261u;
    size_t i;
    for (i = 0; i < size; ++i)
        h = (h ^ data[i]) * 16777619u;
    return h;
}

static uint64_t finish(uint64_t start)
{
    uint64_t end = now();
    return !start || !end || end < start ? UINT64_MAX : end - start;
}

static void record(const char *operation, const char *variant, size_t count,
                   size_t repeats, size_t trial, uint64_t elapsed,
                   uint64_t resolution, uint32_t checksum)
{
    printf("{\"operation\":\"%s\",\"variant\":\"%s\",\"count\":%lu,"
           "\"repeats\":%lu,\"trial\":%lu,\"elapsed_ns\":%" PRIu64 ","
           "\"clock_resolution_ns\":%" PRIu64 ",\"at_least_32_clock_ticks\":%s,"
           "\"checksum\":\"%08" PRIx32 "\",\"operands\":\"retained\"}\n",
           operation, variant, (unsigned long)count, (unsigned long)repeats,
           (unsigned long)trial, elapsed, resolution,
           elapsed >= resolution * 32 ? "true" : "false", checksum);
}

int main(int argc, char **argv)
{
    const size_t add_sizes[] = { 8, 64, 512, 4096 };
    const size_t matrix_sizes[] = { 16, 256, 2048 };
    const char *names[] = { "soft", "vfp-scalar", "vfp-shortvec" };
    add_function additions[] = { add_soft, add_vfp, shortvec_add };
    f32_function f32[] = { batch_f32_soft, batch_f32_vfp };
    f64_function f64[] = { batch_f64_soft, batch_f64_vfp };
    struct timespec clock_resolution;
    uint64_t resolution, start, elapsed;
    size_t i, k, trial, offset, variant, repeat, records = 0;
    unsigned long caps = getauxval(AT_HWCAP);
    if (argc != 2 || strcmp(argv[1], "--run")) {
        fputs("usage: vfp-benchmark --run\n", stderr);
        return 2;
    }
    if (!(caps & HWCAP_VFP) || (caps & HWCAP_VFPv3)) {
        puts("{\"status\":\"SKIP\",\"reason\":\"requires the VFPv2 short-vector target\"}");
        return 0;
    }
    if (shortvec_get_fpscr() & 0x00f70000u)
        return 3;
    if (clock_getres(CLOCK_MONOTONIC, &clock_resolution))
        return 4;
    resolution = (uint64_t)clock_resolution.tv_sec * 1000000000u + clock_resolution.tv_nsec;
    if (!resolution || !now())
        return 4;
    for (i = 0; i < MAX_WORDS; ++i) {
        fa[i] = ((int)(i % 127) - 63) * 0.125f;
        fb[i] = ((int)(i % 61) - 30) * 0.25f;
        da[i] = (double)fa[i];
    }
    for (i = 0; i < 16; ++i) {
        fm[i] = ((int)i - 7) * 0.0625f;
        dm[i] = (double)fm[i];
    }
    for (k = 0; k < sizeof add_sizes / sizeof add_sizes[0]; ++k) {
        size_t count = add_sizes[k], repeats = 131072 / count;
        uint32_t expected;
        add_soft(fa, fb, fo, count / 8);
        expected = hash(fo, count * sizeof(float));
        for (trial = 0; trial < 3; ++trial) {
            for (offset = 0; offset < 3; ++offset) {
                variant = (offset + trial) % 3;
                additions[variant](fa, fb, fo, count / 8);
                start = now();
                for (repeat = 0; repeat < repeats; ++repeat)
                    additions[variant](fa, fb, fo, count / 8);
                elapsed = finish(start);
                if (elapsed == UINT64_MAX)
                    return 4;
                if (!start || hash(fo, count * sizeof(float)) != expected)
                    return 5;
                record("add-f32", names[variant], count, repeats, trial, elapsed, resolution, expected);
                ++records;
            }
        }
    }
    for (k = 0; k < sizeof matrix_sizes / sizeof matrix_sizes[0]; ++k) {
        size_t count = matrix_sizes[k], repeats = 16384 / count;
        uint32_t expected32, expected64;
        f32[0](fm, fa, fo, count);
        f64[0](dm, da, dout, count);
        expected32 = hash(fo, count * 4 * sizeof(float));
        expected64 = hash(dout, count * 4 * sizeof(double));
        for (trial = 0; trial < 3; ++trial) {
            for (offset = 0; offset < 2; ++offset) {
                variant = (offset + trial) % 2;
                f32[variant](fm, fa, fo, count);
                start = now();
                for (repeat = 0; repeat < repeats; ++repeat)
                    f32[variant](fm, fa, fo, count);
                elapsed = finish(start);
                if (elapsed == UINT64_MAX)
                    return 4;
                if (!start || hash(fo, count * 4 * sizeof(float)) != expected32)
                    return 6;
                record("matrix-f32", names[variant], count, repeats, trial, elapsed, resolution, expected32);
                ++records;
                f64[variant](dm, da, dout, count);
                start = now();
                for (repeat = 0; repeat < repeats; ++repeat)
                    f64[variant](dm, da, dout, count);
                elapsed = finish(start);
                if (elapsed == UINT64_MAX)
                    return 4;
                if (!start || hash(dout, count * 4 * sizeof(double)) != expected64)
                    return 7;
                record("matrix-f64", names[variant], count, repeats, trial, elapsed, resolution, expected64);
                ++records;
            }
        }
    }
    printf("{\"status\":\"PASS\",\"records\":%lu,\"timing_scope\":\"retained userspace kernels\","
           "\"execution_environment_verified\":false}\n", (unsigned long)records);
    return 0;
}
