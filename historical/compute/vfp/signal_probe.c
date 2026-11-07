#define _GNU_SOURCE
#include <asm/hwcap.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/auxv.h>
#include <sys/time.h>
#include <time.h>
#include <ucontext.h>

void shortvec_add(const float *, const float *, float *, size_t);
uint32_t shortvec_get_fpscr(void);
void shortvec_set_fpscr(uint32_t);
uint32_t shortvec_signal_scalar(void);
extern char shortvec_active_begin[], shortvec_active_end[];

static volatile sig_atomic_t arrivals, active_arrivals, bad_mode, bad_scalar;
static volatile sig_atomic_t model_linux_entry, entry_vector_modes;
static float a[2048], b[2048], output[2048], expected[2048];

static void handler(int signal_number, siginfo_t *info, void *context)
{
    ucontext_t *frame = context;
    uintptr_t pc = frame->uc_mcontext.arm_pc;
    (void)signal_number;
    (void)info;
    ++arrivals;
    if (pc >= (uintptr_t)shortvec_active_begin && pc < (uintptr_t)shortvec_active_end)
        ++active_arrivals;
    {
        uint32_t entry = shortvec_get_fpscr();
        if (entry & 0x00370000u)
            ++entry_vector_modes;
        if (model_linux_entry)
            shortvec_set_fpscr(entry & ~0x00370000u);
    }
    if (shortvec_get_fpscr() & 0x00370000u)
        ++bad_mode;
    else if (shortvec_signal_scalar() != 0x40700000u)
        ++bad_scalar;
}

static uint64_t now(void)
{
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts))
        return 0;
    return (uint64_t)ts.tv_sec * 1000000000u + ts.tv_nsec;
}

int main(int argc, char **argv)
{
    struct sigaction action, previous;
    struct itimerval timer, previous_timer;
    struct timespec zero = { 0, 0 };
    sigset_t block, old_mask;
    uint32_t original_fpscr;
    uint64_t start, current;
    size_t i, batches = 0;
    int output_bad = 0, clock_bad = 0;
    unsigned long caps = getauxval(AT_HWCAP);
    if (argc == 2 && !strcmp(argv[1], "--model-linux-entry"))
        model_linux_entry = 1;
    else if (argc != 1)
        return 2;
    if (!(caps & HWCAP_VFP) || (caps & HWCAP_VFPv3)) {
        puts("{\"status\":\"SKIP\",\"reason\":\"requires the VFPv2 short-vector target\"}");
        return 0;
    }
    original_fpscr = shortvec_get_fpscr();
    if (original_fpscr & 0x00f70000u)
        return 2;
    if (getitimer(ITIMER_REAL, &previous_timer) || previous_timer.it_value.tv_sec ||
        previous_timer.it_value.tv_usec || previous_timer.it_interval.tv_sec ||
        previous_timer.it_interval.tv_usec)
        return 2;
    for (i = 0; i < 2048; ++i) {
        a[i] = ((int)(i % 47) - 23) * 0.25f;
        b[i] = ((int)(i % 31) - 15) * 0.5f;
        expected[i] = a[i] + b[i];
    }
    memset(&action, 0, sizeof action);
    action.sa_sigaction = handler;
    action.sa_flags = SA_SIGINFO;
    sigemptyset(&action.sa_mask);
    if (sigaction(SIGALRM, &action, &previous))
        return 3;
    memset(&timer, 0, sizeof timer);
    timer.it_value.tv_usec = timer.it_interval.tv_usec = 500;
    start = now();
    if (!start || setitimer(ITIMER_REAL, &timer, NULL)) {
        sigaction(SIGALRM, &previous, NULL);
        return 3;
    }
    do {
        shortvec_add(a, b, output, 256);
        if (memcmp(output, expected, sizeof output)) {
            output_bad = 1;
            break;
        }
        ++batches;
        current = now();
        if (!current || current < start) {
            clock_bad = 1;
            break;
        }
    } while (current - start < 200000000u && batches < 200000);
    sigemptyset(&block);
    sigaddset(&block, SIGALRM);
    if (sigprocmask(SIG_BLOCK, &block, &old_mask))
        return 4;
    memset(&timer, 0, sizeof timer);
    if (setitimer(ITIMER_REAL, &timer, NULL))
        return 4;
    while (sigtimedwait(&block, NULL, &zero) == SIGALRM) { }
    if (sigaction(SIGALRM, &previous, NULL) || sigprocmask(SIG_SETMASK, &old_mask, NULL))
        return 4;
    if (output_bad || clock_bad || bad_mode || bad_scalar ||
        original_fpscr != shortvec_get_fpscr()) {
        printf("{\"status\":\"FAIL\",\"signals\":%d,\"in_vector_window\":%d,"
               "\"bad_handler_mode\":%d,\"bad_handler_scalar\":%d,\"output_bad\":%d,"
               "\"clock_bad\":%d,\"fpscr_before\":\"%08x\",\"fpscr_after\":\"%08x\","
               "\"linux_entry_modeled\":%s,\"raw_entry_vector_modes\":%d}\n",
               (int)arrivals, (int)active_arrivals, (int)bad_mode, (int)bad_scalar,
               output_bad, clock_bad, original_fpscr, shortvec_get_fpscr(),
               model_linux_entry ? "true" : "false", (int)entry_vector_modes);
        return 5;
    }
    if (arrivals < 10 || active_arrivals < 1) {
        printf("{\"status\":\"INCONCLUSIVE\",\"signals\":%d,\"in_vector_window\":%d}\n",
               (int)arrivals, (int)active_arrivals);
        return 6;
    }
    printf("{\"status\":\"PASS\",\"signals\":%d,\"in_vector_window\":%d,"
           "\"batches\":%lu,\"handler_scalar_result_correct\":true,"
           "\"handler_len_stride_clear\":true,\"fpscr_restored\":true,"
           "\"linux_entry_modeled\":%s,\"raw_entry_vector_modes\":%d}\n",
           (int)arrivals, (int)active_arrivals, (unsigned long)batches,
           model_linux_entry ? "true" : "false", (int)entry_vector_modes);
    return 0;
}
