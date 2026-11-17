#!/usr/bin/env python3
"""Stage 22: simultaneous 3-server handshake (faithful to Connect_Do),
then DC Cmd SNAPSHOT on all three connections."""
import json
import os
import re
import select
import socket
import struct
import sys
import time
import urllib.request

sys.path.insert(0, "/Users/YOURNAME/pppp-dig")
import gqproto as gq
import stage13
import stage14

CAM = stage13.CAM
BASE = stage13.BASE
OUTDIR = "/Users/YOURNAME/spectron-photos"


def fetch_p2p():
    tok = json.load(open("/Users/YOURNAME/.config/aci/token.json"))["user_id"]
    req = urllib.request.Request(
        BASE + "/api/ipc/getP2PInfo?devId=" + CAM,
        data=b"", method="POST", headers={"token": tok})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


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
    conns = {}
    for i, srv in enumerate(servers):
        s = socket.create_connection((srv, 443), timeout=8)
        s.setblocking(False)
        lip, lport = s.getsockname()
        s.sendall(gq.wrap_tcp(stage13.plain_rlyreq(did, lip, lport, 0), dsk))
        s.sendall(gq.wrap_tcp(stage13.plain_rlyreq(did, lip, lport, 1), dsk))
        conns[s] = {"idx": i, "buf": bytearray(), "rdy": False}
        print(f"conn{i}: handshake sent to {srv}")
    js = b'{"version":"1.0","ack":false,"seq":1,"cmd":48,"def":""}'
    cmd_pkt = gq.wrap_tcp(stage14.dc_cmd(did, did, 0, js), dsk)
    sent_cmd = False
    end = time.time() + 25
    while time.time() < end and conns:
        r, _, _ = select.select(list(conns), [], [], 1.0)
        for s in r:
            try:
                data_in = s.recv(65536)
            except BlockingIOError:
                continue
            except Exception as e:
                print(f"conn{conns[s]['idx']}: recv error {type(e).__name__}")
                del conns[s]
                continue
            if not data_in:
                print(f"conn{conns[s]['idx']}: CLOSED by peer")
                del conns[s]
                continue
            c = conns[s]
            c["buf"] += data_in
            # parse frames
            while len(c["buf"]) >= 8:
                ln = struct.unpack(">H", c["buf"][0:2])[0]
                if len(c["buf"]) < 8 + ln:
                    break
                frame = bytes(c["buf"][8:8 + ln])
                keyA = bytes(c["buf"][4:6])
                del c["buf"][:8 + ln]
                pkt = gq.unwrap_tcp_payload(frame, keyA, dsk)
                print(f"conn{c['idx']}: frame {stage14.describe(pkt)}")
                if pkt[1] == 0x52:
                    c["rdy"] = True
                if pkt[1] == 0xDC and len(pkt) > 76:
                    print(f"   dc data: {pkt[76:240]!r}")
                for m in re.finditer(rb"\xff\xd8\xff", pkt):
                    fn = os.path.join(OUTDIR, f"p2p-frame-{int(time.time())}.jpg")
                    with open(fn, "wb") as f:
                        f.write(pkt[m.start():])
                    print(f"   JPEG MAGIC -> {fn}")
        if not sent_cmd and conns and all(c["rdy"] for c in conns.values()):
            print("all RlyRdy received; sending DC Cmd on all conns")
            for s in list(conns):
                try:
                    s.sendall(cmd_pkt)
                except Exception as e:
                    print(f"conn{conns[s]['idx']}: send failed {e}")
            sent_cmd = True
    for s in list(conns):
        s.close()


if __name__ == "__main__":
    main()
