import struct
import sys

sys.path.insert(0, "/Users/YOURNAME/pppp-dig")
import emu1
import gqproto as gq

emu1.rand_vals = iter([0x12345678, 0x9ABCDEF0] * 16)
S = emu1.SCRATCH


def fresh_str(s, off):
    return emu1.put_str(s, S + off)


# --- DC Req ---
req = emu1.syms["_Z32cs2p2p_PPPP_Proto_DC_TCPSend_ReqPKciS0_jS0_S0_hjPc"]
# (key, sock, prefix, serial, check, name39, byte, overtime, out)
emu1.captured.clear()
emu1.call(req, [emu1.key, 3, emu1.prefix, 123456, emu1.check,
                fresh_str("NAME39-abcdefghijklmnopqrstuvwxyz0123456789", 0x5000), 0, 0],
          struct.pack("<Q", emu1.outbuf))
if emu1.captured:
    pkt = emu1.captured[0]
    inner = gq.unwrap_tcp_payload(pkt[8:], pkt[4:6], "FAKEDSK123456789")
    print("DC Req inner:", inner.hex(), flush=True)
else:
    print("DC Req: NO SEND", flush=True)

# --- DC Cmd ---
cmd = emu1.syms["_Z32cs2p2p_PPPP_Proto_DC_TCPSend_CmdPKciS0_jS0_S0_ttPKhjPc"]
data = b'{"version":"1.0","ack":false,"seq":1,"cmd":48,"def":"{}"}'
dbuf = S + 0x6000
emu1.uc.mem_write(dbuf, data)
emu1.captured.clear()
# (key, sock, prefix, serial, check, name39, channel, ?, stack: data, len?, out)
emu1.call(cmd, [emu1.key, 3, emu1.prefix, 123456, emu1.check,
                fresh_str("NAME39-abcdefghijklmnopqrstuvwxyz0123456789", 0x5100), 0, len(data)],
          struct.pack("<QQQ", dbuf, 0, emu1.outbuf))
if emu1.captured:
    pkt = emu1.captured[0]
    inner = gq.unwrap_tcp_payload(pkt[8:], pkt[4:6], "FAKEDSK123456789")
    print("DC Cmd inner:", inner.hex(), flush=True)
    print("DC Cmd data tail:", inner[76:], flush=True)
else:
    print("DC Cmd: NO SEND", flush=True)
