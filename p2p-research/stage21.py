#!/usr/bin/env python3
"""Stage 21: data phase in the NoEncrypt envelope (PropEnc only,
zero keyA/CRC head fields) after the proven full-envelope handshake."""
import json
import os
import re
import socket
import struct
import sys
import time
import urllib.request

sys.path.insert(0, "/Users/YOURNAME/pppp-dig")
import gqproto as gq
import stage13
import stage14
import stage15
import stage16

CAM = stage13.CAM
BASE = stage13.BASE
OUTDIR = "/Users/YOURNAME/spectron-photos"


def fetch_p2p():
    tok = json.load(open("/Users/YOURNAME/.config/aci/token.json"))["user_id"]
    req = urllib.request.Request(
        BASE + "/api/ipc/getP2PInfo?devId=" + CAM,
        data=b"", method="POST", headers={"token": tok})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def wrap_ne(inner, key):
    payload = gq.prop_enc(inner, key.encode())
    return struct.pack(">H", len(payload)) + bytes([0x68, 0, 0, 0, 0, 0]) + payload


def read_ne(reader, dsk, seconds, tag):
    end = time.time() + seconds
    while time.time() < end:
        try:
            reader.sock.settimeout(max(0.1, end - time.time()))
            _keyA, payload, _ok = reader.read_frame()
        except socket.timeout:
            print(f"[{tag}] (timeout, still open)")
            return True
        except Exception as e:
            print(f"[{tag}] ended: {type(e).__name__}")
            return False
        # payload may be full-envelope or NoEncrypt; try NoEncrypt first
        pkt = gq.prop_dec(payload, dsk.encode())
        print(f"[{tag}] frame(ne-dec): {stage14.describe(pkt)}")
        if pkt[1] == 0xDC and len(pkt) > 76:
            print(f"[{tag}]   dc data: {pkt[76:240]!r}")
        if pkt[1] == 0xD0 and len(pkt) > 8:
            print(f"[{tag}]   drw data: {pkt[8:160]!r}")
        for m in re.finditer(rb"\xff\xd8\xff", pkt):
            fn = os.path.join(OUTDIR, f"p2p-frame-{int(time.time())}-{m.start()}.jpg")
            with open(fn, "wb") as f:
                f.write(pkt[m.start():])
            print(f"[{tag}]   JPEG MAGIC -> {fn}")
    return True


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
    js = b'{"version":"1.0","ack":false,"seq":1,"cmd":48,"def":""}'
    variants = [
        ("NE Alive", b"\xf1\xe0\x00\x00"),
        ("NE DC Cmd", stage14.dc_cmd(did, did, 0, js)),
        ("NE DRW(DC Cmd)", stage16.drw(0, 0, stage14.dc_cmd(did, did, 0, js))),
        ("NE DC Req", stage14.dc_req(did, did)),
    ]
    for label, pkt in variants:
        print(f"== {label} ==")
        s, reader, ok = stage15.handshake(srv, did, dsk)
        if ok:
            s.sendall(wrap_ne(pkt, dsk))
            read_ne(reader, dsk, 9, label)
        s.close()


if __name__ == "__main__":
    main()
