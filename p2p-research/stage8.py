#!/usr/bin/env python3
"""Stage 8: DevLgn with the corrected crypto (empty-key CRCEnc, DSK
envelope key) + RlyReq flag sweep. The directory definitely processes
DevLgn (the camera's Listen flow sends it here). Prints results only.
"""
import json
import re
import socket
import struct
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


def devlgn(server, did, dsk, body_dsk, inner_type, label):
    try:
        s = socket.create_connection((server, 443), timeout=8)
    except Exception as e:
        print(f"[{label}] connect failed: {e}")
        return
    s.settimeout(6)
    lip, lport = s.getsockname()
    b = bytearray(64)
    b[0:20] = gq.pack_uid(did)
    b[0x14] = 0
    b[0x15:0x18] = bytes([5, 6, 1])
    b[0x18:0x20] = gq.pack_sockaddr(lip, lport)
    if body_dsk:
        b[0x28:0x28 + 24] = dsk.encode()[:23].ljust(24, b"\0")
    inner = bytes([0xF1, inner_type, 0x00, 0x44]) + gq.crc_enc(bytes(b), b"")
    try:
        s.sendall(gq.wrap_tcp(inner, dsk))
        print(f"[{label}] sent DevLgn type=0x{inner_type:02x} bodyDSK={body_dsk}")
        reader = gq.TCPFrameReader(s)
        try:
            while True:
                keyA, payload, ok = reader.read_frame()
                pkt = gq.unwrap_tcp_payload(payload, keyA, dsk)
                t = pkt[1] if len(pkt) > 1 else -1
                print(f"  frame: checkcrc_ok={ok} inner type=0x{t:02x} len={len(pkt)}")
                if t == 0x6F:
                    n = int.from_bytes(pkt[4 + 0x14:4 + 0x16], "big")
                    names = pkt[4 + 0x28:4 + 0x28 + n].decode("ascii", "replace")
                    print(f"    RELAY NAMES: {names}")
                elif t == 0x13:
                    plain = gq.crc_dec(pkt[4:], b"")
                    print(f"    DevLgnAck result={plain[0] if plain else 'CRCDec fail'}")
                elif len(pkt) > 4:
                    print(f"    body[:32]={pkt[4:36].hex()}")
        except socket.timeout:
            print("  (read timeout)")
        except Exception as e:
            print(f"  read end: {type(e).__name__}: {e}")
    except Exception as e:
        print(f"[{label}] send failed: {e}")
    finally:
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
    srv = servers[0]
    devlgn(srv, did, dsk, True, 0x6E, "HDR DevLgn, bodyDSK=key")
    devlgn(srv, did, dsk, False, 0x6E, "HDR DevLgn, bodyDSK=empty")
    devlgn(srv, did, dsk, True, 0x16, "plain DevLgn, bodyDSK=key")


if __name__ == "__main__":
    main()
