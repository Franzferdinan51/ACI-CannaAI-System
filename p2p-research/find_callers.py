import re
import sys

lines = open("/tmp/dis.txt").read().splitlines()
# map: plt stub address -> name ; function start address -> name
plt = {}
funcs = {}
cur_func = None
for ln in lines:
    m = re.match(r"^([0-9a-f]{16}) <(.+)>:", ln)
    if m:
        cur_func = (int(m.group(1), 16), m.group(2))
        if m.group(2).endswith("@plt"):
            plt[int(m.group(1), 16)] = m.group(2)[:-4]
        else:
            funcs[int(m.group(1), 16)] = m.group(2)
    m2 = re.search(r"\sbl\t0x([0-9a-f]+) <(.+?)@plt>", ln)
    if m2 and cur_func:
        tgt = int(m2.group(1), 16)
        name = m2.group(2)
        for want in sys.argv[1:]:
            if want in name:
                addr = int(ln.split(":")[0].strip(), 16)
                print(f"call @{addr:#x} in {cur_func[1]} -> {name}")
