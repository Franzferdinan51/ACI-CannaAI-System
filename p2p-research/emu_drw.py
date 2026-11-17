import struct
import sys

sys.path.insert(0, "/Users/YOURNAME/pppp-dig")
import emu1
import gqproto as gq

emu1.rand_vals = iter([0x12345678, 0x9ABCDEF0] * 16)
S = emu1.SCRATCH
drw = emu1.syms["_Z23cs2p2p_PPPP_DRW_TCPSendPKcihtPKhtjPc"]
data = b"HELLO-DRW-PAYLOAD-1234567890"
dbuf = S + 0x7000
emu1.uc.mem_write(dbuf, data)
# signature: (key, sock, ?, channel?, data, len, overtime, out) — try w2=0, w3=channel 0
for chan in (0, 1):
    emu1.captured.clear()
    emu1.call(drw, [emu1.key, 3, 0, chan, dbuf, len(data), 0, emu1.outbuf])
    if emu1.captured:
        pkt = emu1.captured[0]
        inner = gq.unwrap_tcp_payload(pkt[8:], pkt[4:6], "FAKEDSK123456789")
        print(f"DRW chan={chan} inner: {inner.hex()}", flush=True)
        print(f"   ascii: {inner!r}", flush=True)
    else:
        print(f"DRW chan={chan}: NO SEND", flush=True)
