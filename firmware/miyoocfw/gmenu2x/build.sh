#!/bin/sh
# Build gmenu2x for the F1GameStation's 480x272 panel (patches in this folder).
# Runs in the MiyooCFW toolchain container (miyoocfw/toolchain-shared-<libc>),
# started by scripts/build-docker.sh: /src = work volume, /f1gs = firmware/miyoocfw.
# Writes /src/deploy/gmenu2x-f1gs; make-sd.sh puts it on the card's boot
# partition and normalboot.custom.sh installs it over the release's menu.
set -e
REPO=https://github.com/MiyooCFW/gmenu2x
BASE=b210e7e5361934403e32a230216303bdaa4ffe0f   # the 2.0.0-beta-2 release menu
SRC=/src/gmenu2x

if [ ! -d $SRC/.git ] || [ "$(cat $SRC/.f1gs-patches 2>/dev/null)" != "$(cat /f1gs/gmenu2x/*.patch | md5sum)" ]; then
	rm -rf $SRC
	git clone -q $REPO $SRC
	git -C $SRC checkout -q $BASE
	git -C $SRC -c user.name=f1gs -c user.email=f1gs@localhost am -q /f1gs/gmenu2x/*.patch
	cat /f1gs/gmenu2x/*.patch | md5sum > $SRC/.f1gs-patches
fi
cd $SRC
make -s -f Makefile.miyoo -j"$(nproc)" COMMIT_HASH=$(echo $BASE | cut -c1-7) \
	"CXX=/opt/miyoo/usr/bin/arm-linux-g++ -DF1GS_PANEL" >/src/gmenu2x-build.log 2>&1 ||
	{ tail -30 /src/gmenu2x-build.log; exit 1; }
mkdir -p /src/deploy
cp dist/miyoo/gmenu2x /src/deploy/gmenu2x-f1gs
ls -la /src/deploy/gmenu2x-f1gs
