#!/usr/bin/env python3
"""Stage 28: TCPRSStart live test — the missing data-phase opener.

RE basis (2026-11-16 late, emu_rsstart2.py + disassembly of libgqipcsdk.so):
  Proto_TCPSend_TCPRSStart @0x6de7c builds a 52-byte inner packet
  (f1 52 00 30 + 48-byte st_cs2p2p_TCPRSStart) and hands it to
  Proto_TCPSend_MSG (standard TCP envelope, layer-1 key = DSK) when its
  trailing mode uint (uintC) is 0. uintC=1 suppresses the TCP send.
  Struct layout (Write/Read_TCPRSStart @0x6de04/0x6dd78 agree):
    +0x00 char[8]  DID part 1        +0x08 BE32  DID number
    +0x0C char[8]  DID part 3        +0x14 BE32  session token (free uint)
    +0x18 sockaddr_cs2 wire form (24 B)
  i.e. pack_uid(DID) + BE32 token + sockaddr — the same three values a
  RlyRdy (inbound 0x52) carries at the same offsets (token @+0x14,
  relay sockaddr @+0x18). Hypothesis: after the RlyReq handshake, the
  first packet to the RELAY NODE is TCPRSStart(uid, token from RlyRdy,
  relay sockaddr from RlyRdy). Every other first packet got RST in
  stages 14-27; RSStart was never tried.

This script golden-verifies its pure-Python builder against the SDK's
own emulated output BEFORE connecting, then runs the live flow once:
RlyReq handshake (directory) -> TCPRSStart (relay node; fallback: the
directory connection). Credentials are fetched in-process and never
printed or stored.
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

# Golden inner packet from Unicorn emulation of the SDK's own
# Proto_TCPSend_TCPRSStart (emu_rsstart2.py run A) with fake inputs:
# DID "FAKE-123456-ABCDE", token 0xAABBCCDD, sockaddr 192.168.1.X:54321.
GOLDEN_INNER = bytes.fromhex(
    "f1520030"
    "46414b4500000000" "0001e240"
    "4142434445000000" "aabbccdd"
    "000231d43201a8c0" + "00" * 16)


def rsstart_inner(did, token, relay_sa24):
    b = bytearray(48)
    b[0:20] = gq.pack_uid(did)
    b[0x14:0x18] = struct.pack(">I", token)
    b[0x18:0x30] = relay_sa24
    return b"\xf1\x52" + struct.pack(">H", 48) + bytes(b)


def selfcheck():
    sa = gq.pack_sockaddr("192.168.1.X", 54321).ljust(24, b"\0")
    got = rsstart_inner("FAKE-123456-ABCDE", 0xAABBCCDD, sa)
    assert got == GOLDEN_INNER, (
        f"golden mismatch:\n got {got.hex()}\n exp {GOLDEN_INNER.hex()}")
    print("golden self-check: PASS (builder byte-identical to SDK emulation)")


def parse_sockaddr(sa24):
    fam = struct.unpack(">H", sa24[0:2])[0]
    port = struct.unpack("<H", sa24[2:4])[0]
    ip = ".".join(str(b) for b in sa24[4:8][::-1])
    return fam, ip, port


def drain(reader, key, seconds, tag):
    """Log frames verbatim (describe + hex, no credential-bearing fields
    are ever in inbound frames beyond the DID echo in 0x52, whose hex we
    deliberately do not print)."""
    end = time.time() + seconds
    got = 0
    while time.time() < end:
        try:
            reader.sock.settimeout(max(0.1, end - time.time()))
            keyA, payload, ok = reader.read_frame()
        except socket.timeout:
            print(f"[{tag}] timeout — connection held open")
            break
        except Exception as e:
            print(f"[{tag}] connection ended: {type(e).__name__}")
            break
        pkt = gq.unwrap_tcp_payload(payload, keyA, key)
        got += 1
        print(f"[{tag}] frame: {stage14.describe(pkt)} crc_ok={ok}")
        if pkt and pkt[1] != 0x52:
            print(f"[{tag}]   inner hex: {pkt.hex()}")
    return got


def main():
    selfcheck()
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
            fam, rip, rport = parse_sockaddr(relay_sa)
            print(f"[dir] RlyRdy: session token acquired (4B), "
                  f"relay node {rip}:{rport} (family {fam})")
    if relay_sa is None:
        print("no RlyRdy — aborting before TCPRSStart")
        ds.close()
        return
    rs = rsstart_inner(did, token, relay_sa)
    env = gq.wrap_tcp(rs, dsk)
    # Primary: TCPRSStart as the first packet to the relay node.
    relay_ok = False
    try:
        rsock = socket.create_connection((rip, rport if rport else 443), timeout=8)
        rsock.settimeout(8)
        print(f"[relay] connected to {rip}:{rport if rport else 443}; "
              f"sending TCPRSStart (52B inner, {len(env)}B enveloped)")
        rsock.sendall(env)
        n = drain(gq.TCPFrameReader(rsock), dsk, 15, "relay")
        relay_ok = n > 0
        rsock.close()
    except Exception as e:
        print(f"[relay] connect/send failed: {type(e).__name__}: {e}")
    # Fallback (same session): TCPRSStart on the directory connection.
    if not relay_ok:
        print("[dir] fallback: sending TCPRSStart on the directory connection")
        try:
            ds.sendall(env)
            drain(reader, dsk, 10, "dir")
        except Exception as e:
            print(f"[dir] fallback send failed: {type(e).__name__}: {e}")
    ds.close()
    print("stage28 done")


if __name__ == "__main__":
    main()
