#define _GNU_SOURCE

#include <errno.h>
#include <fcntl.h>
#include <glob.h>
#include <linux/input.h>
#include <linux/uinput.h>
#include <signal.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

#define BITS_PER_LONG (sizeof(unsigned long) * 8)
#define NBITS(x) ((((x) - 1) / BITS_PER_LONG) + 1)

static volatile sig_atomic_t stopping;

struct mapping {
	unsigned short from;
	unsigned short to;
};

/* F13--F17 are private tmux controls. F20 is the internal Fn modifier. */
static const struct mapping mappings[] = {
	{ KEY_F4, KEY_F13 },
	{ KEY_F5, KEY_F14 },
	{ KEY_F6, KEY_F15 },
	{ KEY_F7, KEY_F16 },
	{ KEY_F8, KEY_F17 },
	{ KEY_LEFTALT, KEY_F20 },
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

static unsigned short mapped_code(unsigned short code)
{
	size_t i;

	for (i = 0; i < sizeof(mappings) / sizeof(mappings[0]); i++)
		if (mappings[i].from == code)
			return mappings[i].to;
	return code;
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
	for (i = 0; i < sizeof(mappings) / sizeof(mappings[0]); i++) {
		if (!bit_is_set(keys, mappings[i].from)) {
			fprintf(stderr, "Internal keyboard lacks key code %u\n",
				mappings[i].from);
			errno = ENODEV;
			return -1;
		}
	}
	if (!bit_is_set(keys, KEY_ESC)) {
		fputs("Internal Back/Escape key is unavailable\n", stderr);
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
	    ioctl(fd, UI_SET_EVBIT, EV_MSC) < 0 ||
	    ioctl(fd, UI_SET_MSCBIT, MSC_SCAN) < 0)
		goto fail;

	for (code = 1; code <= KEY_MAX; code++)
		if (bit_is_set(keys, code) && ioctl(fd, UI_SET_KEYBIT, code) < 0)
			goto fail;
	for (i = 0; i < sizeof(mappings) / sizeof(mappings[0]); i++)
		if (ioctl(fd, UI_SET_KEYBIT, mappings[i].to) < 0)
			goto fail;

	setup.id = source_id;
	setup.id.version++;
	strcpy(setup.name, "N810 console keyboard");
	if (ioctl(fd, UI_DEV_SETUP, &setup) < 0 || ioctl(fd, UI_DEV_CREATE) < 0)
		goto fail;
	return fd;

fail:
	close(fd);
	return -1;
}

static int write_event(int fd, const struct input_event *event)
{
	const char *buffer = (const char *)event;
	size_t remaining = sizeof(*event);

	while (remaining > 0) {
		ssize_t written = write(fd, buffer, remaining);

		if (written < 0 && errno == EINTR)
			continue;
		if (written <= 0)
			return -1;
		buffer += written;
		remaining -= (size_t)written;
	}
	return 0;
}

static int self_test(void)
{
	static const unsigned short expected[] = {
		KEY_F13, KEY_F14, KEY_F15, KEY_F16, KEY_F17, KEY_F20,
	};
	size_t i;

	for (i = 0; i < sizeof(mappings) / sizeof(mappings[0]); i++)
		if (mapped_code(mappings[i].from) != expected[i])
			return 1;
	if (mapped_code(KEY_ESC) != KEY_ESC || mapped_code(KEY_A) != KEY_A)
		return 1;
	puts("n810-input-remap self-test passed");
	return 0;
}

int main(int argc, char **argv)
{
	char path[256] = {0};
	char name[256] = {0};
	struct sigaction action = {0};
	int source_fd;
	int virtual_fd = -1;
	int exit_code = 1;

	if (argc == 2 && !strcmp(argv[1], "--version")) {
		puts("n810-input-remap 1");
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

	fprintf(stderr, "Remapping %s (%s); external keyboards are untouched\n",
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
		if (event.type == EV_KEY)
			event.code = mapped_code(event.code);
		if (write_event(virtual_fd, &event) < 0) {
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
