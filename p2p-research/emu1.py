#!/usr/bin/env python3
"""Emulate the SDK's own packet builders with Unicorn (fake inputs only)
and capture the exact bytes handed to cs2_TCPNBSkt_Send."""
import struct
import sys

from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_LITTLE_ENDIAN, UC_HOOK_CODE
from unicorn.arm64_const import (UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2,
                                 UC_ARM64_REG_X3, UC_ARM64_REG_X4, UC_ARM64_REG_X5,
                                 UC_ARM64_REG_X6, UC_ARM64_REG_X7, UC_ARM64_REG_SP,
                                 UC_ARM64_REG_LR, UC_ARM64_REG_PC, UC_ARM64_REG_TPIDR_EL0)

PATH = "/Users/YOURNAME/pppp-dig/libgqipcsdk.so"
blob = open(PATH, "rb").read()
ef = ELFFile(open(PATH, "rb"))
syms = {}
for s in ef.get_section_by_name(".dynsym").iter_symbols():
    if s.entry.st_value:
        syms[s.name] = s.entry.st_value

STACK = 0x40000000
SCRATCH = 0x50000000
STUB = 0x5000F000
TPIDR = 0x60000000

uc = Uc(UC_ARCH_ARM64, UC_MODE_LITTLE_ENDIAN)
uc.mem_map(0, 0x100000)
uc.mem_map(0x100000, 0xF0000)
for seg in ef.iter_segments():
    if seg.header.p_type == "PT_LOAD":
        va = seg.header.p_vaddr
        data = seg.data()
        uc.mem_write(va, data)
uc.mem_map(STACK, 0x100000)
uc.mem_map(SCRATCH, 0x100000)
uc.mem_map(TPIDR, 0x1000)
uc.mem_write(TPIDR + 0x28, struct.pack("<Q", 0x1122334455667788))
uc.reg_write(UC_ARM64_REG_TPIDR_EL0, TPIDR)

# relocations: JUMP_SLOT/GLOB_DAT -> stub or symbol; RELATIVE -> addend
stub_of = {}
dyn = ef.get_section_by_name(".dynamic")
for sec_name in (".rela.plt", ".rela.dyn"):
    sec = ef.get_section_by_name(sec_name)
    if not sec:
        continue
    symtab = ef.get_section_by_name(".dynsym")
    for rel in sec.iter_relocations():
        off = rel.entry.r_offset
        typ = rel.entry.r_info_type
        sidx = rel.entry.r_info_sym
        name = symtab.get_symbol(sidx).name if sidx else ""
        if typ == 1027:  # RELATIVE
            uc.mem_write(off, struct.pack("<Q", rel.entry.r_addend & 0xFFFFFFFFFFFFFFFF))
        elif typ in (1025, 1026):  # GLOB_DAT, JUMP_SLOT
            if name in syms and sidx and symtab.get_symbol(sidx).entry.st_value:
                uc.mem_write(off, struct.pack("<Q", symtab.get_symbol(sidx).entry.st_value))
            elif name == "__stack_chk_guard":
                uc.mem_write(off, struct.pack("<Q", TPIDR + 0x28))
            else:
                if name not in stub_of:
                    stub_of[name] = STUB + len(stub_of) * 16
                    uc.mem_write(stub_of[name], struct.pack("<I", 0xD65F03C0))
                uc.mem_write(off, struct.pack("<Q", stub_of[name]))

captured = []
rand_vals = iter([0x12345678, 0x9ABCDEF0, 0x0BADF00D, 0x0D15EA5E])


def rd(addr, n):
    return bytes(uc.mem_read(addr, n))


def cstr(addr):
    out = b""
    while True:
        b = rd(addr + len(out), 1)
        if b == b"\0":
            return out
        out += b


def emulate_import(name):
    x0 = uc.reg_read(UC_ARM64_REG_X0)
    x1 = uc.reg_read(UC_ARM64_REG_X1)
    x2 = uc.reg_read(UC_ARM64_REG_X2)
    lr = uc.reg_read(UC_ARM64_REG_LR)
    ret = 0
    if name == "strncpy":
        src = cstr(x1)
        n = x2
        data = src[:n].ljust(n, b"\0")
        uc.mem_write(x0, data)
        ret = x0
    elif name == "memset":
        uc.mem_write(x0, bytes([x1 & 0xFF]) * x2)
        ret = x0
    elif name in ("memcpy", "memmove", "__memcpy_chk", "__memmove_chk"):
        uc.mem_write(x0, rd(x1, x2))
        ret = x0
    elif name == "strlen":
        ret = len(cstr(x0))
    elif name == "strnlen":
        s = b""
        while len(s) < x1:
            b = rd(x0 + len(s), 1)
            if b == b"\0":
                break
            s += b
        ret = len(s)
    elif name == "rand":
        ret = next(rand_vals)
    elif name == "inet_pton":
        parts = cstr(x1).decode().split(".")
        uc.mem_write(x2, bytes(int(p) for p in parts))
        ret = 1
    elif name in ("pthread_mutex_lock", "pthread_mutex_unlock"):
        ret = 0
    elif name == "sendto":
        ret = x2
    elif name == "gettimeofday":
        uc.mem_write(x0, struct.pack("<QQ", 1700000000, 0))
        ret = 0
    elif name == "__errno":
        ret = SCRATCH + 0xF00
    else:
        print(f"  [emu] unhandled import {name} -> 0")
    uc.reg_write(UC_ARM64_REG_X0, ret)
    uc.reg_write(UC_ARM64_REG_PC, lr)


SEND_ADDR = syms.get("_Z17cs2_TCPNBSkt_SendiPKhi")


SNPRINTF_WRAPPER = 0x63380


def hook(uc_, address, size, _):
    if address == SNPRINTF_WRAPPER:
        x0 = uc.reg_read(UC_ARM64_REG_X0)
        x2 = uc.reg_read(UC_ARM64_REG_X2)
        x3 = uc.reg_read(UC_ARM64_REG_X3)
        x4 = uc.reg_read(UC_ARM64_REG_X4)
        fmt = cstr(x2)
        if fmt == b"%02X%02X":
            out = ("%02X%02X" % (x3 & 0xFF, x4 & 0xFF)).encode()
            uc.mem_write(x0, out + b"\0")
            uc.reg_write(UC_ARM64_REG_X0, len(out))
        else:
            uc.mem_write(x0, fmt + b"\0")
            uc.reg_write(UC_ARM64_REG_X0, len(fmt))
        uc.reg_write(UC_ARM64_REG_PC, uc.reg_read(UC_ARM64_REG_LR))
        return
    if address == SEND_ADDR:
        x1 = uc.reg_read(UC_ARM64_REG_X1)
        x2 = uc.reg_read(UC_ARM64_REG_X2)
        captured.append(rd(x1, x2 & 0xFFFF))
        uc.emu_stop()
        return
    for name, addr in stub_of.items():
        if address == addr:
            emulate_import(name)
            return


uc.hook_add(UC_HOOK_CODE, hook)

SP0 = STACK + 0x80000


def call(addr, args, stack_args=b""):
    uc.reg_write(UC_ARM64_REG_SP, SP0)
    if stack_args:
        uc.mem_write(SP0, stack_args)
    regs = [UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2, UC_ARM64_REG_X3,
            UC_ARM64_REG_X4, UC_ARM64_REG_X5, UC_ARM64_REG_X6, UC_ARM64_REG_X7]
    for r, v in zip(regs, args):
        uc.reg_write(r, v)
    uc.reg_write(UC_ARM64_REG_LR, 0xDEAD000)
    try:
        uc.emu_start(addr, 0xDEAD000, count=200000)
    except Exception as e:
        print(f"  [emu] stopped: {e}")


def put_str(s, addr):
    b = s.encode() if isinstance(s, str) else s
    uc.mem_write(addr, b + b"\0")
    return addr


# 1) build a sockaddr_cs2 the SDK's own way
sa_buf = SCRATCH + 0x1000
set_sa = syms.get("_Z18cs2_SA_SetSockAddriPKctP12sockaddr_cs2")
print("cs2_SA_SetSockAddr @", hex(set_sa) if set_sa else None)
if set_sa:
    call(set_sa, [2, put_str("192.168.1.X", SCRATCH + 0x2000), 54321, sa_buf])
    print("sockaddr_cs2 built by SDK:", rd(sa_buf, 24).hex())

# 2) golden RlyReqDSK (PreReq form: flag2=0; body DSK empty)
key = put_str("FAKEDSK123456789", SCRATCH + 0x3000)
prefix = put_str("GQAB", SCRATCH + 0x3100)
check = put_str("XYZ9", SCRATCH + 0x3200)
empty = put_str("", SCRATCH + 0x3300)
p3 = SCRATCH + 0x3400
uc.mem_write(p3, bytes([5, 6, 1]))
outbuf = SCRATCH + 0x4000
proto = syms["_Z38cs2p2p_PPPP_Proto_TCPSend_TCPRlyReqDSKPKciS0_jS0_cPKhcPK12sockaddr_cs2S0_jPc"]
for flag2 in (0, 1):
    captured.clear()
    stack_args = struct.pack("<QQQQ", sa_buf, empty, 0, outbuf)
    call(proto, [key, 3, prefix, 123456, check, 0, p3, flag2], stack_args)
    if captured:
        pkt = captured[0]
        print(f"golden RlyReqDSK flag2={flag2}: {len(pkt)}B {pkt.hex()}")
    else:
        print(f"golden RlyReqDSK flag2={flag2}: NO SEND CAPTURED")
