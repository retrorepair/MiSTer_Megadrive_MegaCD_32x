import re, sys
F = sys.argv[1]; maxdepth = int(sys.argv[2]) if len(sys.argv) > 2 else 4
lines = open(F, encoding="utf-8", errors="replace").read().split("\n")
start = next(i for i, l in enumerate(lines) if l.startswith("; Analysis & Synthesis Resource Utilization by Entity"))
hdr = None
print(f"{'membits':>9} {'M10K~':>6}  node [entity]")
for l in lines[start+1:]:
    if l.startswith("; ") and hdr is None and "Compilation Hierarchy" in l:
        hdr = [c.strip() for c in l.split(";")[1:-1]]; continue
    if hdr is None or l.startswith("+"): continue
    if not l.startswith("; "): break
    cols = [c.strip() for c in l.split(";")[1:-1]]; d = dict(zip(hdr, cols))
    node = l.split(";")[1]; depth = (len(node) - len(node.lstrip())) // 3
    bits = int(re.match(r"\d+", d.get("Block Memory Bits","0")).group(0))
    if depth <= maxdepth and bits > 0:
        print(f"{bits:9d} {bits/10240:6.1f}  {'  '*depth}{node.strip()} [{d.get('Entity Name','')}]")
