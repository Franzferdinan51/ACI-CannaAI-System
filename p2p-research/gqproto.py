"""GQ/CS2 PPCS fork protocol primitives — from devlgn-spec.md (phase 2 RE).

Pure stdlib. Tables from tables.json (extracted from libgqipcsdk.so).
No credentials live in this module; callers pass them in memory only.
"""
import socket
import struct
from functools import reduce

T = bytes.fromhex(
    "95e56197830da7f1d305958bdf136def07610d6d7f67172bc1b5130bdf"
    "8b493b7f07d3026d2f13c56d3dfb0d0b29e94f892fe3e90d836de507538b2595471f29")
SBOX = bytes.fromhex(
    "7c9ce84a13dedcb22f2123e4307b3d8cbc0b270c3cf79ae7087196009785ef"
    "c11fc4dba1c2ebd901faba3b05b81587832872d18b5ad6da9358feaacc6e1bf0a388ab43c00db5453"
    "84f502266207f075b14981d9ba72ab9a8cbf1fc4947063eb10e043a945eee541134dd4df9ecc7c9e3"
    "781a6f706ba4bda95dd5f8e5bb26af4237d8e1020aae5f1cc573094e6924906d12b319ad748a2940f"
    "52dbea559e0f479d24bce8982488425c6912ba2fb8fe9a6b09e3f65f603312eac0f952c5ced39b733"
    "6c567eb4a0fd7a815351868d9f77ff6a80dfe2bf10d775645776f355cdd0c818e6364162cf99f2324"
    "c67606192cad3ea637d16b68ed46835c3529d46441e17")
LUT = bytes.fromhex(
    "4959433db5bf6da347534f6165e371e9677f02030badb3892b2f35c16b8b9597"
    "11e5a70deff1050783fb9d3bc5c713171d1f2529d3df")


# ---------- InitString decode (classic PPCS, LUT-based) ----------
def decode_initstring(raw):
    if ":" in raw:
        raw = raw.split(":", 1)[0]
    raw = raw.upper()
    out = bytearray()
    for i in range(len(raw) // 2):
        running = 0x39
        for j in range(i):
            running ^= out[j]
        raw_n = (ord(raw[2 * i + 1]) + (ord(raw[2 * i]) << 4) + 0xAF) & 0xFF
        out.append((LUT[i % 0x36] ^ running ^ raw_n) & 0xFF)
    return bytes(out)


# ---------- CRCEnc / CRCDec (spec section 2) ----------
def _upd(s, ch):
    a, b, c, d = s
    return (T[((ch % a + b) & 7) * 8 + ((c % d + ch) & 7)],
            T[((ch % b + c) & 7) * 8 + ((d % a + ch) & 7)],
            T[((ch % c + d) & 7) * 8 + ((a % b + ch) & 7)],
            T[((ch % d + a) & 7) * 8 + ((b % c + ch) & 7)])


def _crc_state(key):
    s = (1, 3, 5, 7)
    if key:
        for ch in key:
            s = _upd(s, ch)
    return s


def crc_enc(data, key):
    s = _crc_state(key)
    out = bytearray()
    for p in data:
        C = p ^ s[0] ^ s[1] ^ s[2] ^ s[3]
        out.append(C)
        s = _upd(s, C)
    for _ in range(4):
        chk = s[0] ^ s[1] ^ s[2] ^ s[3] ^ 0x43
        out.append(chk)
        s = _upd(s, chk)
    return bytes(out)


def crc_dec(data, key):
    """Decrypt incl. trailer check. Returns plaintext or None if trailer bad."""
    if len(data) < 4:
        return None
    s = _crc_state(key)
    out = bytearray()
    for C in data:
        p = C ^ s[0] ^ s[1] ^ s[2] ^ s[3]
        out.append(p)
        s = _upd(s, C)
    if bytes(out[-4:]) != b"CCCC":
        return None
    return bytes(out[:-4])


# ---------- Proprietary cipher (spec section 3.1) ----------
def prop_key4(key):
    s = sum(key) & 0xFF
    return (s, (-s) & 0xFF, sum((b * 0xAB) >> 9 for b in key) & 0xFF,
            reduce(int.__xor__, key, 0))


def prop_enc(data, key):
    if not key or key[0] == 0:
        return bytes(data)
    K = prop_key4(key[:20])
    out = bytearray(len(data))
    if not data:
        return b""
    out[0] = SBOX[K[0]] ^ data[0]
    for i in range(1, len(data)):
        p = out[i - 1]
        out[i] = SBOX[(K[p & 3] + p) & 0xFF] ^ data[i]
    return bytes(out)


def prop_dec(data, key):
    if not key or key[0] == 0:
        return bytes(data)
    K = prop_key4(key[:20])
    out = bytearray(len(data))
    if not data:
        return b""
    out[0] = SBOX[K[0]] ^ data[0]
    for i in range(1, len(data)):
        p = data[i - 1]  # prev = ciphertext byte
        out[i] = SBOX[(K[p & 3] + p) & 0xFF] ^ data[i]
    return bytes(out)


# ---------- CheckCRC (spec section 3.2) ----------
def tcprelay_checkcrc(data):
    o0, o1, s1, s2 = 0x43, 0x53, 0x43, 0x53
    if not data:
        return bytes([o0, o1])
    i, j = 0, len(data) - 1
    while True:
        t = s1 ^ data[i]
        s1 = t ^ s2
        o0 = s1
        if i % 2 == 0:
            s2 = data[j] ^ t
            o1 = s2
        j -= 1
        i += 1
        if j == -1:
            break
    return bytes([o0, o1])


# ---------- Packing helpers (spec sections 1/5/6) ----------
def pack_uid(did):
    p, s, c = did.split("-")
    return (p.encode()[:7].ljust(8, b"\0") + struct.pack(">I", int(s)) +
            c.encode()[:7].ljust(8, b"\0"))


def pack_sockaddr(ip, port):
    return (struct.pack(">H", 2) + struct.pack("<H", port) +
            socket.inet_aton(ip)[::-1])


def devlgn_body(did, dsk, local_ip, local_port, netinfo3=0):
    b = bytearray(64)
    b[0:20] = pack_uid(did)
    b[0x14] = netinfo3
    b[0x15:0x18] = bytes([5, 6, 1])
    b[0x18:0x20] = pack_sockaddr(local_ip, local_port)
    b[0x28:0x28 + 24] = dsk.encode()[:23].ljust(24, b"\0")
    return bytes(b)


# ---------- TCP envelope (spec section 3) ----------
def wrap_tcp(inner, session_key, keyA=None):
    """Wrap an inner packet (SessionHeader+body) in the TCP outer envelope."""
    if keyA is None:
        import os
        keyA = os.urandom(2)
    layer1 = prop_enc(inner, session_key.encode() if session_key else b"")
    relay_key = ("%02X%02X" % (keyA[0], keyA[1])).encode()
    layer2 = prop_enc(layer1, relay_key)
    head = (struct.pack(">H", len(inner)) + b"\x68\x00" + keyA +
            tcprelay_checkcrc(layer2))
    return head + layer2


def unwrap_tcp_payload(payload, keyA, session_key):
    """Inverse of the two PropEnc layers for a received envelope payload.
    Returns inner packet bytes, or None if CheckCRC fails (checked by caller
    separately if desired)."""
    relay_key = ("%02X%02X" % (keyA[0], keyA[1])).encode()
    layer1 = prop_dec(payload, relay_key)
    return prop_dec(layer1, session_key.encode() if session_key else b"")


class TCPFrameReader:
    """Reads envelope frames from a TCP stream."""

    def __init__(self, sock):
        self.sock = sock
        self.buf = bytearray()

    def _fill(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("socket closed")
            self.buf.extend(chunk)

    def read_frame(self):
        """Returns (keyA, payload_bytes, checkcrc_ok)."""
        self._fill(8)
        length = struct.unpack(">H", self.buf[0:2])[0]
        if self.buf[2] != 0x68:
            raise ValueError("bad outer type 0x%02x" % self.buf[2])
        keyA = bytes(self.buf[4:6])
        crc = bytes(self.buf[6:8])
        self._fill(8 + length)
        payload = bytes(self.buf[8:8 + length])
        del self.buf[:8 + length]
        ok = (tcprelay_checkcrc(payload) == crc)
        return keyA, payload, ok
