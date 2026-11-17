#!/usr/bin/env python3
"""Spectron PPPP dig — TCPRSStart variants round, emulation side.

Experiments (fake inputs only — DID "FAKE-123456-ABCDE", token
0xAABBCCDD, sockaddr 192.168.1.X:54321, key "FAKEDSK123456789"):

A) Proto_Send_TCPRSStart (the raw / non-envelope sender @0x6ed30):
   capture cs2p2p_SendMessage's entry args and the final sendto()
   call (via the sendto PLT entry, regs pristine there) — i.e. the
   exact wire bytes of the raw form + the destination sockaddr_in.
   Cross-check the wire bytes against gqproto.prop_enc(inner, key).

C) Proto_TCPSend_TCPRSStart with uintC != 0: hook
   cs2_TCPNBSkt_Overtime_Send entry + the sendto PLT to prove what
   the uintC path emits (disassembly says: uintC is a send timeout
   in ms for a select-style sendto loop over the SAME envelope, and
   the `out` param is a 1-byte cancel flag — verify live in emu).
"""
import struct
import sys

sys.path.insert(0, "/Users/YOURNAME/pppp-dig")
import emu1
import gqproto as gq

from unicorn import UC_HOOK_CODE
from unicorn.arm64_const import (UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2,
                                 UC_ARM64_REG_X3, UC_ARM64_REG_X4, UC_ARM64_REG_X5)

uc = emu1.uc
rd = emu1.rd

SEND_RAW = emu1.syms["_Z33cs2p2p_PPPP_Proto_Send_TCPRSStartPKciP11sockaddr_inS0_jS0_jPK12sockaddr_cs2"]
SENDMSG = emu1.syms["_Z18cs2p2p_SendMessagePKcPciiP11sockaddr_in"]
OVERTIME = emu1.syms["_Z26cs2_TCPNBSkt_Overtime_SendiPKhijPc"]
TCPSEND_RS = emu1.syms["_Z36cs2p2p_PPPP_Proto_TCPSend_TCPRSStartPKciS0_jS0_jPK12sockaddr_cs2jPc"]
SENDTO_PLT = 0x94250  # sendto@plt in libgqipcsdk.so (per /tmp/dis.txt)

GOLDEN_INNER = bytes.fromhex(
    "f1520030"
    "46414b4500000000" "0001e240"
    "4142434445000000" "aabbccdd"
    "000231d43201a8c0" + "00" * 16)

rec = {"sendto": [], "sendmsg": [], "overtime": []}


def hook2(uc_, address, size, _):
    if address == SENDTO_PLT:
        fd = uc_.reg_read(UC_ARM64_REG_X0)
        buf = uc_.reg_read(UC_ARM64_REG_X1)
        ln = uc_.reg_read(UC_ARM64_REG_X2)
        dest = uc_.reg_read(UC_ARM64_REG_X4)
        alen = uc_.reg_read(UC_ARM64_REG_X5)
        rec["sendto"].append({
            "fd": fd, "data": rd(buf, ln),
            "dest": rd(dest, alen) if dest and 0 < alen <= 128 else b""})
    elif address == SENDMSG:
        rec["sendmsg"].append(tuple(uc_.reg_read(r) for r in (
            UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2,
            UC_ARM64_REG_X3, UC_ARM64_REG_X4)))
    elif address == OVERTIME:
        buf = uc_.reg_read(UC_ARM64_REG_X1)
        ln = uc_.reg_read(UC_ARM64_REG_X2)
        rec["overtime"].append({
            "sock": uc_.reg_read(UC_ARM64_REG_X0), "frame": rd(buf, ln),
            "timeout": uc_.reg_read(UC_ARM64_REG_X3),
            "out": uc_.reg_read(UC_ARM64_REG_X4)})


uc.hook_add(UC_HOOK_CODE, hook2)

part1 = emu1.put_str("FAKE", emu1.SCRATCH + 0x5000)
part3 = emu1.put_str("ABCDE", emu1.SCRATCH + 0x5100)
DID_NUMBER = 123456
TOKEN = 0xAABBCCDD

# sockaddr_in dest (192.168.1.X:54321) for the raw sender
dest_in = emu1.SCRATCH + 0x7000
uc.mem_write(dest_in, struct.pack("<H", 2) + struct.pack(">H", 54321)
             + bytes([192, 168, 1, 50]) + b"\0" * 8)

# SendMessage's IPv6 flag: *(0x9d7a8) -> flag byte. Inspect; patch only
# if the pointer escapes the mapped regions.
flag_ptr = struct.unpack("<Q", rd(0x9D7A8, 8))[0]
print(f"[setup] ipv6 flag ptr = {flag_ptr:#x}")
if not (0 <= flag_ptr < 0x1F0000 or emu1.SCRATCH <= flag_ptr < emu1.SCRATCH + 0x100000):
    uc.mem_write(emu1.SCRATCH + 0x6000, b"\0")
    uc.mem_write(0x9D7A8, struct.pack("<Q", emu1.SCRATCH + 0x6000))
    print("[setup] flag ptr patched to scratch (IPv4 path)")

# ---------- Experiment A: raw sender ----------
rec["sendto"].clear(); rec["sendmsg"].clear()
emu1.rand_vals = iter([0x12345678, 0x9ABCDEF0] * 16)
emu1.call(SEND_RAW, [emu1.key, 3, dest_in, part1, DID_NUMBER, part3, TOKEN, emu1.sa_buf])
ret = uc.reg_read(UC_ARM64_REG_X0)
print(f"[A] Proto_Send_TCPRSStart ret={ret:#x}")
for (k, b, ln, sock, d) in rec["sendmsg"]:
    print(f"[A] SendMessage(key={emu1.cstr(k)!r}, len={ln}, sock={sock}, "
          f"dest={rd(d, 16).hex()}) buf={rd(b, ln).hex()}")
    print(f"[A]   buf == golden inner: {rd(b, ln) == GOLDEN_INNER}")
for s in rec["sendto"]:
    print(f"[A] sendto(fd={s['fd']}, {len(s['data'])}B) data={s['data'].hex()}")
    print(f"[A]   dest={s['dest'].hex()}")
    exp = gq.prop_enc(GOLDEN_INNER, b"FAKEDSK123456789")
    print(f"[A]   data == prop_enc(inner, FAKEDSK): {s['data'] == exp}")
    if s["data"] != exp:
        print(f"[A]   prop_enc(inner, FAKEDSK) = {exp.hex()}")
print(flush=True)

# ---------- Experiment C: uintC (overtime) path ----------
for uintC in (5000, 1):
    rec["sendto"].clear(); rec["overtime"].clear()
    emu1.captured.clear()
    uc.mem_write(emu1.outbuf, b"\0" * 256)  # cancel flag = 0
    emu1.rand_vals = iter([0x12345678, 0x9ABCDEF0] * 16)
    emu1.call(TCPSEND_RS,
              [emu1.key, 3, part1, DID_NUMBER, part3, TOKEN, emu1.sa_buf, uintC],
              struct.pack("<Q", emu1.outbuf))
    ret = uc.reg_read(UC_ARM64_REG_X0)
    print(f"[C] TCPSend uintC={uintC}: ret={ret:#x} "
          f"overtime_calls={len(rec['overtime'])} sendto={len(rec['sendto'])} "
          f"tcpnb_captured={len(emu1.captured)}")
    for o in rec["overtime"]:
        print(f"[C]   Overtime_Send(sock={o['sock']}, len={len(o['frame'])}, "
              f"timeout={o['timeout']}, out={o['out']:#x}) frame={o['frame'].hex()}")
    for s in rec["sendto"]:
        print(f"[C]   sendto(fd={s['fd']}, {len(s['data'])}B) data={s['data'].hex()}")
    print(flush=True)
