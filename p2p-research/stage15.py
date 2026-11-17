#!/usr/bin/env python3
"""Stage 15: session variants after the proven handshake.
A: DC Req immediately after RlyRdy.
B: Alive, then DC Cmd SNAPSHOT directly (no Req).
C: DC Req with name39 = Android app-id style.
"""
import json
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

CAM = stage13.CAM
BASE = stage13.BASE


def fetch_p2p():
    tok = json.load(open("/Users/YOURNAME/.config/aci/token.json"))["user_id"]
    req = urllib.request.Request(
        BASE + "/api/ipc/getP2PInfo?devId=" + CAM,
        data=b"", method="POST", headers={"token": tok})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def handshake(srv, did, dsk):
    s = socket.create_connection((srv, 443), timeout=8)
    s.settimeout(8)
    lip, lport = s.getsockname()
    reader = gq.TCPFrameReader(s)
    s.sendall(gq.wrap_tcp(stage13.plain_rlyreq(did, lip, lport, 0), dsk))
    s.sendall(gq.wrap_tcp(stage13.plain_rlyreq(did, lip, lport, 1), dsk))
    ok = False
    end = time.time() + 8
    while time.time() < end:
        try:
            keyA, payload, cok = reader.read_frame()
        except Exception as e:
            print(f"  handshake read end: {type(e).__name__}")
            break
        pkt = gq.unwrap_tcp_payload(payload, keyA, dsk)
        print(f"  hs frame: {stage14.describe(pkt)}")
        if pkt[1] == 0x52:
            print(f"    RlyRdy body: {pkt[4:].hex()}")
            ok = True
            break
    return s, reader, ok


def read_frames(reader, dsk, seconds, tag):
    end = time.time() + seconds
    got = []
    while time.time() < end:
        try:
            reader.sock.settimeout(max(0.1, end - time.time()))
            keyA, payload, ok = reader.read_frame()
        except socket.timeout:
            print(f"[{tag}] (timeout, still open)")
            break
        except Exception as e:
            print(f"[{tag}] ended: {type(e).__name__}")
            break
        pkt = gq.unwrap_tcp_payload(payload, keyA, dsk)
        got.append(pkt)
        print(f"[{tag}] frame: {stage14.describe(pkt)} crc_ok={ok}")
        if pkt[1] == 0xDC and len(pkt) > 76:
            print(f"[{tag}]   dc data: {pkt[76:200]!r}")
        if pkt[1] == 0xD0 and len(pkt) > 8:
            print(f"[{tag}]   drw data: {pkt[8:120]!r}")
    return got


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

    print("== variant A: DC Req immediately ==")
    s, reader, ok = handshake(srv, did, dsk)
    if ok:
        s.sendall(gq.wrap_tcp(stage14.dc_req(did, did), dsk))
        read_frames(reader, dsk, 8, "A")
    s.close()

    print("== variant B: Alive + DC Cmd direct ==")
    s, reader, ok = handshake(srv, did, dsk)
    if ok:
        s.sendall(gq.wrap_tcp(b"\xf1\xe0\x00\x00", dsk))
        js = b'{"version":"1.0","ack":false,"seq":1,"cmd":48,"def":""}'
        s.sendall(gq.wrap_tcp(stage14.dc_cmd(did, did, 0, js), dsk))
        read_frames(reader, dsk, 10, "B")
    s.close()

    print("== variant C: DC Req name=Android_id ==")
    s, reader, ok = handshake(srv, did, dsk)
    if ok:
        s.sendall(gq.wrap_tcp(stage14.dc_req(did, "Android_0123456789abcdef"), dsk))
        read_frames(reader, dsk, 8, "C")
    s.close()


if __name__ == "__main__":
    main()
