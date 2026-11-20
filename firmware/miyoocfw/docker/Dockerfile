# Build environment for the F1GameStation MiyooCFW kernel and FEL test initramfs.
FROM debian:bookworm
RUN dpkg --add-architecture armel && apt-get update && apt-get install -y --no-install-recommends \
        gcc libc6-dev gcc-arm-linux-gnueabi libc6-dev-armel-cross make bc bison flex libssl-dev libelf-dev cpio kmod \
        u-boot-tools device-tree-compiler git ca-certificates python3 xz-utils file fdisk dosfstools \
    && apt-get download busybox-static:armel && dpkg -x busybox-static_*_armel.deb /opt/busybox-armel \
    && rm -f busybox-static_*_armel.deb && rm -rf /var/lib/apt/lists/*
ENV ARCH=arm CROSS_COMPILE=arm-linux-gnueabi-
WORKDIR /src
