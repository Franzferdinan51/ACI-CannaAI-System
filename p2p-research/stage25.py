#!/usr/bin/env python3
"""Stage 25 (final relay batch): TCPRSLgn to the relay node in raw /
empty-key / token-key envelope variants."""
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
import stage20
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


def probe(relay_ip, label, blob, dsk):
    try:
        s = socket.create_connection((relay_ip, 443), timeout=8)
    except Exception as e:
        print(f"[{label}] connect failed: {type(e).__name__}")
        return
    s.settimeout(8)
    s.sendall(blob)
    try:
        data = s.recv(4096)
        print(f"[{label}] recv {len(data)}B: {data[:48].hex()}")
        if data:
            print(f"[{label}]   as full-env dec: "
                  f"{stage14.describe(gq.unwrap_tcp_payload(data[8:], data[4:6], dsk)) if len(data) > 8 else '-'}")
    except socket.timeout:
        print(f"[{label}] silent, still open")
    except Exception as e:
        print(f"[{label}] ended: {type(e).__name__}")
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
    servers = gq.decode_initstring(initstr).decode("ascii").strip(",").split(",")
    token, relay_ip = stage23.get_rlyrdy(servers[0], did, dsk)
    print(f"relay node: {relay_ip}")
    lip = "192.168.1.X"
    inner = stage20.tcprslgn(did, token, relay_ip, lip, 50000)
    probe(relay_ip, "raw inner", inner, dsk)
    probe(relay_ip, "empty-key env", gq.wrap_tcp(inner, ""), dsk)
    probe(relay_ip, "token-hex-key env", gq.wrap_tcp(inner, token.hex()), dsk)


if __name__ == "__main__":
    main()
