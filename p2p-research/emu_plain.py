import struct
import sys

sys.path.insert(0, "/Users/YOURNAME/pppp-dig")
import emu1
import gqproto as gq

emu1.rand_vals = iter([0x12345678, 0x9ABCDEF0] * 8)
proto = emu1.syms["_Z35cs2p2p_PPPP_Proto_TCPSend_TCPRlyReqPKciS0_jS0_cPKhcPK12sockaddr_cs2jPc"]
for flag2 in (0, 1):
    emu1.captured.clear()
    emu1.call(proto, [emu1.key, 3, emu1.prefix, 123456, emu1.check, 0, emu1.p3, flag2],
              struct.pack("<QQQ", emu1.sa_buf, 0, emu1.outbuf))
    print("flag2", flag2, "captured", len(emu1.captured), flush=True)
    if emu1.captured:
        pkt = emu1.captured[0]
        inner = gq.unwrap_tcp_payload(pkt[8:], pkt[4:6], "FAKEDSK123456789")
        print("inner:", inner.hex(), flush=True)
