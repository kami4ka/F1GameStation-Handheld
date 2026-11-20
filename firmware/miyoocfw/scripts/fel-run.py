#!/usr/bin/env python3
"""Load the MiyooCFW test kernel over FEL, start it from the U-Boot prompt
on the debug UART and log the console.

The licheepi_nano U-Boot does not run the FEL boot script by itself, so this
stops autoboot and types `source <scriptaddr>`. Nothing is written to the SD
card or SPI flash.

usage: fel-run.py <u-boot-sunxi-with-spl.bin> [seconds] [logfile]"""
import glob, os, select, subprocess, sys, termios, time

here = os.path.dirname(os.path.abspath(__file__))
uboot = sys.argv[1]
secs = float(sys.argv[2]) if len(sys.argv) > 2 else 60
log = open(sys.argv[3] if len(sys.argv) > 3 else 'uart.log', 'wb')

fd = os.open(glob.glob('/dev/cu.usbmodemflip_*')[0], os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
a = termios.tcgetattr(fd)
a[0] = a[1] = a[3] = 0
a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
a[4] = a[5] = termios.B115200
termios.tcsetattr(fd, termios.TCSANOW, a)

buf = b''
def pump(t, until=None):
    global buf
    end = time.time() + t
    while time.time() < end:
        r, _, _ = select.select([fd], [], [], 0.05)
        if r:
            b = os.read(fd, 4096)
            buf += b
            log.write(b); log.flush()
            sys.stdout.write(b.decode(errors='replace')); sys.stdout.flush()
            if until and until in buf:
                return True
    return False

fel = subprocess.Popen([os.path.join(here, 'fel-boot.sh'), uboot],
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
while fel.poll() is None:
    pump(0.2)
if fel.returncode:
    sys.exit('fel-boot.sh failed: ' + fel.stderr.read().decode(errors='replace'))
if not pump(20, b'Hit any key'):
    sys.exit('no U-Boot prompt on the UART')
os.write(fd, b'\r')
pump(2, b'=> ')
os.write(fd, b'source 0x81d40000\r')
pump(secs)
