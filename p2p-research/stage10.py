#!/usr/bin/env python3
"""Stage 10: corrected PreReq+RlyReq sequence against ALL THREE directory
servers + a bogus-DID control on server 1 (distinguishes packet-level
reject from DID-level reject)."""
import json
import re
import socket
import sys
import urllib.request

sys.path.insert(0, "/Users/YOURNAME/pppp-dig")
import gqproto as gq
import stage7

CAM = stage7.CAM
BASE = stage7.BASE


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
    bogus = did[:-1] + ("A" if did[-1] != "A" else "B")
    for i, srv in enumerate(servers):
        stage7.run_sequence(srv, did, dsk, None, None, None, f"server{i + 1} real DID")
    stage7.run_sequence(servers[0], bogus, dsk, None, None, None,
                        "server1 BOGUS DID control")


if __name__ == "__main__":
    main()
