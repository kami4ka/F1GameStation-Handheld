/*
 * coverflow: a horizontal game launcher for the F1GameStation (MiyooCFW).
 *
 * Every game from every system sits on one shelf of box art. It reuses the
 * gmenu2x links that MiyooCFW already has (sections/<x>/<link> with
 * selectordir=<roms>/<SYSTEM>), so a game starts exactly the way gmenu2x
 * would start it; ROM folders no link points at are started with a known
 * RetroArch core link. Box art is read from <roms>/<SYSTEM>/.images/<rom>.png,
 * the folder the MiyooCFW scraper also writes to; scripts/fetch-boxart.py
 * fills it on a PC. SDL 1.2, RGB565, 480x272.
 *
 * Buttons: Left/Right move, Up/Down jump by letter, L/R change tab,
 * A play, X favourite, START or SELECT open a quick menu (brightness,
 * volume, game screen size, the classic gmenu2x menu, power off).
 */
#include <SDL/SDL.h>
#include <SDL/SDL_image.h>
#include <SDL/SDL_ttf.h>
#include <ctype.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>
#ifdef F1GS_PANEL
#include <linux/fb.h>
#include <linux/kd.h>
#include <linux/vt.h>
#endif

#define W 480
#define H 272
#define COVER_W 102 /* the box the centre cover is fitted into */
#define COVER_H 136
#define SHELF_BASE 176 /* bottom edge of the covers */
#define MAX_GAMES 8192
#define MAX_SYS 64
#define MAX_TABS (MAX_SYS + 3)
#define CACHE_RANGE 10 /* covers kept loaded either side of the selection */

/* ---------- small helpers ---------- */

static char *xstrdup(const char *s) {
	char *p = strdup(s ? s : "");
	if (!p) { fprintf(stderr, "out of memory\n"); exit(1); }
	return p;
}

static void trim(char *s) {
	char *e = s + strlen(s);
	while (e > s && isspace((unsigned char)e[-1])) *--e = 0;
	char *b = s;
	while (isspace((unsigned char)*b)) b++;
	if (b != s) memmove(s, b, strlen(b) + 1);
}

static const char *env_or(const char *name, const char *def) {
	const char *v = getenv(name);
	return v && *v ? v : def;
}

/* shell-quote like gmenu2x's cmdclean */
static void shquote(char *out, size_t n, const char *in) {
	size_t o = 0;
	if (o < n - 1) out[o++] = '\'';
	for (; *in && o < n - 6; in++) {
		if (*in == '\'') { memcpy(out + o, "'\\''", 4); o += 4; }
		else out[o++] = *in;
	}
	if (o < n - 1) out[o++] = '\'';
	out[o] = 0;
}

static void strreplace(char *s, size_t n, const char *from, const char *to) {
	char buf[2048];
	char *p;
	size_t fl = strlen(from);
	while ((p = strstr(s, from))) {
		snprintf(buf, sizeof buf, "%.*s%s%s", (int)(p - s), s, to, p + fl);
		snprintf(s, n, "%s", buf);
		if (strstr(to, from)) break;
	}
}

/* ---------- systems (from gmenu2x links) and games ---------- */

typedef struct {
	char name[32];      /* folder name, e.g. SNES */
	char longname[48];  /* shown under the title */
	char dir[PATH_MAX];
	char exec[PATH_MAX];
	char params[512];
	char filter[256];   /* ".nes,.zip" (gmenu2x selectorfilter) */
	int prio;
	Uint16 color;
} System;

typedef struct {
	char *path;  /* full path of the ROM */
	char *file;  /* file name */
	char *name;  /* shown name: no extension, no (USA) [!] tags */
	int sys;
	int fav;
	int plays;
	long last;   /* unix time of last launch */
	SDL_Surface *cover;   /* RGB565, fitted into COVER_W x COVER_H */
	int cover_tried;
} Game;

static System systems[MAX_SYS];
static int nsys;
static Game games[MAX_GAMES];
static int ngames;

static const struct { const char *dir, *name; Uint8 r, g, b; } known[] = {
	{"NES", "NES", 190, 40, 40},       {"FC", "Famicom", 190, 40, 40},
	{"FDS", "Famicom Disk System", 170, 60, 40},
	{"SNES", "Super Nintendo", 110, 80, 170}, {"SFC", "Super Famicom", 110, 80, 170},
	{"GB", "Game Boy", 110, 130, 60},         {"GBC", "Game Boy Color", 190, 130, 20},
	{"GBA", "Game Boy Advance", 60, 70, 160}, {"MD", "Mega Drive", 40, 40, 50},
	{"GENESIS", "Genesis", 40, 40, 50},       {"SMD", "Mega Drive", 40, 40, 50},
	{"SMS", "Master System", 30, 60, 140},    {"GG", "Game Gear", 30, 100, 120},
	{"PCE", "PC Engine", 200, 110, 40},       {"NGP", "Neo Geo Pocket", 140, 40, 80},
	{"NGPC", "Neo Geo Pocket Color", 140, 40, 80},
	{"WS", "WonderSwan", 90, 90, 110},        {"WSC", "WonderSwan Color", 90, 90, 110},
	{"PS", "PlayStation", 90, 90, 100},       {"PSX", "PlayStation", 90, 90, 100},
	{"LYNX", "Atari Lynx", 150, 120, 30},     {"A2600", "Atari 2600", 150, 70, 30},
	{"ATARI2600", "Atari 2600", 150, 70, 30}, {"A7800", "Atari 7800", 150, 70, 30},
	{"ARCADE", "Arcade", 160, 30, 90},        {"FBA", "Arcade", 160, 30, 90},
	{"MAME", "Arcade", 160, 30, 90},          {"MSX", "MSX", 60, 110, 90},
	{"PICO8", "PICO-8", 200, 40, 90},         {"POKEMINI", "Pokemon Mini", 200, 150, 30},
	{"VB", "Virtual Boy", 160, 20, 20},       {"COLECO", "ColecoVision", 60, 60, 120},
	{"C64", "Commodore 64", 90, 80, 150},     {"ZX", "ZX Spectrum", 50, 50, 50},
	{"DOOM", "Doom", 120, 40, 20},            {"32X", "32X", 40, 40, 50},
	{"SEGACD", "Mega CD", 40, 40, 50},        {"PCECD", "PC Engine CD", 200, 110, 40},
};

static Uint16 rgb(int r, int g, int b) {
	return (Uint16)(((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3));
}

static void system_style(System *s) {
	for (size_t i = 0; i < sizeof known / sizeof known[0]; i++)
		if (!strcasecmp(known[i].dir, s->name)) {
			snprintf(s->longname, sizeof s->longname, "%s", known[i].name);
			s->color = rgb(known[i].r, known[i].g, known[i].b);
			return;
		}
	snprintf(s->longname, sizeof s->longname, "%s", s->name);
	unsigned h = 0;
	for (const char *p = s->name; *p; p++) h = h * 31 + (unsigned char)toupper(*p);
	s->color = rgb(60 + h % 120, 50 + (h >> 8) % 100, 70 + (h >> 16) % 120);
}

/* All gmenu2x links that can start something. Like gmenu2x, links whose
 * program is missing from the card are left out. */
typedef struct {
	char path[PATH_MAX], section[64], exec[PATH_MAX], params[512], dir[PATH_MAX], filter[256];
} Link;
#define MAX_LINKS 1024
static Link *links;
static int nlinks;

static void read_link(const char *path, const char *section) {
	FILE *f = fopen(path, "r");
	char line[1024];
	if (!f || nlinks == MAX_LINKS) { if (f) fclose(f); return; }
	Link *l = &links[nlinks];
	memset(l, 0, sizeof *l);
	snprintf(l->path, sizeof l->path, "%s", path);
	snprintf(l->section, sizeof l->section, "%s", section);
	while (fgets(line, sizeof line, f)) {
		char *eq = strchr(line, '=');
		if (!eq) continue;
		*eq = 0;
		char *v = eq + 1;
		trim(line);
		trim(v);
		if (!strcmp(line, "exec")) snprintf(l->exec, sizeof l->exec, "%s", v);
		else if (!strcmp(line, "params")) snprintf(l->params, sizeof l->params, "%s", v);
		else if (!strcmp(line, "selectordir")) snprintf(l->dir, sizeof l->dir, "%s", v);
		else if (!strcmp(line, "selectorfilter")) snprintf(l->filter, sizeof l->filter, "%s", v);
	}
	fclose(f);
	if (!*l->exec || access(l->exec, F_OK)) return;
	size_t n = strlen(l->dir);
	while (n > 1 && l->dir[n - 1] == '/') l->dir[--n] = 0;
	nlinks++;
}

static int cmp_names(const void *a, const void *b) {
	return strcmp(*(char *const *)a, *(char *const *)b);
}

static void scan_links(const char *gmenu) {
	char sections[PATH_MAX];
	links = calloc(MAX_LINKS, sizeof *links);
	snprintf(sections, sizeof sections, "%s/sections", gmenu);
	DIR *d = opendir(sections);
	struct dirent *e;
	if (!d || !links) { if (d) closedir(d); return; }
	char *secs[256];
	int nsec = 0;
	while ((e = readdir(d)) && nsec < 256)
		if (strcmp(e->d_name, ".") && strcmp(e->d_name, "..")) secs[nsec++] = xstrdup(e->d_name);
	closedir(d);
	qsort(secs, nsec, sizeof *secs, cmp_names);
	for (int i = 0; i < nsec; i++) {
		char sp[PATH_MAX];
		snprintf(sp, sizeof sp, "%s/%s", sections, secs[i]);
		DIR *sd = opendir(sp);
		if (sd) {
			char *names[512];
			int nl = 0;
			while ((e = readdir(sd)) && nl < 512)
				if (strcmp(e->d_name, ".") && strcmp(e->d_name, "..")) names[nl++] = xstrdup(e->d_name);
			closedir(sd);
			qsort(names, nl, sizeof *names, cmp_names);
			for (int j = 0; j < nl; j++) {
				char lp[PATH_MAX];
				snprintf(lp, sizeof lp, "%s/%s", sp, names[j]);
				read_link(lp, secs[i]);
				free(names[j]);
			}
		}
		free(secs[i]);
	}
}

/* ROM folders: F1L_ROMS (colon separated), default /roms and /mnt/roms */
static char roms_roots[8][PATH_MAX];
static int nroots;

static int is_root_dir(const char *dir) {
	if (!strcmp(dir, "/") || !strcmp(dir, "/mnt") || !strcmp(dir, "/home")) return 1;
	size_t n = strlen(dir);
	for (int i = 0; i < nroots; i++) /* the roots themselves and folders above them */
		if (!strncmp(dir, roms_roots[i], n) && (roms_roots[i][n] == 0 || roms_roots[i][n] == '/')) return 1;
	return 0;
}

static System *add_system(const char *dir, const Link *l) {
	for (int i = 0; i < nsys; i++)
		if (!strcmp(systems[i].dir, dir)) return &systems[i];
	if (nsys == MAX_SYS) return NULL;
	System *s = &systems[nsys++];
	memset(s, 0, sizeof *s);
	const char *slash = strrchr(dir, '/');
	snprintf(s->name, sizeof s->name, "%s", slash ? slash + 1 : dir);
	snprintf(s->dir, sizeof s->dir, "%s", dir);
	snprintf(s->exec, sizeof s->exec, "%s", l->exec);
	snprintf(s->params, sizeof s->params, "%s", l->params);
	snprintf(s->filter, sizeof s->filter, "%s", l->filter);
	s->prio = -1;
	system_style(s);
	return s;
}

static void use_link(System *s, const Link *l, int prio) {
	if (prio <= s->prio) return;
	snprintf(s->exec, sizeof s->exec, "%s", l->exec);
	snprintf(s->params, sizeof s->params, "%s", l->params);
	/* a generic RetroArch link (selectordir=/mnt) has a filter for its core;
	 * keep it, but a system folder's own link filter wins */
	if (*l->filter || prio >= 10) snprintf(s->filter, sizeof s->filter, "%s", l->filter);
	s->prio = prio;
}

/* RetroArch cores to try, best first, for system folders that no link
 * points at (most MiyooCFW core links use selectordir=/mnt) */
static const struct { const char *dir, *cores; } default_cores[] = {
	{"NES", "fceumm quicknes nestopia fceux"}, {"FC", "fceumm quicknes nestopia"},
	{"FDS", "fceumm nestopia"},
	{"SNES", "snes9x2005 snes9x2002 snes9x2010 snes9x"}, {"SFC", "snes9x2005 snes9x2002 snes9x"},
	{"GB", "gambatte gearboy tgbdual mgba"}, {"GBC", "gambatte gearboy tgbdual mgba"},
	{"GBA", "gpsp mgba vba_next vbam"},
	{"MD", "picodrive genesis_plus_gx"}, {"SMD", "picodrive genesis_plus_gx"},
	{"GENESIS", "picodrive genesis_plus_gx"}, {"32X", "picodrive"},
	{"SMS", "picodrive smsplus genesis_plus_gx gearsystem"},
	{"GG", "picodrive smsplus genesis_plus_gx gearsystem"},
	{"PCE", "mednafen_pce_fast mednafen_pce"}, {"NGP", "race mednafen_ngp"},
	{"NGPC", "race mednafen_ngp"}, {"WS", "mednafen_wswan"}, {"WSC", "mednafen_wswan"},
	{"LYNX", "handy mednafen_lynx"}, {"A2600", "stella2014 stella"},
	{"ATARI2600", "stella2014 stella"}, {"A7800", "prosystem"},
	{"PS", "pcsx_rearmed"}, {"PSX", "pcsx_rearmed"}, {"POKEMINI", "pokemini"},
	{"VB", "mednafen_vb"}, {"COLECO", "bluemsx gearcoleco"}, {"MSX", "bluemsx fmsx"},
	{"ARCADE", "fbalpha2012 fbneo mame2003_plus mame2000"},
	{"FBA", "fbalpha2012 fbneo"}, {"MAME", "mame2003_plus mame2000"},
	{"PICO8", "fake08 retro8"}, {"DOOM", "prboom"},
};

static int link_runs_core(const Link *l, const char *core) {
	const char *base = strrchr(l->path, '/');
	base = base ? base + 1 : l->path;
	size_t n = strlen(core);
	/* any dot-separated part of the link name: "snes9x2005.ra",
	 * "snes9x4d.snes9x2005.ra" (MiyooCFW names links <group>.<core>.ra) */
	for (const char *p = base; *p; ) {
		if (!strncmp(p, core, n) && (p[n] == '.' || p[n] == '_')) return 1;
		p = strchr(p, '.');
		if (!p) break;
		p++;
	}
	/* the program it runs: /mnt/emus/retroarch/snes9x2005.sh */
	const char *eb = strrchr(l->exec, '/');
	eb = eb ? eb + 1 : l->exec;
	if (!strncmp(eb, core, n) && (eb[n] == '.' || eb[n] == '_' || eb[n] == 0)) return 1;
	const char *p = strstr(l->params, core);
	return p && (p == l->params || p[-1] == ' ' || p[-1] == '/') &&
	       (p[n] == 0 || p[n] == ' ' || p[n] == '_');
}

static const Link *find_core_link(const char *sysname) {
	for (size_t i = 0; i < sizeof default_cores / sizeof default_cores[0]; i++) {
		if (strcasecmp(default_cores[i].dir, sysname)) continue;
		char buf[256];
		snprintf(buf, sizeof buf, "%s", default_cores[i].cores);
		for (char *c = strtok(buf, " "); c; c = strtok(NULL, " "))
			for (int j = 0; j < nlinks; j++)
				if (link_runs_core(&links[j], c)) return &links[j];
	}
	return NULL;
}

/* user overrides: <data dir>/systems.cfg lines "SNES=/mnt/gmenu2x/sections/cores/snes9x.ra" */
static char override_cfg[PATH_MAX];

static void apply_overrides(void) {
	FILE *f = fopen(override_cfg, "r");
	char line[PATH_MAX + 64];
	if (!f) return;
	while (fgets(line, sizeof line, f)) {
		char *eq = strchr(line, '=');
		if (line[0] == '#' || !eq) continue;
		*eq = 0;
		trim(line);
		trim(eq + 1);
		for (int i = 0; i < nsys; i++) {
			if (strcasecmp(systems[i].name, line)) continue;
			int found = 0;
			for (int j = 0; j < nlinks && !found; j++)
				if (!strcmp(links[j].path, eq + 1)) { use_link(&systems[i], &links[j], 1000); found = 1; }
			if (!found) {
				/* not a gmenu2x link: a program, given the ROM as its argument */
				Link l;
				memset(&l, 0, sizeof l);
				snprintf(l.exec, sizeof l.exec, "%s", eq + 1);
				snprintf(l.filter, sizeof l.filter, "%s", systems[i].filter);
				if (!access(l.exec, F_OK)) use_link(&systems[i], &l, 1000);
			}
		}
	}
	fclose(f);
}

static void find_systems(void) {
	/* 1. links made for one system folder (selectordir=/mnt/roms/SNES) */
	for (int i = 0; i < nlinks; i++) {
		Link *l = &links[i];
		if (!*l->dir || is_root_dir(l->dir)) continue;
		struct stat st;
		if (stat(l->dir, &st) || !S_ISDIR(st.st_mode)) continue;
		System *s = add_system(l->dir, l);
		if (s) use_link(s, l, 10 + (!strcmp(l->section, "emulators") ? 2 : 0) +
		                      (strstr(l->section, "cores") ? 1 : 0));
	}
	/* 2. other folders in the ROM roots, started with a known core */
	for (int r = 0; r < nroots; r++) {
		DIR *d = opendir(roms_roots[r]);
		struct dirent *e;
		if (!d) continue;
		while ((e = readdir(d))) {
			if (e->d_name[0] == '.') continue;
			char dir[PATH_MAX];
			struct stat st;
			snprintf(dir, sizeof dir, "%s/%s", roms_roots[r], e->d_name);
			if (stat(dir, &st) || !S_ISDIR(st.st_mode)) continue;
			int known_dir = 0;
			for (int i = 0; i < nsys; i++) known_dir |= !strcmp(systems[i].dir, dir);
			if (known_dir) continue;
			const Link *l = find_core_link(e->d_name);
			if (!l) continue;
			System *s = add_system(dir, l);
			if (s) use_link(s, l, 1);
		}
		closedir(d);
	}
	apply_overrides();
}

static const char *ext_of(const char *f) {
	const char *d = strrchr(f, '.');
	return d && d != f ? d : "";
}

static int matches_filter(const char *file, const char *filter) {
	const char *ext = ext_of(file);
	if (!*filter) {
		static const char *skip[] = {".png", ".jpg", ".txt", ".xml", ".db", ".srm", ".sav",
		                             ".state", ".cfg", ".ini", ".dat", ".md5", ".log", ".bak", 0};
		for (int i = 0; skip[i]; i++)
			if (!strcasecmp(ext, skip[i])) return 0;
		return 1;
	}
	if (!*ext) return 0;
	char buf[256];
	snprintf(buf, sizeof buf, "%s", filter);
	for (char *tok = strtok(buf, ",|"); tok; tok = strtok(NULL, ",|")) {
		trim(tok);
		if (*tok == '*') tok++;
		if (*tok != '.') { if (!strcasecmp(ext + 1, tok)) return 1; }
		else if (!strcasecmp(ext, tok)) return 1;
	}
	return 0;
}

static char *display_name(const char *file, int strip_ext) {
	char buf[512], out[512];
	snprintf(buf, sizeof buf, "%s", file);
	char *dot = strrchr(buf, '.');
	if (strip_ext && dot && dot != buf) *dot = 0;
	size_t o = 0;
	int depth = 0;
	for (char *p = buf; *p && o < sizeof out - 1; p++) {
		if (*p == '(' || *p == '[') depth++;
		else if ((*p == ')' || *p == ']') && depth) depth--;
		else if (!depth) out[o++] = *p == '_' ? ' ' : *p;
	}
	out[o] = 0;
	/* collapse spaces */
	char *r = out, *w = out;
	for (; *r; r++)
		if (!(*r == ' ' && (w == out || w[-1] == ' '))) *w++ = *r;
	*w = 0;
	trim(out);
	/* "Legend of Zelda, The" -> "The Legend of Zelda" */
	size_t l = strlen(out);
	if (l > 5 && !strcmp(out + l - 5, ", The")) {
		out[l - 5] = 0;
		snprintf(buf, sizeof buf, "The %s", out);
		snprintf(out, sizeof out, "%s", buf);
	}
	return xstrdup(*out ? out : buf);
}

static void scan_games(void) {
	for (int s = 0; s < nsys; s++) {
		int first = ngames;
		DIR *d = opendir(systems[s].dir);
		struct dirent *e;
		if (!d) continue;
		while ((e = readdir(d)) && ngames < MAX_GAMES) {
			if (e->d_name[0] == '.') continue;
			char p[PATH_MAX];
			struct stat st;
			snprintf(p, sizeof p, "%s/%s", systems[s].dir, e->d_name);
			if (stat(p, &st) || !S_ISREG(st.st_mode)) continue;
			if (!matches_filter(e->d_name, systems[s].filter)) continue;
			Game *g = &games[ngames++];
			memset(g, 0, sizeof *g);
			g->path = xstrdup(p);
			g->file = xstrdup(e->d_name);
			g->name = display_name(e->d_name, 1);
			g->sys = s;
		}
		closedir(d);
		/* official names written by tools/fetch-boxart.py: "<file>\t<name>" */
		char np[PATH_MAX], line[1024];
		snprintf(np, sizeof np, "%s/.images/names.txt", systems[s].dir);
		FILE *nf = fopen(np, "r");
		if (nf) {
			while (fgets(line, sizeof line, nf)) {
				char *tab = strchr(line, '\t');
				if (!tab) continue;
				*tab = 0;
				trim(tab + 1);
				if (!tab[1]) continue;
				for (int i = first; i < ngames; i++)
					if (!strcmp(games[i].file, line)) {
						free(games[i].name);
						games[i].name = display_name(tab + 1, 0);
						break;
					}
			}
			fclose(nf);
		}
	}
}

/* ---------- favourites, play history, last selection ---------- */

static char data_dir[PATH_MAX], fav_file[PATH_MAX], hist_file[PATH_MAX], state_file[PATH_MAX];

static Game *game_by_path(const char *p) {
	for (int i = 0; i < ngames; i++)
		if (!strcmp(games[i].path, p)) return &games[i];
	return NULL;
}

static void load_lists(void) {
	char line[PATH_MAX + 64];
	FILE *f = fopen(fav_file, "r");
	if (f) {
		while (fgets(line, sizeof line, f)) {
			trim(line);
			Game *g = game_by_path(line);
			if (g) g->fav = 1;
		}
		fclose(f);
	}
	f = fopen(hist_file, "r");
	if (f) {
		while (fgets(line, sizeof line, f)) {
			long last;
			int plays, n = 0;
			if (sscanf(line, "%ld %d %n", &last, &plays, &n) < 2 || !n) continue;
			char *p = line + n;
			trim(p);
			Game *g = game_by_path(p);
			if (g) { g->last = last; g->plays = plays; }
		}
		fclose(f);
	}
}

static void save_lists(void) {
	FILE *f = fopen(fav_file, "w");
	if (f) {
		for (int i = 0; i < ngames; i++)
			if (games[i].fav) fprintf(f, "%s\n", games[i].path);
		fclose(f);
	}
	f = fopen(hist_file, "w");
	if (f) {
		for (int i = 0; i < ngames; i++)
			if (games[i].plays) fprintf(f, "%ld %d %s\n", games[i].last, games[i].plays, games[i].path);
		fclose(f);
	}
	sync();
}

/* ---------- tabs ---------- */

enum { TAB_RECENT, TAB_ALL, TAB_FAV, TAB_SYS };
typedef struct { int kind, sys; char label[32]; } Tab;
static Tab tabs[MAX_TABS];
static int ntabs, cur_tab;
static int list[MAX_GAMES], nlist;
static int sel;            /* index into list */
static float anim;         /* animated position that follows sel */

static int cmp_game_name(const void *a, const void *b) {
	const Game *x = &games[*(const int *)a], *y = &games[*(const int *)b];
	int c = strcasecmp(x->name, y->name);
	return c ? c : x->sys - y->sys;
}
static int cmp_game_recent(const void *a, const void *b) {
	const Game *x = &games[*(const int *)a], *y = &games[*(const int *)b];
	return (y->last > x->last) - (y->last < x->last);
}

static void build_list(int keep_game) {
	Tab *t = &tabs[cur_tab];
	nlist = 0;
	for (int i = 0; i < ngames; i++) {
		Game *g = &games[i];
		if ((t->kind == TAB_ALL) || (t->kind == TAB_FAV && g->fav) ||
		    (t->kind == TAB_RECENT && g->last) || (t->kind == TAB_SYS && g->sys == t->sys))
			list[nlist++] = i;
	}
	qsort(list, nlist, sizeof *list, t->kind == TAB_RECENT ? cmp_game_recent : cmp_game_name);
	sel = 0;
	for (int i = 0; i < nlist; i++)
		if (list[i] == keep_game) sel = i;
	anim = sel;
}

static int cmp_sys_name(const void *a, const void *b) {
	return strcasecmp(systems[((const Tab *)a)->sys].name, systems[((const Tab *)b)->sys].name);
}

static void build_tabs(void) {
	int has_recent = 0, has_fav = 0;
	for (int i = 0; i < ngames; i++) {
		has_recent |= games[i].last != 0;
		has_fav |= games[i].fav;
	}
	ntabs = 0;
	if (has_recent) tabs[ntabs++] = (Tab){TAB_RECENT, -1, "Recent"};
	tabs[ntabs++] = (Tab){TAB_ALL, -1, "All"};
	if (has_fav) tabs[ntabs++] = (Tab){TAB_FAV, -1, "Favourites"};
	int first = ntabs;
	for (int s = 0; s < nsys; s++) {
		int n = 0;
		for (int i = 0; i < ngames && !n; i++) n = games[i].sys == s;
		if (!n) continue;
		tabs[ntabs].kind = TAB_SYS;
		tabs[ntabs].sys = s;
		snprintf(tabs[ntabs].label, sizeof tabs[ntabs].label, "%s", systems[s].name);
		ntabs++;
	}
	qsort(tabs + first, ntabs - first, sizeof *tabs, cmp_sys_name);
}

static int find_tab(const char *label) {
	for (int i = 0; i < ntabs; i++)
		if (!strcmp(tabs[i].label, label)) return i;
	return -1;
}

static void save_state(void) {
	FILE *f = fopen(state_file, "w");
	if (!f) return;
	fprintf(f, "tab=%s\n", tabs[cur_tab].label);
	if (nlist) fprintf(f, "game=%s\n", games[list[sel]].path);
	fclose(f);
}

static void load_state(void) {
	char line[PATH_MAX + 16], tab[32] = "All", game[PATH_MAX] = "";
	FILE *f = fopen(state_file, "r");
	if (f) {
		while (fgets(line, sizeof line, f)) {
			trim(line);
			if (!strncmp(line, "tab=", 4)) snprintf(tab, sizeof tab, "%s", line + 4);
			if (!strncmp(line, "game=", 5)) snprintf(game, sizeof game, "%s", line + 5);
		}
		fclose(f);
	}
	int t = find_tab(tab);
	cur_tab = t >= 0 ? t : find_tab("All");
	Game *g = game_by_path(game);
	build_list(g ? (int)(g - games) : -1);
}

/* ---------- drawing ---------- */

static SDL_Surface *screen, *frame, *background;
static TTF_Font *f_tab, *f_tab_b, *f_title, *f_sub, *f_hint, *f_key, *f_card, *f_clock;
static Uint16 bg_row[H];

static inline Uint16 blend565(Uint16 a, Uint16 b, int alpha /* 0..32, 32 = all a */) {
	Uint32 x = (a | ((Uint32)a << 16)) & 0x07E0F81F;
	Uint32 y = (b | ((Uint32)b << 16)) & 0x07E0F81F;
	Uint32 r = ((((x - y) * alpha) >> 5) + y) & 0x07E0F81F;
	return (Uint16)(r | (r >> 16));
}

static void make_background(void) {
	background = SDL_CreateRGBSurface(SDL_SWSURFACE, W, H, 16, 0xF800, 0x07E0, 0x001F, 0);
	for (int y = 0; y < H; y++) {
		float t = (float)y / H;
		bg_row[y] = rgb(20 + 10 * t, 22 + 8 * t, 40 + 30 * t);
	}
	/* faint floor under the shelf */
	for (int y = SHELF_BASE + 2; y < H; y++) bg_row[y] = blend565(rgb(30, 30, 55), bg_row[y], 20);
	SDL_LockSurface(background);
	for (int y = 0; y < H; y++) {
		Uint16 *p = (Uint16 *)((Uint8 *)background->pixels + y * background->pitch);
		for (int x = 0; x < W; x++) p[x] = bg_row[y];
	}
	SDL_UnlockSurface(background);
}

static void fill_rect(SDL_Surface *s, int x, int y, int w, int h, Uint16 c) {
	SDL_Rect r = {x, y, w, h};
	SDL_FillRect(s, &r, c);
}

static void text(SDL_Surface *dst, TTF_Font *f, const char *s, int x, int y, SDL_Color c, int align) {
	if (!s || !*s) return;
	SDL_Surface *t = TTF_RenderUTF8_Blended(f, s, c);
	if (!t) return;
	SDL_Rect r = {x - (align == 1 ? t->w / 2 : align == 2 ? t->w : 0), y, 0, 0};
	SDL_BlitSurface(t, NULL, dst, &r);
	SDL_FreeSurface(t);
}

static int text_w(TTF_Font *f, const char *s) {
	int w = 0, h;
	TTF_SizeUTF8(f, s, &w, &h);
	return w;
}

/* Scale src (RGB565) into dst at (dx,dy,dw,dh), nearest neighbour, darkened by
 * dim (0..32) and with a fading reflection of refl rows under it. */
static void draw_cover(SDL_Surface *src, int dx, int dy, int dw, int dh, int dim, int refl) {
	if (dw <= 0 || dh <= 0) return;
	Uint16 shade = rgb(10, 10, 25);
	Uint32 sx_step = ((Uint32)src->w << 16) / dw, sy_step = ((Uint32)src->h << 16) / dh;
	int x0 = dx < 0 ? -dx : 0, x1 = dx + dw > W ? W - dx : dw;
	for (int y = 0; y < dh + refl; y++) {
		int ty = dy + y;
		if (ty < 0 || ty >= H) continue;
		int sy, alpha;
		if (y < dh) { sy = (y * sy_step) >> 16; alpha = 32 - dim; }
		else {
			int r = y - dh; /* reflection row */
			sy = ((dh - 1 - r) * sy_step) >> 16;
			alpha = (14 * (refl - r) / refl) * (32 - dim) / 32;
		}
		const Uint16 *s = (const Uint16 *)((const Uint8 *)src->pixels + sy * src->pitch);
		Uint16 *d = (Uint16 *)((Uint8 *)frame->pixels + ty * frame->pitch) + dx;
		Uint32 sx = x0 * sx_step;
		if (y < dh) {
			if (dim)
				for (int x = x0; x < x1; x++, sx += sx_step) d[x] = blend565(s[sx >> 16], shade, alpha);
			else
				for (int x = x0; x < x1; x++, sx += sx_step) d[x] = s[sx >> 16];
		} else {
			for (int x = x0; x < x1; x++, sx += sx_step) d[x] = blend565(s[sx >> 16], d[x], alpha);
		}
	}
}

/* convert any surface to RGB565 and shrink it (area average) to fit the cover box */
static SDL_Surface *fit_cover(SDL_Surface *img) {
	SDL_Surface *rgb32 = SDL_CreateRGBSurface(SDL_SWSURFACE, img->w, img->h, 32,
	                                          0x00FF0000, 0x0000FF00, 0x000000FF, 0);
	if (!rgb32) return NULL;
	SDL_FillRect(rgb32, NULL, SDL_MapRGB(rgb32->format, 20, 20, 30));
	SDL_SetAlpha(img, img->flags & SDL_SRCALPHA, 255);
	SDL_BlitSurface(img, NULL, rgb32, NULL);
	float k = (float)COVER_W / img->w;
	if ((float)COVER_H / img->h < k) k = (float)COVER_H / img->h;
	if (k > 1) k = 1;
	int w = img->w * k + 0.5f, h = img->h * k + 0.5f;
	if (w < 1) w = 1;
	if (h < 1) h = 1;
	SDL_Surface *out = SDL_CreateRGBSurface(SDL_SWSURFACE, w, h, 16, 0xF800, 0x07E0, 0x001F, 0);
	SDL_LockSurface(rgb32);
	SDL_LockSurface(out);
	for (int y = 0; y < h; y++) {
		int sy0 = y * img->h / h, sy1 = (y + 1) * img->h / h;
		if (sy1 <= sy0) sy1 = sy0 + 1;
		Uint16 *d = (Uint16 *)((Uint8 *)out->pixels + y * out->pitch);
		for (int x = 0; x < w; x++) {
			int sx0 = x * img->w / w, sx1 = (x + 1) * img->w / w;
			if (sx1 <= sx0) sx1 = sx0 + 1;
			Uint32 r = 0, g = 0, b = 0, n = 0;
			for (int yy = sy0; yy < sy1; yy++) {
				const Uint32 *s = (const Uint32 *)((const Uint8 *)rgb32->pixels + yy * rgb32->pitch);
				for (int xx = sx0; xx < sx1; xx++, n++) {
					r += (s[xx] >> 16) & 255;
					g += (s[xx] >> 8) & 255;
					b += s[xx] & 255;
				}
			}
			d[x] = rgb(r / n, g / n, b / n);
		}
	}
	SDL_UnlockSurface(out);
	SDL_UnlockSurface(rgb32);
	SDL_FreeSurface(rgb32);
	return out;
}

/* a plain card for games without box art: system colour, system name, title */
static SDL_Surface *make_card(Game *g) {
	System *s = &systems[g->sys];
	SDL_Surface *c = SDL_CreateRGBSurface(SDL_SWSURFACE, COVER_W, COVER_H, 16, 0xF800, 0x07E0, 0x001F, 0);
	SDL_FillRect(c, NULL, blend565(s->color, rgb(20, 20, 30), 20));
	fill_rect(c, 0, 0, COVER_W, 22, s->color);
	SDL_Color white = {255, 255, 255, 0};
	text(c, f_tab_b, s->name, COVER_W / 2, 3, white, 1);
	/* word-wrap the title into up to 5 lines */
	char buf[512], line[512] = "";
	const char *lines[6];
	char store[6][128];
	int nl = 0;
	snprintf(buf, sizeof buf, "%s", g->name);
	for (char *w = strtok(buf, " "); w && nl < 5; w = strtok(NULL, " ")) {
		char tryl[512];
		snprintf(tryl, sizeof tryl, "%s%s%s", line, *line ? " " : "", w);
		if (*line && text_w(f_card, tryl) > COVER_W - 10) {
			snprintf(store[nl], sizeof store[nl], "%s", line);
			lines[nl] = store[nl];
			nl++;
			snprintf(line, sizeof line, "%s", w);
		} else snprintf(line, sizeof line, "%s", tryl);
	}
	if (*line && nl < 5) { snprintf(store[nl], sizeof store[nl], "%s", line); lines[nl] = store[nl]; nl++; }
	int lh = TTF_FontLineSkip(f_card), y = 22 + (COVER_H - 22 - nl * lh) / 2;
	for (int i = 0; i < nl; i++, y += lh) text(c, f_card, lines[i], COVER_W / 2, y, white, 1);
	return c;
}

static void load_cover(Game *g) {
	g->cover_tried = 1;
	char p[PATH_MAX], base[512];
	snprintf(base, sizeof base, "%s", g->file);
	char *dot = strrchr(base, '.');
	if (dot && dot != base) *dot = 0;
	static const char *exts[] = {".png", ".jpg", ".PNG", ".JPG", 0};
	SDL_Surface *img = NULL;
	for (int i = 0; exts[i] && !img; i++) {
		snprintf(p, sizeof p, "%s/.images/%s%s", systems[g->sys].dir, base, exts[i]);
		if (access(p, R_OK) == 0) img = IMG_Load(p);
	}
	if (img) {
		g->cover = fit_cover(img);
		SDL_FreeSurface(img);
	}
	if (!g->cover) g->cover = make_card(g);
}

/* keep covers near the selection, load at most one new cover per frame */
static void manage_cache(void) {
	for (int i = 0; i < nlist; i++) {
		Game *g = &games[list[i]];
		if (g->cover && abs(i - sel) > CACHE_RANGE + 4) {
			SDL_FreeSurface(g->cover);
			g->cover = NULL;
			g->cover_tried = 0;
		}
	}
	for (int d = 0; d <= CACHE_RANGE; d++)
		for (int sgn = -1; sgn <= 1; sgn += 2) {
			int i = sel + d * sgn;
			if (i < 0 || i >= nlist) continue;
			Game *g = &games[list[i]];
			if (!g->cover_tried) { load_cover(g); return; }
		}
}

static void free_all_covers(void) {
	for (int i = 0; i < ngames; i++)
		if (games[i].cover) { SDL_FreeSurface(games[i].cover); games[i].cover = NULL; games[i].cover_tried = 0; }
}

/* slot geometry by distance from the centre: 0, 1, 2, 3, 4 (4 = off screen) */
static const float slot_x[] = {0, 96, 140, 190, 250};
static const float slot_s[] = {1.0f, 0.72f, 0.588f, 0.47f, 0.40f};
static const float slot_dim[] = {0, 9, 15, 20, 26};

static float lerp_tab(const float *t, float d) {
	if (d >= 4) return t[4];
	int i = (int)d;
	float f = d - i;
	return t[i] + (t[i + 1] - t[i]) * f;
}

static void draw_shelf(void) {
	int lo = (int)anim - 4, hi = (int)anim + 5;
	/* far covers first, the centre one last */
	for (int ring = 5; ring >= 0; ring--)
		for (int i = lo; i <= hi; i++) {
			if (i < 0 || i >= nlist) continue;
			float p = i - anim, d = p < 0 ? -p : p;
			if ((int)(d + 0.5f) != ring || d > 4.2f) continue;
			Game *g = &games[list[i]];
			SDL_Surface *c = g->cover;
			if (!c) continue;
			float s = lerp_tab(slot_s, d);
			float cx = W / 2 + (p < 0 ? -1 : 1) * lerp_tab(slot_x, d);
			int dw = c->w * s + 0.5f, dh = c->h * s + 0.5f;
			int bw = COVER_W * s + 0.5f;
			int dx = (int)(cx - dw / 2.0f), dy = SHELF_BASE - dh;
			(void)bw;
			int dim = (int)lerp_tab(slot_dim, d);
			if (d < 0.5f) {
				fill_rect(frame, dx - 2, dy - 2, dw + 4, dh + 4, rgb(255, 255, 255));
				fill_rect(frame, dx - 2, SHELF_BASE, dw + 4, 2, bg_row[SHELF_BASE]);
			}
			SDL_LockSurface(frame);
			draw_cover(c, dx, dy, dw, dh, dim, dh / 3);
			SDL_UnlockSurface(frame);
		}
}

static SDL_Surface *tabbar, *hintbar;
static int titlebar_for = -3;

static void render_tabbar(void) {
	if (tabbar) SDL_FreeSurface(tabbar);
	tabbar = SDL_CreateRGBSurface(SDL_SWSURFACE, W, 26, 16, 0xF800, 0x07E0, 0x001F, 0);
	SDL_Rect src = {0, 0, W, 26};
	SDL_BlitSurface(background, &src, tabbar, NULL);
	int xs[MAX_TABS] = {0}, ws[MAX_TABS] = {0}, x = 0;
	for (int i = 0; i < ntabs; i++) {
		ws[i] = text_w(i == cur_tab ? f_tab_b : f_tab, tabs[i].label);
		xs[i] = x;
		x += ws[i] + 16;
	}
	/* scroll so the current tab stays visible left of the clock */
	int off = 12, right = W - 40;
	if (xs[cur_tab] + ws[cur_tab] + off > right) off = right - xs[cur_tab] - ws[cur_tab];
	SDL_Color on = {255, 255, 255, 0}, offc = {170, 170, 180, 0};
	for (int i = 0; i < ntabs; i++) {
		int tx = xs[i] + off;
		if (tx + ws[i] < 0 || tx > right + 10) continue;
		text(tabbar, i == cur_tab ? f_tab_b : f_tab, tabs[i].label, tx, 5, i == cur_tab ? on : offc, 0);
		if (i == cur_tab) fill_rect(tabbar, tx, 22, ws[i], 2, rgb(255, 255, 255));
	}
	/* fade the tabs out under the clock */
	SDL_LockSurface(tabbar);
	for (int y = 0; y < 26; y++) {
		Uint16 *p = (Uint16 *)((Uint8 *)tabbar->pixels + y * tabbar->pitch);
		for (int x = right; x < W; x++) {
			int a = x - right >= 24 ? 0 : 32 - (x - right) * 32 / 24;
			p[x] = blend565(p[x], bg_row[y], a);
		}
	}
	SDL_UnlockSurface(tabbar);
}

static void key_hint(SDL_Surface *s, int *x, int y, const char *key, const char *label) {
	int kw = text_w(f_key, key) + 8;
	if (kw < 14) kw = 14;
	SDL_Color dark = {20, 20, 20, 0}, light = {220, 220, 225, 0};
	/* rounded pill */
	fill_rect(s, *x + 2, y, kw - 4, 14, rgb(235, 235, 235));
	fill_rect(s, *x, y + 2, kw, 10, rgb(235, 235, 235));
	fill_rect(s, *x + 1, y + 1, kw - 2, 12, rgb(235, 235, 235));
	text(s, f_key, key, *x + kw / 2, y + 1, dark, 1);
	text(s, f_hint, label, *x + kw + 5, y, light, 0);
	*x += kw + 5 + text_w(f_hint, label) + 14;
}

static void render_hintbar(void) {
	hintbar = SDL_CreateRGBSurface(SDL_SWSURFACE, W, 18, 16, 0xF800, 0x07E0, 0x001F, 0);
	SDL_Rect src = {0, H - 20, W, 18};
	SDL_BlitSurface(background, &src, hintbar, NULL);
	int x = 12;
	key_hint(hintbar, &x, 2, "A", "Play");
	key_hint(hintbar, &x, 2, "X", "Favourite");
	key_hint(hintbar, &x, 2, "L", "");
	x -= 14 + 5;
	key_hint(hintbar, &x, 2, "R", "Switch list");
	key_hint(hintbar, &x, 2, "START", "Menu");
}

static SDL_Surface *render_text(TTF_Font *f, const char *str, SDL_Color c) {
	return str && *str ? TTF_RenderUTF8_Blended(f, str, c) : NULL;
}

/* title and subtitle are cached as alpha surfaces and blended over the
 * reflections every frame */
static SDL_Surface *title_s, *sub_s;

static void render_titlebar(void) {
	if (title_s) SDL_FreeSurface(title_s);
	if (sub_s) SDL_FreeSurface(sub_s);
	SDL_Color white = {255, 255, 255, 0}, grey = {180, 180, 200, 0};
	if (!nlist) {
		title_s = render_text(f_title, tabs[cur_tab].kind == TAB_FAV ? "No favourites yet" : "No games found", white);
		sub_s = render_text(f_sub, "Copy ROMs to roms/<SYSTEM>/ on the card", grey);
		titlebar_for = -1;
		return;
	}
	Game *g = &games[list[sel]];
	char name[256];
	snprintf(name, sizeof name, "%s%s", g->fav ? "\xE2\x98\x85 " : "", g->name);
	/* shorten long titles */
	while (text_w(f_title, name) > W - 24 && strlen(name) > 4) {
		size_t l = strlen(name) - 3; /* drop the "..." added last time round */
		if (strcmp(name + l, "...")) l += 3;
		do l--; while (l > 1 && (name[l] & 0xC0) == 0x80);
		snprintf(name + l, sizeof name - l, "...");
	}
	title_s = render_text(f_title, name, white);
	/* no "played 2 days ago": without a real-time clock the date is wrong */
	char sub[160];
	snprintf(sub, sizeof sub, "%s  \xE2\x80\xA2  %d of %d", systems[g->sys].longname, sel + 1, nlist);
	sub_s = render_text(f_sub, sub, grey);
	titlebar_for = list[sel];
}

static int battery_level(void) {
	FILE *f = fopen(env_or("F1L_BATTERY", "/sys/class/power_supply/miyoo-battery/voltage_now"), "r");
	long mv = -1;
	if (!f) return -1;
	if (fscanf(f, "%ld", &mv) != 1) mv = -1;
	fclose(f);
	if (mv < 0) return -1;
	if (mv > 100000) mv /= 1000; /* uV */
	int lvl = (int)((mv - 3400) * 100 / (4150 - 3400));
	return lvl < 0 ? 0 : lvl > 100 ? 100 : lvl;
}

/* battery only: the board has no real-time clock, so no clock either */
static void draw_status(void) {
	int lvl = battery_level();
	int bx = W - 22;
	if (lvl >= 0) {
		Uint16 wc = rgb(255, 255, 255), fillc = lvl < 15 ? rgb(240, 70, 60) : wc;
		fill_rect(frame, bx, 9, 14, 1, wc);
		fill_rect(frame, bx, 17, 14, 1, wc);
		fill_rect(frame, bx, 9, 1, 9, wc);
		fill_rect(frame, bx + 13, 9, 1, 9, wc);
		fill_rect(frame, bx + 14, 11, 2, 5, wc);
		fill_rect(frame, bx + 2, 11, (10 * lvl + 50) / 100, 5, fillc);
	}
}

static void draw_menu(void);
static int menu_open;

static void draw(void) {
	SDL_BlitSurface(background, NULL, frame, NULL);
	SDL_Rect r = {0, 0, 0, 0};
	SDL_BlitSurface(tabbar, NULL, frame, &r);
	draw_status();
	draw_shelf();
	if (titlebar_for != (nlist ? list[sel] : -1)) render_titlebar();
	if (title_s) { r.x = (W - title_s->w) / 2; r.y = 202; SDL_BlitSurface(title_s, NULL, frame, &r); }
	if (sub_s) { r.x = (W - sub_s->w) / 2; r.y = 226; SDL_BlitSurface(sub_s, NULL, frame, &r); }
	r.x = 0;
	r.y = H - 20;
	SDL_BlitSurface(hintbar, NULL, frame, &r);
	if (menu_open) draw_menu();
	SDL_BlitSurface(frame, NULL, screen, NULL);
	SDL_Flip(screen);
}

/* ---------- panel mode (same trick as the F1GameStation gmenu2x build) ---------- */

static int set_panel_mode(int w, int h) {
#ifdef F1GS_PANEL
	int ok = 0, fd = open("/dev/fb0", O_RDWR);
	if (fd >= 0) {
		struct fb_var_screeninfo var;
		if (ioctl(fd, FBIOGET_VSCREENINFO, &var) == 0) {
			var.xres = var.xres_virtual = w;
			var.yres = h;
			var.yres_virtual = h * 2;
			var.xoffset = var.yoffset = 0;
			var.bits_per_pixel = 16;
			ok = ioctl(fd, FBIOPUT_VSCREENINFO, &var) == 0;
		}
		close(fd);
	}
	return ok;
#else
	(void)w; (void)h;
	return 0;
#endif
}

/* A game killed with MENU+SELECT can leave the console locked in graphics
 * mode with a raw keyboard; SDL then waits forever for its VT. Put it back
 * the way gmenu2x does before starting SDL. */
static void reset_console(void) {
#ifdef F1GS_PANEL
	int fd = open("/dev/tty0", O_RDONLY);
	if (fd >= 0) {
		ioctl(fd, VT_UNLOCKSWITCH, 1);
		ioctl(fd, KDSETMODE, KD_TEXT);
		ioctl(fd, KDSKBMODE, K_XLATE);
		close(fd);
	}
	usleep(1000);
#endif
}

static void shutdown_video(void) {
	free_all_covers();
	TTF_Quit();
	SDL_Quit();
	set_panel_mode(320, 240); /* games and gmenu2x expect the usual 320x240 screen */
	unsetenv("SDL_FB_BROKEN_MODES");
}

/* ---------- launching ---------- */

static void launch(Game *g) {
	System *s = &systems[g->sys];
	char rom[PATH_MAX + 64], dir[PATH_MAX + 64], file[PATH_MAX], fileq[PATH_MAX + 64], tmp[PATH_MAX];
	char params[2048], cmd[4096];
	g->plays++;
	g->last = time(NULL);
	save_lists();
	save_state();
	shquote(rom, sizeof rom, g->path);
	shquote(dir, sizeof dir, s->dir);
	snprintf(file, sizeof file, "%s", g->file);
	char *dot = strrchr(file, '.');
	shquote(fileq, sizeof fileq, g->file);
	snprintf(params, sizeof params, "%s", s->params);
	if (!*params) snprintf(params, sizeof params, "%s", rom);
	else {
		char orig[2048];
		snprintf(orig, sizeof orig, "%s", params);
		strreplace(params, sizeof params, "[selFullPath]", rom);
		strreplace(params, sizeof params, "%f", rom);
		strreplace(params, sizeof params, "[selPath]", dir);
		if (dot) *dot = 0;
		shquote(tmp, sizeof tmp, file);
		strreplace(params, sizeof params, "[selFile]", tmp);
		strreplace(params, sizeof params, "[selFileFull]", fileq);
		shquote(tmp, sizeof tmp, dot ? dot + 1 : "");
		strreplace(params, sizeof params, "[selExt]", tmp);
		if (!strcmp(orig, params)) {
			size_t l = strlen(params);
			snprintf(params + l, sizeof params - l, " %s", rom);
		}
	}
	snprintf(cmd, sizeof cmd, "%s %s", s->exec, params);
	fprintf(stderr, "coverflow: %s\n", cmd);
	if (getenv("F1L_DRYRUN")) { printf("%s\n", cmd); exit(0); }
	shutdown_video();
	snprintf(tmp, sizeof tmp, "%s", s->exec);
	char *slash = strrchr(tmp, '/');
	if (slash) { *slash = 0; if (chdir(*tmp ? tmp : "/")) perror("chdir"); }
	execlp("/bin/sh", "/bin/sh", "-c", cmd, (char *)NULL);
	perror("exec");
	exit(1);
}

static void open_gmenu2x(const char *gmenu) {
	save_state();
	shutdown_video();
	if (chdir(gmenu)) perror("chdir");
	execlp("./gmenu2x", "./gmenu2x", (char *)NULL);
	perror("gmenu2x");
	exit(1);
}

/* ---------- quick menu (START / SELECT) ---------- */

/* Same controls gmenu2x uses on MiyooCFW: backlight level 1-10 in sysfs and
 * /mnt/.backlight.conf, volume 0-9 through /dev/miyoo_snd and /mnt/.volume.conf */
#define MIYOO_SND_SET_VOLUME _IOWR(0x100, 0, unsigned long)
#define MIYOO_SND_GET_VOLUME _IOWR(0x101, 0, unsigned long)

static int menu_sel, menu_confirm;
static char bl_path[PATH_MAX];
static int bl_max = 10;

static const char *snd_dev(void) { return env_or("F1L_SND", "/dev/miyoo_snd"); }

static void find_backlight(void) {
	const char *fixed = env_or("F1L_BACKLIGHT", "/sys/devices/platform/backlight/backlight/backlight");
	char p[PATH_MAX];
	snprintf(p, sizeof p, "%s/brightness", fixed);
	if (access(p, W_OK) == 0) snprintf(bl_path, sizeof bl_path, "%s", fixed);
	else {
		DIR *d = opendir("/sys/class/backlight");
		struct dirent *e;
		while (d && (e = readdir(d)))
			if (e->d_name[0] != '.') {
				snprintf(bl_path, sizeof bl_path, "/sys/class/backlight/%s", e->d_name);
				break;
			}
		if (d) closedir(d);
	}
	if (!*bl_path) return;
	snprintf(p, sizeof p, "%s/max_brightness", bl_path);
	FILE *f = fopen(p, "r");
	if (f) {
		if (fscanf(f, "%d", &bl_max) != 1 || bl_max < 1) bl_max = 10;
		fclose(f);
	}
	if (bl_max > 10) bl_max = 10; /* MiyooCFW keeps levels 1-10 */
}

static int read_int(const char *path) {
	int v = -1;
	FILE *f = fopen(path, "r");
	if (f) { if (fscanf(f, "%d", &v) != 1) v = -1; fclose(f); }
	return v;
}

static void write_int(const char *path, int v) {
	FILE *f = fopen(path, "w");
	if (f) { fprintf(f, "%d\n", v); fclose(f); }
}

static int get_brightness(void) {
	char p[PATH_MAX];
	if (!*bl_path) return -1;
	snprintf(p, sizeof p, "%s/brightness", bl_path);
	return read_int(p);
}

static void set_brightness(int v) {
	char p[PATH_MAX];
	if (!*bl_path) return;
	if (v < 1) v = 1;
	if (v > bl_max) v = bl_max;
	snprintf(p, sizeof p, "%s/brightness", bl_path);
	write_int(p, v);
	write_int(env_or("F1L_BACKLIGHT_CONF", "/mnt/.backlight.conf"), v);
}

static int get_volume(void) {
	int fd = open(snd_dev(), O_RDWR), v = -1;
	if (fd < 0) return -1;
	if (ioctl(fd, MIYOO_SND_GET_VOLUME, &v)) v = -1;
	close(fd);
	return v;
}

static void set_volume(int v) {
	if (v < 0) v = 0;
	if (v > 9) v = 9;
	int fd = open(snd_dev(), O_RDWR);
	if (fd < 0) return;
	ioctl(fd, MIYOO_SND_SET_VOLUME, v);
	close(fd);
	write_int(env_or("F1L_VOLUME_CONF", "/mnt/.volume.conf"), v);
}

/* How the display driver (rgb480x272fb) shows 320x240 games: 0 centred,
 * 1 fit the height (362x272), 2 fill 480x272. Saved in /mnt/.f1gs-scale.conf,
 * which normalboot.custom.sh writes back at boot. */
static const char *scale_names[] = {"Original", "Fit", "Fill"};

static const char *scale_path(void) {
	return env_or("F1L_SCALE", "/sys/module/rgb480x272fb/parameters/scale");
}

static int get_scale(void) {
	int v = read_int(scale_path());
	return v >= 0 && v <= 2 ? v : -1;
}

static void set_scale(int v) {
	if (v < 0) v = 0;
	if (v > 2) v = 2;
	write_int(scale_path(), v);
	write_int(env_or("F1L_SCALE_CONF", "/mnt/.f1gs-scale.conf"), v);
}

enum { MI_RESUME, MI_BRIGHT, MI_VOLUME, MI_SCALE, MI_CLASSIC, MI_POWER, MI_COUNT };

static void power_off(void) {
	save_state();
	save_lists();
	if (getenv("F1L_DRYRUN")) { printf("poweroff\n"); exit(0); }
	shutdown_video();
	execlp("/bin/sh", "/bin/sh", "-c", "sync; mount -o remount,ro \"${HOME:-/mnt}\"; poweroff", (char *)NULL);
	exit(1);
}

static void bar(int x, int y, int w, int level, int max) {
	fill_rect(frame, x, y, w, 6, rgb(70, 70, 95));
	if (max > 0 && level > 0) fill_rect(frame, x, y, w * level / max, 6, rgb(235, 235, 245));
}

static void draw_menu(void) {
	SDL_LockSurface(frame);
	for (int y = 0; y < H; y++) {
		Uint16 *p = (Uint16 *)((Uint8 *)frame->pixels + y * frame->pitch);
		for (int x = 0; x < W; x++) p[x] = blend565(p[x], rgb(5, 5, 15), 12);
	}
	SDL_UnlockSurface(frame);
	const int pw = 240, ph = 30 + MI_COUNT * 26, px = (W - pw) / 2, py = (H - ph) / 2;
	fill_rect(frame, px + 2, py, pw - 4, ph, rgb(32, 34, 58));
	fill_rect(frame, px, py + 2, pw, ph - 4, rgb(32, 34, 58));
	SDL_Color white = {255, 255, 255, 0}, grey = {170, 170, 185, 0}, dim = {110, 110, 125, 0};
	text(frame, f_tab_b, "Menu", px + 16, py + 8, grey, 0);
	int b = get_brightness(), v = get_volume(), sc = get_scale();
	for (int i = 0; i < MI_COUNT; i++) {
		int y = py + 30 + i * 26;
		int on = i == menu_sel;
		if (on) fill_rect(frame, px + 8, y - 3, pw - 16, 24, rgb(70, 74, 120));
		const char *label = i == MI_RESUME ? "Back to games" : i == MI_BRIGHT ? "Brightness"
		                  : i == MI_VOLUME ? "Volume" : i == MI_SCALE ? "Game screen"
		                  : i == MI_CLASSIC ? "Classic menu (gmenu2x)"
		                  : menu_confirm ? "Press A again to power off" : "Power off";
		int disabled = (i == MI_BRIGHT && b < 0) || (i == MI_VOLUME && v < 0) || (i == MI_SCALE && sc < 0);
		text(frame, on ? f_tab_b : f_tab, label, px + 18, y, disabled ? dim : on ? white : grey, 0);
		if (i == MI_BRIGHT && b >= 0) bar(px + pw - 110, y + 6, 90, b, bl_max);
		if (i == MI_VOLUME && v >= 0) bar(px + pw - 110, y + 6, 90, v, 9);
		if (i == MI_SCALE && sc >= 0) {
			char val[24];
			snprintf(val, sizeof val, "%s%s%s", sc > 0 ? "\xE2\x80\xB9 " : "", scale_names[sc],
			         sc < 2 ? " \xE2\x80\xBA" : "");
			text(frame, on ? f_tab_b : f_tab, val, px + pw - 20, y, on ? white : grey, 2);
		}
	}
}

static void menu_key(SDLKey k, const char *gmenu) {
	if (k != SDLK_LALT) menu_confirm = 0;
	switch (k) {
	case SDLK_UP: menu_sel = (menu_sel + MI_COUNT - 1) % MI_COUNT; break;
	case SDLK_DOWN: menu_sel = (menu_sel + 1) % MI_COUNT; break;
	case SDLK_LEFT:
	case SDLK_RIGHT: {
		int d = k == SDLK_LEFT ? -1 : 1;
		if (menu_sel == MI_BRIGHT && get_brightness() >= 0) set_brightness(get_brightness() + d);
		if (menu_sel == MI_VOLUME && get_volume() >= 0) set_volume(get_volume() + d);
		if (menu_sel == MI_SCALE && get_scale() >= 0) set_scale(get_scale() + d);
		break;
	}
	case SDLK_LALT: /* A */
		if (menu_sel == MI_RESUME) menu_open = 0;
		else if (menu_sel == MI_SCALE && get_scale() >= 0) set_scale((get_scale() + 1) % 3);
		else if (menu_sel == MI_CLASSIC && gmenu) open_gmenu2x(gmenu);
		else if (menu_sel == MI_POWER) {
			if (menu_confirm) power_off();
			menu_confirm = 1;
		}
		break;
	case SDLK_LCTRL:  /* B */
	case SDLK_RETURN: /* START */
	case SDLK_ESCAPE: /* SELECT */
		menu_open = 0;
		break;
	default: break;
	}
}

/* ---------- input ---------- */

static void move(int d) {
	if (!nlist) return;
	sel += d;
	if (sel < 0) sel = 0;
	if (sel >= nlist) sel = nlist - 1;
}

static void jump_letter(int dir) {
	if (!nlist) return;
	int c0 = toupper((unsigned char)games[list[sel]].name[0]);
	int i = sel;
	if (dir > 0) {
		while (i < nlist - 1 && toupper((unsigned char)games[list[i]].name[0]) == c0) i++;
	} else {
		/* to the first game of this letter, or of the previous letter */
		while (i > 0 && toupper((unsigned char)games[list[i - 1]].name[0]) == c0) i--;
		if (i == sel && i > 0) {
			int c1 = toupper((unsigned char)games[list[i - 1]].name[0]);
			i--;
			while (i > 0 && toupper((unsigned char)games[list[i - 1]].name[0]) == c1) i--;
		}
	}
	sel = i;
}

static void switch_tab(int d) {
	int keep = nlist ? list[sel] : -1;
	cur_tab = (cur_tab + d + ntabs) % ntabs;
	build_list(keep);
	render_tabbar();
	titlebar_for = -2;
}

static void toggle_fav(void) {
	if (!nlist) return;
	Game *g = &games[list[sel]];
	g->fav = !g->fav;
	save_lists();
	char label[32];
	snprintf(label, sizeof label, "%s", tabs[cur_tab].label);
	build_tabs();
	int t = find_tab(label);
	cur_tab = t >= 0 ? t : find_tab("All");
	build_list((int)(g - games));
	render_tabbar();
	titlebar_for = -2;
}

/* returns 0 to keep going */
static int handle_key(SDLKey k, const char *gmenu) {
	if (menu_open) { menu_key(k, gmenu); return 0; }
	switch (k) {
	case SDLK_LEFT: move(-1); break;
	case SDLK_RIGHT: move(1); break;
	case SDLK_UP: jump_letter(-1); break;
	case SDLK_DOWN: jump_letter(1); break;
	case SDLK_TAB: switch_tab(-1); break;       /* L */
	case SDLK_BACKSPACE: switch_tab(1); break;  /* R */
	case SDLK_PAGEUP: move(-10); break;         /* L2 */
	case SDLK_PAGEDOWN: move(10); break;        /* R2 */
	case SDLK_LSHIFT: toggle_fav(); break;      /* X */
	case SDLK_LALT:                              /* A */
		if (nlist) launch(&games[list[sel]]);
		break;
	case SDLK_RETURN:                            /* START */
	case SDLK_ESCAPE:                            /* SELECT */
		menu_open = 1;
		menu_sel = MI_RESUME;
		menu_confirm = 0;
		break;
	default: break;
	}
	return 0;
}

static void step_anim(float dt_ms) {
	float diff = sel - anim;
	if (diff > 3) anim = sel - 3;
	if (diff < -3) anim = sel + 3;
	diff = sel - anim;
	float k = dt_ms / 70.0f;
	if (k > 1) k = 1;
	anim += diff * k;
	if (diff * (sel - anim) <= 0 || (sel - anim < 0.01f && sel - anim > -0.01f)) anim = sel;
}

/* ---------- main ---------- */

static TTF_Font *open_font(const char *dir, const char *file, int size) {
	char p[PATH_MAX];
	snprintf(p, sizeof p, "%s/fonts/%s", dir, file);
	TTF_Font *f = TTF_OpenFont(p, size);
	if (!f) { fprintf(stderr, "coverflow: font %s: %s\n", p, TTF_GetError()); exit(1); }
	return f;
}

int main(int argc, char **argv) {
	(void)argc;
	char exe_dir[PATH_MAX];
	ssize_t n = readlink("/proc/self/exe", exe_dir, sizeof exe_dir - 1);
	if (n <= 0) snprintf(exe_dir, sizeof exe_dir, "%s", argv[0]);
	else exe_dir[n] = 0;
	char *sl = strrchr(exe_dir, '/');
	if (sl) *sl = 0;

	char rr[sizeof roms_roots];
	snprintf(rr, sizeof rr, "%s", env_or("F1L_ROMS", "/roms:/mnt/roms"));
	for (char *t = strtok(rr, ":"); t && nroots < 8; t = strtok(NULL, ":")) {
		snprintf(roms_roots[nroots], PATH_MAX, "%s", t);
		size_t l = strlen(roms_roots[nroots]);
		while (l > 1 && roms_roots[nroots][l - 1] == '/') roms_roots[nroots][--l] = 0;
		nroots++;
	}
	const char *gmenu = env_or("F1L_GMENU2X", "/mnt/gmenu2x");
	snprintf(data_dir, sizeof data_dir, "%s", env_or("F1L_DATA", exe_dir));
	snprintf(override_cfg, sizeof override_cfg, "%s/systems.cfg", data_dir);
	snprintf(fav_file, sizeof fav_file, "%s/favourites.txt", data_dir);
	snprintf(hist_file, sizeof hist_file, "%s/history.txt", data_dir);
	snprintf(state_file, sizeof state_file, "%s/state.txt", data_dir);

	scan_links(gmenu);
	find_systems();
	scan_games();
	load_lists();
	build_tabs();
	fprintf(stderr, "coverflow: %d systems, %d games\n", nsys, ngames);

	reset_console();
	/* not SDL_FBCON_DONT_CLEAR like gmenu2x: with a single-buffered screen,
	 * SDL 1.2's fbcon then copies from the missing second page in SDL_Quit
	 * and crashes */
	unsetenv("SDL_FBCON_DONT_CLEAR");
	setenv("SDL_NOMOUSE", "1", 1);
	if (set_panel_mode(W, H)) setenv("SDL_FB_BROKEN_MODES", "1", 1);
	if (SDL_Init(SDL_INIT_VIDEO) < 0) { fprintf(stderr, "SDL_Init: %s\n", SDL_GetError()); return 1; }
	unsetenv("SDL_FB_BROKEN_MODES");
	SDL_ShowCursor(SDL_DISABLE);
	screen = SDL_SetVideoMode(W, H, 16, SDL_SWSURFACE);
	if (!screen) { fprintf(stderr, "SDL_SetVideoMode: %s\n", SDL_GetError()); return 1; }
	SDL_EnableKeyRepeat(260, 70);
	TTF_Init();
	f_tab = open_font(exe_dir, "DejaVuSans.ttf", 12);
	f_tab_b = open_font(exe_dir, "DejaVuSans-Bold.ttf", 12);
	f_title = open_font(exe_dir, "DejaVuSans-Bold.ttf", 18);
	f_sub = open_font(exe_dir, "DejaVuSans.ttf", 11);
	f_hint = open_font(exe_dir, "DejaVuSans.ttf", 11);
	f_key = open_font(exe_dir, "DejaVuSans-Bold.ttf", 9);
	f_card = open_font(exe_dir, "DejaVuSans-Bold.ttf", 12);
	f_clock = open_font(exe_dir, "DejaVuSans.ttf", 12);

	frame = SDL_CreateRGBSurface(SDL_SWSURFACE, W, H, 16, 0xF800, 0x07E0, 0x001F, 0);
	make_background();
	load_state();
	find_backlight();
	render_tabbar();
	render_hintbar();

	/* test hooks: F1L_KEYS="rrl..." plays keys, F1L_SCREENSHOT=file.bmp saves
	 * the settled frame and quits, F1L_BENCH=N times N scrolling frames */
	const char *keys = getenv("F1L_KEYS");
	for (; keys && *keys; keys++) {
		SDLKey k = 0;
		switch (*keys) {
		case 'l': k = SDLK_LEFT; break;   case 'r': k = SDLK_RIGHT; break;
		case 'u': k = SDLK_UP; break;     case 'd': k = SDLK_DOWN; break;
		case 'L': k = SDLK_TAB; break;    case 'R': k = SDLK_BACKSPACE; break;
		case 'x': k = SDLK_LSHIFT; break; case 'a': k = SDLK_LALT; break;
		case 's': k = SDLK_RETURN; break; case 'b': k = SDLK_LCTRL; break;
		}
		if (k) handle_key(k, NULL);
	}
	const char *shot = getenv("F1L_SCREENSHOT");
	if (shot) {
		float t = getenv("F1L_ANIM") ? atof(getenv("F1L_ANIM")) : 0;
		anim = sel - t;
		for (int i = 0; i < 2 * CACHE_RANGE + 2; i++) manage_cache();
		draw();
		SDL_SaveBMP(frame, shot);
		SDL_Quit();
		return 0;
	}
	const char *bench = getenv("F1L_BENCH");
	if (bench) {
		int frames = atoi(bench);
		for (int i = 0; i < 2 * CACHE_RANGE + 2; i++) manage_cache();
		Uint32 t0 = SDL_GetTicks();
		for (int i = 0; i < frames; i++) {
			anim = (i % 40) * 0.1f;
			sel = (int)(anim + 0.5f) < nlist ? (int)(anim + 0.5f) : 0;
			draw();
		}
		Uint32 t1 = SDL_GetTicks();
		printf("coverflow: %d frames in %u ms, %.2f ms/frame\n", frames, t1 - t0, (float)(t1 - t0) / frames);
		SDL_Quit();
		return 0;
	}

	Uint32 last = SDL_GetTicks(), last_clock = 0;
	int dirty = 1;
	for (;;) {
		SDL_Event e;
		while (SDL_PollEvent(&e)) {
			if (e.type == SDL_QUIT) { save_state(); SDL_Quit(); return 0; }
			if (e.type == SDL_KEYDOWN) {
				if (handle_key(e.key.keysym.sym, gmenu)) { save_state(); SDL_Quit(); return 0; }
				dirty = 1;
			}
		}
		Uint32 now = SDL_GetTicks();
		float before = anim;
		step_anim((float)(now - last));
		last = now;
		if (anim != before) dirty = 1;
		int loading = 0;
		for (int i = sel - CACHE_RANGE; i <= sel + CACHE_RANGE; i++)
			if (i >= 0 && i < nlist && !games[list[i]].cover_tried) loading = 1;
		if (loading) { manage_cache(); dirty = 1; }
		if (now - last_clock > 20000) { last_clock = now; dirty = 1; }
		if (dirty) { draw(); dirty = 0; }
		else SDL_Delay(16);
	}
}
