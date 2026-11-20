/*
 * F1GameStation bring-up test for the MiyooCFW kernel drivers.
 *
 *   f1gs-test fb      draw a test card on /dev/fb0 (320x240 RGB565)
 *   f1gs-test keys    print key events from the miyoo_keypad input device
 *   f1gs-test tone    play 2 s of 1 kHz through /dev/dsp
 *
 * Build: arm-linux-gnueabi-gcc -static -O2 -o f1gs-test f1gs-test.c -lm
 */
#include <dirent.h>
#include <fcntl.h>
#include <linux/fb.h>
#include <linux/input.h>
#include <linux/soundcard.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>

#define RGB565(r, g, b) ((((r) >> 3) << 11) | (((g) >> 2) << 5) | ((b) >> 3))

static int test_fb(void)
{
	struct fb_var_screeninfo var;
	struct fb_fix_screeninfo fix;
	static const uint16_t bars[8] = {
		RGB565(255, 255, 255), RGB565(255, 255, 0), RGB565(0, 255, 255), RGB565(0, 255, 0),
		RGB565(255, 0, 255), RGB565(255, 0, 0), RGB565(0, 0, 255), RGB565(0, 0, 0),
	};
	int fd = open("/dev/fb0", O_RDWR);
	if (fd < 0 || ioctl(fd, FBIOGET_VSCREENINFO, &var) || ioctl(fd, FBIOGET_FSCREENINFO, &fix)) {
		perror("fb0");
		return 1;
	}
	printf("fb0: %s %ux%u virtual %ux%u %u bpp, line %u, mem %u\n", fix.id, var.xres, var.yres,
	       var.xres_virtual, var.yres_virtual, var.bits_per_pixel, fix.line_length, fix.smem_len);
	uint8_t *mem = mmap(NULL, fix.smem_len, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
	if (mem == MAP_FAILED) {
		perror("mmap");
		return 1;
	}
	for (unsigned y = 0; y < var.yres; y++) {
		uint16_t *row = (uint16_t *)(mem + y * fix.line_length);
		for (unsigned x = 0; x < var.xres; x++) {
			uint16_t c;
			if (x == 0 || y == 0 || x == var.xres - 1 || y == var.yres - 1)
				c = RGB565(255, 255, 255);	/* 1 px frame shows the 320x240 edge */
			else if (y < var.yres * 2 / 3)
				c = bars[x * 8 / var.xres];
			else {
				unsigned v = x * 255 / (var.xres - 1);	/* grey ramp */
				c = RGB565(v, v, v);
			}
			row[x] = c;
		}
	}
	/* a second frame in red, so a pan to yoffset 240 is visible */
	if (var.yres_virtual >= 2 * var.yres) {
		for (unsigned y = 0; y < var.yres; y++) {
			uint16_t *row = (uint16_t *)(mem + (var.yres + y) * fix.line_length);
			for (unsigned x = 0; x < var.xres; x++)
				row[x] = RGB565(255, 0, 0);
		}
	}
	munmap(mem, fix.smem_len);
	close(fd);
	return 0;
}

static int open_keypad(void)
{
	char path[300], name[64];
	DIR *d = opendir("/dev/input");
	struct dirent *e;
	int fd;

	while (d && (e = readdir(d))) {
		if (strncmp(e->d_name, "event", 5))
			continue;
		snprintf(path, sizeof(path), "/dev/input/%s", e->d_name);
		fd = open(path, O_RDONLY);
		if (fd < 0)
			continue;
		if (ioctl(fd, EVIOCGNAME(sizeof(name)), name) > 0 && !strcmp(name, "miyoo_keypad")) {
			closedir(d);
			printf("%s: %s\n", path, name);
			return fd;
		}
		close(fd);
	}
	if (d)
		closedir(d);
	return -1;
}

static const char *key_name(int code)
{
	/* button names as MiyooCFW layout 1 reports them */
	switch (code) {
	case KEY_UP: return "UP";
	case KEY_DOWN: return "DOWN";
	case KEY_LEFT: return "LEFT";
	case KEY_RIGHT: return "RIGHT";
	case KEY_LEFTALT: return "A";
	case KEY_LEFTCTRL: return "B";
	case KEY_LEFTSHIFT: return "X";
	case KEY_SPACE: return "Y";
	case KEY_ENTER: return "START";
	case KEY_ESC: return "SELECT";
	case KEY_RIGHTCTRL: return "MENU";
	case KEY_TAB: return "L";
	case KEY_BACKSPACE: return "R";
	case KEY_PAGEUP: return "L2 (MENU+L)";
	case KEY_PAGEDOWN: return "R2 (MENU+R)";
	case KEY_RIGHTALT: return "L3 (MENU+Y)";
	case KEY_RIGHTSHIFT: return "R3 (MENU+X)";
	}
	return "?";
}

static int test_keys(void)
{
	struct input_event ev;
	int fd = open_keypad();

	if (fd < 0) {
		fprintf(stderr, "miyoo_keypad not found (is evdev loaded?)\n");
		return 1;
	}
	while (read(fd, &ev, sizeof(ev)) == sizeof(ev)) {
		if (ev.type == EV_KEY)
			printf("%-12s %s\n", key_name(ev.code), ev.value ? "down" : "up");
		fflush(stdout);
	}
	return 0;
}

static int test_tone(void)
{
	/* 1 kHz near full scale, like the bring-up test: the small speaker
	 * is far quieter at a few hundred Hz */
	int rate = 48000, ch = 2, fmt = AFMT_S16_LE;
	int fd = open("/dev/dsp", O_WRONLY);
	static int16_t buf[48000 * 2 * 2];

	if (fd < 0 || ioctl(fd, SNDCTL_DSP_SETFMT, &fmt) || ioctl(fd, SNDCTL_DSP_CHANNELS, &ch) ||
	    ioctl(fd, SNDCTL_DSP_SPEED, &rate)) {
		perror("dsp");
		return 1;
	}
	printf("dsp: %d Hz, %d ch, 2 s of 1 kHz\n", rate, ch);
	for (int i = 0; i < rate * 2; i++)
		buf[2 * i] = buf[2 * i + 1] = 28000 * sin(2 * M_PI * 1000 * i / rate);
	if (write(fd, buf, rate * 2 * 2 * ch) < 0)
		perror("write");
	ioctl(fd, SNDCTL_DSP_SYNC, 0);
	close(fd);
	return 0;
}

int main(int argc, char **argv)
{
	if (argc > 1 && !strcmp(argv[1], "fb"))
		return test_fb();
	if (argc > 1 && !strcmp(argv[1], "keys"))
		return test_keys();
	if (argc > 1 && !strcmp(argv[1], "tone"))
		return test_tone();
	fprintf(stderr, "usage: %s fb|keys|tone\n", argv[0]);
	return 2;
}
