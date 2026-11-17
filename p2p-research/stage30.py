#!/usr/bin/env python3
"""Stage 30: TCPRSStart variant (b) — OWN sockaddr in the +0x18 slot.

Stage 28 sent TCPRSStart (envelope form) carrying the RELAY node's
sockaddr from RlyRdy — the relay RST, the directory FIN'd. Variant
(b): the sockaddr slot carries OUR OWN advertised sockaddr instead
(the local endpoint of the directory connection — the address the
client is telling the session it can be reached at), mirroring how
RlyReq/devlgn_body advertise the local endpoint. Same golden-verified
builder (stage28.rsstart_inner, asserted below), same envelope.

Live flow (one run): RlyReq handshake -> RlyRdy (token), then
  1. enveloped TCPRSStart(own sockaddr) as first packet to relay node
  2. same packet on the directory connection (fallback)
If either draws frames, follow with DC Req + DC Cmd SNAPSHOT_IMG
(cmd 48) on that connection, stage14-style. Credentials are fetched
in-process and never printed or stored.
"""
import re
import socket
import struct
import sys
import time

sys.path.insert(0, "/Users/YOURNAME/pppp-dig")
import gqproto as gq
import stage13
import stage14
import stage28


def snapshot_followon(sock, reader, did, dsk, tag):
    print(f"[{tag}] data phase may be open — DC Req + SNAPSHOT cmd")
    try:
        sock.sendall(gq.wrap_tcp(stage14.dc_req(did, did), dsk))
        stage14.drain(reader, dsk, 8, tag + "-req")
        js = b'{"version":"1.0","ack":false,"seq":1,"cmd":48,"def":""}'
        sock.sendall(gq.wrap_tcp(stage14.dc_cmd(did, did, 0, js), dsk))
        stage14.drain(reader, dsk, 10, tag + "-cmd")
    except Exception as e:
        print(f"[{tag}] follow-on failed: {type(e).__name__}: {e}")


def main():
    stage28.selfcheck()
    data = stage13.fetch_p2p().get("data") or {}
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
    print(f"handshake: directory {srv}:443")
    ds = socket.create_connection((srv, 443), timeout=8)
    ds.settimeout(8)
    lip, lport = ds.getsockname()
    ds.sendall(gq.wrap_tcp(stage13.plain_rlyreq(did, lip, lport, 0), dsk))
    ds.sendall(gq.wrap_tcp(stage13.plain_rlyreq(did, lip, lport, 1), dsk))
    reader = gq.TCPFrameReader(ds)
    token = relay_sa = None
    end = time.time() + 20
    while time.time() < end and relay_sa is None:
        try:
            reader.sock.settimeout(max(0.1, end - time.time()))
            keyA, payload, ok = reader.read_frame()
        except socket.timeout:
            print("[dir] timeout waiting for RlyRdy")
            break
        except Exception as e:
            print(f"[dir] connection ended: {type(e).__name__}")
            break
        pkt = gq.unwrap_tcp_payload(payload, keyA, dsk)
        print(f"[dir] frame: {stage14.describe(pkt)} crc_ok={ok}")
        if pkt and pkt[1] == 0x52 and len(pkt) >= 52:
            token = struct.unpack(">I", pkt[0x18:0x1C])[0]
            relay_sa = pkt[0x1C:0x34]
            fam, rip, rport = stage28.parse_sockaddr(relay_sa)
            print(f"[dir] RlyRdy: session token acquired (4B), "
                  f"relay node {rip}:{rport} (family {fam})")
    if relay_sa is None:
        print("no RlyRdy — aborting before TCPRSStart")
        ds.close()
        return
    rport = rport if rport else 443
    own_sa = gq.pack_sockaddr(lip, lport).ljust(24, b"\0")
    print(f"[own] advertised sockaddr = directory connection local "
          f"endpoint {lip}:{lport}")
    env = gq.wrap_tcp(stage28.rsstart_inner(did, token, own_sa), dsk)
    opened = False

    # Primary: enveloped TCPRSStart(own sockaddr) to the relay node.
    try:
        rs = socket.create_connection((rip, rport), timeout=8)
        rs.settimeout(8)
        print(f"[relay] connected to {rip}:{rport}; sending TCPRSStart "
              f"with OWN sockaddr ({len(env)}B enveloped)")
        rs.sendall(env)
        rreader = gq.TCPFrameReader(rs)
        n = stage28.drain(rreader, dsk, 15, "relay")
        if n > 0:
            opened = True
            snapshot_followon(rs, rreader, did, dsk, "relay")
        rs.close()
    except Exception as e:
        print(f"[relay] connect/send failed: {type(e).__name__}: {e}")

    # Fallback: same packet on the directory connection.
    if not opened:
        print("[dir] fallback: sending TCPRSStart(own) on the "
              "directory connection")
        try:
            ds.sendall(env)
            n = stage28.drain(reader, dsk, 10, "dir")
            if n > 0:
                opened = True
                snapshot_followon(ds, reader, did, dsk, "dir")
        except Exception as e:
            print(f"[dir] fallback send failed: {type(e).__name__}: {e}")
    ds.close()
    print(f"stage30 done — data phase opened: {opened}")


if __name__ == "__main__":
    main()
