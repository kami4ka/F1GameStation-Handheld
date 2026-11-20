#!/bin/sh
# Boot the F1GameStation MiyooCFW test kernel from RAM over FEL.
# Nothing is written to the SD card or SPI flash.
# usage: fel-boot.sh <u-boot-sunxi-with-spl.bin (licheepi_nano)> [deploy dir]
set -e
UBOOT=${1:?u-boot-sunxi-with-spl.bin for licheepi_nano}
D=${2:-/Volumes/f1gs-src/deploy}
sunxi-fel ver
sunxi-fel -p uboot "$UBOOT" \
	write 0x81000000 "$D/zImage" \
	write 0x81800000 "$D/initramfs.uimg" \
	write 0x81d50000 "$D/suniv-f1c100s-f1gamestation.dtb" \
	write 0x81d40000 "$D/boot-fel.scr"
