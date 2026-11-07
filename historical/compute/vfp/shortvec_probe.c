#include <asm/hwcap.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/auxv.h>

void add_soft(const float *, const float *, float *, size_t);
void shortvec_add(const float *, const float *, float *, size_t);
uint32_t shortvec_get_fpscr(void);
void shortvec_set_fpscr(uint32_t);
struct context { uint32_t seed[16], after[16], fpscr; };
void shortvec_context(const float *, const float *, float *, size_t, struct context *);

enum { WORDS = 4096 };
static float a[WORDS], b[WORDS], expected[WORDS], actual[WORDS + 2];
static uint32_t random_state = 0x11362420;

static uint32_t random_word(void)
{
    random_state ^= random_state << 13;
    random_state ^= random_state >> 17;
    random_state ^= random_state << 5;
    return random_state;
}

int main(void)
{
    const size_t blocks[] = { 0, 1, 2, 7, 64, 512 };
    uint32_t original, mode;
    size_t iteration, k, i, words = 0, frames = 0, negative_zeros = 0;
    unsigned long caps = getauxval(AT_HWCAP);
    if (!(caps & HWCAP_VFP) || (caps & HWCAP_VFPv3)) {
        puts("{\"status\":\"SKIP\",\"reason\":\"requires the VFPv2 short-vector target\"}");
        return 0;
    }
    original = shortvec_get_fpscr();
    for (iteration = 0; iteration < 256; ++iteration) {
        struct context state;
        for (i = 0; i < WORDS; ++i) {
            a[i] = ((int32_t)(random_word() % 8193) - 4096) * 0.125f;
            b[i] = ((int32_t)(random_word() % 8193) - 4096) * 0.125f;
        }
        for (i = 0; i < 16; ++i)
            state.seed[i] = random_word();
        /* Exact dyadic sums isolate lane/control behavior from rounding. */
        mode = ((iteration & 3u) << 22) | (((iteration >> 2) & 3u) << 24)
               | (random_word() & 0xf000009fu);
        for (k = 0; k < sizeof blocks / sizeof blocks[0]; ++k) {
            size_t count = blocks[k] * 8;
            for (i = 0; i < WORDS + 2; ++i)
                actual[i] = 12345.0f;
            memset(state.after, 0, sizeof state.after);
            add_soft(a, b, expected, blocks[k]);
            /* Exact cancellation has negative zero under round-toward-minus. */
            if ((mode & 0x00c00000u) == 0x00800000u) {
                for (i = 0; i < count; ++i) {
                    if (expected[i] == 0.0f && (a[i] != 0.0f || b[i] != 0.0f)) {
                        expected[i] = -0.0f;
                        ++negative_zeros;
                    }
                }
            }
            shortvec_set_fpscr(mode);
            shortvec_context(a, b, actual + 1, blocks[k], &state);
            shortvec_set_fpscr(original);
            if (memcmp(actual + 1, expected, count * sizeof(float))) {
                for (i = 0; i < count; ++i) {
                    uint32_t got, want;
                    memcpy(&got, actual + 1 + i, sizeof got);
                    memcpy(&want, expected + i, sizeof want);
                    if (got != want) {
                        printf("{\"status\":\"MISMATCH\",\"iteration\":%lu,\"block_count\":%lu,"
                               "\"word\":%lu,\"got\":\"%08lx\",\"want\":\"%08lx\",\"mode\":\"%08lx\"}\n",
                               (unsigned long)iteration, (unsigned long)blocks[k], (unsigned long)i,
                               (unsigned long)got, (unsigned long)want, (unsigned long)mode);
                        break;
                    }
                }
                return 3;
            }
            if (state.fpscr != mode || memcmp(state.seed, state.after, sizeof state.seed)) {
#ifdef EXPECT_CONTEXT_FAILURE
                printf("{\"status\":\"DETECTED\",\"fpscr_mismatch\":%s,\"register_mismatch\":%s}\n",
                       state.fpscr != mode ? "true" : "false",
                       memcmp(state.seed, state.after, sizeof state.seed) ? "true" : "false");
                return 0;
#else
                return 4;
#endif
            }
            if (actual[0] != 12345.0f)
                return 5;
            for (i = count + 1; i < WORDS + 2; ++i)
                if (actual[i] != 12345.0f)
                    return 6;
            words += count;
            ++frames;
        }
    }
#ifdef EXPECT_CONTEXT_FAILURE
    return 7;
#endif
    printf("{\"status\":\"PASS\",\"frames\":%lu,\"output_words\":%lu,"
           "\"round_minus_negative_zero_cases\":%lu,"
           "\"fpscr_and_d8_d15_preserved\":true,\"performance_measured\":false}\n",
           (unsigned long)frames, (unsigned long)words, (unsigned long)negative_zeros);
    return 0;
}
