#!/bin/sh
# Build qemu-system-arm with the F1GameStation board and the CPU pacing
# plugin (qemu/*.patch on top of QEMU 9.2.0). Works on macOS (Cocoa window, CoreAudio) and Linux.
#   macOS deps: xcode-select --install; brew install ninja pkgconf glib pixman mtools
#   Debian/Ubuntu: apt install ninja-build pkg-config libglib2.0-dev libpixman-1-dev libsdl2-dev mtools
# usage: build-qemu.sh            (output: $F1GS_EMU_DIR/src/build/qemu-system-arm)
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
. "$HERE/emu-env.sh"
QEMU_TAG=v9.2.0

if [ ! -d "$F1GS_EMU_DIR/src/.git" ]; then
	mkdir -p "$F1GS_EMU_DIR"
	git clone -q --depth 1 --branch $QEMU_TAG https://gitlab.com/qemu-project/qemu.git "$F1GS_EMU_DIR/src"
fi
cd "$F1GS_EMU_DIR/src"
# (re)apply the board patch only when it changed, to keep rebuilds incremental
STAMP=build/.f1gs-patch
mkdir -p build
if ! cat "$HERE"/qemu/*.patch | cmp -s - $STAMP; then
	git checkout -q -- . && git clean -fdq hw contrib
	for p in "$HERE"/qemu/*.patch; do git apply "$p"; done
	cat "$HERE"/qemu/*.patch > $STAMP
fi
cd build
[ -f build.ninja ] || ../configure --target-list=arm-softmmu --disable-docs --disable-werror
make -j"$(getconf _NPROCESSORS_ONLN)" qemu-system-arm qemu-img contrib-plugins
echo "built $F1GS_EMU_DIR/src/build/qemu-system-arm"
