#!/bin/sh
# Cross-compile coverflow for the F1GameStation in the MiyooCFW toolchain image.
#   docker run --rm -v "$PWD":/src -w /src miyoocfw/toolchain-shared-musl:2.0.0-beta-2 sh build.sh
# Writes dist/coverflow/ and dist/coverflow.tar.gz. make-sd.sh puts the tarball
# on the boot partition and normalboot.custom.sh unpacks it to /mnt/coverflow.
set -e
SYSROOT=$(ls -d /opt/miyoo/arm-miyoo-linux-*/sysroot | head -1)
CC=/opt/miyoo/usr/bin/arm-linux-gcc
mkdir -p dist/coverflow
$CC -O2 -march=armv5te -mtune=arm926ej-s -Wall -Wno-format-truncation -Wno-restrict \
	-DF1GS_PANEL -I$SYSROOT/usr/include -D_GNU_SOURCE=1 -D_REENTRANT \
	-o dist/coverflow/coverflow src/coverflow.c \
	-L$SYSROOT/usr/lib -lSDL_image -lSDL_ttf -lSDL -lfreetype -lpthread -lm
/opt/miyoo/usr/bin/arm-linux-strip dist/coverflow/coverflow
cp -r assets/* dist/coverflow/
cp sd/autoexec.sh sd/coverflow.gmenu2x-link dist/coverflow/
chmod 755 dist/coverflow dist/coverflow/fonts dist/coverflow/coverflow
chmod 644 dist/coverflow/fonts/* dist/coverflow/autoexec.sh dist/coverflow/coverflow.gmenu2x-link
tar -czf dist/coverflow.tar.gz -C dist coverflow
ls -la dist/coverflow dist/coverflow.tar.gz
