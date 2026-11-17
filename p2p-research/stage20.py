#!/usr/bin/env python3
"""Stage 20: two-hop flow — directory RlyReq -> RlyRdy (relay node +
token) -> NEW connection to relay node -> TCPRSLgn -> DC Cmd SNAPSHOT."""
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


def tcprslgn(did, token, relay_ip, lip, lport):
    b = bytearray(56)
    b[0:4] = b"\xf1\x50\x00\x38"
    b[4:24] = gq.pack_uid(did)
    b[0x18:0x1C] = token
    for i, octet in enumerate(relay_ip.split(".")):
        b[0x1C + i * 2:0x1E + i * 2] = struct.pack(">H", int(octet))
    b[0x24:0x24 + 8] = gq.pack_sockaddr(lip, lport)
    return bytes(b)


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
            print(f"[{tag}]   dc data: {pkt[76:220]!r}")
        if pkt[1] == 0xD0 and len(pkt) > 8:
            print(f"[{tag}]   drw data: {pkt[8:140]!r}")
        for m in re.finditer(rb"\xff\xd8\xff", pkt):
            fn = os.path.join(OUTDIR, f"p2p-frame-{int(time.time())}-{m.start()}.jpg")
            with open(fn, "wb") as f:
                f.write(pkt[m.start():])
            print(f"[{tag}]   JPEG MAGIC -> {fn}")
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
    s, reader, ok = stage15.handshake(servers[0], did, dsk)
    if not ok:
        print("handshake failed")
        return
    # re-read the RlyRdy body: handshake() printed it; redo handshake inline
    # (handshake consumed it) — instead: fresh handshake capturing the body
    s.close()
    s = socket.create_connection((servers[0], 443), timeout=8)
    s.settimeout(8)
    lip, lport = s.getsockname()
    reader = gq.TCPFrameReader(s)
    s.sendall(gq.wrap_tcp(stage13.plain_rlyreq(did, lip, lport, 0), dsk))
    s.sendall(gq.wrap_tcp(stage13.plain_rlyreq(did, lip, lport, 1), dsk))
    rly = None
    end = time.time() + 8
    while time.time() < end:
        keyA, payload, ok2 = reader.read_frame()
        pkt = gq.unwrap_tcp_payload(payload, keyA, dsk)
        if pkt[1] == 0x52:
            rly = pkt
            break
    if rly is None:
        print("no RlyRdy")
        return
    body = rly[4:]
    token = body[0x14:0x18]
    relay_ip = ".".join(str(x) for x in body[0x1C:0x20][::-1])
    print(f"RlyRdy: relay={relay_ip}:443 token={token.hex()}")
    s.close()
    # hop 2: relay node login
    rs = socket.create_connection((relay_ip, 443), timeout=8)
    rs.settimeout(8)
    rlip, rlport = rs.getsockname()
    rreader = gq.TCPFrameReader(rs)
    rs.sendall(gq.wrap_tcp(tcprslgn(did, token, relay_ip, rlip, rlport), dsk))
    frames = read_frames(rreader, dsk, 8, "rslgn")
    js = b'{"version":"1.0","ack":false,"seq":1,"cmd":48,"def":""}'
    rs.sendall(gq.wrap_tcp(stage14.dc_cmd(did, did, 0, js), dsk))
    read_frames(rreader, dsk, 12, "cmd")
    rs.close()


if __name__ == "__main__":
    main()
