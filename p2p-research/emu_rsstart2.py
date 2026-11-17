#!/usr/bin/env python3
"""Spectron PPPP dig — TCPRSStart emulation, instrumented (phase 2 follow-up).

Fixes vs emu_rsstart.py:
  * correct AAPCS packing for the 9-param signature
    (PKc key, i sock, PKc strA, j uintA, PKc strB, j uintB,
     PKsockaddr_cs2 sa, j uintC, Pc out[stack])
  * out-buffer pre-filled with 0xEE sentinel and dumped after the call
  * return value (X0) read back
  * trace hook on Proto_TCPSend_MSG entry + its return site in TCPRSStart

Fake DID-shaped values only (part1/number/part3) — no real credentials.
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

RSSTART = emu1.syms["_Z36cs2p2p_PPPP_Proto_TCPSend_TCPRSStartPKciS0_jS0_jPK12sockaddr_cs2jPc"]
MSG = emu1.syms["_Z29cs2p2p_PPPP_Proto_TCPSend_MSGPKciPKhtjPc"]
RET_AFTER_MSG = RSSTART + 0xD8  # insn after `bl TCPSend_MSG` (0x6df50 + 4)
print("TCPRSStart @", hex(RSSTART), " TCPSend_MSG @", hex(MSG))

trace = {"msg_calls": 0}


def hook_trace(uc_, address, size, _):
    if address == MSG:
        trace["msg_calls"] += 1
        x0 = uc_.reg_read(UC_ARM64_REG_X0)
        x1 = uc_.reg_read(UC_ARM64_REG_X1)
        x2 = uc_.reg_read(UC_ARM64_REG_X2)
        x3 = uc_.reg_read(UC_ARM64_REG_X3)
        x4 = uc_.reg_read(UC_ARM64_REG_X4)
        x5 = uc_.reg_read(UC_ARM64_REG_X5)
        print(f"  [trace] TCPSend_MSG(key={emu1.cstr(x0)!r}, sock={x1}, "
              f"pkt={rd(x2, 56).hex()}, len={x3}, uint={x4:#x}, out={x5:#x})")
    elif address == RET_AFTER_MSG:
        print(f"  [trace] TCPSend_MSG returned X0={uc_.reg_read(UC_ARM64_REG_X0):#x}")


uc.hook_add(UC_HOOK_CODE, hook_trace)

# DID-shaped fake field values (NOT the real DID)
part1 = emu1.put_str("FAKE", emu1.SCRATCH + 0x5000)
part3 = emu1.put_str("ABCDE", emu1.SCRATCH + 0x5100)
DID_NUMBER = 123456


def run(label, uintB, uintC):
    emu1.captured.clear()
    trace["msg_calls"] = 0
    uc.mem_write(emu1.outbuf, b"\xEE" * 256)
    emu1.rand_vals = iter([0x12345678, 0x9ABCDEF0] * 16)
    emu1.call(RSSTART,
              [emu1.key, 3, part1, DID_NUMBER, part3, uintB, emu1.sa_buf, uintC],
              struct.pack("<Q", emu1.outbuf))
    ret = uc.reg_read(UC_ARM64_REG_X0)
    out = rd(emu1.outbuf, 256)
    print(f"[{label}] ret X0={ret:#x} msg_calls={trace['msg_calls']} "
          f"captured={len(emu1.captured)}")
    if out != b"\xEE" * 256:
        nz = out.rstrip(b"\xEE")
        print(f"[{label}] OUTBUF written ({len(nz)}B): {nz.hex()}")
    else:
        print(f"[{label}] outbuf untouched")
    if emu1.captured:
        pkt = emu1.captured[0]
        print(f"[{label}] SEND {len(pkt)}B: {pkt.hex()}")
        inner = gq.unwrap_tcp_payload(pkt[8:], pkt[4:6], "FAKEDSK123456789")
        print(f"[{label}] inner: {inner.hex() if inner else None}")
    print(flush=True)


run("A uintB=0xAABBCCDD uintC=0", 0xAABBCCDD, 0)
run("B uintB=0xAABBCCDD uintC=1", 0xAABBCCDD, 1)
run("C uintB=0 uintC=0", 0, 0)
