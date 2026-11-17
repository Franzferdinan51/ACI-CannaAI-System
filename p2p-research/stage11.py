#!/usr/bin/env python3
"""Stage 11: matrix over the two unsolved body variables:
- gNetInfo[3] flag byte (0 swept already; try 1..5)
- DSKWI blob = WAN sockaddr_in (16B: family LE, port BE, IPv4, zeros)
Sequence per attempt: PreReq (flag2=0) then RlyReq (flag2=1), key=DSK,
body DSK field empty.
"""
import json
import re
import socket
import struct
import sys
import urllib.request

sys.path.insert(0, "/Users/YOURNAME/pppp-dig")
import gqproto as gq
import stage7

CAM = stage7.CAM
BASE = stage7.BASE


def fetch_p2p():
    tok = json.load(open("/Users/YOURNAME/.config/aci/token.json"))["user_id"]
    req = urllib.request.Request(
        BASE + "/api/ipc/getP2PInfo?devId=" + CAM,
        data=b"", method="POST", headers={"token": tok})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def rlyreq(did, lip, lport, flag2, natflag, wi_blob=None):
    n = 92 if wi_blob is not None else 76
    b = bytearray(n)
    b[0:20] = gq.pack_uid(did)
    b[0x14:0x14 + 8] = gq.pack_sockaddr(lip, lport)
    b[0x2C] = natflag
    b[0x2D:0x30] = bytes([5, 6, 1])
    b[0x30] = flag2
    if wi_blob is not None:
        b[0x4C:0x4C + 16] = wi_blob
    t = 0x57 if wi_blob is not None else 0x54
    return bytes([0xF1, t]) + struct.pack(">H", n) + bytes(b)


def attempt(server, did, dsk, natflag, wi_blob, label):
    try:
        s = socket.create_connection((server, 443), timeout=8)
    except Exception as e:
        print(f"[{label}] connect failed: {e}")
        return False
    s.settimeout(6)
    lip, lport = s.getsockname()
    if wi_blob is not None:
        wi_blob = wi_blob(lip, lport)
    try:
        s.sendall(gq.wrap_tcp(rlyreq(did, lip, lport, 0, natflag, wi_blob), dsk))
        s.sendall(gq.wrap_tcp(rlyreq(did, lip, lport, 1, natflag, None), dsk))
        reader = gq.TCPFrameReader(s)
        try:
            while True:
                keyA, payload, ok = reader.read_frame()
                pkt = gq.unwrap_tcp_payload(payload, keyA, dsk)
                t = pkt[1] if len(pkt) > 1 else -1
                print(f"[{label}] FRAME type=0x{t:02x} len={len(pkt)} crc_ok={ok}")
                if t == 0x55 and len(pkt) >= 6:
                    print(f"[{label}]   RlyReqAck result={pkt[4]} sub={pkt[5]}")
                return True
        except socket.timeout:
            print(f"[{label}] timeout (no close!)")
            return True
        except Exception as e:
            print(f"[{label}] closed ({type(e).__name__})")
            return False
    finally:
        s.close()


def main():
    data = fetch_p2p().get("data") or {}
    did = initstr = None
    for v in data.values():
        if isinstance(v, str) and re.fullmatch(r"[A-Z]{3,8}-\d{3,8}-[A-Z0-9]{3,8}", v):
            did = v
        if (isinstance(v, str) and len(v) >= 20
                and set(v.split(":", 1)[0]) <= set("ABCDEFGHIJKLMNOP")
                and len(v.split(":", 1)[0]) % 2 == 0):
            initstr = v
    dsk = data.get("key")
    servers = gq.decode_initstring(initstr).decode("ascii").strip(",").split(",")
    srv = servers[0]
    wan = urllib.request.urlopen("https://api.ipify.org", timeout=15).read().decode()
    print(f"WAN IP learned (not printed per policy beyond need): {wan.count('.') == 3}")

    def blob(_lip, lport):
        return struct.pack("<H", 2) + struct.pack(">H", lport) + \
            socket.inet_aton(wan) + b"\0" * 8

    for flag in (1, 2, 3, 4, 5):
        if attempt(srv, did, dsk, flag, None, f"plain flag={flag}"):
            return
    for flag in (0, 1, 4):
        if attempt(srv, did, dsk, flag, blob, f"DSKWI flag={flag}"):
            return
    print("matrix exhausted")


if __name__ == "__main__":
    main()
