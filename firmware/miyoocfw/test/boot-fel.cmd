# U-Boot script for a RAM-only boot over FEL; addresses are the licheepi_nano
# U-Boot defaults (kernel_addr_r, ramdisk_addr_r, fdt_addr_r).
setenv bootargs console=ttyS0,115200 earlycon=uart,mmio32,0x01c25000 rdinit=/init panic=3 miyoo_kbd.miyoo_ver=8 miyoo_video.driver=rgb480x272fb miyoo.miyoo_snd=4 pwm_suniv.motor_ver=0
bootz 0x81000000 0x81800000 0x81d50000
