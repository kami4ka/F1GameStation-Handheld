#!/usr/bin/env python3
"""Update files on the F1GameStation SD card's FAT (BOOT) partition over the
debug UART, with the card left in the board.

If MiyooCFW is running, it logs in on the UART console (sd/uart-getty.sh)
and reboots; it then stops U-Boot's autoboot, sends each file with ymodem
(`loady`, needs lrzsz's `sz`), writes it with `fatwrite` and boots.
115200 baud moves about 11 KB/s, so a 3 MB zImage takes ~4.5 minutes.

usage: sd-update.py <file>[=<name on card>] ...
       e.g. sd-update.py /Volumes/f1gs-src/deploy/zImage sd/boot.scr"""
import glob, os, re, select, subprocess, sys, termios, time

LOAD_ADDR = 0x81000000

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
            sys.stdout.write(b.decode(errors='replace')); sys.stdout.flush()
            if until is not None and re.search(until, buf[-4096:]):
                return True
    return False

def send(s):
    global buf
    buf = b''
    os.write(fd, s.encode() + b'\r')

files = []
for arg in sys.argv[1:]:
    path, _, name = arg.partition('=')
    files.append((path, name or os.path.basename(path)))
if not files:
    sys.exit(__doc__)

# get to the U-Boot prompt: reboot Linux if it is running
send('')
if pump(3, rb'login: ?$'):
    send('root')
    pump(5, rb'(assword: ?$|# ?$)')
    if re.search(rb'assword', buf):
        send('')
        pump(5, rb'# ?$')
if re.search(rb'# ?$', buf):
    send('sync; reboot')
elif not re.search(rb'=> ?$', buf):
    print('\n** reset the board now (no FEL) **')
if not re.search(rb'=> ?$', buf):
    if not pump(900, rb"Hit any key"):
        sys.exit('no U-Boot prompt seen')
    os.write(fd, b'\r')
    pump(3, rb'=> ?$')

for path, name in files:
    size = os.path.getsize(path)
    send('loady 0x%x' % LOAD_ADDR)
    pump(5, rb'download to')
    t0 = time.time()
    os.set_blocking(fd, True)
    r = subprocess.run(['sz', '--ymodem', '-k', path], stdin=fd, stdout=fd, stderr=subprocess.DEVNULL)
    os.set_blocking(fd, False)
    if r.returncode:
        sys.exit('ymodem transfer of %s failed' % path)
    pump(5, rb'=> ?$')
    print('\n-- %s: %d bytes in %.0f s' % (path, size, time.time() - t0))
    send('fatwrite mmc 0:1 0x%x %s 0x%x' % (LOAD_ADDR, name, size))
    pump(30, rb'=> ?$')
    if not re.search(rb'%d bytes written' % size, buf):
        sys.exit('fatwrite of %s failed' % name)

send('boot')
pump(10)
