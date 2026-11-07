/* Event-driven X11 app rail. Matchbox owns window placement. */
#define _POSIX_C_SOURCE 200809L
#include <X11/Xlib.h>
#include <X11/Xatom.h>
#include <X11/keysym.h>
#include <stdbool.h>
#include <fcntl.h>
#include <errno.h>
#include <poll.h>
#include <sys/inotify.h>
#include <signal.h>
#include <unistd.h>
#include <time.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define LIMIT 64
#define WIDTH 48
#define ROW 48
#ifndef SCREEN_DIR
#define SCREEN_DIR "/run/n810-screen"
#endif
static Display *d;
static Window root, rail, dock, clients[LIMIT];
static Atom list_atom, active_atom, close_atom;
static Window pressed_window, action_window;
static bool actions;
static Time pressed_time;
static int pressed_x, pressed_y;
static GC gc;
static unsigned long background, highlight, foreground;
static unsigned count, selected, first, rows;
static int height, wifi_bars;
static bool wifi_connected;
static time_t next_status;
static char clock_text[8], battery_text[8];
static bool visible, pinned, choosing, picker, locked, screen_off;
static const char *screen_dir;
static char locked_path[1024], blanked_path[1024];
struct app { const char *label, *command; };
static const struct app apps[] = {
    {"Term", NULL}, {"Files", "pcmanfm"}, {"Thunar", "thunar"}, {"MC", "mc"}, {"Web", "dillo"},
    {"TextWeb", "n810-media"}, {"Mesh", "nomadnet"}, {"Gopher", "n810-gopher"}, {"Chat", "irssi"},
    {"Mail", "neomutt"}, {"Setup", "n810-setup"}, {"Console", "n810-gui"}, {"End GUI", "n810-gui"}
};
static unsigned available_apps[sizeof apps / sizeof apps[0]], app_count;
static bool installed(const char *name)
{
    const char *dirs[] = {"/usr/local/bin", "/usr/bin", "/bin"};
    char path[256];
    for (unsigned i=0; i<sizeof dirs/sizeof dirs[0]; i++) {
        snprintf(path, sizeof path, "%s/%s", dirs[i], name);
        if (!access(path, X_OK)) return true;
    }
    return false;
}
static unsigned entries(void) { return actions ? 2 : picker ? app_count : count+1; }
static void launch(unsigned index)
{
    const struct app *app = &apps[available_apps[index]];
    pid_t pid = fork();
    if (pid < 0) { perror("launch"); return; }
    if (pid) return;
    setsid();
    if (!app->command)
        execlp("xterm", "xterm", "-title", "Terminal", (char *)NULL);
    else if (!strcmp(app->command, "n810-gui"))
        execlp("n810-gui", "n810-gui", !strcmp(app->label, "Console") ? "console" : "stop", (char *)NULL);
    else if (!strcmp(app->command, "dillo"))
        execlp("dillo", "dillo", "/usr/local/share/n810/n810-web-start.html", (char *)NULL);
    else if (!strcmp(app->command, "netsurf-fb"))
        execlp("netsurf-fb", "netsurf-fb", "-f", "x", "file:///usr/local/share/n810/n810-web-start.html", (char *)NULL);
    else if (!strcmp(app->command, "pcmanfm") || !strcmp(app->command, "thunar"))
        execlp(app->command, app->command, (char *)NULL);
    else if (!strcmp(app->command, "mc"))
        execlp("xterm", "xterm", "-title", "Files", "-e", "mc", "-x", "-u", (char *)NULL);
    else if (!strcmp(app->command, "n810-media"))
        execlp("xterm", "xterm", "-title", "Web", "-e", "n810-media", "web", (char *)NULL);
    else
        execlp("xterm", "xterm", "-title", app->label, "-e", app->command, (char *)NULL);
    perror("xterm"); _exit(127);
}
static unsigned long color(unsigned rgb)
{
    XColor value = {.red=((rgb >> 16) & 255) * 257,
                    .green=((rgb >> 8) & 255) * 257, .blue=(rgb & 255) * 257};
    if (!XAllocColor(d, DefaultColormap(d, DefaultScreen(d)), &value)) {
        fputs("Cannot allocate rail color.\n", stderr); exit(1);
    }
    return value.pixel;
}
static int xerror(Display *display, XErrorEvent *error)
{
    (void)display;
    /* Client windows may disappear between enumeration and drawing. */
    if (error->error_code == BadWindow || error->error_code == BadDrawable) return 0;
    char message[128]; XGetErrorText(d, error->error_code, message, sizeof message);
    fprintf(stderr, "n810-rail: %s\n", message);
    exit(1);
}
static unsigned windows(Window *out)
{
    Atom type; int format; unsigned long n, left; unsigned char *data = NULL;
    unsigned result = 0;
    if (XGetWindowProperty(d, root, list_atom, 0, LIMIT, False, XA_WINDOW,
                          &type, &format, &n, &left, &data) == Success &&
        type == XA_WINDOW && format == 32 && data) {
        for (unsigned long i = 0; i < n && result < LIMIT; i++) {
            Window w = ((Window *)data)[i];
            if (w != rail && w != dock) out[result++] = w;
        }
    }
    if (data) XFree(data);
    return result;
}
static Window active(void)
{
    Atom type; int format; unsigned long n, left; unsigned char *data = NULL;
    Window w = None;
    if (XGetWindowProperty(d, root, active_atom, 0, 1, False, XA_WINDOW,
                          &type, &format, &n, &left, &data) == Success &&
        type == XA_WINDOW && format == 32 && n == 1 && data) w = *(Window *)data;
    if (data) XFree(data);
    return w;
}
static void update_status(void)
{
    time_t now = time(NULL);
    if (now < next_status) return;
    struct tm local;
    if (localtime_r(&now, &local)) strftime(clock_text, sizeof clock_text, "%H:%M", &local);
    else snprintf(clock_text, sizeof clock_text, "--:--");
    snprintf(battery_text, sizeof battery_text, "--%%");
    const char *battery = getenv("N810_GUI_BATTERY");
    if (!battery) battery = "/sys/class/power_supply/n8x0-battery";
    char path[512], status[32] = "";
    int capacity = -1;
    if (snprintf(path, sizeof path, "%s/capacity", battery) < (int)sizeof path) {
        FILE *f = fopen(path, "r");
        if (f) { if (fscanf(f, "%d", &capacity) != 1) capacity = -1; fclose(f); }
    }
    if (snprintf(path, sizeof path, "%s/status", battery) < (int)sizeof path) {
        FILE *f = fopen(path, "r");
        if (f) { if (!fgets(status, sizeof status, f)) status[0] = 0; fclose(f); }
    }
    if (capacity >= 0 && capacity <= 100)
        snprintf(battery_text, sizeof battery_text, "%d%%%s", capacity,
                 !strncmp(status, "Charging", 8) ? "+" : "");
    wifi_bars = 0; wifi_connected = false;
    FILE *net = fopen("/sys/class/net/wlan0/carrier", "r");
    int carrier = 0;
    if (net) { if (fscanf(net, "%d", &carrier) != 1) carrier = 0; fclose(net); }
    if (carrier) {
        net = fopen("/proc/net/wireless", "r");
        if (net) {
            char line[256];
            while (fgets(line, sizeof line, net)) {
                char *iface = strstr(line, "wlan0:");
                float quality, level;
                if (iface && sscanf(iface + 6, "%*x %f %f", &quality, &level) == 2) {
                    wifi_connected = true;
                    wifi_bars = level >= -50 ? 3 : level >= -65 ? 2 : 1;
                    break;
                }
            }
            fclose(net);
        }
    }
    next_status = now - now % 60 + 60;
}
static void draw(void)
{
    if (!locked && !screen_off) update_status();
    XClearWindow(d, rail);
    if (selected < first) first = selected;
    if (selected >= first + rows) first = selected - rows + 1;
    Window current = active();
    for (unsigned i = first; i < entries() && i < first + rows; i++) {
        int y = (int)(i - first) * ROW;
        if (choosing && i == selected) {
            XSetForeground(d, gc, highlight);
            XFillRectangle(d, rail, gc, 0, y, WIDTH, ROW);
        }
        if (!picker && !actions && i < count && clients[i] == current) {
            XSetForeground(d, gc, foreground);
            XFillRectangle(d, rail, gc, 0, y + 8, 2, ROW - 16);
        }
        char *name = NULL, label[8];
        if (actions) snprintf(label, sizeof label, "%s", i ? "Close" : "Show");
        else if (picker) snprintf(label, sizeof label, "%.7s", apps[available_apps[i]].label);
        else if (i == count) snprintf(label, sizeof label, "+");
        else {
            XFetchName(d, clients[i], &name);
            snprintf(label, sizeof label, "%.6s", name && !strcmp(name, "Terminal") ? ">_" : name ? name : "App");
            if (name) XFree(name);
        }
        /* Core font labels stay bounded and avoid per-app icon dependencies. */
        XSetForeground(d, gc, foreground);
        XDrawString(d, rail, gc, 4, y + 28, label, (int)strlen(label));
    }

    XSetForeground(d, gc, foreground);
    XDrawLine(d, rail, gc, 4, height - ROW, WIDTH - 4, height - ROW);
    XDrawString(d, rail, gc, 4, height - 28, clock_text, (int)strlen(clock_text));
    XDrawString(d, rail, gc, 4, height - 10, battery_text, (int)strlen(battery_text));
    if (wifi_connected) {
        for (int i=0; i<3; i++) {
            int h=3*(i+1), x=36+4*i, y=height-10-h;
            if (i<wifi_bars) XFillRectangle(d, rail, gc, x, y, 2, (unsigned)h);
            else XDrawRectangle(d, rail, gc, x, y, 1, (unsigned)h-1);
        }
    } else {
        XDrawLine(d, rail, gc, 36, height-18, 45, height-10);
        XDrawLine(d, rail, gc, 36, height-10, 45, height-18);
    }
    XFlush(d);
}
static void refresh(void)
{
    count = windows(clients);
    if (selected >= entries()) selected = 0;
    if (visible) draw();
}
static void dismiss(void)
{
    XUngrabKeyboard(d, CurrentTime); choosing = picker = actions = false;
    if (!pinned) { XUnmapWindow(d, rail); visible = false; }
    else { selected = first = 0; refresh(); }
}
static void show(void)
{
    next_status = 0;
    count = windows(clients); selected = first = 0; picker = false;
    Window current = active();
    for (unsigned i = 0; i < count; i++) if (clients[i] == current) selected = i;
    XMapRaised(d, rail); visible = true;
    if (XGrabKeyboard(d, rail, False, GrabModeAsync, GrabModeAsync,
                      CurrentTime) != GrabSuccess) { dismiss(); return; }
    choosing = true; draw();
}
/* Observe shared policy; never own charging, shutdown or idle timers. */
static void sync_lock(void)
{
    screen_off = access(blanked_path, F_OK) == 0;
    if (screen_off) pressed_window = None;
    bool next = access(locked_path, F_OK) == 0;
    if (next == locked) return;
    if (next) {
        pressed_window = None;
        dismiss();
        int keyboard = XGrabKeyboard(d, root, False, GrabModeAsync, GrabModeAsync, CurrentTime);
        int pointer = XGrabPointer(d, root, False, 0, GrabModeAsync, GrabModeAsync,
                                   None, None, CurrentTime);
        if (keyboard != GrabSuccess || pointer != GrabSuccess) {
            fputs("Cannot inhibit GUI input while locked.\n", stderr); exit(1);
        }
    } else {
        XUngrabKeyboard(d, CurrentTime); XUngrabPointer(d, CurrentTime);
    }
    locked = next; XFlush(d);
}
static void toggle_rail(void)
{
    pinned = !pinned; next_status = 0;
    if (pinned) { XMapWindow(d, dock); XMapRaised(d, rail); visible = true; }
    else XUnmapWindow(d, dock);
    dismiss();
    XFlush(d);
}
static void message(Window w, Atom atom, long a, long b, long c)
{
    XEvent e = {0}; e.xclient.type = ClientMessage; e.xclient.window = w;
    e.xclient.message_type = atom; e.xclient.format = 32;
    e.xclient.data.l[0] = a; e.xclient.data.l[1] = b; e.xclient.data.l[2] = c;
    XSendEvent(d, root, False, SubstructureRedirectMask | SubstructureNotifyMask, &e);
    XFlush(d);
}
static void app_actions(Window w)
{
    action_window = w; actions = true; picker = false; selected = first = 0;
    if (!choosing) {
        if (XGrabKeyboard(d, rail, False, GrabModeAsync, GrabModeAsync,
                          CurrentTime) != GrabSuccess) { dismiss(); return; }
        choosing = true;
    }
    draw();
}
static void choose(void)
{
    if (actions) {
        Window w = action_window; bool close = selected == 1;
        dismiss(); message(w, close ? close_atom : active_atom,
                           close ? CurrentTime : 2, close ? 2 : CurrentTime, 0);
        return;
    }
    if (!picker && selected == count) {
        picker = true; selected = first = 0;
        if (!choosing) {
            if (XGrabKeyboard(d, rail, False, GrabModeAsync, GrabModeAsync,
                              CurrentTime) != GrabSuccess) { dismiss(); return; }
            choosing = true;
        }
        draw(); return;
    }
    if (picker) { unsigned app = selected; dismiss(); launch(app); return; }
    Window w = clients[selected];
    dismiss();
    message(w, active_atom, 2, CurrentTime, 0);
}
int main(void)
{
    screen_dir = getenv("N810_SCREEN_RUN_DIR");
    if (!screen_dir) screen_dir = SCREEN_DIR;
    if (snprintf(locked_path, sizeof locked_path, "%s/locked", screen_dir) >= (int)sizeof locked_path) {
        fputs("Display policy path too long.\n", stderr); return 1;
    }
    if (snprintf(blanked_path, sizeof blanked_path, "%s/blanked", screen_dir) >= (int)sizeof blanked_path) return 1;
    d = XOpenDisplay(NULL); if (!d) { fputs("Cannot open X display.\n", stderr); return 1; }
    signal(SIGCHLD, SIG_IGN);
    fcntl(ConnectionNumber(d), F_SETFD, FD_CLOEXEC);
    XSetErrorHandler(xerror); root = DefaultRootWindow(d);
    list_atom = XInternAtom(d, "_NET_CLIENT_LIST", False);
    active_atom = XInternAtom(d, "_NET_ACTIVE_WINDOW", False);
    close_atom = XInternAtom(d, "_NET_CLOSE_WINDOW", False);
    XSelectInput(d, root, PropertyChangeMask);
    for (unsigned i=0; i<sizeof apps/sizeof apps[0]; i++)
        if (installed("xterm") && (!apps[i].command || installed(apps[i].command)) &&
            (strcmp(apps[i].label, "TextWeb") || installed("w3m")))
            available_apps[app_count++] = i;
    if (!app_count) { fputs("Missing xterm.\n", stderr); return 1; }
    height = DisplayHeight(d, DefaultScreen(d)); rows = (unsigned)(height - ROW) / ROW;
    if (!rows) rows = 1;
    background=color(0x23313b); highlight=color(0x355266); foreground=color(0xe0e8ed);
    XSetWindowAttributes attrs = {.override_redirect=True, .background_pixel=background,
        .event_mask=ExposureMask | KeyPressMask | ButtonPressMask | ButtonReleaseMask | PointerMotionMask};
    rail = XCreateWindow(d, root, 0, 0, WIDTH, (unsigned)height, 0, CopyFromParent,
                        InputOutput, CopyFromParent, CWOverrideRedirect | CWBackPixel | CWEventMask, &attrs);
    dock = XCreateSimpleWindow(d, root, 0, 0, WIDTH, (unsigned)height, 0, background, background);
    Atom dock_type = XInternAtom(d, "_NET_WM_WINDOW_TYPE_DOCK", False);
    XChangeProperty(d, dock, XInternAtom(d, "_NET_WM_WINDOW_TYPE", False), XA_ATOM,
                    32, PropModeReplace, (unsigned char *)&dock_type, 1);
    unsigned long strut[4] = {WIDTH, 0, 0, 0};
    XChangeProperty(d, dock, XInternAtom(d, "_NET_WM_STRUT", False), XA_CARDINAL,
                    32, PropModeReplace, (unsigned char *)strut, 4);
    XStoreName(d, dock, "N810 rail space");
    XStoreName(d, rail, "N810 app switcher"); gc = XCreateGC(d, rail, 0, NULL);
    XFontStruct *font = XLoadQueryFont(d, "fixed");
    if (!font) { fputs("Missing fixed X font.\n", stderr); return 1; }
    XSetFont(d, gc, font->fid);
    const KeySym shortcuts[] = {XK_F11, XK_F14, XK_F15};
    for (size_t i = 0; i < sizeof(shortcuts) / sizeof(shortcuts[0]); i++) {
        KeySym key = shortcuts[i];
        KeyCode code = XKeysymToKeycode(d, (KeySym)key);
        if (!code) { fputs("Missing hardware key mapping.\n", stderr); return 1; }
        XGrabKey(d, code, AnyModifier, root, False, GrabModeAsync, GrabModeAsync);
    }
    XSync(d, False);
    int lock_fd = inotify_init1(IN_NONBLOCK | IN_CLOEXEC);
    if (lock_fd < 0 || inotify_add_watch(lock_fd, screen_dir,
            IN_CREATE | IN_DELETE | IN_MOVED_FROM | IN_MOVED_TO) < 0) {
        perror("Watch display policy"); return 1;
    }
    sync_lock();
    for (;;) {
        if (!XPending(d)) {
            struct pollfd fds[2] = {{ConnectionNumber(d), POLLIN, 0}, {lock_fd, POLLIN, 0}};
            int timeout = -1;
            if (visible && !locked && !screen_off) {
                time_t remaining = next_status - time(NULL);
                timeout = remaining > 0 ? (int)remaining * 1000 : 0;
            }
            int ready = poll(fds, 2, timeout);
            if (!ready) { draw(); continue; }
            if (ready < 0) {
                if (errno == EINTR) continue;
                perror("poll"); return 1;
            }
            if (fds[1].revents & POLLIN) {
                char events[4096];
                while (read(lock_fd, events, sizeof events) > 0) {}
                sync_lock();
            }
            if (!(fds[0].revents & POLLIN)) continue;
        }
        XEvent e; XNextEvent(d, &e);
        if (e.type == PropertyNotify && e.xproperty.window == root &&
            (e.xproperty.atom == list_atom || e.xproperty.atom == active_atom)) refresh();
        else if (e.type == Expose && visible) draw();
        else if (e.type == ButtonPress && visible && !locked) {
            unsigned i = first + (unsigned)e.xbutton.y / ROW;
            if (e.xbutton.button == Button3 && !picker && !actions &&
                e.xbutton.y >= 0 && e.xbutton.y < (int)rows * ROW && i < count) {
                pressed_window = None; app_actions(clients[i]);
            } else if (e.xbutton.button == Button1 && e.xbutton.y >= 0 &&
                e.xbutton.y < (int)rows * ROW && i < entries()) {
                selected = i;
                if (actions || picker || i == count) choose();
                else {
                    pressed_window = clients[i]; pressed_time = e.xbutton.time;
                    pressed_x = e.xbutton.x; pressed_y = e.xbutton.y;
                }
            }
        } else if (e.type == MotionNotify && pressed_window) {
            if (abs(e.xmotion.x - pressed_x) > 12 || abs(e.xmotion.y - pressed_y) > 12)
                pressed_window = None;
        } else if (e.type == ButtonRelease && e.xbutton.button == Button1 && pressed_window) {
            Window w = pressed_window; pressed_window = None;
            if (locked || screen_off || !visible) continue;
            unsigned long held = (e.xbutton.time - pressed_time) & 0xffffffffUL;
            if (held >= 800) app_actions(w);
            else { dismiss(); message(w, active_atom, 2, e.xbutton.time, 0); }
        } else if (e.type == KeyPress && !locked) {
            pressed_window = None;
            KeySym key = XLookupKeysym(&e.xkey, 0);
            if (key == XK_F11 || key == XK_F15) toggle_rail();
            else if (key == XK_F14) { if (choosing) choose(); else show(); }
            else if (choosing) {
                if (key == XK_Escape) {
                    if (picker) { picker = false; selected = first = 0; refresh(); }
                    else dismiss();
                } else if (key == XK_Return || key == XK_KP_Enter) choose();
                else if (key == XK_F16 || key == XK_Right || key == XK_Down) {
                    selected = (selected + 1) % entries(); draw();
                } else if (key == XK_F17 || key == XK_Left || key == XK_Up) {
                    selected = (selected + entries() - 1) % entries(); draw();
                }
            }
        }
    }
}
