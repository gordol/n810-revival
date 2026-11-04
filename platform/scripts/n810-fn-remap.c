#define _GNU_SOURCE

#include <errno.h>
#include <fcntl.h>
#include <glob.h>
#include <linux/input.h>
#include <linux/uinput.h>
#include <signal.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

#define BITS_PER_LONG (sizeof(unsigned long) * 8)
#define NBITS(x) ((((x) - 1) / BITS_PER_LONG) + 1)

static volatile sig_atomic_t stopping;
#ifndef SCREEN_RUN
#define SCREEN_RUN "/run/n810-screen"
#endif
static bool emitted_keys[KEY_MAX + 1], blocked_keys[KEY_MAX + 1];

struct chord {
	unsigned short from;
	unsigned short plain;
	bool plain_shift;
	unsigned short with_shift;
	bool with_shift_shift;
};

/* Symbols follow the legends and the agreed programmer layer. */
static const struct chord chords[] = {
	{ KEY_Q, KEY_1, false, KEY_1, false },
	{ KEY_W, KEY_2, false, KEY_2, false },
	{ KEY_E, KEY_3, false, KEY_3, false },
	{ KEY_R, KEY_4, false, KEY_4, false },
	{ KEY_T, KEY_5, false, KEY_5, false },
	{ KEY_Y, KEY_6, false, KEY_6, false },
	{ KEY_U, KEY_7, false, KEY_7, false },
	{ KEY_I, KEY_8, false, KEY_8, false },
	{ KEY_O, KEY_9, false, KEY_9, false },
	{ KEY_P, KEY_0, false, KEY_0, false },
	{ KEY_A, KEY_1, true, KEY_1, true },
	{ KEY_S, KEY_APOSTROPHE, true, KEY_APOSTROPHE, true },
	{ KEY_D, KEY_2, true, KEY_2, true },
	{ KEY_F, KEY_3, true, KEY_3, true },
	{ KEY_G, KEY_BACKSLASH, false, KEY_LEFTBRACE, true },
	{ KEY_H, KEY_SLASH, false, KEY_RIGHTBRACE, true },
	{ KEY_J, KEY_9, true, KEY_LEFTBRACE, false },
	{ KEY_K, KEY_0, true, KEY_RIGHTBRACE, false },
	{ KEY_L, KEY_8, true, KEY_8, true },
	{ KEY_SEMICOLON, KEY_BACKSLASH, true, KEY_BACKSLASH, true },
	{ KEY_APOSTROPHE, KEY_SLASH, true, KEY_SLASH, true },
	{ KEY_Z, KEY_GRAVE, false, KEY_GRAVE, true },
	{ KEY_X, KEY_6, true, KEY_6, true },
	{ KEY_C, KEY_GRAVE, true, KEY_GRAVE, true },
	{ KEY_V, KEY_5, true, KEY_5, true },
	{ KEY_B, KEY_7, true, KEY_7, true },
	{ KEY_N, KEY_4, true, KEY_4, true },
	{ KEY_M, KEY_BACKSLASH, true, KEY_BACKSLASH, true },
	{ KEY_COMMA, KEY_COMMA, true, KEY_COMMA, true },
	{ KEY_DOT, KEY_DOT, true, KEY_DOT, true },
	{ KEY_MINUS, KEY_MINUS, true, KEY_MINUS, true },
	{ KEY_EQUAL, KEY_EQUAL, false, KEY_EQUAL, false },
	{ KEY_BACKSPACE, KEY_DELETE, false, KEY_DELETE, false },
	{ KEY_ENTER, KEY_ENTER, false, KEY_ENTER, false },
	{ KEY_SPACE, KEY_TAB, false, KEY_TAB, false },
	{ KEY_UP, KEY_PAGEUP, false, KEY_PAGEUP, false },
	{ KEY_DOWN, KEY_PAGEDOWN, false, KEY_PAGEDOWN, false },
	{ KEY_LEFT, KEY_HOME, false, KEY_HOME, false },
	{ KEY_RIGHT, KEY_END, false, KEY_END, false },
};

struct active_chord {
	unsigned short target;
	bool shifted;
};

struct remap_state {
	bool fn;
	bool fullscreen, fullscreen_used;
	unsigned char brightness_held;
	bool left_shift;
	bool right_shift;
	struct active_chord active[KEY_MAX + 1];
};

static void handle_signal(int signal_number)
{
	(void)signal_number;
	stopping = 1;
}

static bool bit_is_set(const unsigned long *bits, unsigned int bit)
{
	return bits[bit / BITS_PER_LONG] & (1UL << (bit % BITS_PER_LONG));
}

static const struct chord *find_chord(unsigned short code)
{
	size_t i;

	for (i = 0; i < sizeof(chords) / sizeof(chords[0]); i++)
		if (chords[i].from == code)
			return &chords[i];
	return NULL;
}

static int find_internal_keyboard(char *path, size_t path_size,
				  char *name, size_t name_size)
{
	glob_t paths = {0};
	size_t i;
	int fd = -1;

	if (glob("/dev/input/event*", 0, NULL, &paths) != 0)
		return -1;
	for (i = 0; i < paths.gl_pathc; i++) {
		char candidate_name[256] = {0};
		char phys[256] = {0};
		int candidate = open(paths.gl_pathv[i], O_RDONLY | O_CLOEXEC);

		if (candidate < 0)
			continue;
		if (ioctl(candidate, EVIOCGNAME(sizeof(candidate_name)),
			  candidate_name) >= 0 &&
		    ioctl(candidate, EVIOCGPHYS(sizeof(phys)), phys) >= 0 &&
		    (!strcmp(candidate_name, "Internal keyboard") ||
		     !strcmp(candidate_name, "LM8323 keypad")) &&
		    strstr(phys, "/input-kp") != NULL) {
			if (strlen(paths.gl_pathv[i]) >= path_size ||
			    strlen(candidate_name) >= name_size) {
				close(candidate);
				errno = ENAMETOOLONG;
				break;
			}
			strcpy(path, paths.gl_pathv[i]);
			strcpy(name, candidate_name);
			fd = candidate;
			break;
		}
		close(candidate);
	}
	globfree(&paths);
	return fd;
}

static int verify_source(int fd)
{
	unsigned long keys[NBITS(KEY_MAX + 1)] = {0};
	size_t i;

	if (ioctl(fd, EVIOCGBIT(EV_KEY, sizeof(keys)), keys) < 0)
		return -1;
	if (!bit_is_set(keys, KEY_F20) || !bit_is_set(keys, KEY_ESC)) {
		fputs("Internal Fn/F20 or Back/Escape key is unavailable\n", stderr);
		errno = ENODEV;
		return -1;
	}
	for (i = 0; i < sizeof(chords) / sizeof(chords[0]); i++)
		if (!bit_is_set(keys, chords[i].from)) {
			fprintf(stderr, "Internal keyboard lacks key code %u\n",
				chords[i].from);
			errno = ENODEV;
			return -1;
		}
	return 0;
}

static int create_virtual_keyboard(int source_fd)
{
	unsigned long keys[NBITS(KEY_MAX + 1)] = {0};
	struct input_id source_id = {0};
	struct uinput_setup setup = {0};
	unsigned int code;
	size_t i;
	int fd;

	fd = open("/dev/uinput", O_WRONLY | O_NONBLOCK | O_CLOEXEC);
	if (fd < 0)
		return -1;
	if (ioctl(source_fd, EVIOCGBIT(EV_KEY, sizeof(keys)), keys) < 0 ||
	    ioctl(source_fd, EVIOCGID, &source_id) < 0 ||
	    ioctl(fd, UI_SET_EVBIT, EV_KEY) < 0 ||
	    ioctl(fd, UI_SET_EVBIT, EV_SYN) < 0)
		goto fail;
	for (code = 1; code <= KEY_MAX; code++)
		if (bit_is_set(keys, code) && ioctl(fd, UI_SET_KEYBIT, code) < 0)
			goto fail;
	for (i = 0; i < sizeof(chords) / sizeof(chords[0]); i++)
		if (ioctl(fd, UI_SET_KEYBIT, chords[i].plain) < 0 ||
		    ioctl(fd, UI_SET_KEYBIT, chords[i].with_shift) < 0)
			goto fail;
	if (ioctl(fd, UI_SET_KEYBIT, KEY_BRIGHTNESSUP) < 0 ||
	    ioctl(fd, UI_SET_KEYBIT, KEY_BRIGHTNESSDOWN) < 0 ||
	    ioctl(fd, UI_SET_KEYBIT, KEY_LEFTSHIFT) < 0)
		goto fail;

	setup.id = source_id;
	setup.id.version++;
	strcpy(setup.name, "N810 internal keyboard");
	if (ioctl(fd, UI_DEV_SETUP, &setup) < 0 || ioctl(fd, UI_DEV_CREATE) < 0)
		goto fail;
	return fd;

fail:
	close(fd);
	return -1;
}

static int emit_event(int fd, unsigned short type, unsigned short code, int value)
{
	struct input_event event = {0};
	const char *buffer = (const char *)&event;
	size_t remaining = sizeof(event);

	event.type = type;
	event.code = code;
	event.value = value;
	while (remaining > 0) {
		ssize_t written = write(fd, buffer, remaining);

		if (written < 0 && errno == EINTR)
			continue;
		if (written <= 0)
			return -1;
		buffer += written;
		remaining -= (size_t)written;
	}
	if (type == EV_KEY && code <= KEY_MAX) emitted_keys[code] = value != 0;
	return 0;
}

static int emit_key_with_shift(int fd, const struct remap_state *state,
			       unsigned short code, bool shifted, int value)
{
	bool physical_shift = state->left_shift || state->right_shift;

	if (!shifted && state->left_shift && emit_event(fd, EV_KEY, KEY_LEFTSHIFT, 0) < 0)
		return -1;
	if (!shifted && state->right_shift && emit_event(fd, EV_KEY, KEY_RIGHTSHIFT, 0) < 0)
		return -1;
	if (shifted && !physical_shift && emit_event(fd, EV_KEY, KEY_LEFTSHIFT, 1) < 0)
		return -1;
	if (emit_event(fd, EV_KEY, code, value) < 0)
		return -1;
	if (shifted && !physical_shift && emit_event(fd, EV_KEY, KEY_LEFTSHIFT, 0) < 0)
		return -1;
	if (!shifted && state->left_shift && emit_event(fd, EV_KEY, KEY_LEFTSHIFT, 1) < 0)
		return -1;
	if (!shifted && state->right_shift && emit_event(fd, EV_KEY, KEY_RIGHTSHIFT, 1) < 0)
		return -1;
	return 0;
}

static int handle_key(int fd, struct remap_state *state,
		      unsigned short code, int value)
{
	const struct chord *chord;
	bool physical_shift;

	/* In Power/slide-only wake mode, suppress console input while off.
	 * Release already emitted keys and consume blocked releases after wake. */
	if (code <= KEY_MAX && blocked_keys[code]) {
		if (value == 0) blocked_keys[code] = false;
		return 0;
	}
	if (access(SCREEN_RUN "/quiet-charging", F_OK) == 0 ||
	    access(SCREEN_RUN "/locked", F_OK) == 0 ||
	    (access(SCREEN_RUN "/power-only", F_OK) == 0 &&
	     (access(SCREEN_RUN "/blanked", F_OK) == 0 || access(SCREEN_RUN "/hold", F_OK) == 0))) {
		if (code <= KEY_MAX) blocked_keys[code] = value != 0;
		for (unsigned short key = 1; key <= KEY_MAX; key++)
			if (emitted_keys[key] && emit_event(fd, EV_KEY, key, 0) < 0) return -1;
		memset(state, 0, sizeof(*state));
		return 0;
	}
	/* Fullscreen alone is emitted on release. Brightness chords never reach
	 * tmux as fullscreen/zoom buttons; release ordering cannot leak a key. */
	if (code == KEY_F15) {
		if (value == 1) { state->fullscreen = true; state->fullscreen_used = false; }
		if (value == 0) {
			state->fullscreen = false;
			if (!state->fullscreen_used) {
				if (emit_event(fd, EV_KEY, KEY_F15, 1) < 0) return -1;
				return emit_event(fd, EV_KEY, KEY_F15, 0);
			}
		}
		return 0;
	}
	if (code == KEY_F16 || code == KEY_F17) {
		unsigned char bit = code == KEY_F16 ? 1 : 2;
		unsigned short target = code == KEY_F16 ? KEY_BRIGHTNESSUP : KEY_BRIGHTNESSDOWN;
		if (value == 1 && state->fullscreen) {
			state->brightness_held |= bit;
			state->fullscreen_used = true;
		}
		if (state->brightness_held & bit) {
			if (value == 0) state->brightness_held &= ~bit;
			return emit_event(fd, EV_KEY, target, value);
		}
	}
	if (code == KEY_F20) {
		state->fn = value != 0;
		return 0;
	}
	if (code == KEY_LEFTSHIFT)
		state->left_shift = value != 0;
	else if (code == KEY_RIGHTSHIFT)
		state->right_shift = value != 0;

	if (code <= KEY_MAX && state->active[code].target != 0) {
		struct active_chord active = state->active[code];

		if (value == 0)
			state->active[code].target = 0;
		return emit_key_with_shift(fd, state, active.target,
					   active.shifted, value);
	}
	/* The N810 legend is plain +, blue Fn =. External keyboards bypass us. */
	static const struct chord plus_key = { KEY_EQUAL, KEY_EQUAL, true, KEY_EQUAL, true };
	chord = state->fn ? find_chord(code) : (code == KEY_EQUAL ? &plus_key : NULL);
	if (chord == NULL)
		return emit_event(fd, EV_KEY, code, value);
	if (value == 0)
		return 0;

	physical_shift = state->left_shift || state->right_shift;
	state->active[code].target = physical_shift ? chord->with_shift : chord->plain;
	state->active[code].shifted = physical_shift ? chord->with_shift_shift :
		chord->plain_shift;
	return emit_key_with_shift(fd, state, state->active[code].target,
				   state->active[code].shifted, value);
}

static int self_test(void)
{
	const struct chord *chord;
	struct input_event events[3];
	struct remap_state state = {0};
	int pipe_fds[2];
	size_t i, j;

	for (i = 0; i < sizeof(chords) / sizeof(chords[0]); i++) {
		if (chords[i].from == 0 || chords[i].plain == 0 ||
		    chords[i].with_shift == 0)
			return 1;
		for (j = i + 1; j < sizeof(chords) / sizeof(chords[0]); j++)
			if (chords[i].from == chords[j].from)
				return 1;
	}
	chord = find_chord(KEY_M);
	if (chord == NULL || chord->plain != KEY_BACKSLASH || !chord->plain_shift)
		return 1;
	chord = find_chord(KEY_Z);
	if (chord == NULL || chord->plain != KEY_GRAVE || chord->plain_shift ||
	    chord->with_shift != KEY_GRAVE || !chord->with_shift_shift)
		return 1;
	chord = find_chord(KEY_SPACE);
	if (chord == NULL || chord->plain != KEY_TAB || chord->plain_shift)
		return 1;
	if (find_chord(KEY_ESC) != NULL)
		return 1;

	/* Exercise the event transform without uinput or hardware. */
	if (pipe(pipe_fds) < 0)
		return 1;
	state.fn = true;
	if (handle_key(pipe_fds[1], &state, KEY_M, 1) < 0 ||
	    read(pipe_fds[0], events, sizeof(events)) != (ssize_t)sizeof(events) ||
	    events[0].code != KEY_LEFTSHIFT || events[0].value != 1 ||
	    events[1].code != KEY_BACKSLASH || events[1].value != 1 ||
	    events[2].code != KEY_LEFTSHIFT || events[2].value != 0)
		return 1;
	if (handle_key(pipe_fds[1], &state, KEY_M, 0) < 0 ||
	    read(pipe_fds[0], events, sizeof(events)) != (ssize_t)sizeof(events) ||
	    events[1].code != KEY_BACKSLASH || events[1].value != 0)
		return 1;
	memset(&state, 0, sizeof(state));
	state.fn = true;
	state.left_shift = true;
	if (handle_key(pipe_fds[1], &state, KEY_Q, 1) < 0 ||
	    read(pipe_fds[0], events, sizeof(events)) != (ssize_t)sizeof(events) ||
	    events[0].code != KEY_LEFTSHIFT || events[0].value != 0 ||
	    events[1].code != KEY_1 || events[1].value != 1 ||
	    events[2].code != KEY_LEFTSHIFT || events[2].value != 1)
		return 1;
	memset(&state, 0, sizeof(state));
	if (handle_key(pipe_fds[1], &state, KEY_EQUAL, 1) < 0 ||
	    read(pipe_fds[0], events, sizeof(events)) != (ssize_t)sizeof(events) ||
	    events[0].code != KEY_LEFTSHIFT || events[0].value != 1 ||
	    events[1].code != KEY_EQUAL || events[1].value != 1 ||
	    events[2].code != KEY_LEFTSHIFT || events[2].value != 0)
		return 1;
	if (handle_key(pipe_fds[1], &state, KEY_EQUAL, 0) < 0 ||
	    read(pipe_fds[0], events, sizeof(events)) != (ssize_t)sizeof(events) ||
	    events[1].code != KEY_EQUAL || events[1].value != 0)
		return 1;
	state.fn = true;
	if (handle_key(pipe_fds[1], &state, KEY_EQUAL, 1) < 0 ||
	    read(pipe_fds[0], events, sizeof(events[0])) != (ssize_t)sizeof(events[0]) ||
	    events[0].code != KEY_EQUAL || events[0].value != 1)
		return 1;
	state.fn = false; /* Releasing Fn first must preserve the matching key-up. */
	if (handle_key(pipe_fds[1], &state, KEY_EQUAL, 0) < 0 ||
	    read(pipe_fds[0], events, sizeof(events[0])) != (ssize_t)sizeof(events[0]) ||
	    events[0].code != KEY_EQUAL || events[0].value != 0)
		return 1;
	close(pipe_fds[0]);
	close(pipe_fds[1]);
	puts("n810-fn-remap self-test passed");
	return 0;
}

int main(int argc, char **argv)
{
	char path[256] = {0};
	char name[256] = {0};
	struct sigaction action = {0};
	struct remap_state state = {0};
	int source_fd;
	int virtual_fd = -1;
	int exit_code = 1;

	if (argc == 2 && !strcmp(argv[1], "--version")) {
		puts("n810-fn-remap 1");
		return 0;
	}
	if (argc == 2 && !strcmp(argv[1], "--self-test"))
		return self_test();
	if (argc > 2 || (argc == 2 && strcmp(argv[1], "--check"))) {
		fprintf(stderr, "Usage: %s [--check|--self-test|--version]\n", argv[0]);
		return 2;
	}

	source_fd = find_internal_keyboard(path, sizeof(path), name, sizeof(name));
	if (source_fd < 0) {
		perror("Internal LM8323 keyboard not found");
		return 1;
	}
	if (verify_source(source_fd) < 0) {
		perror("Internal keyboard verification failed");
		close(source_fd);
		return 1;
	}
	if (argc == 2) {
		printf("Verified %s (%s)\n", path, name);
		close(source_fd);
		return 0;
	}

	virtual_fd = create_virtual_keyboard(source_fd);
	if (virtual_fd < 0) {
		perror("Unable to create virtual internal keyboard");
		goto out;
	}
	if (ioctl(source_fd, EVIOCGRAB, 1) < 0) {
		perror("Unable to grab internal keyboard");
		goto out;
	}
	action.sa_handler = handle_signal;
	sigemptyset(&action.sa_mask);
	if (sigaction(SIGINT, &action, NULL) < 0 ||
	    sigaction(SIGTERM, &action, NULL) < 0) {
		perror("Unable to install signal handlers");
		goto ungrab;
	}

	fprintf(stderr, "Remapping Fn chords on %s (%s); external keyboards are untouched\n",
		path, name);
	while (!stopping) {
		struct input_event event;
		ssize_t length = read(source_fd, &event, sizeof(event));

		if (length < 0 && errno == EINTR)
			continue;
		if (length != sizeof(event)) {
			if (!stopping)
				perror("Internal keyboard read failed");
			break;
		}
		if (event.type == EV_KEY) {
			if (handle_key(virtual_fd, &state, event.code, event.value) < 0) {
				perror("Virtual keyboard write failed");
				break;
			}
		} else if (event.type == EV_SYN &&
			   emit_event(virtual_fd, event.type, event.code, event.value) < 0) {
			perror("Virtual keyboard write failed");
			break;
		}
	}
	if (stopping)
		exit_code = 0;

ungrab:
	if (ioctl(source_fd, EVIOCGRAB, 0) < 0 && !stopping)
		perror("Unable to release internal keyboard");
out:
	if (virtual_fd >= 0) {
		ioctl(virtual_fd, UI_DEV_DESTROY);
		close(virtual_fd);
	}
	close(source_fd);
	return exit_code;
}
