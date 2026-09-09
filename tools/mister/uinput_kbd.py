#!/usr/bin/env python3
"""Drive the MiSTer OSD from a shell by synthesising keystrokes.

Runs ON the MiSTer (which has python3 but no gcc).  Creates a virtual keyboard
through /dev/uinput; MiSTer's input.cpp has an inotify watch on /dev/input and
picks the new device up on its own, so no restart is needed.

    ./uinput_kbd.py osd up up enter          # F12, two downs^W ups, select
    ./uinput_kbd.py --list                   # show the key names understood

Key names are the linux input-event-codes names minus the KEY_ prefix, lower
case.  A bare number is sent as that raw keycode.  "wait:N" pauses N seconds
between keys (default 0.12 s, and 0.6 s after the OSD key so the menu can draw).
"""

import fcntl, os, struct, sys, time

UINPUT = "/dev/uinput"
UI_SET_EVBIT   = 0x40045564
UI_SET_KEYBIT  = 0x40045565
UI_DEV_CREATE  = 0x00005501
UI_DEV_DESTROY = 0x00005502
EV_SYN, EV_KEY = 0x00, 0x01
SYN_REPORT = 0

KEYS = {
    "esc": 1, "1": 2, "2": 3, "3": 4, "4": 5, "5": 6, "6": 7, "7": 8, "8": 9,
    "9": 10, "0": 11, "minus": 12, "equal": 13, "backspace": 14, "tab": 15,
    "q": 16, "w": 17, "e": 18, "r": 19, "t": 20, "y": 21, "u": 22, "i": 23,
    "o": 24, "p": 25, "enter": 28, "ctrl": 29, "a": 30, "s": 31, "d": 32,
    "f": 33, "g": 34, "h": 35, "j": 36, "k": 37, "l": 38, "shift": 42,
    "z": 44, "x": 45, "c": 46, "v": 47, "b": 48, "n": 49, "m": 50,
    "alt": 56, "space": 57,
    "f1": 59, "f2": 60, "f3": 61, "f4": 62, "f5": 63, "f6": 64, "f7": 65,
    "f8": 66, "f9": 67, "f10": 68, "f11": 87, "f12": 88,
    "up": 103, "left": 105, "right": 106, "down": 108,
    "home": 102, "pgup": 104, "end": 107, "pgdn": 109,
    "ins": 110, "del": 111,
}
KEYS["osd"] = KEYS["f12"]      # MiSTer opens/closes the OSD with F12
KEYS["menu"] = KEYS["f12"]
KEYS["back"] = KEYS["esc"]

GAP_DEFAULT = 0.12
GAP_AFTER_OSD = 0.6            # the OSD needs a few frames to draw


class VKbd:
    def __init__(self, name=b"MiSTer virtual keyboard"):
        self.fd = os.open(UINPUT, os.O_WRONLY | os.O_NONBLOCK)
        fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_KEY)
        fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_SYN)
        for code in range(1, 256):
            fcntl.ioctl(self.fd, UI_SET_KEYBIT, code)
        # struct uinput_user_dev: name[80], input_id{bustype,vendor,product,version},
        # ff_effects_max, then absmax/absmin/absfuzz/absflat[64] each.
        dev = name[:79].ljust(80, b"\0")
        dev += struct.pack("HHHH", 0x03, 0x1209, 0x0001, 1)   # BUS_USB
        dev += struct.pack("I", 0)
        dev += b"\0" * (4 * 64 * 4)
        os.write(self.fd, dev)
        fcntl.ioctl(self.fd, UI_DEV_CREATE)
        time.sleep(1.2)          # let MiSTer's inotify watch open the new event node

    def _ev(self, etype, code, value):
        os.write(self.fd, struct.pack("llHHi", 0, 0, etype, code, value))

    def tap(self, code, hold=0.05):
        self._ev(EV_KEY, code, 1); self._ev(EV_SYN, SYN_REPORT, 0)
        time.sleep(hold)
        self._ev(EV_KEY, code, 0); self._ev(EV_SYN, SYN_REPORT, 0)

    def close(self):
        try:
            fcntl.ioctl(self.fd, UI_DEV_DESTROY)
        finally:
            os.close(self.fd)


FIFO = "/tmp/mister_kbd"
PIDFILE = "/tmp/mister_kbd.pid"


def daemon_pid():
    """PID of a live daemon, or None."""
    try:
        pid = int(open(PIDFILE).read().strip())
        os.kill(pid, 0)
        return pid
    except (OSError, ValueError):
        return None


def resolve(tok):
    name = tok.lower()
    code = KEYS.get(name)
    if code is None and name.isdigit():
        code = int(name)
    return name, code


def daemon():
    """Hold the virtual keyboard open and take key lines from a FIFO.

    Creating the device per invocation is unreliable: MiSTer notices it through an inotify
    watch on /dev/input and then spends a while looking for map files (config/kbd_*.map,
    inputs/*_v3.map, gamecontrollerdb), so early keystrokes are typed into a device nothing
    is reading yet.  Keeping one device open for the whole session removes that race.
    """
    # Exactly one daemon.  A --send line is read by whichever daemon happens to be blocked in
    # open() on the FIFO, and MiSTer opens at most NUMDEV input devices - so with several daemons
    # a keystroke can land on a device MiSTer never opened and silently vanish.  That happened:
    # eight daemons and nine virtual keyboards accumulated over a night of restarts and made a
    # run of hardware results unreliable.
    pid = daemon_pid()
    if pid:
        print("a keyboard daemon is already running (pid %d); kill it first" % pid, file=sys.stderr)
        return 1
    if not os.path.exists(FIFO):
        os.mkfifo(FIFO, 0o666)
    kbd = VKbd()
    with open(PIDFILE, "w") as f:
        f.write(str(os.getpid()))
    print("ready", flush=True)
    try:
        while True:
            with open(FIFO) as f:              # reopen: each writer sends one line then EOFs
                for line in f:
                    for tok in line.split():
                        if tok.startswith("wait:"):
                            time.sleep(float(tok[5:]))
                            continue
                        name, code = resolve(tok)
                        if code is None:
                            print("unknown key: %s" % tok, file=sys.stderr, flush=True)
                            continue
                        kbd.tap(code)
                        time.sleep(GAP_AFTER_OSD if name in ("osd", "menu", "f12") else GAP_DEFAULT)
    finally:
        kbd.close()
        try:
            os.unlink(PIDFILE)
        except OSError:
            pass
    return 0


def main(argv):
    if "--list" in argv:
        print(" ".join(sorted(KEYS)))
        return 0
    if not argv:
        print(__doc__)
        return 1
    if argv[0] == "--daemon":
        return daemon()
    if argv[0] == "--send":                    # hand the rest to a running daemon
        if daemon_pid() is None:
            print("no keyboard daemon is running; start one with --daemon", file=sys.stderr)
            return 1
        with open(FIFO, "w") as f:
            f.write(" ".join(argv[1:]) + "\n")
        return 0
    kbd = VKbd()
    try:
        for tok in argv:
            if tok.startswith("wait:"):
                time.sleep(float(tok[5:]))
                continue
            name = tok.lower()
            code = KEYS.get(name)
            if code is None and name.isdigit():
                code = int(name)
            if code is None:
                print("unknown key: %s" % tok, file=sys.stderr)
                return 2
            kbd.tap(code)
            time.sleep(GAP_AFTER_OSD if name in ("osd", "menu", "f12") else GAP_DEFAULT)
        time.sleep(0.3)
    finally:
        kbd.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
