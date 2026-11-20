# F1GameStation SD boot script for the mainline licheepi_nano U-Boot.
# Replaces MiyooCFW's boot.scr, whose U-Boot detects Miyoo panels and
# writes uEnv.txt; here the board settings are fixed. The panel driver is
# built in, so miyoo_video.driver=none keeps MiyooCFW from modprobing a
# panel module.
setenv bootargs console=tty0 console=ttyS0,115200 panic=5 rootwait root=/dev/mmcblk0p2 ro miyoo_kbd.miyoo_ver=8 miyoo_kbd.miyoo_layout=1 miyoo.miyoo_snd=4 pwm_suniv.motor_ver=0 miyoo_video.driver=none
load mmc 0:1 ${kernel_addr_r} zImage
load mmc 0:1 ${fdt_addr_r} suniv-f1c100s-f1gamestation.dtb
bootz ${kernel_addr_r} - ${fdt_addr_r}
