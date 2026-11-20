#!/usr/bin/env python3
"""Copy a file to the running F1GameStation (MiyooCFW, root shell on the
debug UART) as base64 text, then check its md5. Good for small files such
as ROMs: about 8 KB/s of payload at 115200 baud.

usage: uart-put.py <local file> <path on the board>"""
import base64, glob, hashlib, os, re, select, sys, termios, time

src, dst = sys.argv[1], sys.argv[2]
data = open(src, 'rb').read()

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
        r, _, _ = select.select([fd], [], [], 0.02)
        if r:
            try:
                buf += os.read(fd, 4096)
            except BlockingIOError:
                pass
            if until is not None and re.search(until, buf[-4096:]):
                return True
    return False

def cmd(s, t=5):
    global buf
    buf = b''
    os.write(fd, s.encode() + b'\r')
    pump(t, rb'\n# ?$')
    return buf.decode(errors='replace')

os.write(fd, b'\r')
if pump(2, rb'login: ?$'):
    os.write(fd, b'root\r')
    pump(4, rb'# ?$')
# stop the shell echoing the payload back
cmd('stty -echo')
buf = b''
os.write(fd, b'cat > /tmp/uart-put.b64\r')
time.sleep(0.3)
lines = base64.encodebytes(data).splitlines()
t0 = time.time()
for i, line in enumerate(lines):
    os.write(fd, line + b'\r')
    # 77 bytes per line at ~11.5 KB/s; stay a little under the line rate
    pump(0.0075)
    if i % 200 == 0:
        sys.stderr.write('\r%d/%d lines' % (i, len(lines)))
os.write(fd, b'\x04')
pump(1)
out = cmd('stty echo; mkdir -p "$(dirname "%s")" && base64 -d /tmp/uart-put.b64 > "%s" && rm /tmp/uart-put.b64 && sync && md5sum "%s"' % (dst, dst, dst), 30)
want = hashlib.md5(data).hexdigest()
print('\n%d bytes in %.0f s' % (len(data), time.time() - t0))
if want in out:
    print('md5 OK', want)
else:
    sys.exit('md5 mismatch or error:\n' + out)
