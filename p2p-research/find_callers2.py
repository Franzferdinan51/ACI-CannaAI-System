import re
import sys

lines = open("/tmp/dis.txt").read().splitlines()
funcs = {}
cur = None
calls = []
for ln in lines:
    m = re.match(r"^([0-9a-f]{16}) <(.+)>:", ln)
    if m:
        cur = (int(m.group(1), 16), m.group(2))
        funcs[cur[0]] = cur[1]
    m2 = re.search(r"\sbl\t0x([0-9a-f]+)", ln)
    if m2 and cur:
        calls.append((cur, int(m2.group(1), 16), int(ln.split(":")[0].strip(), 16)))

for want in sys.argv[1:]:
    for addr, name in funcs.items():
        if want in name and not name.endswith("@plt"):
            for (cf, tgt, at) in calls:
                if tgt == addr:
                    print(f"call @{at:#x} in {cf[1]} -> {name}")
