import struct
import sys

sys.path.insert(0, "/Users/YOURNAME/pppp-dig")
import emu1
from unicorn import UC_HOOK_CODE
from unicorn.arm64_const import UC_ARM64_REG_PC, UC_ARM64_REG_LR

emu1.rand_vals = iter([0x12345678, 0x9ABCDEF0] * 16)
proto = emu1.syms["_Z34cs2p2p_PPPP_Proto_TCPSend_TCPRSLgnPKciS0_jS0_ttttjPK12sockaddr_cs2jPc"]
uc = emu1.uc
events = []
stub_names = {v: k for k, v in emu1.stub_of.items()}
interesting = {0x6D780: "TCPSend_MSG", 0x6731C: "TCP_SEND_LEAF"}


def hook2(uc_, address, size, _):
    if address in stub_names:
        events.append(f"import {stub_names[address]}")
    elif address in interesting:
        events.append(interesting[address])


uc.hook_add(UC_HOOK_CODE, hook2)
emu1.captured.clear()
emu1.call(proto, [emu1.key, 3, emu1.prefix, 123456, emu1.check, 0x62, 0x55, 0x95],
          struct.pack("<QQQQQ", 0x21, 0xAABBCCDD, emu1.sa_buf, 0x11223344, emu1.outbuf))
print("captured:", len(emu1.captured))
print("events:", events[:30])
print("final PC:", hex(uc.reg_read(UC_ARM64_REG_PC)), "LR:", hex(uc.reg_read(UC_ARM64_REG_LR)))
