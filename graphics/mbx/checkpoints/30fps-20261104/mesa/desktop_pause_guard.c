/* SPDX-License-Identifier: MIT
 * Independent resume guard for one already-validated pidfd. No PID lookup,
 * desktop discovery or radio/service control belongs in this helper.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <limits.h>
#include <poll.h>
#include <signal.h>
#include <stdlib.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>

static volatile sig_atomic_t interrupted;
static void interrupt_guard(int sig) { interrupted = sig; }
static int send_signal(int fd, int sig)
{ return syscall(SYS_pidfd_send_signal, fd, sig, NULL, 0); }
static double now(void)
{
 struct timespec ts;
 if (clock_gettime(CLOCK_MONOTONIC, &ts)) return -1;
 return ts.tv_sec + ts.tv_nsec / 1e9;
}
static int descriptor(const char *text)
{
 char *end; errno = 0; long value = strtol(text, &end, 10);
 return errno || *end || end == text || value < 0 || value > INT_MAX ? -1 : (int)value;
}
int main(int argc, char **argv)
{
 if (argc != 5) return 2;
 int target = descriptor(argv[1]), control = descriptor(argv[2]), ready = descriptor(argv[3]);
 char *end; double timeout = strtod(argv[4], &end);
 if (target < 0 || control < 0 || ready < 0 || *end || end == argv[4] ||
     !(timeout > 0 && timeout <= 3600)) return 2;
 struct sigaction action = {.sa_handler = interrupt_guard};
 sigemptyset(&action.sa_mask);
 if (sigaction(SIGTERM, &action, NULL) || sigaction(SIGINT, &action, NULL) ||
     sigaction(SIGHUP, &action, NULL)) return 3;
 signal(SIGPIPE, SIG_IGN); /* A dead parent must still resume the target. */
 if (interrupted) return 128 + interrupted;
 int result = 0;
 double deadline = now();
 if (deadline < 0) return 3;
 deadline += timeout;
 if (send_signal(target, SIGSTOP)) return errno == ESRCH ? 0 : 3;
 if (write(ready, "P", 1) != 1) result = 3;
 close(ready);
 struct pollfd watches[2] = {{.fd = control, .events = POLLIN}, {.fd = target, .events = POLLIN}};
 while (!result && !interrupted) {
  double current = now();
  if (current < 0) { result = 3; break; }
  if (current >= deadline) break;
  int wait_ms = (int)((deadline - current) * 1000) + 1;
  int count = poll(watches, 2, wait_ms);
  if (count > 0) break; /* Resume on request, pipe closure or target exit. */
  if (count < 0 && errno != EINTR) { result = 3; break; }
 }
 if (send_signal(target, SIGCONT) && errno != ESRCH) result = 3;
 close(target); close(control);
 return interrupted ? 128 + interrupted : result;
}
