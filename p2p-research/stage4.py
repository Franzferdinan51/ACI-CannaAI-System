#!/usr/bin/env python3
"""Spectron PPPP phase 2, stage 4: TCP DevLgn to a directory server.

Fetches getP2PInfo in-process (credentials never printed / never leave the
process), builds the DevLgn packet per devlgn-spec.md, wraps it in the TCP
envelope, sends it to a directory server on TCP 443, and parses what comes
back (HDR relay-name list 0x6F, or plain DevLgnAck 0x13 as a crypto canary).
"""
import json
import re
import socket
import sys
import urllib.request

sys.path.insert(0, "/Users/YOURNAME/pppp-dig")
import gqproto as gq

CAM = "YOUR_CAMERA_DEV_ID"
BASE = "https://www.acinfinityserver.com"


def fetch_p2p():
    tok = json.load(open("/Users/YOURNAME/.config/aci/token.json"))["user_id"]
    req = urllib.request.Request(
        BASE + "/api/ipc/getP2PInfo?devId=" + CAM,
        data=b"", method="POST", headers={"token": tok})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def pick_fields(data):
    did = initstr = None
    for v in data.values():
        if isinstance(v, str) and re.fullmatch(r"[A-Z]{3,8}-\d{3,8}-[A-Z0-9]{3,8}", v):
            did = v
        if (isinstance(v, str) and len(v) >= 20
                and set(v.split(":", 1)[0]) <= set("ABCDEFGHIJKLMNOP")
                and len(v.split(":", 1)[0]) % 2 == 0):
            initstr = v
    return did, data.get("key"), data.get("crcKey"), initstr


def attempt(server, did, dsk, crckey, inner_type, netinfo3=0, timeout=10):
    print(f"  -> {server}:443 inner type 0x{inner_type:02x} netinfo3={netinfo3}")
    s = socket.create_connection((server, 443), timeout=timeout)
    s.settimeout(timeout)
    lip, lport = s.getsockname()
    body = gq.devlgn_body(did, dsk, lip, lport, netinfo3)
    inner = bytes([0xF1, inner_type, 0x00, 0x44]) + gq.crc_enc(body, crckey.encode())
    wire = gq.wrap_tcp(inner, did)
    s.sendall(wire)
    reader = gq.TCPFrameReader(s)
    got = []
    try:
        while True:
            keyA, payload, crc_ok = reader.read_frame()
            inner_pkt = gq.unwrap_tcp_payload(payload, keyA, did)
            got.append(inner_pkt)
            t = inner_pkt[1] if len(inner_pkt) > 1 else None
            print(f"     frame: inner len={len(inner_pkt)} type=0x{t:02x} "
                  f"checkcrc_ok={crc_ok}")
            if t == 0x6F:
                parse_hdr(inner_pkt, did)
                break
            if t == 0x13:
                plain = gq.crc_dec(inner_pkt[4:], crckey.encode())
                if plain is None:
                    print("     DevLgnAck: CRCDec trailer FAILED")
                else:
                    print(f"     DevLgnAck: result byte = {plain[0]} "
                          f"(body len {len(plain)})")
                break
    except (socket.timeout, TimeoutError):
        print("     (timeout waiting for more frames)")
    except Exception as e:
        print(f"     read error: {type(e).__name__}: {e}")
    finally:
        s.close()
    return got


def parse_hdr(pkt, did):
    body = pkt[4:]
    n = int.from_bytes(body[0x14:0x16], "big")
    names = body[0x28:0x28 + n].decode("ascii", "replace")
    print(f"     HDR relay list ({n} bytes): {names}")
    echo = body[0:8].rstrip(b"\0").decode("ascii", "replace")
    print(f"     DID echo prefix={echo!r} serial={int.from_bytes(body[8:12], 'big')}")
    return names.split(",") if names else []


def main():
    resp = fetch_p2p()
    data = resp.get("data") or {}
    did, dsk, crckey, initstr = pick_fields(data)
    print("fields ok:", bool(did), bool(dsk), bool(crckey), bool(initstr))
    if not all([did, dsk, crckey, initstr]):
        print("STOP: missing fields")
        return
    servers = gq.decode_initstring(initstr).decode("ascii").strip(",").split(",")
    print("directory servers:", servers)
    for srv in servers:
        print(f"[HDR attempt] {srv}")
        got = attempt(srv, did, dsk, crckey, 0x6E)
        if got and any(p[1] == 0x6F for p in got if len(p) > 1):
            return
    for srv in servers:
        print(f"[plain canary] {srv}")
        got = attempt(srv, did, dsk, crckey, 0x16)
        if got:
            return


if __name__ == "__main__":
    main()
