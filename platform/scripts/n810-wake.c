/* Observe input without grabbing it. Display policy only: no system suspend or
 * shutdown. Input wake remains active even when automatic idle blanking is off.
 */
#include <errno.h>
#include <fcntl.h>
#include <glob.h>
#include <linux/input.h>
#include <linux/gpio.h>
#include <linux/kd.h>
#include <poll.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#ifndef INPUT_GLOB
#define INPUT_GLOB "/dev/input/event*"
#endif
#ifndef CONFIG_PATH
#define CONFIG_PATH "/etc/n810-idle.conf"
#endif
#ifndef SCREEN_DIR
#define SCREEN_DIR "/run/n810-screen"
#endif
#ifndef SCREEN_COMMAND
#define SCREEN_COMMAND "/usr/local/sbin/n810-screen"
#endif
#ifndef MODE_COMMAND
#define MODE_COMMAND "/usr/local/sbin/n810-mode"
#endif
#ifndef MENU_COMMAND
#define MENU_COMMAND "/usr/local/sbin/n810-console-power-menu"
#endif
#ifndef ACTIVE_VT_PATH
#define ACTIVE_VT_PATH "/dev/tty0"
#endif
#ifndef GPIO_GLOB
#define GPIO_GLOB "/dev/gpiochip*"
#endif
#define MAX_INPUTS 32
struct device { int fd, kind; char path[512]; };
static struct device devices[MAX_INPUTS];
static int count;
static volatile sig_atomic_t stopping;

static double now(void)
{
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec + t.tv_nsec / 1e9;
}
static void stop(int sig) { (void)sig; stopping = 1; }
static int marker(const char *name)
{
    char path[512];
    snprintf(path, sizeof(path), "%s/%s", SCREEN_DIR, name);
    return access(path, F_OK) == 0;
}
static int command(const char *path, const char *action)
{
    pid_t pid = fork();
    if (pid < 0) { perror("fork"); return -1; }
    if (!pid) {
        execl(path, path, action, (char *)NULL);
        _exit(127);
    }
    int status;
    while (waitpid(pid, &status, 0) < 0) {
        if (errno != EINTR) return -1;
    }
    if (WIFEXITED(status) && !WEXITSTATUS(status)) return 0;
    fprintf(stderr, "%s %s failed\n", path, action);
    return -1;
}
static int screen(const char *action)
{
    return command(SCREEN_COMMAND, action);
}
/* A framebuffer application owns presentation on a graphics VT. */
static int graphics_active(void)
{
    int fd=open(ACTIVE_VT_PATH,O_RDONLY|O_NONBLOCK|O_CLOEXEC);
    if(fd<0) return 0;
    int mode=KD_TEXT;
    int result=ioctl(fd,KDGETMODE,&mode);
    close(fd);
    return result==0 && mode==KD_GRAPHICS;
}
/* Recognize external keyboards by capabilities, independent of product name. */
static int keyboard_device(int fd)
{
    unsigned long keys[(KEY_MAX + 1 + sizeof(unsigned long) * 8 - 1) /
                       (sizeof(unsigned long) * 8)] = {0};
    const unsigned bits = sizeof(unsigned long) * 8;
    if (ioctl(fd, EVIOCGBIT(EV_KEY, sizeof(keys)), keys) < 0) return 0;
    return (keys[KEY_A / bits] & (1UL << (KEY_A % bits))) &&
           (keys[KEY_ENTER / bits] & (1UL << (KEY_ENTER % bits)));
}
static void discover(void)
{
    glob_t paths = {0};
    if (glob(INPUT_GLOB, 0, NULL, &paths)) { globfree(&paths); return; }
    for (size_t i = 0; i < paths.gl_pathc && count < MAX_INPUTS; i++) {
        int found = 0;
        for (int j = 0; j < count; j++)
            if (!strcmp(devices[j].path, paths.gl_pathv[i])) found = 1;
        if (found) continue;
        int fd = open(paths.gl_pathv[i], O_RDONLY | O_NONBLOCK | O_CLOEXEC);
        if (fd < 0) continue;
        char name[128] = {0};
        int kind = 0;
        if (ioctl(fd, EVIOCGNAME(sizeof(name)), name) >= 0) {
            if (!strcmp(name, "Internal keyboard") || !strcmp(name, "LM8323 keypad") ||
                !strcmp(name, "N810 internal keyboard")) kind = 1;
            else if (!strcmp(name, "gpio-keys")) kind = 2;
            else if (!strcmp(name, "retu-pwrbutton")) kind = 3;
            else if (!strcmp(name, "TSC2005 touchscreen")) kind = 4;
            else if (keyboard_device(fd)) kind = 1;
        }
        if (!kind || strlen(paths.gl_pathv[i]) >= sizeof(devices[0].path)) {
            close(fd); continue;
        }
        devices[count].fd = fd;
        devices[count].kind = kind;
        strcpy(devices[count++].path, paths.gl_pathv[i]);
    }
    globfree(&paths);
}
/* N810 kb_lock is active-low GPIO 102: bank 96-127, offset 6.
 * Request only input edges; do not touch pin mux, clocks, or output values. */
static int lock_input(void)
{
    glob_t paths = {0};
    int result = -1;
    if (glob(GPIO_GLOB, 0, NULL, &paths)) { globfree(&paths); return -1; }
    for (size_t i = 0; i < paths.gl_pathc; i++) {
        int fd = open(paths.gl_pathv[i], O_RDONLY | O_CLOEXEC);
        if (fd < 0) continue;
        struct gpiochip_info chip = {0};
        if (!ioctl(fd, GPIO_GET_CHIPINFO_IOCTL, &chip) &&
            !strcmp(chip.label, "gpio-96-127")) {
            struct gpioevent_request request = {
                .lineoffset = 6, .handleflags = GPIOHANDLE_REQUEST_INPUT,
                .eventflags = GPIOEVENT_REQUEST_BOTH_EDGES,
                .consumer_label = "n810-lock"
            };
            if (!ioctl(fd, GPIO_GET_LINEEVENT_IOCTL, &request)) {
                result = request.fd;
                fcntl(result, F_SETFL, O_NONBLOCK);
                fcntl(result, F_SETFD, FD_CLOEXEC);
            } else perror("Lock slider input");
        }
        close(fd);
        if (result >= 0) break;
    }
    globfree(&paths);
    return result;
}
struct lock_debounce {
    double deadline;
    int level, armed;
};
/* Process timestamps as well as live deadlines: display I/O may queue edges. */
static int lock_settle(struct lock_debounce *state, double time)
{
    if (!state->deadline || time < state->deadline) return 0;
    state->deadline = 0;
    if (state->level) { state->armed = 1; return 0; }
    int pressed = state->armed;
    state->armed = 0;
    return pressed;
}
int main(int argc, char **argv)
{
    if (argc == 2 && !strcmp(argv[1], "--version")) { puts("n810-wake 3"); return 0; }
    int trace_lock = argc == 2 && !strcmp(argv[1], "--trace-lock");
    if (argc != 1 && !trace_lock) return 2;
    unsigned enabled = 0, idle_enabled = 0, keyboard_wake = 1, slide_wake = 1;
    unsigned dim_seconds = 60, off_seconds = 300;
    FILE *config = fopen(CONFIG_PATH, "r");
    if (config) {
        char line[256], key[64]; unsigned value;
        while (fgets(line, sizeof(line), config)) {
            if (sscanf(line, " %63[^=]=%u", key, &value) != 2) continue;
            if (!strcmp(key, "enabled")) enabled = value;
            else if (!strcmp(key, "idle_enabled")) idle_enabled = value;
            else if (!strcmp(key, "keyboard_wake")) keyboard_wake = value;
            else if (!strcmp(key, "slide_wake")) slide_wake = value;
            else if (!strcmp(key, "dim_seconds")) dim_seconds = value;
            else if (!strcmp(key, "off_seconds")) off_seconds = value;
        }
        fclose(config);
    }
    if (enabled > 1 || idle_enabled > 1 || keyboard_wake > 1 || slide_wake > 1 || !dim_seconds || off_seconds <= dim_seconds || off_seconds > 86400) {
        fputs("Invalid idle settings\n", stderr); return 2;
    }
    if (!enabled) { puts("Display idle/wake disabled pending hardware validation"); return 0; }
    char inhibit[512];
    snprintf(inhibit, sizeof(inhibit), "%s/power-only", SCREEN_DIR);
    if (keyboard_wake) unlink(inhibit);
    else {
        if (mkdir(SCREEN_DIR, 0755) < 0 && errno != EEXIST) { perror(SCREEN_DIR); return 1; }
        FILE *f = fopen(inhibit, "w");
        if (!f) { perror(inhibit); return 1; }
        fclose(f);
    }
    signal(SIGTERM, stop); signal(SIGINT, stop);
    double activity = now(), scan = 0, power_down = 0, retry = 0;
    struct lock_debounce lock_state = {.level = 1, .armed = 1};
    int lock_fd = lock_input();
    pid_t menu = 0;
    int idle_state = 0;
    while (!stopping) {
        double time = now();
        if (time >= scan) { discover(); scan = time + 2; }
        if (menu && waitpid(menu, NULL, WNOHANG) == menu) {
            menu = 0; activity = time;
        }
        struct pollfd fds[MAX_INPUTS + 1];
        for (int i = 0; i < count; i++) fds[i] = (struct pollfd){devices[i].fd, POLLIN, 0};
        fds[count] = (struct pollfd){lock_fd, POLLIN, 0};
        int timeout = 1000;
        if (lock_state.deadline) {
            double remaining = lock_state.deadline - now();
            timeout = remaining > 0 ? (int)(remaining * 1000) + 1 : 0;
            if (timeout > 1000) timeout = 1000;
        }
        int ready = poll(fds, count + 1, timeout);
        if (ready < 0 && errno != EINTR) { perror("poll"); break; }
        int graphics = graphics_active() && !marker("x11-managed");
        if (graphics) { activity = now(); idle_state = 0; }
        int lock_actions = 0;
        if (fds[count].revents & POLLIN) {
            struct gpioevent_data edge;
            while (read(lock_fd, &edge, sizeof(edge)) == sizeof(edge)) {
                if (edge.id != GPIOEVENT_EVENT_FALLING_EDGE &&
                    edge.id != GPIOEVENT_EVENT_RISING_EDGE) continue;
                double stamp = edge.timestamp / 1e9;
                lock_actions += lock_settle(&lock_state, stamp);
                if (trace_lock) fprintf(stderr, "lock edge %.6f %s\n", stamp,
                    edge.id == GPIOEVENT_EVENT_RISING_EDGE ? "released" : "pressed");
                lock_state.level = edge.id == GPIOEVENT_EVENT_RISING_EDGE;
                lock_state.deadline = stamp + .06;
            }
        }
        lock_actions += lock_settle(&lock_state, now());
        if (!graphics && !marker("quiet-charging")) while (lock_actions-- > 0) {
            const char *action = marker("locked") ? "unlock" : "lock";
            if (trace_lock) fprintf(stderr, "lock action %.6f %s\n", now(), action);
            screen(action);
            activity = now(); idle_state = 0;
        }
        for (int i = count - 1; i >= 0; i--) {
            if (!fds[i].revents) continue;
            struct input_event event;
            ssize_t n;
            while ((n = read(devices[i].fd, &event, sizeof(event))) == sizeof(event)) {
                time = now();
                if (marker("quiet-charging")) {
                    if (devices[i].kind == 3 && event.type == EV_KEY && event.code == KEY_POWER) {
                        if (event.value == 1) power_down = time;
                        if (event.value == 0 && power_down) {
                            double held = time - power_down; power_down = 0;
                            if (held < 1.5 && !command(MODE_COMMAND, "normal")) {
                                activity = now(); idle_state = 0;
                            }
                        }
                    }
                    continue;
                }
                if (graphics) continue;
                int key_input = devices[i].kind == 1 && event.type == EV_KEY && event.value > 0;
                int slide_input = devices[i].kind == 2 && event.type == EV_SW &&
                                  event.code == SW_KEYPAD_SLIDE && event.value == 1;
                /* Touch keeps an already lit GUI active, but never wakes a blank screen. */
                int touch_input = devices[i].kind == 4 && event.type == EV_KEY &&
                                  event.code == BTN_TOUCH && event.value == 1 && !marker("blanked");
                int input = key_input || slide_input || touch_input;
                int wake_input = (key_input && keyboard_wake) || (slide_input && slide_wake);
                if (devices[i].kind == 3 && event.type == EV_KEY && event.code == KEY_POWER) {
                    if (event.value == 1) power_down = time;
                    if (event.value == 0 && power_down) {
                        double held = time - power_down; power_down = 0;
                        if (held < 1.5) {
                            activity = time;
                            if (marker("locked")) {
                                screen(marker("blanked") ? "on" : "off");
                                continue;
                            }
                            if (marker("blanked") || marker("hold")) {
                                if (!screen("on")) idle_state = 0;
                            } else if (!menu) {
                                if (marker("idle-percent") && !screen("on")) idle_state = 0;
                                menu = fork();
                                if (!menu) { execl(MENU_COMMAND, MENU_COMMAND, (char *)NULL); _exit(127); }
                                if (menu < 0) { perror("fork menu"); menu = 0; }
                            }
                        }
                    }
                }
                if (marker("locked")) continue;
                if (devices[i].kind == 1 && event.type == EV_KEY && event.value > 0 &&
                    (event.code == KEY_BRIGHTNESSUP || event.code == KEY_BRIGHTNESSDOWN)) {
                    activity = time;
                    screen(event.code == KEY_BRIGHTNESSUP ? "brighter" : "dimmer");
                }
                if (input) {
                    activity = time;
                    if (!marker("hold") && !marker("blanked") && !marker("idle-percent")) idle_state = 0;
                    if (wake_input && (marker("hold") || marker("blanked") || marker("idle-percent"))) {
                        if (!screen("on")) idle_state = 0;
                    }
                }
            }
            if (!n || (n < 0 && errno != EAGAIN && errno != EINTR)) {
                close(devices[i].fd);
                devices[i] = devices[--count];
            }
        }
        time = now();
        if (marker("quiet-charging") || graphics || !idle_enabled || menu || marker("hold") || time < retry) continue;
        const char *action = NULL;
        int next = idle_state;
        if (time - activity >= off_seconds && idle_state < 2) { action = "blank"; next = 2; }
        else if (time - activity >= dim_seconds && idle_state < 1) { action = "dim"; next = 1; }
        if (action) {
            if (!screen(action)) idle_state = next;
            else retry = time + 5;
        }
    }
    unlink(inhibit);
    if (lock_fd >= 0) close(lock_fd);
    for (int i = 0; i < count; i++) close(devices[i].fd);
    return stopping ? 0 : 1;
}
