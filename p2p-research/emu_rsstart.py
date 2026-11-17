import struct
import sys

sys.path.insert(0, "/Users/YOURNAME/pppp-dig")
import emu1
import gqproto as gq

emu1.rand_vals = iter([0x12345678, 0x9ABCDEF0] * 16)
proto = emu1.syms["_Z36cs2p2p_PPPP_Proto_TCPSend_TCPRSStartPKciS0_jS0_jPK12sockaddr_cs2jPc"]
print("TCPRSStart @", hex(proto))
# (key, sock, prefix, serial, check, uint, sockaddr*, uint, out)
emu1.captured.clear()
emu1.call(proto, [emu1.key, 3, emu1.prefix, 123456, emu1.check, 0xAABBCCDD],
          struct.pack("<QQQ", emu1.sa_buf, 0, emu1.outbuf))
if emu1.captured:
    pkt = emu1.captured[0]
    inner = gq.unwrap_tcp_payload(pkt[8:], pkt[4:6], "FAKEDSK123456789")
    print("TCPRSStart inner:", inner.hex(), flush=True)
else:
    print("TCPRSStart: NO SEND", flush=True)
