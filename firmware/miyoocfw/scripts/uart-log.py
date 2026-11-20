#!/usr/bin/env python3
"""Log the debug UART (Flipper Zero USB-UART bridge) to stdout and a file.
usage: uart-log.py [seconds] [logfile] [device]"""
import glob, os, select, sys, termios, time

secs = float(sys.argv[1]) if len(sys.argv) > 1 else 60
log = open(sys.argv[2] if len(sys.argv) > 2 else 'uart.log', 'ab')
dev = sys.argv[3] if len(sys.argv) > 3 else (glob.glob('/dev/cu.usbmodemflip_*') or ['/dev/null'])[0]
fd = os.open(dev, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
a = termios.tcgetattr(fd)
a[0] = a[1] = a[3] = 0
a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
a[4] = a[5] = termios.B115200
termios.tcsetattr(fd, termios.TCSANOW, a)
end = time.time() + secs
while time.time() < end:
    r, _, _ = select.select([fd], [], [], 0.1)
    if r:
        b = os.read(fd, 4096)
        log.write(b); log.flush()
        sys.stdout.write(b.decode(errors='replace')); sys.stdout.flush()
