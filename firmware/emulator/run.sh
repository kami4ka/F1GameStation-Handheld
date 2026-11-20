#!/bin/sh
# Run the F1GameStation emulator: our kernel + DTB booting the MiyooCFW SD
# card image, in a 480x272 window (2x by default) with the keyboard as the
# 13 buttons, sound on the host and the debug UART in this terminal.
#
# usage: run.sh [options] [-- extra qemu args]
#   --image FILE    SD card image   (default $F1GS_DEPLOY/f1gamestation-sd.img)
#   --kernel FILE   zImage          (default $F1GS_DEPLOY/zImage)
#   --dtb FILE      device tree     (default $F1GS_DEPLOY/suniv-f1c100s-f1gamestation.dtb)
#   --share DIR     copy DIR onto a second SD card (/dev/mmcblk1 in the
#                   emulator); after exit, files the emulator wrote to its
#                   out/ folder are copied back to DIR/out/
#   --fresh         forget the emulated card's changes (start from --image)
#   --scale N       window size, 1-4 x 480x272 (default 2)
#   --battery MV    battery voltage the gauge reads (default 3900)
#   --headless      no window (use --vnc or the QMP socket for screenshots)
#   --mips N        CPU speed cap in million instructions/s (default 500,
#                   about the F1C200s's ARM926 at 720 MHz)
#   --fast          no speed cap: run as fast as the host allows
#
# The card image itself is never written: changes go to an overlay in
# $F1GS_EMU_DIR/state that survives restarts until --fresh or a newer image.
# Quit: close the window, or Ctrl-A then X in this terminal.
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
. "$HERE/emu-env.sh"
QEMU_BUILD=$F1GS_EMU_DIR/src/build
STATE=$F1GS_EMU_DIR/state

IMAGE= KERNEL= DTB= SHARE= FRESH= SCALE=2 BATTERY=3900 HEADLESS= FAST= MIPS=500
while [ $# -gt 0 ]; do
	case $1 in
	--image) IMAGE=$2; shift ;;
	--kernel) KERNEL=$2; shift ;;
	--dtb) DTB=$2; shift ;;
	--share) SHARE=$2; shift ;;
	--fresh) FRESH=1 ;;
	--scale) SCALE=$2; shift ;;
	--battery) BATTERY=$2; shift ;;
	--headless) HEADLESS=1 ;;
	--fast) FAST=1 ;;
	--mips) MIPS=$2; shift ;;
	--) shift; break ;;
	-h|--help) sed -n '2,27p' "$0"; exit 0 ;;
	*) echo "unknown option $1" >&2; exit 1 ;;
	esac
	shift
done

# the Mac's case-sensitive Docker work volume holds the build output
if [ -z "$IMAGE$KERNEL$DTB" ] && [ ! -d "$F1GS_DEPLOY" ] && [ -f "$F1GS_SRC_IMG" ] && command -v hdiutil >/dev/null; then
	hdiutil attach "$F1GS_SRC_IMG" >/dev/null
fi
IMAGE=${IMAGE:-$F1GS_DEPLOY/f1gamestation-sd.img}
KERNEL=${KERNEL:-$F1GS_DEPLOY/zImage}
DTB=${DTB:-$F1GS_DEPLOY/suniv-f1c100s-f1gamestation.dtb}
for f in "$QEMU_BUILD/qemu-system-arm" "$IMAGE" "$KERNEL" "$DTB"; do
	[ -f "$f" ] || { echo "missing $f (see firmware/emulator/README.md)" >&2; exit 1; }
done

# same kernel command line as the real card (sd/boot.cmd)
BOOTARGS=$(sed -n 's/^setenv bootargs //p' "$HERE/../miyoocfw/sd/boot.cmd")

# copy-on-write overlay, power-of-two sized as QEMU's SD card needs
mkdir -p "$STATE"
OVL=$STATE/sd.qcow2
if [ -n "$FRESH" ] || [ ! -f "$OVL" ] || [ "$IMAGE" -nt "$OVL" ] ||
   [ "$(cat "$STATE/sd.base" 2>/dev/null)" != "$IMAGE" ]; then
	[ -f "$OVL" ] && echo "starting from a clean copy of $IMAGE"
	rm -f "$OVL"
	"$QEMU_BUILD/qemu-img" create -q -f qcow2 -b "$IMAGE" -F raw "$OVL" 2G
	echo "$IMAGE" > "$STATE/sd.base"
fi

set -- -drive if=sd,index=0,file="$OVL",format=qcow2 "$@"
if [ -n "$SHARE" ]; then
	command -v mformat >/dev/null || { echo "--share needs mtools (brew install mtools)" >&2; exit 1; }
	SHIMG=$STATE/share.img
	rm -f "$SHIMG"
	dd if=/dev/zero of="$SHIMG" bs=1 count=0 seek=512M 2>/dev/null
	MTOOLS_SKIP_CHECK=1 mformat -i "$SHIMG" -F -v SHARE ::
	[ -z "$(ls -A "$SHARE")" ] || MTOOLS_SKIP_CHECK=1 mcopy -s -i "$SHIMG" "$SHARE"/* ::
	set -- -drive if=sd,index=1,file="$SHIMG",format=raw "$@"
fi

case $(uname -s) in
Darwin) AUDIO=coreaudio DISPLAY_OPT=cocoa ;;
*) AUDIO=${F1GS_AUDIO:-sdl} DISPLAY_OPT=${F1GS_DISPLAY:-sdl} ;;
esac
[ -z "$HEADLESS" ] || DISPLAY_OPT=none

# CPU pacing: the f1gs-pace plugin stops the CPU from running more than
# MIPS million instructions per second of real time. The ARM926 averages
# roughly 0.7 instructions per clock on real code, so 500 is close to the
# F1C200s at 720 MHz. Guest time stays real time (timers, sound, vblank).
if [ -z "$FAST" ]; then
	PLUGIN=
	for f in "$QEMU_BUILD"/contrib/plugins/libf1gs-pace.so "$QEMU_BUILD"/contrib/plugins/libf1gs-pace.dylib; do
		[ -f "$f" ] && PLUGIN=$f
	done
	[ -n "$PLUGIN" ] || { echo "pacing plugin missing: re-run build-qemu.sh (or use --fast)" >&2; exit 1; }
	set -- -plugin "$PLUGIN",ips="${MIPS}000000" "$@"
fi

echo "F1GameStation emulator: keys Arrows=D-pad X=A Z=B S=X A=Y Q=L W=R Enter=START RShift/Backspace=SELECT Esc/M=MENU"
[ -n "$FAST" ] && echo "CPU: no speed cap" || echo "CPU: capped at $MIPS MIPS"
echo "debug UART below (login: root); Ctrl-A X quits; QMP socket $STATE/qmp.sock"
rc=0
"$QEMU_BUILD/qemu-system-arm" -M f1gamestation,scale="$SCALE",battery-mv="$BATTERY",audiodev=snd \
	-audiodev "$AUDIO",id=snd -display "$DISPLAY_OPT" \
	-kernel "$KERNEL" -dtb "$DTB" -append "$BOOTARGS" \
	-serial mon:stdio -qmp unix:"$STATE/qmp.sock",server=on,wait=off \
	-name F1GameStation "$@" || rc=$?

if [ -n "$SHARE" ] && MTOOLS_SKIP_CHECK=1 mdir -i "$SHIMG" ::/out >/dev/null 2>&1; then
	mkdir -p "$SHARE/out"
	MTOOLS_SKIP_CHECK=1 mcopy -s -n -i "$SHIMG" ::/out/* "$SHARE/out/" && echo "copied the emulator's out/ to $SHARE/out/"
fi
exit $rc
