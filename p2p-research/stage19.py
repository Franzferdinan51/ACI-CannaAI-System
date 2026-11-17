#!/usr/bin/env python3
"""Stage 19: single-packet tolerance matrix — which first data packet
lets the session survive?"""
import socket
import struct
import sys
import time

sys.path.insert(0, "/Users/YOURNAME/pppp-dig")
import gqproto as gq
import stage13
import stage14
import stage15
import stage16


def probe(srv, did, dsk, label, pkt):
    s, reader, ok = stage15.handshake(srv, did, dsk)
    if not ok:
        print(f"[{label}] handshake failed")
        s.close()
        return
    if pkt is not None:
        s.sendall(gq.wrap_tcp(pkt, dsk))
    alive = True
    end = time.time() + 6
    while time.time() < end:
        try:
            reader.sock.settimeout(max(0.1, end - time.time()))
            keyA, payload, ok2 = reader.read_frame()
            p = gq.unwrap_tcp_payload(payload, keyA, dsk)
            print(f"[{label}] frame: {stage14.describe(p)}")
            if p[1] == 0xDC and len(p) > 76:
                print(f"[{label}]   dc data: {p[76:200]!r}")
            if p[1] == 0xD0 and len(p) > 8:
                print(f"[{label}]   drw data: {p[8:120]!r}")
        except socket.timeout:
            break
        except Exception:
            alive = False
            break
    print(f"[{label}] session {'SURVIVED' if alive else 'KILLED'}")
    s.close()


def main():
    data = stage15.fetch_p2p().get("data") or {}
    did = initstr = None
    for v in data.values():
        if isinstance(v, str) and len(v.split("-")) == 3 and len(v) == 17:
            did = v
        if isinstance(v, str) and len(v) >= 20 and ":" not in v and len(v) % 2 == 0 \
                and set(v) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"):
            initstr = v
    dsk = data.get("key")
    servers = gq.decode_initstring(initstr).decode("ascii").strip(",").split(",")
    srv = servers[0]
    js = b'{"version":"1.0","ack":false,"seq":1,"cmd":48,"def":""}'
    probe(srv, did, dsk, "alive-only", b"\xf1\xe0\x00\x00")
    probe(srv, did, dsk, "drw-empty-c0", stage16.drw(0, 0, b""))
    probe(srv, did, dsk, "drw-json-c0", stage16.drw(0, 0, js))
    probe(srv, did, dsk, "drw-json-c2", stage16.drw(2, 0, js))
    probe(srv, did, dsk, "drw-dccmd-c0", stage16.drw(0, 0, stage14.dc_cmd(did, did, 0, js)))


if __name__ == "__main__":
    main()
