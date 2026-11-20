# F1GameStation emulator

A QEMU board model of the handheld, so the firmware and apps can be developed
without the hardware. It runs the same files as the real SD card: our MiyooCFW
kernel and device tree (`firmware/miyoocfw`), and the MiyooCFW root filesystem
with gmenu2x and the emulators.

```
build-qemu.sh   build qemu-system-arm with the board and the CPU pacing plugin
                (QEMU 9.2.0 + qemu/*.patch)
run.sh          boot the card image in a window, debug UART in the terminal
emu-ctl.py      screenshots and button presses over QMP, for scripted tests
emu-env.sh      shared paths (all overridable from the environment)
```

## What is emulated

| Hardware | In the emulator |
| --- | --- |
| F1C200s ARM926EJ-S, 64 MiB DRAM | same CPU core (QEMU `arm926`), 64 MiB |
| Interrupt controller, timers, watchdog | yes (reboot works through the watchdog) |
| CCU clocks | registers only; PLLs always report locked |
| 480x272 RGB panel (DEBE layer 0 + TCON0) | window, 2x by default, with vblank IRQs; RGB565, ARGB1555, RGB888 and ARGB8888 layers |
| Menu at 480x272, games at 320x240 | as on the handheld: gmenu2x fills the panel, games are centred with a black border |
| Panel mounted upside down | the kernel's 180 degree rotation is undone, so the window shows what the handheld shows |
| Backlight (PWM1 on PE6) | dims and blanks the window |
| 13 buttons (PIO) | host keyboard, see below; PA1-PA3 read cleanly (no charge-then-sense quirk) |
| Audio codec + DMA | played on the host (CoreAudio on the Mac), with the volume setting |
| Battery gauge (LRADC0) | fixed voltage, `--battery` (default 3.9 V) |
| SD card (MMC0) | the card image, through a copy-on-write overlay |
| MMC1 | optional second card for moving files in and out (`--share`) |
| UART0 | this terminal (login `root`) |
| SPI NOR, USB OTG, video engine, TV-out | not emulated; their device-tree nodes are disabled at boot |

## CPU speed

QEMU translates ARM code to host code and can't model clock cycles, so speed
is set as an instruction rate. The `f1gs-pace` plugin caps the CPU at 500
million instructions per second of real time, our estimate for the ARM926 at
720 MHz (it averages about 0.7 instructions per clock on real code). Guest
time stays real time, so timers, vblank and sound run normally; only the CPU
is held back, and idle time isn't saved up for bursts.

- `run.sh --mips 400` sets another cap, `run.sh --fast` removes it.
- The cap doesn't follow gmenu2x's CPU clock setting (PLL_CPU).
- It's a ceiling: a slow host can't reach it. Kernel BogoMIPS
  (`grep Bogo /proc/cpuinfo`) shows the rate the guest measured at boot.
- To calibrate against the board, time the same thing on both, e.g.
  `time sh -c 'i=0; while [ $i -lt 200000 ]; do i=$((i+1)); done'`
  (about 10.5 s in the emulator at 500), and scale `--mips` by the ratio.

Timing is still approximate (no cache or memory stalls), so check
performance-sensitive work on the board.

## Keys

| Button | Key |
| --- | --- |
| D-pad | arrow keys |
| A / B / X / Y | X / Z / S / A |
| L / R | Q / W |
| START | Enter |
| SELECT | Right Shift or Backspace |
| MENU | Esc or M |

MENU + SELECT force-quits the running app, as on the handheld.

## Setup (Mac)

```
xcode-select --install                     # once, if not done already
brew install ninja pkgconf glib pixman mtools
firmware/emulator/build-qemu.sh            # about 5 minutes the first time
```

QEMU is cloned and built in `~/Projects/Hardware/miyoocfw/qemu` (set
`F1GS_EMU_DIR` to move it). Re-run `build-qemu.sh` after the patch changes;
it only rebuilds what changed.

The emulator boots the outputs of the normal firmware build:

```
firmware/miyoocfw/scripts/build-docker.sh  # zImage, DTB and gmenu2x-f1gs in /Volumes/f1gs-src/deploy
# then the card image (/Volumes/f1gs-src/deploy/f1gamestation-sd.img):
docker run --rm --privileged -v /Volumes/f1gs-src:/src -v "$PWD/firmware/miyoocfw":/f1gs:ro \
  -v ~/Projects/Hardware/miyoocfw/release:/release:ro f1gs-build /f1gs/scripts/make-sd.sh \
  "/release/build image (musl)/miyoo-cfw-2.0.0-67298a0_musl-BETAv2.img" /src/u-boot-sunxi-with-spl.bin
```

`gmenu2x-f1gs` is the menu built for the 480x272 panel
(`firmware/miyoocfw/gmenu2x`). It has to match the release image's C library:
`build-docker.sh` builds it for musl, `F1GS_LIBC=uclibc build-docker.sh` for
the uClibc image. The card installs it over the release's 320x240 menu at
boot and keeps the old one as `gmenu2x.320x240`.

The U-Boot file only matters for real cards: the emulator boots the kernel
directly. After a kernel rebuild the emulator needs only `zImage` and the DTB,
not a new card image.

`run.sh` attaches the work volume itself if it isn't mounted.

## Running

```
firmware/emulator/run.sh                   # window + UART console here
firmware/emulator/run.sh --fresh           # throw away the emulated card's changes
firmware/emulator/run.sh --share ~/f1gs-share
```

The first boot shows MiyooCFW's setup screens, like a new card: RIGHT then
START on the License screen, then let the partition resize run. Changes to the
emulated card persist between runs in `$F1GS_EMU_DIR/state`, and the card
image itself is never modified. A newer image (or `--fresh`) starts over.

Quit by closing the window or with Ctrl-A then X in the terminal.

## Development loops

**Kernel and drivers.** Edit the kernel (or a patch in
`firmware/miyoocfw/kernel/patches`), run `build-docker.sh`, then `run.sh`. The
new `zImage` and DTB boot directly, with no card writes and no UART transfers.
Kernel messages and a root shell are in the terminal.

**Apps and emulators.** Build them with the MiyooCFW toolchain (the
`buildroot` checkout next to the kernel), put the binaries in a folder and
start with `--share` that folder. In the emulator's shell:

```
mkdir -p /mnt/host && mount /dev/mmcblk1 /mnt/host
cp /mnt/host/myapp /mnt/apps/...           # or run it straight from /mnt/host
mkdir -p /mnt/host/out && cp log.txt /mnt/host/out/
umount /mnt/host
```

Anything written to `out/` on that card is copied back to `<folder>/out/`
when the emulator exits. The share card is rebuilt from the folder at every
start, so the folder on the Mac is the master copy.

**Scripted checks.** While the emulator runs:

```
firmware/emulator/emu-ctl.py shot:menu.png key:right key:ret sleep:2 shot:after.png
firmware/emulator/emu-ctl.py "hmp:xp /4wx 0x01c21000"    # read SoC registers
```

`run.sh --headless` runs without a window, for automated tests.

## How it works

`qemu/0001-*.patch` adds `hw/arm/f1gamestation.c`: the suniv interrupt controller, CCU, PIO with the
button matrix, watchdog, LRADC, the DEBE/TCON display, PWM backlight and the
DMA + codec audio path. It reuses QEMU's Allwinner sun4i timer and SD host
models and its 8250 UART. Boot is direct (`-kernel`/`-dtb` with the command
line from `firmware/miyoocfw/sd/boot.cmd`), skipping the boot ROM and U-Boot.
At load time the board disables the SPI flash, USB and video engine nodes in
the DTB and, with `--share`, enables MMC1.

`qemu/0002-*.patch` adds the pacing plugin, `contrib/plugins/f1gs-pace.c`.

Board options (on `-M f1gamestation,...`): `scale=1..4`, `rotate=on|off`
(off shows the raw scanout, upside down) and `battery-mv=N`.
