#!/usr/bin/env python3
"""Stage 14: full session — plain RlyReq handshake (proven), then DC Req,
then DC Cmd SNAPSHOT_IMG; log every frame; extract any JPEG."""
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


def dc_packet(did, subtype, name, second_len):
    prefix, serial, check = did.split("-")
    p = bytearray(76)
    p[4] = 0xD1
    p[5] = subtype
    p[6:8] = struct.pack(">H", second_len)
    p[8:8 + 39] = name.encode()[:39].ljust(39, b"\0")
    p[0x30:0x30 + 7] = prefix.encode()[:7].ljust(7, b"\0")
    p[0x38:0x3C] = struct.pack(">I", int(serial))
    p[0x3C:0x3C + 7] = check.encode()[:7].ljust(7, b"\0")
    return p


def dc_req(did, name):
    p = dc_packet(did, 0x01, name, 8)
    return b"\xf1\xdc" + struct.pack(">H", 72) + bytes(p[4:])


def dc_cmd(did, name, channel, payload):
    p = dc_packet(did, 0x11, name, len(payload) + 8)
    p[0x44:0x46] = struct.pack(">H", channel)
    p[0x46:0x48] = struct.pack(">H", len(payload))
    body = bytes(p[4:]) + payload
    return b"\xf1\xdc" + struct.pack(">H", len(body)) + body


def describe(pkt):
    if len(pkt) < 4:
        return f"short len={len(pkt)}"
    t = pkt[1]
    if t == 0x55:
        return f"RlyReqAck result={pkt[4]} sub={pkt[5]}"
    if t == 0xDC and len(pkt) >= 6:
        return f"DC subtype=0x{pkt[5]:02x} len={len(pkt)}"
    if t == 0xD0:
        return f"DRW len={len(pkt)} chan_byte={pkt[5] if len(pkt) > 5 else '?'}"
    return f"type=0x{t:02x} len={len(pkt)}"


def drain(reader, key, seconds, tag):
    end = time.time() + seconds
    frames = []
    while time.time() < end:
        try:
            reader.sock.settimeout(max(0.1, end - time.time()))
            keyA, payload, ok = reader.read_frame()
        except socket.timeout:
            break
        except Exception as e:
            print(f"[{tag}] connection ended: {type(e).__name__}")
            break
        pkt = gq.unwrap_tcp_payload(payload, keyA, key)
        frames.append(pkt)
        print(f"[{tag}] frame: {describe(pkt)} crc_ok={ok}")
        if pkt[1] == 0xDC and len(pkt) > 76:
            body = pkt[76:]
            print(f"[{tag}]   dc data: {body[:120]!r}")
        if pkt[1] == 0xD0 and len(pkt) > 8:
            print(f"[{tag}]   drw data[:80]: {pkt[8:88]!r}")
        # JPEG hunt
        for m in re.finditer(rb"\xff\xd8\xff", pkt):
            fn = os.path.join(OUTDIR, f"p2p-frame-{int(time.time())}-{m.start()}.jpg")
            with open(fn, "wb") as f:
                f.write(pkt[m.start():])
            print(f"[{tag}]   JPEG MAGIC at {m.start()} -> saved {fn} ({len(pkt) - m.start()}B)")
    return frames


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
    s = socket.create_connection((srv, 443), timeout=8)
    s.settimeout(8)
    lip, lport = s.getsockname()
    reader = gq.TCPFrameReader(s)
    s.sendall(gq.wrap_tcp(stage13.plain_rlyreq(did, lip, lport, 0), dsk))
    s.sendall(gq.wrap_tcp(stage13.plain_rlyreq(did, lip, lport, 1), dsk))
    frames = drain(reader, dsk, 6, "rly")
    if not any(f[1] == 0x55 and f[4] == 0 for f in frames):
        print("no successful RlyReqAck; aborting")
        return
    print("relay session up; sending DC Req")
    s.sendall(gq.wrap_tcp(dc_req(did, did), dsk))
    drain(reader, dsk, 8, "req")
    for i, deffrag in enumerate(['""', '"{}"']):
        js = ('{"version":"1.0","ack":false,"seq":%d,"cmd":48,"def":%s}'
              % (i + 1, deffrag)).encode()
        print(f"sending SNAPSHOT cmd def={deffrag}")
        s.sendall(gq.wrap_tcp(dc_cmd(did, did, 0, js), dsk))
        drain(reader, dsk, 10, f"cmd{i + 1}")
    s.close()


if __name__ == "__main__":
    main()
