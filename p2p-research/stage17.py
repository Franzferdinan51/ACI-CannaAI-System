#!/usr/bin/env python3
"""Stage 17 (control): handshake, then send NOTHING for 20s; timestamp
every frame/close to learn whether the session dies on its own."""
import socket
import sys
import time

sys.path.insert(0, "/Users/YOURNAME/pppp-dig")
import gqproto as gq
import stage13
import stage14
import stage15


def main():
    data = stage15.fetch_p2p().get("data") or {}
    did = initstr = None
    for v in data.values():
        if isinstance(v, str) and len(v.split("-")) == 3:
            did = v
        if isinstance(v, str) and len(v) >= 20 and ":" not in v and len(v) % 2 == 0 \
                and set(v) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"):
            initstr = v
    dsk = data.get("key")
    import gqproto
    servers = gqproto.decode_initstring(initstr).decode("ascii").strip(",").split(",")
    srv = servers[0]
    s = socket.create_connection((srv, 443), timeout=8)
    s.settimeout(3)
    lip, lport = s.getsockname()
    reader = gq.TCPFrameReader(s)
    t0 = time.time()
    s.sendall(gq.wrap_tcp(stage13.plain_rlyreq(did, lip, lport, 0), dsk))
    s.sendall(gq.wrap_tcp(stage13.plain_rlyreq(did, lip, lport, 1), dsk))
    print(f"t={time.time() - t0:.1f} sent RlyReq pair")
    while time.time() - t0 < 22:
        try:
            keyA, payload, ok = reader.read_frame()
            pkt = gq.unwrap_tcp_payload(payload, keyA, dsk)
            print(f"t={time.time() - t0:.1f} frame: {stage14.describe(pkt)}")
        except socket.timeout:
            print(f"t={time.time() - t0:.1f} (alive, no data)")
        except Exception as e:
            print(f"t={time.time() - t0:.1f} CLOSED: {type(e).__name__}")
            break
    s.close()


if __name__ == "__main__":
    main()
