#!/usr/bin/env python3
"""Stage 26: DevLgn FIRST (HDR form), then RlyReq pair, then DC Cmd —
testing the 'RlyReq is a lookup, DevLgn is the auth' theory."""
import json
import os
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


def devlgn_hdr(did, dsk, lip, lport, crc_key):
    body = gq.devlgn_body(did, dsk, lip, lport)
    return b"\xf1\x6e\x00\x44" + gq.crc_enc(body, crc_key)


def attempt(srv, did, dsk, crc_key, label):
    print(f"== DevLgn (crc_key={'empty' if not crc_key else 'crcKey'}) ==")
    s = socket.create_connection((srv, 443), timeout=8)
    s.settimeout(8)
    lip, lport = s.getsockname()
    reader = gq.TCPFrameReader(s)
    s.sendall(gq.wrap_tcp(devlgn_hdr(did, dsk, lip, lport, crc_key), dsk))
    frames = stage15.read_frames(reader, dsk, 5, label)
    if frames is False:
        s.close()
        return
    s.sendall(gq.wrap_tcp(stage13.plain_rlyreq(did, lip, lport, 0), dsk))
    s.sendall(gq.wrap_tcp(stage13.plain_rlyreq(did, lip, lport, 1), dsk))
    stage15.read_frames(reader, dsk, 5, label + "-rly")
    js = b'{"version":"1.0","ack":false,"seq":1,"cmd":48,"def":""}'
    try:
        s.sendall(gq.wrap_tcp(stage14.dc_cmd(did, did, 0, js), dsk))
    except Exception as e:
        print(f"[{label}] cmd send failed: {type(e).__name__}")
        s.close()
        return
    stage15.read_frames(reader, dsk, 10, label + "-cmd")
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
    crckey = data.get("crcKey") or ""
    servers = gq.decode_initstring(initstr).decode("ascii").strip(",").split(",")
    attempt(servers[0], did, dsk, "", "empty")
    attempt(servers[0], did, dsk, crckey, "crcKey")


if __name__ == "__main__":
    main()
