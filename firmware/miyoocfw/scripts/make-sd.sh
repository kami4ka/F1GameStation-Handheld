#!/bin/sh
# Turn a MiyooCFW release SD image into an F1GameStation image.
# Runs in the f1gs-build container with --privileged (loop mounts):
#   /src  = work volume with /src/out and /src/deploy from build.sh
#   /f1gs = this firmware/miyoocfw folder
# usage: make-sd.sh <miyoo-cfw release .img> <u-boot-sunxi-with-spl.bin (licheepi_nano)>
# Writes /src/deploy/f1gamestation-sd.img. Only the image file is changed.
set -e
SRC=${1:?MiyooCFW release image}
UBOOT=${2:?u-boot-sunxi-with-spl.bin}
IMG=/src/deploy/f1gamestation-sd.img

# The release's BOOT partition (8 MB) is too small to hold games on their
# way to the card, so it is made BOOT_MB big (FAT32, visible on any
# computer) and partitions 2-4 move up by the difference. MiyooCFW's first
# boot only looks at partition 4's start when it grows it, so moving is safe.
BOOT_MB=${F1GS_BOOT_MB:-256}
# partition table as "start size rest-of-line", without device names
sfdisk -d "$SRC" | sed -n 's|^.* : start= *\([0-9]*\), *size= *\([0-9]*\),\(.*\)|\1 \2 \3|p' > /tmp/src.parts
part() { sed -n "${1}p" /tmp/src.parts | cut -d' ' -f$2; }
P1S=$(part 1 1); P1N=$(part 1 2); P2S=$(part 2 1)
NEW1=$((BOOT_MB * 2048))
D=$((P1S + NEW1 - P2S)) # sectors partitions 2-4 move by
[ $D -ge 0 ] || { echo "BOOT_MB is smaller than the release's BOOT partition" >&2; exit 1; }
END=$(($(part 4 1) + $(part 4 2)))
rm -f $IMG
truncate -s $(((END + D) * 512)) $IMG
# MBR gap with U-Boot, then partitions 2-4 in one piece at their new place
dd if="$SRC" of=$IMG bs=512 count=$P1S conv=notrunc status=none
dd if="$SRC" of=$IMG bs=1M iflag=skip_bytes,count_bytes oflag=seek_bytes conv=notrunc status=none \
	skip=$((P2S * 512)) seek=$(((P2S + D) * 512)) count=$(((END - P2S) * 512))
awk -v d=$D -v n1=$NEW1 'BEGIN { print "label: dos" }
	{ s = $1; n = $2; $1 = $2 = ""; sub(/^ +/, "")
	  if (NR == 1) n = n1; else s += d
	  print "start=" s ", size=" n ", " $0 }' /tmp/src.parts | sfdisk -q --no-reread $IMG
# a new, bigger FAT32 BOOT with the release's boot files
mkfs.vfat -F 32 -s 1 -n BOOT --offset=$P1S $IMG $((NEW1 / 2)) >/dev/null
mkdir -p /mnt/oldboot /mnt/boot
mount -o loop,ro,offset=$((P1S * 512)),sizelimit=$((P1N * 512)) "$SRC" /mnt/oldboot
mount -o loop,offset=$((P1S * 512)),sizelimit=$((NEW1 * 512)) $IMG /mnt/boot
cp -r /mnt/oldboot/. /mnt/boot/
umount /mnt/oldboot /mnt/boot
# mainline licheepi_nano U-Boot replaces MiyooCFW's at the 8 KiB eGON offset;
# it runs boot.scr from the FAT partition through distro boot
dd if="$UBOOT" of=$IMG bs=1024 seek=8 conv=notrunc status=none

part_offset() {
	# start sector of partition $1 from the MBR, in bytes
	od -A n -t u4 -j $((446 + 16 * ($1 - 1) + 8)) -N 4 $IMG | awk '{print $1 * 512}'
}

mkdir -p /mnt/boot /mnt/root
mount -o loop,offset=$(part_offset 1) $IMG /mnt/boot
cp /src/out/arch/arm/boot/zImage /mnt/boot/zImage
cp /src/out/arch/arm/boot/dts/suniv-f1c100s-f1gamestation.dtb /mnt/boot/
mkimage -A arm -O linux -T script -C none -d /f1gs/sd/boot.cmd /mnt/boot/boot.scr >/dev/null
for f in modules.custom.sh normalboot.custom.sh firstboot.custom.sh uart-getty.sh; do
	cp /f1gs/sd/$f /mnt/boot/$f
done
# gmenu2x for the 480x272 panel; normalboot.custom.sh installs it
[ -f /src/deploy/gmenu2x-f1gs ] && cp /src/deploy/gmenu2x-f1gs /mnt/boot/
# coverflow launcher (firmware/launcher); normalboot.custom.sh unpacks it to /mnt
[ -f /src/deploy/coverflow.tar.gz ] && cp /src/deploy/coverflow.tar.gz /mnt/boot/
# games inbox: normalboot.custom.sh moves add-games/<SYSTEM>/* into roms/
mkdir -p /mnt/boot/add-games
for s in NES SNES GB GBC GBA MD; do mkdir -p /mnt/boot/add-games/$s; done
cp /f1gs/sd/add-games-README.txt /mnt/boot/add-games/README.txt
umount /mnt/boot

mount -o loop,offset=$(part_offset 2) $IMG /mnt/root
make -s -C /src/kernel O=/src/out INSTALL_MOD_PATH=/mnt/root modules_install
ls /mnt/root/lib/modules
umount /mnt/root
ls -la $IMG
