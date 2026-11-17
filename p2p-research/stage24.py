#!/usr/bin/env python3
"""Stage 24 (final probe batch):
A. handshake -> second RlyReq pair on the same connection.
B. handshake -> TCPRSLgn on the DIRECTORY connection.
"""
import json
import re
import socket
import sys
import time
import urllib.request

sys.path.insert(0, "/Users/YOURNAME/pppp-dig")
import gqproto as gq
import stage13
import stage14
import stage15
import stage20

CAM = stage13.CAM
BASE = stage13.BASE


def fetch_p2p():
    tok = json.load(open("/Users/YOURNAME/.config/aci/token.json"))["user_id"]
    req = urllib.request.Request(
        BASE + "/api/ipc/getP2PInfo?devId=" + CAM,
        data=b"", method="POST", headers={"token": tok})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


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

    print("== A: second RlyReq pair after RlyRdy ==")
    s, reader, ok = stage15.handshake(srv, did, dsk)
    if ok:
        lip, lport = s.getsockname()
        s.sendall(gq.wrap_tcp(stage13.plain_rlyreq(did, lip, lport, 0), dsk))
        s.sendall(gq.wrap_tcp(stage13.plain_rlyreq(did, lip, lport, 1), dsk))
        stage15.read_frames(reader, dsk, 6, "A")
    s.close()

    print("== B: TCPRSLgn on directory connection ==")
    # handshake capturing RlyRdy fields
    s = socket.create_connection((srv, 443), timeout=8)
    s.settimeout(8)
    lip, lport = s.getsockname()
    reader = gq.TCPFrameReader(s)
    s.sendall(gq.wrap_tcp(stage13.plain_rlyreq(did, lip, lport, 0), dsk))
    s.sendall(gq.wrap_tcp(stage13.plain_rlyreq(did, lip, lport, 1), dsk))
    token = relay_ip = None
    end = time.time() + 8
    while time.time() < end:
        keyA, payload, ok2 = reader.read_frame()
        pkt = gq.unwrap_tcp_payload(payload, keyA, dsk)
        if pkt[1] == 0x52:
            body = pkt[4:]
            token = body[0x14:0x18]
            relay_ip = ".".join(str(x) for x in body[0x1C:0x20][::-1])
            break
    print(f"RlyRdy: relay={relay_ip} token={token.hex() if token else None}")
    if token:
        s.sendall(gq.wrap_tcp(stage20.tcprslgn(did, token, relay_ip, lip, lport), dsk))
        stage15.read_frames(reader, dsk, 8, "B")
    s.close()


if __name__ == "__main__":
    main()
