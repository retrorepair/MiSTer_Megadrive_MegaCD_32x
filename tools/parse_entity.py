#!/usr/bin/env python3
"""Extract the 'Fitter Resource Utilization by Entity' table from a Quartus .fit.rpt.
Usage: parse_entity.py <file.fit.rpt> [out.tsv] [--depth N] [--min-alm N]
Prints a readable tree (ALMs needed, self ALMs, regs, M10K, DSP) and writes a TSV."""
import re, sys, csv
args = [a for a in sys.argv[1:] if not a.startswith("--")]
opts = {a.split("=")[0]: a.split("=")[1] if "=" in a else "1" for a in sys.argv[1:] if a.startswith("--")}
F = args[0]; out = args[1] if len(args) > 1 else None
maxdepth = int(opts.get("--depth", "99")); minalm = float(opts.get("--min-alm", "0"))
rows = []; intable = False; hdr_seen = 0
with open(F, encoding="utf-8", errors="replace") as f:
    for ln, line in enumerate(f, 1):
        if "Fitter Resource Utilization by Entity" in line and not intable:
            intable = True; continue
        if not intable: continue
        if line.startswith("; ") and hdr_seen < 1:
            if "Compilation Hierarchy Node" in line: hdr_seen = 1
            continue
        if hdr_seen and line.startswith("+"): continue
        if hdr_seen and line.strip() == "": break
        if not line.startswith("; "): continue
        cols = [c.strip() for c in line.rstrip("\n").split(";")[1:-1]]
        if len(cols) < 16: continue
        node = cols[0]
        tot = lambda s: float(re.match(r"([\d.]+)", s).group(1)) if re.match(r"([\d.]+)", s) else 0.0
        slf = lambda s: float(re.search(r"\(([\d.]+)\)", s).group(1)) if re.search(r"\(([\d.]+)\)", s) else 0.0
        rows.append(dict(depth=(len(node)-len(node.lstrip()))//3, node=node.strip(),
            alm=tot(cols[1]), alm_self=slf(cols[1]), regs=tot(cols[7]), regs_self=slf(cols[7]),
            membits=int(cols[9]) if cols[9].isdigit() else 0, m10k=int(cols[10]) if cols[10].isdigit() else 0,
            dsp=int(cols[11]) if cols[11].isdigit() else 0, full=cols[14], entity=cols[15]))
print(f"{'ALM':>8} {'self':>7} {'regs':>7} {'M10K':>5} {'DSP':>4}  node")
for r in rows:
    if r["depth"] <= maxdepth and r["alm"] >= minalm:
        print(f"{r['alm']:8.0f} {r['alm_self']:7.0f} {r['regs']:7.0f} {r['m10k']:5d} {r['dsp']:4d}  {'  '*r['depth']}{r['node']}  [{r['entity']}]")
if out:
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter="\t"); w.writerow(list(rows[0].keys()))
        for r in rows: w.writerow(list(r.values()))
    print("wrote", out, file=sys.stderr)
