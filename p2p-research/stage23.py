#!/usr/bin/env python3
"""Stage 23: relay-node experiments.
1. Plain RlyReq handshake directly against the relay node from RlyRdy.
2. TCPRSLgn to the relay node in NoEncrypt envelope.
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
import stage15
import stage20
import stage21

CAM = stage13.CAM
BASE = stage13.BASE


def fetch_p2p():
    tok = json.load(open("/Users/YOURNAME/.config/aci/token.json"))["user_id"]
    req = urllib.request.Request(
        BASE + "/api/ipc/getP2PInfo?devId=" + CAM,
        data=b"", method="POST", headers={"token": tok})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def get_rlyrdy(srv, did, dsk):
    s = socket.create_connection((srv, 443), timeout=8)
    s.settimeout(8)
    lip, lport = s.getsockname()
    reader = gq.TCPFrameReader(s)
    s.sendall(gq.wrap_tcp(stage13.plain_rlyreq(did, lip, lport, 0), dsk))
    s.sendall(gq.wrap_tcp(stage13.plain_rlyreq(did, lip, lport, 1), dsk))
    end = time.time() + 8
    while time.time() < end:
        keyA, payload, ok = reader.read_frame()
        pkt = gq.unwrap_tcp_payload(payload, keyA, dsk)
        if pkt[1] == 0x52:
            body = pkt[4:]
            token = body[0x14:0x18]
            relay_ip = ".".join(str(x) for x in body[0x1C:0x20][::-1])
            s.close()
            return token, relay_ip
    s.close()
    return None, None


def try_read(reader, dsk, tag, seconds=6):
    end = time.time() + seconds
    while time.time() < end:
        try:
            reader.sock.settimeout(max(0.1, end - time.time()))
            keyA, payload, ok = reader.read_frame()
        except socket.timeout:
            print(f"[{tag}] (timeout, open)")
            return
        except Exception as e:
            print(f"[{tag}] ended: {type(e).__name__}")
            return
        pkt = gq.unwrap_tcp_payload(payload, keyA, dsk)
        print(f"[{tag}] frame: {stage14.describe(pkt)}")


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
    token, relay_ip = get_rlyrdy(servers[0], did, dsk)
    print(f"relay node: {relay_ip}, token: {token.hex() if token else None}")

    print("== RlyReq handshake directly to relay node ==")
    try:
        s = socket.create_connection((relay_ip, 443), timeout=8)
        s.settimeout(8)
        lip, lport = s.getsockname()
        reader = gq.TCPFrameReader(s)
        s.sendall(gq.wrap_tcp(stage13.plain_rlyreq(did, lip, lport, 0), dsk))
        s.sendall(gq.wrap_tcp(stage13.plain_rlyreq(did, lip, lport, 1), dsk))
        try_read(reader, dsk, "relay-hs")
        s.close()
    except Exception as e:
        print(f"relay-hs connect/send failed: {type(e).__name__}: {e}")

    print("== TCPRSLgn NoEncrypt to relay node ==")
    try:
        s = socket.create_connection((relay_ip, 443), timeout=8)
        s.settimeout(8)
        lip, lport = s.getsockname()
        reader = gq.TCPFrameReader(s)
        s.sendall(stage21.wrap_ne(stage20.tcprslgn(did, token, relay_ip, lip, lport), dsk))
        try_read(reader, dsk, "rslgn-ne")
        s.close()
    except Exception as e:
        print(f"rslgn-ne connect/send failed: {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
