#!/usr/bin/env python3
"""Stage 16: DRW-wrapped payloads after the proven handshake.
Payload candidates: DC Cmd packet / bare JSON / DC Req packet."""
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

CAM = stage13.CAM
BASE = stage13.BASE


def drw(channel, dtype, data):
    body = bytes([0xD1, channel]) + struct.pack(">H", dtype) + data
    return b"\xf1\xd0" + struct.pack(">H", len(data) + 4) + body


def main():
    data = stage15.fetch_p2p().get("data") or {}
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
        ("DRW(DC Cmd)", drw(0, 0, stage14.dc_cmd(did, did, 0, js))),
        ("DRW(bare JSON)", drw(0, 0, js)),
        ("DRW(DC Req)", drw(0, 0, stage14.dc_req(did, did))),
        ("DRW(DC Cmd) chan1", drw(1, 0, stage14.dc_cmd(did, did, 0, js))),
    ]
    for label, pkt in variants:
        print(f"== {label} ==")
        s, reader, ok = stage15.handshake(srv, did, dsk)
        if ok:
            s.sendall(gq.wrap_tcp(pkt, dsk))
            stage15.read_frames(reader, dsk, 8, label)
        s.close()


if __name__ == "__main__":
    main()
