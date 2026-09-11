#!/usr/bin/env python3
"""Stop re-executing a live CDD command every frame, which pins the drive and kills file reads.

WHY
Main_MiSTer owns the CD drive. Its poll loop treats every toggle of the core's request line as a
NEW command (Main_MiSTer/support/megacd/megacd.cpp, mcd_poll):

    uint8_t req = spi_uio_cmd_cont(UIO_CD_GET);
    if (req != last_req) {
        last_req = req;
        ...
        cdd.SetCommand(c, 0);
        cdd.CommandExec();        // <-- executes it
        has_command = 1;
    }

and CommandExec re-seeks for a play (support/megacd/megacdd.cpp):

    case CD_COMM_PLAY:
        MSFToLBA(&lba_, comm[2]*10+comm[3], ...);
        SeekToLBA(lba_, 1);       // <-- back to the LBA in the command registers
        this->status = CD_STAT_PLAY;

Main advances the drive on its OWN 75 Hz timer (GetTimer(13...)), one sector per cdd.Update(), so
our request line is only ever meant to mean "here is a new command".

This gate array, however, hands the command registers over again once per 75 Hz frame as well as on
a write to $FF804A. While a PLAY is still sitting in those registers that makes Main seek back to the
start of the read about 75 times a second, so the transfer never advances. Measured on Doom CD32X
Fusion: SECTOR_END reaches 34 and then stops for ever, the WAD never loads, and the game panics with
"R_InitData: <n> >= numlumps" (read out of the SH-2 stack via DDR3) and halts itself in `bra .`.

Titles that boot from the disc under the BIOS are unaffected because well-behaved software leaves
CD_COMM_IDLE (0x00) in the command registers between commands, and IDLE is idempotent - it only
reports status. That is why Night Trap streams happily at 75 sectors/s on the same build.

THE FIX
Keep sending on a command write - that is the real event, and what Main expects. Only poll
periodically while the command register holds CD_COMM_IDLE. That preserves the reason the periodic
send was added (software which sets HOCK and then only polls status never saw it change, and
mcd-verificator hung on CDC INIT) while never re-issuing a live command.

Usage: phase36_cdd_idle_poll.py <core dir>"""
import sys, os

d = sys.argv[1]


def edit(rel, pairs):
    p = os.path.join(d, rel)
    s = open(p, encoding="utf-8", errors="replace").read()
    for old, new in pairs:
        assert old in s, rel + ": anchor missing: " + old[:70]
        assert s.count(old) == 1, rel + ": anchor not unique: " + old[:70]
        s = s.replace(old, new, 1)
    open(p, "w", encoding="utf-8", newline="").write(s)
    print(rel, "ok")


edit("rtl/MCD/ASIC.vhd", [
    ("""				elsif CLK_12M_F = '1' then
					if CDD_FRAME_CNT = 166666 then
						CDD_SEND <= '1';
						CDD_FRAME_CNT <= (others => '0');""",
     """				elsif CLK_12M_F = '1' then
					if CDD_FRAME_CNT = 166666 then
						-- Only poll while the command register holds CD_COMM_IDLE (0). Main_MiSTer
						-- re-EXECUTES whatever is in the command registers on every request toggle
						-- (megacd.cpp mcd_poll: cdd.SetCommand(); cdd.CommandExec()), and
						-- CD_COMM_PLAY re-seeks to the LBA it carries (megacdd.cpp CommandExec).
						-- Handing a live PLAY over again each frame therefore drags the drive back
						-- to the start of the read ~75 times a second and the file never advances:
						-- Doom CD32X Fusion got 34 sectors and then stalled for ever. IDLE is
						-- idempotent - it only reports status - so periodic polling still does what
						-- it was added for (CDC INIT, and software that sets HOCK then only polls).
						if CDDC(3 downto 0) = x"0" then
							CDD_SEND <= '1';
						end if;
						CDD_FRAME_CNT <= (others => '0');"""),
])
