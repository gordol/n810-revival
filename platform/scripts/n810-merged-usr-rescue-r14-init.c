/* Freestanding ARM init for one exact N810 merged-/usr repair. */
typedef unsigned int u32;
typedef long ssize_t;
struct timespec { long sec; long nsec; };

#define O_RDONLY 0
#define MS_RDONLY 1
#define MS_NOSUID 2
#define MS_NODEV 4
#define MS_NOEXEC 8

static long call1(long n, long a)
{
	register long r0 __asm__("r0") = a;
	register long r7 __asm__("r7") = n;
	__asm__ volatile("svc 0" : "+r"(r0) : "r"(r7) : "memory");
	return r0;
}
static long call2(long n, long a, long b)
{
	register long r0 __asm__("r0") = a;
	register long r1 __asm__("r1") = b;
	register long r7 __asm__("r7") = n;
	__asm__ volatile("svc 0" : "+r"(r0) : "r"(r1), "r"(r7) : "memory");
	return r0;
}
static long call3(long n, long a, long b, long c)
{
	register long r0 __asm__("r0") = a;
	register long r1 __asm__("r1") = b;
	register long r2 __asm__("r2") = c;
	register long r7 __asm__("r7") = n;
	__asm__ volatile("svc 0" : "+r"(r0) : "r"(r1), "r"(r2), "r"(r7) : "memory");
	return r0;
}
static long call5(long n, long a, long b, long c, long d, long e)
{
	register long r0 __asm__("r0") = a;
	register long r1 __asm__("r1") = b;
	register long r2 __asm__("r2") = c;
	register long r3 __asm__("r3") = d;
	register long r4 __asm__("r4") = e;
	register long r7 __asm__("r7") = n;
	__asm__ volatile("svc 0" : "+r"(r0) : "r"(r1), "r"(r2), "r"(r3), "r"(r4), "r"(r7) : "memory");
	return r0;
}
static unsigned length(const char *s) { unsigned n = 0; while (s[n]) n++; return n; }
static long output_fd = 1;
static void say(const char *s) { call3(4, output_fd, (long)s, length(s)); }
static const char *yesno(int value) { return value ? "yes" : "no"; }
static void stop(const char *s)
{
	static const struct timespec delay = { 60, 0 };
	say("RESCUE REFUSED: "); say(s); say("\n");
	for (;;) call2(162, (long)&delay, 0);
}
static void must(long result, const char *what) { if (result < 0) stop(what); }
static void must_open(const char *path, int flags)
{
	long fd = call3(5, (long)path, flags, 0);
	if (fd < 0) stop(path);
	call1(6, fd);
}
static int opens(const char *path, int flags)
{
	long fd = call3(5, (long)path, flags, 0);
	if (fd < 0) return 0;
	call1(6, fd);
	return 1;
}
static int expected_lib_link(void)
{
	char target[16];
	long n = call3(85, (long)"/newroot/lib", (long)target, sizeof(target));
	return n == 7 && target[0] == 'u' && target[1] == 's' &&
		target[2] == 'r' && target[3] == '/' && target[4] == 'l' &&
		target[5] == 'i' && target[6] == 'b';
}
static int init_exists(void) { return opens("/newroot/sbin/init", O_RDONLY); }
static int systemd_exists(void) { return opens("/newroot/usr/lib/systemd/systemd", O_RDONLY); }
static int path_exists(const char *path)
{
	char target[16];
	return call3(85, (long)path, (long)target, sizeof(target)) >= 0 ||
		opens(path, O_RDONLY);
}
static int known_emmc(const char *device)
{
	unsigned char mbr[512];
	long fd = call3(5, (long)device, O_RDONLY, 0);
	if (fd < 0) return 0;
	long n = call3(3, fd, (long)mbr, sizeof(mbr));
	call1(6, fd);
	return n == sizeof(mbr) && mbr[440] == 0xbe && mbr[441] == 0x23 &&
		mbr[442] == 0x30 && mbr[443] == 0x8f &&
		mbr[510] == 0x55 && mbr[511] == 0xaa && mbr[466] == 0x83;
}
static void verify_root(const char *device)
{
	must(call5(21, (long)device, (long)"/newroot", (long)"ext4",
		MS_RDONLY, (long)"noload"), "mount identified Debian root read-only");
	int loader = opens("/newroot/usr/lib/ld-linux.so.3", O_RDONLY);
	int init = systemd_exists();
	int link = expected_lib_link();
	say("probe="); say(device);
	say(" loader="); say(yesno(loader));
	say(" init="); say(yesno(init));
	say(" lib-link="); say(yesno(link)); say("\n");
	must(call2(52, (long)"/newroot", 0), "unmount checked Debian root");
	if (!loader || !init) stop("identified eMMC p2 is not the Debian root");
}

void _start(void)
{
	static char *const init_argv[] = { "/sbin/init", 0 };
	static char *const init_env[] = { "HOME=/", "PATH=/usr/sbin:/usr/bin:/sbin:/bin", 0 };

	say("N810 guarded merged-/usr rescue starting\n");
	call2(39, (long)"/dev", 0755);
	must(call5(21, (long)"devtmpfs", (long)"/dev", (long)"devtmpfs", MS_NOSUID, 0), "mount devtmpfs");
	output_fd = call3(5, (long)"/dev/console", 1, 0);
	if (output_fd < 0) output_fd = 1;
	say("N810 rescue console ready\n");
	call2(39, (long)"/newroot", 0755);
	const char *disk = 0;
	const char *device = 0;
	struct timespec delay = { 1, 0 };
	for (int attempt = 0; attempt < 60; attempt++) {
		if (known_emmc("/dev/mmcblk1") && opens("/dev/mmcblk1p2", O_RDONLY)) {
			disk = "/dev/mmcblk1"; device = "/dev/mmcblk1p2"; break;
		}
		if (known_emmc("/dev/mmcblk0") && opens("/dev/mmcblk0p2", O_RDONLY)) {
			disk = "/dev/mmcblk0"; device = "/dev/mmcblk0p2"; break;
		}
		call2(162, (long)&delay, 0);
	}
	if (!device) stop("known eMMC PARTUUID 8f3023be-02 did not appear");
	say("identified-disk="); say(disk); say(" partition="); say(device); say("\n");
	verify_root(device);
	must(call5(21, (long)device, (long)"/newroot", (long)"ext4", 0, 0), "remount verified Debian root read-write");

	must_open("/newroot/usr/lib/ld-linux.so.3", O_RDONLY);
	if (!systemd_exists()) stop("/newroot/usr/lib/systemd/systemd");
	if (!expected_lib_link()) {
		if (path_exists("/newroot/lib.rescue-r14")) stop("/lib.rescue-r14 already exists");
		must(call2(38, (long)"/newroot/lib", (long)"/newroot/lib.rescue-r14"),
			"preserve old /lib");
		if (call2(83, (long)"usr/lib", (long)"/newroot/lib") < 0) {
			call2(38, (long)"/newroot/lib.rescue-r14", (long)"/newroot/lib");
			stop("restore /lib -> usr/lib");
		}
		if (!opens("/newroot/lib/ld-linux.so.3", O_RDONLY) ||
		    !init_exists()) {
			call1(10, (long)"/newroot/lib");
			call2(38, (long)"/newroot/lib.rescue-r14", (long)"/newroot/lib");
			stop("loader/init verification failed; old /lib restored");
		}
	}
	must_open("/newroot/lib/ld-linux.so.3", O_RDONLY);
	if (!init_exists()) stop("/newroot/sbin/init after repair");
	call1(36, 0);
	say("N810 merged-/usr repair complete; starting Debian\n");

	call2(39, (long)"/newroot/dev", 0755);
	call2(39, (long)"/newroot/proc", 0555);
	call2(39, (long)"/newroot/sys", 0555);
	must(call5(21, (long)"devtmpfs", (long)"/newroot/dev", (long)"devtmpfs", MS_NOSUID, 0), "mount target devtmpfs");
	must(call5(21, (long)"proc", (long)"/newroot/proc", (long)"proc", MS_NOSUID | MS_NODEV | MS_NOEXEC, 0), "mount target proc");
	must(call5(21, (long)"sysfs", (long)"/newroot/sys", (long)"sysfs", MS_NOSUID | MS_NODEV | MS_NOEXEC, 0), "mount target sysfs");
	must(call1(12, (long)"/newroot"), "chdir new root");
	must(call1(61, (long)"."), "chroot new root");
	must(call1(12, (long)"/"), "chdir /");
	call3(11, (long)"/sbin/init", (long)init_argv, (long)init_env);
	stop("exec /sbin/init");
}
