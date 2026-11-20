#!/bin/sh
# Host wrapper: create/mount the case-sensitive work image (the Linux tree
# does not check out cleanly on case-insensitive APFS), build the Docker
# image and run build.sh in it.
# Also builds gmenu2x for the 480x272 panel and the coverflow launcher in the
# MiyooCFW toolchain image;
# F1GS_LIBC=musl (default) or uclibc must match the card's release image.
# usage: build-docker.sh [work image path]
set -e
HERE=$(cd "$(dirname "$0")/.." && pwd)
IMG=${1:-$HOME/Projects/Hardware/miyoocfw/f1gs-src.sparseimage}
VOL=/Volumes/f1gs-src
if [ ! -d $VOL ]; then
	[ -f "$IMG" ] || hdiutil create -size 12g -type SPARSE -fs "Case-sensitive APFS" -volname f1gs-src "$IMG"
	hdiutil attach "$IMG" >/dev/null
fi
docker build -q -t f1gs-build "$HERE/docker" >/dev/null
docker run --rm -v $VOL:/src -v "$HERE":/f1gs:ro f1gs-build /f1gs/scripts/build.sh
docker run --rm -v $VOL:/src -v "$HERE":/f1gs:ro \
	miyoocfw/toolchain-shared-${F1GS_LIBC:-musl}:2.0.0-beta-2 sh /f1gs/gmenu2x/build.sh
# the coverflow launcher (firmware/launcher), same toolchain
docker run --rm -v "$HERE/../launcher":/l -w /l \
	miyoocfw/toolchain-shared-${F1GS_LIBC:-musl}:2.0.0-beta-2 sh build.sh
cp "$HERE/../launcher/dist/coverflow.tar.gz" $VOL/deploy/
