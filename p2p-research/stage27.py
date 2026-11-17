#!/usr/bin/env python3
"""Stage 27 (final probe): UDP data plane. After a TCP RlyRdy, send UDP
datagrams (DC Cmd / DRW / Alive; raw, PropEnc, TCP-envelope payload
forms) to the relay node and directory IPs on port 443; listen for
replies."""
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
import stage16
import stage23

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
    token, relay_ip = stage23.get_rlyrdy(servers[0], did, dsk)
    print(f"relay node: {relay_ip}")
    js = b'{"version":"1.0","ack":false,"seq":1,"cmd":48,"def":""}'
    dccmd = stage14.dc_cmd(did, did, 0, js)
    forms = [
        ("raw DC Cmd", dccmd),
        ("propenc DC Cmd", gq.prop_enc(dccmd, dsk.encode())),
        ("raw DRW", stage16.drw(0, 0, js)),
        ("propenc DRW", gq.prop_enc(stage16.drw(0, 0, js), dsk.encode())),
        ("raw Alive", b"\xf1\xe0\x00\x00"),
        ("propenc Alive", gq.prop_enc(b"\xf1\xe0\x00\x00", dsk.encode())),
    ]
    targets = [(relay_ip, 443), (servers[0], 443)]
    u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    u.bind(("0.0.0.0", 0))
    u.settimeout(2.0)
    for tip, tport in targets:
        for label, blob in forms:
            u.sendto(blob, (tip, tport))
            try:
                resp, addr = u.recvfrom(65536)
                print(f"[{tip} {label}] REPLY {len(resp)}B from {addr}: {resp[:40].hex()}")
                dec = gq.prop_dec(resp, dsk.encode())
                print(f"   propdec: {stage14.describe(dec)}")
            except socket.timeout:
                print(f"[{tip} {label}] no reply")
    u.close()


if __name__ == "__main__":
    main()
