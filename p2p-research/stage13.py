#!/usr/bin/env python3
"""Stage 13: NON-DSK branch — TCPRlyPreReq/TCPRlyReq (inner 0x53, 52-byte
body per the golden emulation) with layer-1 key = DSK and = empty."""
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


def plain_rlyreq(did, lip, lport, flag2):
    b = bytearray(52)
    b[0:20] = gq.pack_uid(did)
    b[0x14:0x14 + 8] = gq.pack_sockaddr(lip, lport)
    b[0x1C] = 0
    b[0x2D:0x30] = bytes([5, 6, 1])
    b[0x30] = flag2
    return b"\xf1\x53" + struct.pack(">H", 52) + bytes(b)


def attempt(server, did, key, label):
    try:
        s = socket.create_connection((server, 443), timeout=8)
    except Exception as e:
        print(f"[{label}] connect failed: {e}")
        return False
    s.settimeout(6)
    lip, lport = s.getsockname()
    try:
        s.sendall(gq.wrap_tcp(plain_rlyreq(did, lip, lport, 0), key))
        s.sendall(gq.wrap_tcp(plain_rlyreq(did, lip, lport, 1), key))
        reader = gq.TCPFrameReader(s)
        try:
            while True:
                keyA, payload, ok = reader.read_frame()
                pkt = gq.unwrap_tcp_payload(payload, keyA, key)
                t = pkt[1] if len(pkt) > 1 else -1
                print(f"[{label}] FRAME type=0x{t:02x} len={len(pkt)} crc_ok={ok}")
                if t == 0x55 and len(pkt) >= 6:
                    print(f"[{label}]   Ack result={pkt[4]} sub={pkt[5]}")
                return True
        except socket.timeout:
            print(f"[{label}] timeout (held open)")
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
    if attempt(srv, did, dsk, "plain 0x53 key=DSK"):
        return
    attempt(srv, did, "", "plain 0x53 key=empty")


if __name__ == "__main__":
    main()
