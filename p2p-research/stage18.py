#!/usr/bin/env python3
"""Stage 18: plain handshake + DC Cmd on EACH of the 3 servers.
The device may be registered on only one node."""
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
    js = b'{"version":"1.0","ack":false,"seq":1,"cmd":48,"def":""}'
    for i, srv in enumerate(servers):
        print(f"== server{i + 1} {srv} ==")
        s, reader, ok = stage15.handshake(srv, did, dsk)
        if ok:
            s.sendall(gq.wrap_tcp(stage14.dc_cmd(did, did, 0, js), dsk))
            stage15.read_frames(reader, dsk, 8, f"s{i + 1}")
        s.close()


if __name__ == "__main__":
    main()
