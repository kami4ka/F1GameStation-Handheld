# Firmware

The handheld runs [MiyooCFW](https://github.com/MiyooCFW) 2.0 (Linux 5.15 on the F1C100s/F1C200s)
with F1GameStation changes on top. Everything here is built in Docker; nothing needs installing on the
host except Docker itself.

| Folder | What |
| --- | --- |
| [`miyoocfw/kernel`](miyoocfw/kernel) | patches on MiyooCFW/kernel `add4deb1`: the `rgb480x272fb` panel driver (480×272, 180° rotation, 320×240 games scaled to the panel height), keypad layout 8 with the PA1–PA3 workaround, sound variant 4, the device tree |
| [`miyoocfw/gmenu2x`](miyoocfw/gmenu2x) | gmenu2x patched to fill the 480×272 panel |
| [`miyoocfw/sd`](miyoocfw/sd) | U-Boot boot script and the MiyooCFW hook scripts copied to the card |
| [`miyoocfw/scripts`](miyoocfw/scripts) | build, SD image, FEL boot and UART tools |
| [`miyoocfw/test`](miyoocfw/test) | a small initramfs with a hardware test program, booted over USB (FEL) |
| [`launcher`](launcher) | the cover-flow game launcher ([README](launcher/README.md)) |
| [`emulator`](emulator) | a QEMU model of the handheld ([README](emulator/README.md)) |

There are no prebuilt images: build the card from these sources as described below, then flash it
as in [docs/BUILD.md](../docs/BUILD.md#3-flash-the-microsd-card).

## Building

### 1. Kernel, menu and launcher

```sh
firmware/miyoocfw/scripts/build-docker.sh
```

This builds the `f1gs-build` Docker image (Debian, ARM cross compiler), clones the MiyooCFW kernel at
the pinned commit, applies `kernel/patches/*.patch` and builds `zImage`, the device tree and the
modules. It then builds gmenu2x and the launcher in MiyooCFW's own toolchain image
(`miyoocfw/toolchain-shared-musl:2.0.0-beta-2`; set `F1GS_LIBC=uclibc` for the uClibc release).

Linux kernel sources need a case-sensitive file system. On macOS the script creates and mounts a
12 GB case-sensitive sparse image (`~/Projects/Hardware/miyoocfw/f1gs-src.sparseimage`, pass another
path as the first argument) at `/Volumes/f1gs-src`. On Linux, run the two steps by hand with any
directory as the work volume:

```sh
docker build -t f1gs-build firmware/miyoocfw/docker
docker run --rm -v $PWD/work:/src -v $PWD/firmware/miyoocfw:/f1gs:ro f1gs-build /f1gs/scripts/build.sh
```

Outputs land in `<work>/deploy`: `zImage`, `suniv-f1c100s-f1gamestation.dtb`, `gmenu2x-f1gs`,
`coverflow.tar.gz`, and the FEL test initramfs.

### 2. U-Boot

The card boots mainline U-Boot (tested with v2025.10) built for the Lichee Pi Nano, which has the
same SoC and DRAM:

```sh
git clone --depth 1 -b v2025.10 https://source.denx.de/u-boot/u-boot.git
cd u-boot
make CROSS_COMPILE=arm-linux-gnueabi- licheepi_nano_defconfig
make CROSS_COMPILE=arm-linux-gnueabi- -j8
# -> u-boot-sunxi-with-spl.bin
```

### 3. SD card image

Download the MiyooCFW **2.0.0 beta 2** release image (musl) from
[MiyooCFW/MiyooCFW releases](https://github.com/MiyooCFW/MiyooCFW/releases) and unpack the `.img`.
Then:

```sh
docker run --rm --privileged -v /Volumes/f1gs-src:/src -v "$PWD/firmware/miyoocfw":/f1gs:ro \
  -v /path/to/release:/release:ro f1gs-build /f1gs/scripts/make-sd.sh \
  /release/miyoo-cfw-2.0.0-67298a0_musl-BETAv2.img /src/u-boot-sunxi-with-spl.bin
```

`make-sd.sh` copies the release image to `deploy/f1gamestation-sd.img`, grows the FAT `BOOT`
partition to 256 MB (so games can be dropped in from any computer), puts U-Boot at the 8 KiB offset,
and installs the kernel, device tree, `boot.scr`, the menu, the launcher and the hook scripts. The
release image itself is not modified. `--privileged` is needed for the loop mounts.

### Updating a card

After a kernel rebuild only the FAT partition changes: copy `zImage` (and the `.dtb` if it changed)
to the card's `BOOT` volume.

## Booting over USB (FEL)

Useful for bring-up, nothing is written to the card or the flash. Hold FEL, press Reset, then:

```sh
firmware/miyoocfw/scripts/fel-boot.sh u-boot-sunxi-with-spl.bin /Volumes/f1gs-src/deploy
```

This loads U-Boot, the kernel, the test initramfs and the device tree into RAM and boots them.
`uart-log.py` records the debug UART (UART0 on the TX/RX pads, 115200 8N1).
Needs [`sunxi-fel`](https://github.com/linux-sunxi/sunxi-tools).

## Board-specific kernel parameters

From [`sd/boot.cmd`](miyoocfw/sd/boot.cmd):

| Parameter | Why |
| --- | --- |
| `miyoo_kbd.miyoo_ver=8` | F1GameStation button map, charge-then-sense read of PA1–PA3 |
| `miyoo.miyoo_snd=4` | amplifier enable on PA0, no headphone detect |
| `pwm_suniv.motor_ver=0` | no rumble motor (the default drives PE12, which is START here) |
| `miyoo_video.driver=none` | the panel driver is built in |

## License

GPL-2.0, see [LICENSE](LICENSE). The kernel and QEMU patches are derived works of GPL-2.0 projects.
The launcher bundles the DejaVu fonts under their own licence.
