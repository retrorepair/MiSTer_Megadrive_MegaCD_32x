#!/usr/bin/env python3
"""Synthesis-stage entity table from a Quartus .map.rpt: ALUTs (comb), regs, M10K, DSP per node."""
import re, sys
F = sys.argv[1]; maxdepth = int(sys.argv[2]) if len(sys.argv) > 2 else 2; minalut = float(sys.argv[3]) if len(sys.argv) > 3 else 200
lines = open(F, encoding="utf-8", errors="replace").read().split("\n")
start = next(i for i, l in enumerate(lines) if l.startswith("; Analysis & Synthesis Resource Utilization by Entity"))
hdr = None; rows = []
for l in lines[start+1:]:
    if l.startswith("; ") and hdr is None and "Compilation Hierarchy" in l:
        hdr = [c.strip() for c in l.split(";")[1:-1]]; continue
    if hdr is None: continue
    if l.startswith("+"): continue
    if not l.startswith("; "): break
    cols = [c.strip() for c in l.split(";")[1:-1]]
    node = l.split(";")[1]; depth = (len(node) - len(node.lstrip())) // 3
    d = dict(zip(hdr, cols))
    num = lambda k: float(re.match(r"[\d.]+", d.get(k, "0") or "0").group(0)) if re.match(r"[\d.]+", d.get(k, "0") or "0") else 0.0
    rows.append((depth, node.strip(), num("Combinational ALUTs"), num("Dedicated Logic Registers"), num("M10K"), num("DSP Blocks"), d.get("Entity Name", "")))
print(f"{'ALUT':>7} {'regs':>7} {'M10K':>5} {'DSP':>4}  node [entity]")
for depth, node, alut, regs, m10k, dsp, ent in rows:
    if depth <= maxdepth and alut >= minalut:
        print(f"{alut:7.0f} {regs:7.0f} {m10k:5.0f} {dsp:4.0f}  {'  '*depth}{node} [{ent}]")
