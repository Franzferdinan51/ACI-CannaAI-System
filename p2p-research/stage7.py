#!/usr/bin/env python3
"""Stage 7: corrected client flow per keyfinding.md.

- Envelope layer-1 key = DSK (getP2PInfo `key`).
- RlyReq body DSK field = EMPTY (session+0x194 is empty in the app flow;
  the DSK serves only as the PropEnc key).
- One connection: TCPRlyPreReqDSK (flag2=0) then TCPRlyReqDSK (flag2=1),
  then read frames (expect RlyReqAck 0x55).
Prints types/results only — never credential values.
"""
import json
import re
import socket
import struct
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


def rlyreq_body(did, local_ip, local_port, flag2, wi_blob=None):
    n = 92 if wi_blob is not None else 76
    b = bytearray(n)
    b[0:20] = gq.pack_uid(did)
    b[0x14:0x14 + 8] = gq.pack_sockaddr(local_ip, local_port)
    b[0x2C] = 0  # gNetInfo[3]
    b[0x2D:0x30] = bytes([5, 6, 1])
    b[0x30] = flag2
    # +0x34 DSK field: 24 zero bytes (empty in the app flow)
    if wi_blob is not None:
        b[0x4C:0x4C + 16] = wi_blob
    return bytes(b)


def run_sequence(server, did, dsk, lip, lport, wi_blob, label):
    print(f"[{label}] connect {server}:443")
    try:
        s = socket.create_connection((server, 443), timeout=8)
    except Exception as e:
        print(f"  connect failed: {e}")
        return False
    s.settimeout(6)
    lip2, lport2 = s.getsockname()
    pre = rlyreq_body(did, lip2, lport2, 0, wi_blob)
    pre_inner = bytes([0xF1, 0x57 if wi_blob is not None else 0x54]) + \
        struct.pack(">H", len(pre)) + pre
    req = rlyreq_body(did, lip2, lport2, 1, None)
    req_inner = b"\xf1\x54" + struct.pack(">H", len(req)) + req
    try:
        s.sendall(gq.wrap_tcp(pre_inner, dsk))
        print(f"  sent PreReq type=0x{pre_inner[1]:02x} len={len(pre_inner)}")
        s.sendall(gq.wrap_tcp(req_inner, dsk))
        print(f"  sent RlyReq type=0x54 len={len(req_inner)}")
        reader = gq.TCPFrameReader(s)
        got_any = False
        try:
            while True:
                keyA, payload, ok = reader.read_frame()
                pkt = gq.unwrap_tcp_payload(payload, keyA, dsk)
                got_any = True
                t = pkt[1] if len(pkt) > 1 else -1
                print(f"  frame: checkcrc_ok={ok} inner type=0x{t:02x} len={len(pkt)}")
                if t == 0x55 and len(pkt) >= 6:
                    print(f"    RlyReqAck result={pkt[4]} sub={pkt[5]}")
                elif len(pkt) > 4:
                    print(f"    body[:24]={pkt[4:28].hex()}")
        except socket.timeout:
            print(f"  (read timeout; got_any={got_any})")
        except Exception as e:
            print(f"  read end: {type(e).__name__}: {e}; got_any={got_any}")
        return got_any
    except Exception as e:
        print(f"  send failed: {type(e).__name__}: {e}")
        return False
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
    probe = socket.create_connection((srv, 443), timeout=8)
    lip, lport = probe.getsockname()
    probe.close()
    if run_sequence(srv, did, dsk, lip, lport, None, "plain PreReq+RlyReq"):
        return
    run_sequence(srv, did, dsk, lip, lport, b"\0" * 16, "DSKWI(zeros)+RlyReq")


if __name__ == "__main__":
    main()
