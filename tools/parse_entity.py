import re, sys, csv
F = "b65.fit.rpt"
START = 11396
rows = []
with open(F, encoding="utf-8", errors="replace") as f:
    for ln, line in enumerate(f, 1):
        if ln < START:
            continue
        if line.strip() == "":
            break
        if not line.startswith("; "):
            continue
        cols = [c.strip() for c in line.rstrip("\n").split(";")[1:-1]]
        if len(cols) < 17:
            print("SHORT ROW", ln, len(cols), file=sys.stderr)
            continue
        node = cols[0]
        def tot(s):
            m = re.match(r"([\d.]+)", s)
            return float(m.group(1)) if m else 0.0
        def self_(s):
            m = re.search(r"\(([\d.]+)\)", s)
            return float(m.group(1)) if m else 0.0
        rows.append(dict(
            line=ln,
            depth=(len(node) - len(node.lstrip())) // 3,
            node=node.strip(),
            alm=tot(cols[1]), alm_self=self_(cols[1]),
            almA=tot(cols[2]),
            alut=tot(cols[6]),
            regs=tot(cols[7]), regs_self=self_(cols[7]),
            membits=int(cols[9]) if cols[9].isdigit() else 0,
            m10k=int(cols[10]) if cols[10].isdigit() else 0,
            dsp=int(cols[11]) if cols[11].isdigit() else 0,
            full=cols[14],
            entity=cols[15],
        ))
print("rows:", len(rows), "last line:", rows[-1]["line"], file=sys.stderr)
out = "entity.tsv"
with open(out, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f, delimiter="\t")
    w.writerow(["line","depth","alm","alm_self","regs","regs_self","membits","m10k","dsp","full","entity"])
    for r in rows:
        w.writerow([r["line"], r["depth"], r["alm"], r["alm_self"], r["regs"], r["regs_self"], r["membits"], r["m10k"], r["dsp"], r["full"], r["entity"]])
print("wrote", out, file=sys.stderr)
