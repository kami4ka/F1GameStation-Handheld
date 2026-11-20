#!/bin/sh
# Build the F1GameStation MiyooCFW kernel, DTB and FEL test initramfs.
# Runs in the f1gs-build container: /src = case-sensitive work volume
# (kernel checkout, build output), /f1gs = this firmware/miyoocfw folder.
# Output goes to /src/deploy.
set -e
KERNEL_REPO=https://github.com/MiyooCFW/kernel
KERNEL_BASE=add4deb177dfd8d2324650703f0014e9c862baa8

if [ ! -d /src/kernel/.git ]; then
	git clone -q $KERNEL_REPO /src/kernel
	git -C /src/kernel checkout -q -b f1gamestation $KERNEL_BASE
fi
# apply the patches the tree doesn't have yet (one commit per patch, in order)
n=$(git -C /src/kernel rev-list --count $KERNEL_BASE..HEAD)
for p in $(ls /f1gs/kernel/patches/*.patch | tail -n +$((n + 1))); do
	git -C /src/kernel -c user.name=f1gs -c user.email=f1gs@localhost am -q "$p"
done
cd /src/kernel
make -s O=/src/out miyoo_defconfig
scripts/kconfig/merge_config.sh -m -O /src/out /src/out/.config /f1gs/kernel/f1gamestation.config >/dev/null
make -s O=/src/out olddefconfig
make -s O=/src/out -j"$(nproc)" zImage modules dtbs

rm -rf /src/rootfs && mkdir -p /src/rootfs/bin /src/rootfs/proc /src/rootfs/sys /src/rootfs/dev /src/deploy
make -s O=/src/out INSTALL_MOD_PATH=/src/rootfs modules_install
cp /opt/busybox-armel/bin/busybox /src/rootfs/bin/
for a in $(/opt/busybox-armel/bin/busybox --list); do
	[ "$a" = busybox ] || ln -sf busybox /src/rootfs/bin/$a
done
ln -sfn bin /src/rootfs/sbin
arm-linux-gnueabi-gcc -static -O2 -Wall -o /src/rootfs/bin/f1gs-test /f1gs/test/f1gs-test.c -lm
install -m 755 /f1gs/test/init /src/rootfs/init
(cd /src/rootfs && find . | cpio -o -H newc --quiet | gzip -9) > /src/deploy/initramfs.cpio.gz
mkimage -A arm -O linux -T ramdisk -C none -d /src/deploy/initramfs.cpio.gz /src/deploy/initramfs.uimg >/dev/null
cp /src/out/arch/arm/boot/zImage /src/out/arch/arm/boot/dts/suniv-f1c100s-f1gamestation.dtb /src/deploy/
mkimage -A arm -O linux -T script -C none -d /f1gs/test/boot-fel.cmd /src/deploy/boot-fel.scr >/dev/null
ls -la /src/deploy
