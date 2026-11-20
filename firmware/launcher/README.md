# Coverflow launcher

A horizontal game shelf for the F1GameStation, in place of gmenu2x's icon grid.
All games from all systems sit on one row of box art; L/R switch between
All, Recent, Favourites and one list per system.

| Button | Does |
| --- | --- |
| Left / Right | previous / next game (hold to scroll) |
| Up / Down | jump to the previous / next letter |
| L / R | switch list (Recent, All, Favourites, NES, SNES, ...) |
| L2 / R2 | 10 games back / forward |
| A | play |
| X | add to / remove from Favourites |
| START or SELECT | quick menu: brightness, volume, game screen (Original 320x240 / Fit height / Fill), classic gmenu2x menu (settings, apps), power off |

## How it finds and starts games

ROMs live in `roms/<SYSTEM>/` (`/mnt/roms` on the MiyooCFW card, `/roms` on
others; `F1L_ROMS` changes the list). It reads gmenu2x's own links
(`/mnt/gmenu2x/sections/*/*`) and, like gmenu2x, ignores links whose program
isn't on the card. A link with `selectordir=<roms>/<SYSTEM>` gives that system
its emulator (one in `sections/emulators` wins, then `cores`). System folders
without such a link are started with a known RetroArch core link instead
(GB/GBC gambatte, GBA gpsp, NES fceumm, SNES snes9x2005, MD picodrive, ...).
A game starts with the link's `exec` and `params`, exactly as from gmenu2x.
To pick a different emulator, add a line to `/mnt/coverflow/systems.cfg`:

    SNES=/mnt/gmenu2x/sections/cores/snes9x2005_plus.ra

Favourites, play history and the last position are kept in `/mnt/coverflow/`.

## Adding games

The card's games partition (btrfs, `/mnt/roms`) can't be opened on a Mac or
PC, so new games go through the BOOT partition, which can:

1. Put the card in the computer. Copy the ROMs to `add-games/<SYSTEM>/` on the
   BOOT volume, e.g. `add-games/NES/`, `add-games/SNES/` (the folder names of
   `roms/` on the console; NES, SNES, GB, GBC, GBA and MD are there already).
2. For box art and proper names, run
   `python3 tools/fetch-boxart.py /Volumes/BOOT/add-games` (needs internet).
3. Eject the card and start the console. `normalboot.custom.sh` moves the
   games, covers and names into `roms/<SYSTEM>/` (merging `names.txt`) and
   empties `add-games/`; macOS's `._*` and `.DS_Store` files are dropped.

BOOT is 256 MB on cards made with `firmware/miyoocfw/scripts/make-sd.sh`.
Games without art still show, on a plain card with their file name.

## Box art

Covers are read from `roms/<SYSTEM>/.images/<ROM file name>.png`, the
folder the MiyooCFW scraper and gmenu2x already use. Games without art get a
plain card in the system's colour.

`tools/fetch-boxart.py` fills those folders from a computer with internet:

    python3 tools/fetch-boxart.py /Volumes/BOOT/add-games   # games waiting on the card

It matches each ROM by its No-Intro name, then by CRC (so renamed files still
match), then by a fuzzy name match, downloads the cover from the
libretro-thumbnails collection and shrinks it to 102x136 so the console only
has to decode a small PNG. `--kind Named_Titles` fetches title screens instead.
It also writes the official name of every game it recognises to
`.images/names.txt`, so a file called `drmario_usa.nes` shows as "Dr. Mario".
Run it again after adding ROMs; existing covers are kept.

## Build and install

    docker run --rm -v "$PWD":/src -w /src miyoocfw/toolchain-shared-musl:2.0.0-beta-2 sh build.sh

This writes `dist/coverflow.tar.gz`. `firmware/miyoocfw/scripts/make-sd.sh`
puts it on the boot partition, and `normalboot.custom.sh` unpacks it to
`/mnt/coverflow` on the next boot, adds `/mnt/autoexec.sh` (MiyooCFW runs that
instead of gmenu2x) and a Coverflow link in gmenu2x's applications. Delete
`/mnt/autoexec.sh` to boot into gmenu2x again. On its first boot it also
removes the demo ROMs the MiyooCFW release puts in `roms/` (only files with
the stock name and size).

On a PC (`sdl-config`, SDL_image and SDL_ttf 1.2 installed) it builds and runs
in a window for testing:

    gcc -O2 -o coverflow src/coverflow.c $(sdl-config --cflags --libs) -lSDL_image -lSDL_ttf
    python3 test/make_fixture.py /tmp/f1l    # fake gmenu2x links, ROMs and art (needs Pillow)
    F1L_ROMS=/tmp/f1l/roms F1L_GMENU2X=/tmp/f1l/gmenu2x ./coverflow

`F1L_SCREENSHOT=out.bmp` saves one frame and quits, `F1L_KEYS=rrL` presses
keys first, and `F1L_BENCH=300` prints the time per frame while scrolling.

## Speed

Everything is drawn into one 480x272 RGB565 buffer: a gradient background,
seven covers scaled nearest-neighbour with their reflections, and cached text.
Covers are loaded one per frame, nearest to the selection first, and only
about 20 stay in memory, so large libraries use little RAM.
