#!/usr/bin/env python3
"""Drive the MegaCD core's MiSTer OSD blind, from the dev box, over plink.

WHY BLIND
---------
MiSTer composites the OSD overlay AFTER the scaler in sys_top.v, and
Main_MiSTer's request_screenshot() (scaler.cpp) copies out of the scaler
buffer.  A screenshot therefore can NEVER contain the OSD.  There is no way
to read back where the cursor is; the only option is to know the selection
index and count keypresses.  This file is that knowledge, made executable.

The indices below were derived by reading Main_MiSTer/menu.cpp
(case MENU_GENERIC_MAIN2, ~line 1907-2230, and the shared up/down handler at
~line 1489-1527) against MegaCD.sv's CONF_STR (line 153) and

    wire [15:0] status_menumask =
        {6'd0, en216p, region, !region, ~gg_available,
         !gun_mode, tmss_loaded, ~dbg_menu, 1'b0, ~bk_ena};   // MegaCD.sv:231

Rules that produce the map (all from menu.cpp):

  * Only P-headers, F/S, C, T/R/t/r and O/o rows do `selentry++`.  A "-"
    separator does `entry++` only (menu.cpp:2191-2199) -> NOT selectable.
    "V,...", "J1,...", "jn,...", "jp,..." match no branch at all -> invisible.
  * HIDDEN (h/H) rows are skipped by `if (!h && inpage)` (menu.cpp:1991), so
    they consume NO selection slot.
  * DISABLED (d/D) rows ARE drawn and DO consume a slot; `d` is only passed to
    MenuWrite() as the stipple flag and `menumask` still gets its 1 bit
    (e.g. menu.cpp:2182-2185).  They are reachable but inert, because
    MENU_GENERIC_MAIN3 guards the action with `if (p && !d)` (menu.cpp:2403).
  * Polarity: 'H' hides when the mask bit is 1, 'h' hides when it is 0;
    'D' disables when the bit is 1, 'd' disables when it is 0
    (menu.cpp:1963-1966).
  * "P1,Audio & Video;" (comma right after the digit) is a page HEADER and
    appears on page 0 as one selectable ">" row.  "P1O[30],..." (no comma)
    is a page-1 MEMBER and is dropped from page 0 by
    `if (!page && n && !flat) inpage = 0;` (menu.cpp:1976).
  * The final STD_EXIT row IS selectable: menusub_last = selentry and
    menumask gets one more bit (menu.cpp:2211-2218).
  * Selection WRAPS both ways (menu.cpp:1489-1527), and because every
    selectable row sets its mask bit to 1 the mask is a solid run of ones.
    So from the freshly-opened menu (MENU_NONE2 forces `menusub = 0`,
    menu.cpp:1613) ONE 'up' lands on Exit, two on the last real item, etc.

ASSUMPTIONS baked into TOP_INDEX (state at the time of writing):
    dbg_menu      = 0   (Enter+Esc chord not pressed) -> mask bit 2 = 1,
                        so the five "H2..." debug rows + "H2-" are HIDDEN.
    gg_available  = 0   (no cheat file) -> mask bit 5 = 1,
                        so "H5O[24],Cheats Enabled" is HIDDEN.
    region        = 0/1/2 -> exactly one of h6/h7/h8 "Region" rows is shown.
    no game manual PDF  -> menu.cpp:2097 does not insert an extra " Manual"
                        row above "Cheats".
    tmss_loaded   = 0, bk_ena = anything, gun_mode = 0, en216p = anything:
                        these drive only d/D (disable) or page-1 rows and so
                        CANNOT move any page-0 index.
    flat          = 0   (menu.cpp:1171; toggled only by the ` GRAVE key,
                        menu.cpp:2619 - never send that key).
    page          = 0   (the OSD was not left inside a P1/P2 sub-page; `page`
                        is static and is NOT reset when the OSD closes).

Every assumption that CAN move an index moves rows that all sit ABOVE
"Reset & Eject CD".  Nothing below it is hideable.  Therefore the UP_INDEX
(count-from-the-bottom) values are correct even if every assumption above is
wrong, which is why this script prefers UP for the bottom items.

USAGE
    osd.py list                          # print the derived map
    osd.py select "Eject Disc"           # open OSD, navigate, press Enter
    osd.py goto  "Backup RAM"            # navigate but do not press Enter
    osd.py keys osd down down enter      # raw passthrough to uinput_kbd.py
    osd.py close                         # F12 to dismiss the OSD
    osd.py shot out.png                  # screenshot (core video, no OSD)
    ... any of the above with -n / --dry-run to just print the commands.

Requires tools/mister/uinput_kbd.py already at /media/fat/uinput_kbd.py.
Python 3, stdlib only.
"""

import argparse
import os
import posixpath
import shlex
import subprocess
import sys
import time

# --- connection, same values/style as deploy.sh --------------------------
MISTER = "192.168.1.182"
USER = "root"
PW = "1"
HK = "SHA256:FqNJOsj3FLUoMQxgn+cqGoXvVfENmVK4QFoSCMKl2lU"
PLINK = "/c/Program Files/PuTTY/plink.exe"
PSCP = "/c/Program Files/PuTTY/pscp.exe"

KBD = "/media/fat/uinput_kbd.py"
SHOTDIR = "/media/fat/screenshots"

# --- the map -------------------------------------------------------------
# (label, confstr source, note).  Order == selection order on page 0.
MAIN_PAGE = [
    ("Insert Disk",              "S0,CUECHD",        "file browser (.cue/.chd)"),
    ("Insert Cartridge",         "FS6,BINGENMD",     "file browser (.bin/.gen/.md)"),
    ("Disc Insert",              "O[36]",            "cycles Reset / Keep Running"),
    ("TMSS",                     "d3O[9]",           "greyed unless boot2.rom loaded"),
    ("Region",                   "h6/h7/h8 O[7:6]",  "one of three rows, per region"),
    ("Cheats",                   "C",                "greyed unless a cheat file exists"),
    ("Backup RAM",               "O[3]",             "Internal / Internal+Cart"),
    ("Reload Backup RAM",        "D0R[16]",          "greyed while bk_ena = 0"),
    ("Save Backup RAM",          "D0R[17]",          "greyed while bk_ena = 0"),
    ("Autosave",                 "D0O[13]",          "greyed while bk_ena = 0"),
    ("Audio & Video",            "P1 header",        "submenu -> page 1"),
    ("Input",                    "P2 header",        "submenu -> page 2"),
    ("Pause When OSD is Open",   "O[60]",            "index valid only if dbg_menu = 0"),
    ("Reset & Eject CD",         "R[0]",             "bottom-anchored, always 4 ups"),
    ("Remove Cartridge & Reset", "R[37]",            "bottom-anchored, always 3 ups"),
    ("Eject Disc",               "R[38]",            "bottom-anchored, always 2 ups"),
    ("Exit",                     "STD_EXIT",         "bottom-anchored, always 1 up"),
]
N_SEL = len(MAIN_PAGE)  # 17 -> menumask = 0x1FFFF, menusub_last = 16

# Rows at or below this index have no hideable row beneath them, so their
# distance from the bottom is invariant to every assumption in the docstring.
FIRST_BOTTOM_SAFE = 13  # "Reset & Eject CD"

ALIASES = {
    "disk": "Insert Disk", "disc": "Insert Disk", "insert disk": "Insert Disk",
    "cart": "Insert Cartridge", "cartridge": "Insert Cartridge",
    "disc insert": "Disc Insert",
    "tmss": "TMSS", "region": "Region", "cheats": "Cheats",
    "bram": "Backup RAM", "backup": "Backup RAM",
    "reload": "Reload Backup RAM", "save": "Save Backup RAM",
    "autosave": "Autosave",
    "av": "Audio & Video", "video": "Audio & Video", "audio": "Audio & Video",
    "input": "Input",
    "pause": "Pause When OSD is Open",
    "reset": "Reset & Eject CD", "reset & eject cd": "Reset & Eject CD",
    "remove cart": "Remove Cartridge & Reset",
    "remove cartridge": "Remove Cartridge & Reset",
    "eject": "Eject Disc", "eject disc": "Eject Disc",
    "exit": "Exit",
}


def resolve(name):
    """Return (index, label) for a target name; raise SystemExit if unknown."""
    key = " ".join(name.lower().split())
    label = ALIASES.get(key)
    if label is None:
        for i, (lab, _, _) in enumerate(MAIN_PAGE):
            if lab.lower() == key:
                return i, lab
        raise SystemExit("osd.py: unknown target %r (try: osd.py list)" % name)
    for i, (lab, _, _) in enumerate(MAIN_PAGE):
        if lab == label:
            return i, lab
    raise SystemExit("osd.py: internal alias table error for %r" % name)


def ups_for(index):
    """Presses of UP from a freshly-opened menu (menusub == 0) to reach index."""
    return N_SEL - index          # index 16 -> 1 up, index 13 -> 4 ups


def keyseq(index, press_enter, force=None):
    """Build the uinput_kbd.py argv for reaching `index` from a closed OSD."""
    downs, ups = index, ups_for(index)
    if force == "down":
        use_up = False
    elif force == "up":
        use_up = True
    else:
        # Prefer UP for the assumption-proof bottom rows; otherwise fewest keys.
        use_up = index >= FIRST_BOTTOM_SAFE or ups < downs
    keys = ["osd"]
    keys += ["up"] * ups if use_up else ["down"] * downs
    if press_enter:
        keys += ["wait:0.3", "enter"]
    return keys


# --- plumbing ------------------------------------------------------------
def exe(p):
    """Accept deploy.sh's MSYS path; fall back to the Win32 form if needed."""
    if os.path.exists(p):
        return p
    if len(p) > 3 and p[0] == "/" and p[2] == "/":
        win = p[1].upper() + ":" + p[2:].replace("/", "\\")
        if os.path.exists(win):
            return win
    return p


def plink(remote_cmd, dry=False, check=True):
    argv = [exe(PLINK), "-ssh", "-batch", "-hostkey", HK, "-pw", PW,
            "%s@%s" % (USER, MISTER), remote_cmd]
    if dry:
        print("+ " + " ".join(shlex.quote(a) for a in argv))
        return ""
    r = subprocess.run(argv, capture_output=True, text=True)
    if r.stderr.strip():
        sys.stderr.write(r.stderr)
    if check and r.returncode != 0:
        raise SystemExit("osd.py: plink failed (%d)" % r.returncode)
    return r.stdout


def pscp(remote_path, local_path, dry=False):
    argv = [exe(PSCP), "-batch", "-hostkey", HK, "-pw", PW,
            "%s@%s:%s" % (USER, MISTER, remote_path), local_path]
    if dry:
        print("+ " + " ".join(shlex.quote(a) for a in argv))
        return True
    r = subprocess.run(argv, capture_output=True, text=True)
    if r.stderr.strip():
        sys.stderr.write(r.stderr)
    return r.returncode == 0


def send_keys(keys, dry=False):
    cmd = "python3 %s %s" % (KBD, " ".join(shlex.quote(k) for k in keys))
    print("keys: " + " ".join(keys))
    return plink(cmd, dry=dry)


# --- commands ------------------------------------------------------------
def cmd_list(_args):
    print("MegaCD OSD main page (page 0) - selectable rows only")
    print("menumask = 0x%05X, menusub_last = %d\n" % ((1 << N_SEL) - 1, N_SEL - 1))
    print("  idx  ups  confstr             label")
    for i, (lab, src, note) in enumerate(MAIN_PAGE):
        mark = "*" if i >= FIRST_BOTTOM_SAFE else " "
        print(" %s%3d  %3d  %-18s  %-26s  %s" % (mark, i, ups_for(i), src, lab, note))
    print("\n  ups = UP presses from a freshly-opened OSD (menusub starts at 0,")
    print("        and UP from 0 wraps to the last row: menu.cpp:1519-1524).")
    print("  *   = distance from the bottom is immune to every assumption in")
    print("        this file's docstring; prefer these.")
    return 0


def cmd_goto(args, press_enter=False):
    idx, label = resolve(args.target)
    force = "up" if args.up else ("down" if args.down else None)
    keys = keyseq(idx, press_enter, force)
    print("%-26s index %d (%d ups / %d downs)"
          % (label, idx, ups_for(idx), idx))
    send_keys(keys, dry=args.dry_run)
    return 0


def cmd_select(args):
    return cmd_goto(args, press_enter=True)


def cmd_keys(args):
    if not args.keys:
        raise SystemExit("osd.py keys: nothing to send")
    send_keys(args.keys, dry=args.dry_run)
    return 0


def cmd_close(args):
    send_keys(["osd"], dry=args.dry_run)
    return 0


def cmd_shot(args):
    """Screenshot the SCALER output.  Reminder: this can never show the OSD."""
    local = args.outfile
    base = os.path.basename(local)
    if not base.lower().endswith(".png"):
        base += ".png"
    # A name ending in .png lands flat in screenshots/ (file_io.cpp:934-946);
    # anything else gets a datecode and a per-core subdir.
    safe = "".join(c if (c.isalnum() or c in "._-") else "_" for c in base)
    remote = posixpath.join(SHOTDIR, safe)

    plink("rm -f %s; echo screenshot %s > /dev/MiSTer_cmd"
          % (shlex.quote(remote), shlex.quote(safe)), dry=args.dry_run)
    if args.dry_run:
        pscp(remote, local, dry=True)
        return 0

    for _ in range(20):
        time.sleep(0.25)
        if plink("test -s %s && echo ok" % shlex.quote(remote),
                 check=False).strip() == "ok":
            break
    else:
        # Fall back to whatever PNG appeared most recently anywhere under
        # screenshots/ (a core subdir, if the name path was rejected).
        newest = plink("ls -1t %s/*.png %s/*/*.png 2>/dev/null | head -1"
                       % (SHOTDIR, SHOTDIR), check=False).strip()
        if not newest:
            raise SystemExit("osd.py: no screenshot appeared under " + SHOTDIR)
        remote = newest
        print("osd.py: falling back to " + remote)

    if not pscp(remote, local):
        raise SystemExit("osd.py: pscp of %s failed" % remote)
    print("saved %s  (scaler output only - the OSD is composited after the "
          "scaler and cannot appear)" % local)
    return 0


def main(argv):
    ap = argparse.ArgumentParser(
        prog="osd.py",
        description="Blind-drive the MegaCD core's MiSTer OSD over SSH.",
        epilog="Indices come from Main_MiSTer/menu.cpp; see the module docstring.")
    ap.add_argument("-n", "--dry-run", action="store_true",
                    help="print the commands instead of running them")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="print the derived selection map").set_defaults(
        func=cmd_list)

    for name, fn, helptext in (("select", cmd_select, "navigate and press Enter"),
                               ("goto", cmd_goto, "navigate only")):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("target", help='menu label or alias, e.g. "Eject Disc"')
        g = p.add_mutually_exclusive_group()
        g.add_argument("--up", action="store_true",
                       help="force bottom-anchored navigation (UP presses)")
        g.add_argument("--down", action="store_true",
                       help="force top-anchored navigation (DOWN presses)")
        p.set_defaults(func=fn)

    p = sub.add_parser("keys", help="send raw key names to uinput_kbd.py")
    p.add_argument("keys", nargs="*", help="e.g. osd down down enter wait:0.5")
    p.set_defaults(func=cmd_keys)

    sub.add_parser("close", help="press F12 to dismiss the OSD").set_defaults(
        func=cmd_close)

    p = sub.add_parser("shot", help="screenshot the core video and fetch it")
    p.add_argument("outfile", help="local .png path to write")
    p.set_defaults(func=cmd_shot)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
