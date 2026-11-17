#!/usr/bin/env python3
"""Stage 29: TCPRSStart variant (a) — RAW non-envelope form live test.

RE basis (emu_rsstart3.py, Unicorn emulation of libgqipcsdk.so):
  Proto_Send_TCPRSStart @0x6ed30 builds the same 52B inner packet as
  the TCP sender and hands it to cs2p2p_SendMessage, which emits
  prop_enc(inner, key) — 52 bytes, no envelope header / CheckCRC /
  keyA layer — via sendto() to a caller-supplied sockaddr_in.
  Emulated wire bytes with fake inputs are byte-identical to
  gqproto.prop_enc(inner, key); the golden is asserted below before
  any connection is made.

Live flow (one run): RlyReq handshake -> RlyRdy (token + relay
sockaddr), then the raw form, in order:
  1. raw bytes over a fresh TCP connection to the relay node
  2. raw bytes as a UDP datagram to the relay node (the raw sender's
     native transport — SendMessage is sendto-based)
  3. raw bytes on the (already handshaken) directory connection
Any reply is logged verbatim (DID-bearing hex withheld, per stage28).
If a framed-TCP attempt opens the data phase, follow with DC Req +
DC Cmd SNAPSHOT_IMG (cmd 48) on that connection, stage14-style.
Credentials are fetched in-process and never printed or stored.
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

# Golden raw wire bytes from Unicorn emulation of the SDK's own
# Proto_Send_TCPRSStart + SendMessage (emu_rsstart3.py experiment A)
# with fake inputs: DID "FAKE-123456-ABCDE", token 0xAABBCCDD,
# sockaddr 192.168.1.X:54321, key "FAKEDSK123456789".
GOLDEN_RAW = bytes.fromhex(
    "2666c61f44d787255bb700d7cccf69eda670060ba6326bff3e8cf685a630ed33"
    "72f7e1245274225ed23c274e12a7e495b700d7cc")


def selfcheck():
    got = gq.prop_enc(stage28.GOLDEN_INNER, b"FAKEDSK123456789")
    assert got == GOLDEN_RAW, (
        f"golden mismatch:\n got {got.hex()}\n exp {GOLDEN_RAW.hex()}")
    print("golden self-check: PASS (prop_enc builder byte-identical "
          "to SDK emulation of Proto_Send_TCPRSStart)")


def analyze(buf, dsk_b, did, tag):
    """Interpret a raw reply buffer without leaking the DID in hex."""
    if not buf:
        print(f"[{tag}] no bytes received")
        return False
    print(f"[{tag}] received {len(buf)}B")
    if len(buf) >= 8 and buf[2] == 0x68:
        # framed TCP envelope(s)
        off = 0
        any_pkt = False
        while off + 8 <= len(buf):
            ln = struct.unpack(">H", buf[off:off + 2])[0]
            keyA = buf[off + 4:off + 6]
            payload = buf[off + 8:off + 8 + ln]
            if len(payload) < ln:
                break
            pkt = gq.unwrap_tcp_payload(payload, keyA, dsk_b)
            print(f"[{tag}] framed reply: {stage14.describe(pkt)}")
            if pkt and did.encode() not in pkt and pkt[1] != 0x52:
                print(f"[{tag}]   inner hex: {pkt.hex()}")
            any_pkt = True
            off += 8 + ln
        return any_pkt
    pkt = gq.prop_dec(buf, dsk_b)
    if pkt[:1] == b"\xf1":
        print(f"[{tag}] prop_dec -> {stage14.describe(pkt)}")
        if did.encode() in pkt:
            print(f"[{tag}]   (hex withheld — packet carries device id)")
        else:
            print(f"[{tag}]   inner hex: {pkt.hex()}")
        return True
    print(f"[{tag}] prop_dec yields no f1 packet; first bytes type "
          f"unknown (hex withheld pending identification)")
    return False


def raw_drain_tcp(sock, seconds, tag):
    sock.settimeout(seconds)
    buf = b""
    try:
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                print(f"[{tag}] peer closed (FIN)")
                break
            buf += chunk
    except socket.timeout:
        print(f"[{tag}] timeout — connection held open")
    except Exception as e:
        print(f"[{tag}] connection ended: {type(e).__name__}")
    return buf


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
    dsk_b = dsk.encode() if isinstance(dsk, str) else dsk
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
    raw = gq.prop_enc(stage28.rsstart_inner(did, token, relay_sa), dsk_b)
    assert len(raw) == 52
    opened = False

    # Attempt 1: raw over fresh TCP to the relay node.
    try:
        rs = socket.create_connection((rip, rport), timeout=8)
        print(f"[relay-tcp] connected to {rip}:{rport}; sending raw "
              f"TCPRSStart ({len(raw)}B, prop_enc form)")
        rs.sendall(raw)
        buf = raw_drain_tcp(rs, 12, "relay-tcp")
        if buf:
            opened = analyze(buf, dsk_b, did, "relay-tcp")
            if opened:
                snapshot_followon(rs, gq.TCPFrameReader(rs), did, dsk,
                                  "relay-tcp")
        rs.close()
    except Exception as e:
        print(f"[relay-tcp] connect/send failed: {type(e).__name__}: {e}")

    # Attempt 2: raw as a UDP datagram to the relay node (native
    # transport of Proto_Send_* / SendMessage).
    if not opened:
        try:
            us = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            us.settimeout(10)
            print(f"[relay-udp] sending raw TCPRSStart datagram to "
                  f"{rip}:{rport}")
            us.sendto(raw, (rip, rport))
            try:
                data_u, addr = us.recvfrom(4096)
                print(f"[relay-udp] reply from {addr[0]}:{addr[1]}")
                opened = analyze(data_u, dsk_b, did, "relay-udp")
            except socket.timeout:
                print("[relay-udp] no reply within 10s")
            us.close()
        except Exception as e:
            print(f"[relay-udp] failed: {type(e).__name__}: {e}")

    # Attempt 3: raw on the directory connection (post-handshake).
    if not opened:
        print("[dir] sending raw TCPRSStart on the directory connection")
        try:
            ds.sendall(raw)
            buf = raw_drain_tcp(ds, 10, "dir")
            if buf:
                opened = analyze(buf, dsk_b, did, "dir")
        except Exception as e:
            print(f"[dir] send failed: {type(e).__name__}: {e}")
    ds.close()
    print(f"stage29 done — data phase opened: {opened}")


if __name__ == "__main__":
    main()
