#!/usr/bin/env python3
"""Drive a running F1GameStation emulator over its QMP socket: screenshots
and button presses, for scripted tests.

usage: emu-ctl.py [--sock PATH] step ...
  shot:FILE.png      save the screen
  key:x              press and release a key (QEMU key names, e.g. x, z,
                     ret, esc, up, shift_r); key:esc+shift_r holds both
  sleep:SECONDS      wait
  hmp:COMMAND        run a monitor command, e.g. "hmp:xp /4wx 0x01c21000"
Buttons: up/down/left/right = D-pad, x=A, z=B, s=X, a=Y, q=L, w=R,
ret=START, shift_r=SELECT, esc=MENU.
default socket: $F1GS_EMU_DIR/state/qmp.sock"""
import json, os, socket, sys, time

def conn(path):
    s = socket.socket(socket.AF_UNIX)
    s.connect(path)
    f = s.makefile('rw')
    f.readline()
    cmd(f, 'qmp_capabilities')
    return f

def cmd(f, name, **args):
    f.write(json.dumps({'execute': name, 'arguments': args}) + '\n')
    f.flush()
    while True:
        r = json.loads(f.readline())
        if 'return' in r or 'error' in r:
            if 'error' in r:
                sys.exit('%s: %s' % (name, r['error']['desc']))
            return r['return']

def key(f, keys, down):
    for k in keys:
        cmd(f, 'input-send-event', events=[{'type': 'key', 'data': {
            'down': down, 'key': {'type': 'qcode', 'data': k}}}])

def main(argv):
    path = os.path.join(os.environ.get('F1GS_EMU_DIR', os.path.expanduser(
        '~/Projects/Hardware/miyoocfw/qemu')), 'state', 'qmp.sock')
    if argv[:1] == ['--sock']:
        path, argv = argv[1], argv[2:]
    if not argv:
        sys.exit(__doc__)
    f = conn(path)
    for a in argv:
        op, _, arg = a.partition(':')
        if op == 'shot':
            cmd(f, 'screendump', filename=os.path.abspath(arg), format='png')
        elif op == 'key':
            key(f, arg.split('+'), True)
            time.sleep(0.15)
            key(f, arg.split('+'), False)
            time.sleep(0.3)
        elif op == 'sleep':
            time.sleep(float(arg))
        elif op == 'hmp':
            print(cmd(f, 'human-monitor-command', **{'command-line': arg}), end='')
        else:
            sys.exit('unknown step ' + a)

if __name__ == '__main__':
    main(sys.argv[1:])
