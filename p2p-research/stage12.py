#!/usr/bin/env python3
"""Stage 12: replicate the app's full Connect_Do order in one process:
UDP probe phase (cs2pppp session machinery sends Hello / CheckDevice /
P2PReq for the DID to all 3 servers), then immediately the TCP
PreReq+RlyReq sequence on each server.
"""
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


def udp_probe(did, servers):
    """Send the classic CS2 UDP probe packets for the DID (unencrypted
    session-header packets, as cs2pppp does pre-session)."""
    uid = gq.pack_uid(did)
    pkts = [
        b"\xf1\x00\x00\x00",                       # HELLO
        b"\xf1\x20\x00\x14" + uid,                 # CHECK_DEVICE_STATUS (P2PReq-ish probe)
        b"\xf1\x30\x00\x14" + uid,                 # P2P_REQ
    ]
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0.5)
    for srv in servers:
        for p in pkts:
            try:
                s.sendto(p, (srv, 32108))
            except Exception as e:
                print(f"udp send to {srv} failed: {e}")
    try:
        while True:
            d, a = s.recvfrom(2048)
            print(f"udp reply from {a}: {d[:24].hex()}")
    except socket.timeout:
        pass
    s.close()
    print("udp probe sent (replies above if any)")


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
    udp_probe(did, servers)
    for i, srv in enumerate(servers):
        if stage7.run_sequence(srv, did, dsk, None, None, None, f"tcp server{i + 1}"):
            return
    print("still rejected after UDP probe")


if __name__ == "__main__":
    main()
