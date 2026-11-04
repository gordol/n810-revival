// SPDX-License-Identifier: MIT
// Nokia N810 keyboard backlight policy: slide, activity, ambient light, fade.
#define _POSIX_C_SOURCE 200809L

#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/input.h>
#include <limits.h>
#include <poll.h>
#include <signal.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <syslog.h>
#include <time.h>
#include <unistd.h>

#define CONFIG_PATH "/etc/n810-backlight.conf"
#define LED_PATH "/sys/class/leds/n810::keyboard/brightness"
#define LUX_PATH "/sys/bus/i2c/devices/1-0029/iio:device1/in_illuminance0_input"
#define BATTERY_PATH "/sys/class/power_supply/n8x0-battery/capacity"
#define CHARGER_PATH "/sys/class/power_supply/tahvo-charger/online"
#define LOCK_PATH "/run/n810-screen/locked"
#define INPUT_DIR "/dev/input"

struct config {
	int hold_seconds;
	int fade_seconds;
	int idle_seconds;
	int sample_seconds;
	int min_brightness;
	int max_brightness;
	int off_lux;
};

static volatile sig_atomic_t running = 1;

static void stop_running(int unused)
{
	(void)unused;
	running = 0;
}

static long long milliseconds(void)
{
	struct timespec ts;
	clock_gettime(CLOCK_MONOTONIC, &ts);
	return (long long)ts.tv_sec * 1000 + ts.tv_nsec / 1000000;
}

static int read_number(const char *path, int fallback)
{
	FILE *file = fopen(path, "r");
	int value;
	if (!file)
		return fallback;
	if (fscanf(file, "%d", &value) != 1)
		value = fallback;
	fclose(file);
	return value;
}

static int write_brightness(int brightness)
{
	FILE *file = fopen(LED_PATH, "w");
	if (!file)
		return -1;
	if (fprintf(file, "%d\n", brightness) < 0) {
		fclose(file);
		return -1;
	}
	return fclose(file);
}

static void read_config(struct config *config)
{
	FILE *file;
	char line[128], key[64];
	int value;

	config->hold_seconds = 60;
	config->idle_seconds = 300;
	config->fade_seconds = 10;
	config->sample_seconds = 2;
	config->min_brightness = 56;
	config->max_brightness = 160;
	config->off_lux = 200;
	file = fopen(CONFIG_PATH, "r");
	if (!file)
		return;
	while (fgets(line, sizeof(line), file)) {
		if (sscanf(line, " %63[^=]=%d", key, &value) != 2)
			continue;
		if (!strcmp(key, "keyboard_hold_seconds") && value >= 0 && value <= 600)
			config->hold_seconds = value;
		else if (!strcmp(key, "keyboard_fade_seconds") && value >= 1 && value <= 600)
			config->fade_seconds = value;
		else if (!strcmp(key, "keyboard_idle_seconds") && value >= 0 && value <= 86400)
			config->idle_seconds = value;
		else if (!strcmp(key, "keyboard_sample_seconds") && value >= 1 && value <= 60)
			config->sample_seconds = value;
		else if (!strcmp(key, "keyboard_min_brightness") && value >= 1 && value <= 255)
			config->min_brightness = value;
		else if (!strcmp(key, "keyboard_max_brightness") && value >= 1 && value <= 255)
			config->max_brightness = value;
		else if (!strcmp(key, "keyboard_off_lux") && value >= 0)
			config->off_lux = value;
	}
	fclose(file);
	if (config->max_brightness < config->min_brightness)
		config->max_brightness = config->min_brightness;
}

static int ambient_brightness(const struct config *config)
{
	int lux = read_number(LUX_PATH, -1);
	int range = config->max_brightness - config->min_brightness;
	int full_lux;
	if (lux < 0)
		return (config->min_brightness + config->max_brightness) / 2;
	if (config->off_lux && lux >= config->off_lux)
		return 0;
	full_lux = config->off_lux ? config->off_lux / 2 : 1000;
	if (full_lux < 1 || lux >= full_lux)
		return config->max_brightness;
	return config->min_brightness + range * lux / full_lux;
}

static int power_adjusted_brightness(const struct config *config)
{
	int brightness = ambient_brightness(config);
	int capacity, percent;

	if (!brightness || read_number(CHARGER_PATH, 0))
		return brightness;
	capacity = read_number(BATTERY_PATH, 100);
	if (capacity <= 10)
		return brightness < config->min_brightness ? brightness : config->min_brightness;
	if (capacity <= 25)
		percent = 60;
	else if (capacity <= 50)
		percent = 75;
	else
		percent = 85;
	brightness = brightness * percent / 100;
	return brightness > 0 ? brightness : 1;
}

static int find_input(const char *wanted_name)
{
	DIR *dir = opendir(INPUT_DIR);
	struct dirent *entry;
	char path[PATH_MAX], name[128];
	int fd;

	if (!dir)
		return -1;
	while ((entry = readdir(dir))) {
		if (strncmp(entry->d_name, "event", 5))
			continue;
		snprintf(path, sizeof(path), "%s/%s", INPUT_DIR, entry->d_name);
		fd = open(path, O_RDONLY | O_NONBLOCK | O_CLOEXEC);
		if (fd < 0)
			continue;
		memset(name, 0, sizeof(name));
		if (ioctl(fd, EVIOCGNAME(sizeof(name)), name) >= 0 && !strcmp(name, wanted_name)) {
			closedir(dir);
			return fd;
		}
		close(fd);
	}
	closedir(dir);
	return -1;
}

static bool slide_is_open(int fd)
{
	unsigned long switches[(SW_MAX + 8 * sizeof(long)) / (8 * sizeof(long))];
	memset(switches, 0, sizeof(switches));
	if (ioctl(fd, EVIOCGSW(sizeof(switches)), switches) < 0)
		return false;
	return switches[SW_KEYPAD_SLIDE / (8 * sizeof(long))] &
	       (1UL << (SW_KEYPAD_SLIDE % (8 * sizeof(long))));
}

static void set_light(int value, int *last)
{
	if (value == *last)
		return;
	if (write_brightness(value) < 0) {
		syslog(LOG_ERR, "cannot set keyboard brightness: %s", strerror(errno));
		return;
	}
	*last = value;
}

static void usage(const char *name)
{
	fprintf(stderr, "Usage: %s [--status]\n", name);
}

int main(int argc, char **argv)
{
	struct config config;
	struct pollfd pollfd[3];
	struct input_event events[16];
	bool open;
	long long activity = 0, next_sample = 0, next_discovery = 0;
	int keyboard_fd, switch_fd, virtual_fd, last = -1, active_brightness = 0;
	ssize_t bytes;

	read_config(&config);
	keyboard_fd = find_input("Internal keyboard");
	virtual_fd = find_input("N810 internal keyboard");
	switch_fd = find_input("gpio-keys");
	if (switch_fd < 0) {
		fprintf(stderr, "n810-backlightd: keypad slide input not found\n");
		return 1;
	}
	open = slide_is_open(switch_fd);
	if (argc == 2 && !strcmp(argv[1], "--status")) {
		printf("keyboard_open=%s lux=%d brightness=%d power=%s capacity=%d hold=%d fade=%d off=%d sample=%d\n",
		       open ? "yes" : "no", read_number(LUX_PATH, -1),
		       read_number(LED_PATH, -1), read_number(CHARGER_PATH, 0) ? "external" : "battery",
		       read_number(BATTERY_PATH, -1), config.hold_seconds, config.fade_seconds,
		       config.idle_seconds, config.sample_seconds);
		close(switch_fd);
		if (keyboard_fd >= 0)
			close(keyboard_fd);
		if (virtual_fd >= 0)
			close(virtual_fd);
		return 0;
	}
	if (argc != 1) {
		usage(argv[0]);
		return 2;
	}
	if (keyboard_fd < 0 && virtual_fd < 0) {
		fprintf(stderr, "n810-backlightd: internal keyboard input not found\n");
		return 1;
	}

	openlog("n810-backlightd", LOG_PID, LOG_DAEMON);
	signal(SIGINT, stop_running);
	signal(SIGTERM, stop_running);
	pollfd[0].fd = keyboard_fd;
	pollfd[0].events = POLLIN;
	pollfd[1].fd = switch_fd;
	pollfd[1].events = POLLIN;
	pollfd[2].fd = virtual_fd;
	pollfd[2].events = POLLIN;
	if (open) {
		activity = milliseconds();
		active_brightness = power_adjusted_brightness(&config);
		next_sample = activity + (long long)config.sample_seconds * 1000;
		set_light(active_brightness, &last);
	} else {
		set_light(0, &last);
	}

	bool was_locked = false;
	while (running) {
		bool locked = access(LOCK_PATH, F_OK) == 0;
		if (was_locked && !locked) activity = milliseconds();
		was_locked = locked;
		long long now = milliseconds();
		long long hold_end = activity + (long long)config.hold_seconds * 1000;
		long long fade_end = hold_end + (long long)config.fade_seconds * 1000;
		long long off_end = activity + (long long)config.idle_seconds * 1000;
		bool illuminated = !locked && open && (!config.idle_seconds || now < off_end);
		int floor = active_brightness < config.min_brightness ?
			active_brightness : config.min_brightness;
		int timeout = -1;
		int ready;
		/* The remapper grabs the physical device and creates its virtual
		 * keyboard after us at boot. Rediscover by name, never event number,
		 * and reconnect when either keyboard disappears and returns. */
		if (now >= next_discovery) {
			if (pollfd[0].fd < 0)
				pollfd[0].fd = find_input("Internal keyboard");
			if (pollfd[2].fd < 0)
				pollfd[2].fd = find_input("N810 internal keyboard");
			next_discovery = now + 2000;
		}
		if (illuminated && now >= next_sample) {
			active_brightness = power_adjusted_brightness(&config);
			next_sample = now + (long long)config.sample_seconds * 1000;
			floor = active_brightness < config.min_brightness ?
				active_brightness : config.min_brightness;
		}

		if (illuminated && now < hold_end) {
			set_light(active_brightness, &last);
			timeout = (int)(hold_end - now);
		} else if (illuminated && now < fade_end) {
			long long remaining = fade_end - now;
			int value = floor + (int)((long long)(active_brightness - floor) * remaining /
					  ((long long)config.fade_seconds * 1000));
			set_light(value, &last);
			timeout = remaining < 250 ? (int)remaining : 250;
		} else if (illuminated) {
			set_light(floor, &last);
		} else if (open) {
			set_light(0, &last);
		}
		if (illuminated && config.idle_seconds &&
		    (timeout < 0 || off_end - now < timeout))
			timeout = (int)(off_end - now);
		if (illuminated) {
			long long until_sample = next_sample - now;
			if (until_sample < 1)
				until_sample = 1;
			if (timeout < 0 || until_sample < timeout)
				timeout = (int)until_sample;
		}
		if (timeout < 0 || next_discovery - now < timeout)
			timeout = (int)(next_discovery - now);
		ready = poll(pollfd, 3, timeout);
		if (ready < 0) {
			if (errno == EINTR)
				continue;
			syslog(LOG_ERR, "poll failed: %s", strerror(errno));
			break;
		}
		if (ready == 0)
			continue;

		if (pollfd[1].revents & POLLIN) {
			bytes = read(switch_fd, events, sizeof(events));
			for (ssize_t i = 0; i < bytes / (ssize_t)sizeof(events[0]); i++) {
				if (events[i].type != EV_SW || events[i].code != SW_KEYPAD_SLIDE)
					continue;
				open = events[i].value != 0;
				if (open && !locked) {
					activity = milliseconds();
					active_brightness = power_adjusted_brightness(&config);
					next_sample = activity + (long long)config.sample_seconds * 1000;
					set_light(active_brightness, &last);
				} else {
					set_light(0, &last);
				}
			}
		}
		for (int source = 0; source <= 2; source += 2) {
			if (pollfd[source].revents & (POLLHUP | POLLERR | POLLNVAL)) {
				close(pollfd[source].fd);
				pollfd[source].fd = -1;
				continue;
			}
			if (!(pollfd[source].revents & POLLIN))
				continue;
			bytes = read(pollfd[source].fd, events, sizeof(events));
			for (ssize_t i = 0; open && !locked && i < bytes / (ssize_t)sizeof(events[0]); i++) {
				if (events[i].type == EV_KEY && events[i].value == 1) {
					activity = milliseconds();
					active_brightness = power_adjusted_brightness(&config);
					next_sample = activity + (long long)config.sample_seconds * 1000;
					set_light(active_brightness, &last);
					break;
				}
			}
		}
	}

	write_brightness(0);
	if (pollfd[0].fd >= 0)
		close(pollfd[0].fd);
	if (pollfd[2].fd >= 0)
		close(pollfd[2].fd);
	close(switch_fd);
	closelog();
	return 0;
}
