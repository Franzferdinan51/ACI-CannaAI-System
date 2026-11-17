# Spectron 7 / GQ IPC SDK — TCP DevLgn packet spec (phase 2, thread A)

Static RE of `libgqipcsdk.so` (arm64, 635,840 B, md5 6440660136d3842199a5f24db014948e)
from the AC Infinity app. All offsets/addresses are file/vaddr in that binary.
Cross-validated against the open-source `cs2pppp` 0.2.11 Python implementation
of the same CS2 PPCS protocol family where noted. NO live traffic was sent.

## 0. Common framing

Every PPCS packet (UDP and TCP) starts with `st_cs2p2p_SessionHeader` (4 bytes),
written by `cs2p2p_PPPP_Proto_Write_Header` @0x68144, parsed by
`cs2p2p_PPPP_Proto_Read_Header` @0x68160 (rejects unless byte0 == 0xF1):

```
+0  u8    magic = 0xF1
+1  u8    message type
+2  u16BE payload length (bytes following this header)
```

TCP messages are carried by `cs2p2p_PPPP_Proto_TCPSend_MSG` @0x6d780 /
`Proto_TCPSend_MSG_NoEncrypt` @0x6fa08: the same 4-byte header precedes the
(possibly CRCEnc-encrypted) payload on the stream.

## 1. DevLgn request (device login, DSK variant)

### 1.1 Plaintext body — `st_cs2p2p_DevLgnWithDSK`, 64 bytes (0x40)

Written by `cs2p2p_PPPP_Proto_Write_DevLgnWithDSK` @0x6ccb4 (identical twin
@cs2p2p_cs2p2p_… @0x6e1cc). The non-DSK `st_cs2p2p_DevLgn` is the first 32 bytes
only (`Proto_Write_DevLgn` @0x68770, reader `Proto_Read_DevLgn` @0x6881c —
symmetric, confirms every field below).

```
off  size  field
0x00 8     DID prefix, ASCII, NUL-padded (strncpy n=7)      e.g. "GHBB"
0x08 4     DID serial, u32 BIG-ENDIAN (rev store)           atoi of DID middle segment
0x0c 8     DID check, ASCII, NUL-padded (strncpy n=7)       e.g. "ZKMNP"
0x14 1     flag byte (see §1.3)
0x15 3     constant {0x05, 0x06, 0x01} in the HDR/TCP path (see §1.3)
0x18 8     local sockaddr of the sending socket, wire form (see below)
0x20 8     zero / unused by the writer
0x28 24    DSK (per-device key string), ASCII, strncpy n=23, NUL-padded
           (total struct 0x40; last byte 0x3f is pad)
```

The DID triple (0x00–0x13) is exactly the 20-byte wire UID:
`pack_uid("PREFIX-serial-CHECK")` in cs2pppp `_protocol.py` — independent
confirmation of prefix/serial/check order and the u32BE serial.

Wire sockaddr form (@0x18, from a native `sockaddr_in`): family u16BE,
port u16 **little-endian**, IPv4 octets **reversed** — identical to
cs2pppp `pack_sockaddr`. (Writer byte-swaps each field of the in-memory
`sockaddr_in`, whose port/addr are already network-order in memory; the
composition yields the quirky wire form above.)

### 1.2 The HDR (TCP) login packet on the wire — 72 bytes

Built inline by `cs2p2p_PPPP_Proto_TCPSend_HDR_DevLgn_DSK` @0x72d78
(caller `cs2p2p_Do_TCPSendDevLgnDSK` @0x4ae48, per-session, up to 3 sockets):

```
+0  4     header: F1 6E 00 44     type 0x6E, payload len 0x44 = 68
+4  68    CRCEnc( DevLgnWithDSK[64], key = crcKey string )   (§2)
```

Sent with `Proto_TCPSend_MSG(ctx, sock, buf, total_len=72, …)`.
Destination: a directory server from the InitString (18.221.228.168 /
35.173.71.126 / 54.183.197.109), TCP port 443 (phase-1 probe: all three
accept TCP 443, no banner).

The non-HDR TCP variant `Proto_TCPSend_DevLgn_DSK` @0x6e290 is identical
except the inner header is `F1 16 00 44` (type **0x16**); the HDR type
0x6E is the one `Do_TCPSendDevLgnDSK` prefers when `cs2p2p_gbFlagAllowHDR`
is set (it tries plain first, then HDR, per its two call sites). The UDP
variants `Proto_Send_DevLgn_DSK` @0x6cd78 / `Proto_Send_HDR_DevLgn_DSK`
@0x729f0 use the same 64-byte body and CRCEnc; only the transport/header
type differ.

### 1.3 Field semantics — resolved

- flag @0x14: in `Do_TCPSendDevLgnDSK` it is `cs2p2p_gNetInfo[3]`
  (GOT slot 0x9d818 = `cs2p2p_gNetInfo`) — a network-type byte produced
  by the SDK's NetworkDetect probe. An implementation should send the
  byte its own network probe yields; on an ordinary NAT'd LAN client
  this is a small integer (exact value is environment-dependent — the
  one field in the packet not derivable from getP2PInfo).
- 3 bytes @0x15: in `Do_TCPSendDevLgnDSK` @0x4ae48 the caller stack-builds
  `{0x05, 0x06, 0x01}` (sturh 0x0605 + sturb 1) and passes it as the
  `unsigned char*` argument — a constant version-looking triple on this
  path, NOT key material.
- DSK @0x28: the `key` field from getP2PInfo (16 chars, fits the 23 cap).
- CRCEnc key (§2): the global `cs2p2p_gCRCKey` (GOT slot 0x9d820 =
  `cs2p2p_gCRCKey`), i.e. the getP2PInfo `crcKey` string the app installs
  at init/connect. If it is empty the cipher uses the bare (1,3,5,7) seed.

## 2. CRCEnc / CRCDec — the "CRC" stream cipher + trailer

`cs2p2p_PPPP_CRCEnc(uchar* in, int inlen, uchar* out, int outcap, uchar* key)`
@0x64768; `cs2p2p_PPPP_CRCDec` @0x64a44 (mirror). Returns -1 if
outcap < inlen+4. Output = inlen + 4 bytes.

**Table: VALIDATED.** The candidate 64-byte table at file offset **0x26d35**
(phase-1 `tables.json`) is loaded by `adr x9, 0x26d35` at CRCEnc+0x20 and
used as an 8×8 byte matrix `T[row][col]`, row = base + row*8. It is the
cipher key-schedule table, **not** a CRC polynomial table (the SDK's "CRC"
name is a misnomer). cs2pppp likewise expects a caller-supplied 64-byte
`crc_table`. The 256-byte S-box at 0x26d75 is NOT used here (it belongs to
the proprietary cipher, §4).

**State:** four bytes (a, b, c, d), initialised (1, 3, 5, 7).

**Key schedule** — for each byte `ch` of the NUL-terminated key string
(the getP2PInfo `crcKey`, 8 chars; if key NULL/empty the initial state is
used as-is), update (all arithmetic on unsigned bytes, `%` = unsigned mod,
indices masked &7):

```
a' = T[(ch % a + b) & 7][(c % d + ch) & 7]
b' = T[(ch % b + c) & 7][(d % a + ch) & 7]
c' = T[(ch % c + d) & 7][(a % b + ch) & 7]
d' = T[(ch % d + a) & 7][(b % c + ch) & 7]
(a, b, c, d) = (a', b', c', d')
```

(Register-level derivation: CRCEnc 0x647ac–0x6485c; the four `ldrb` table
reads land in the registers that become the next iteration's a, b, c, d.)

**Encryption** — for each plaintext byte p, with current state:

```
C = p ^ a ^ b ^ c ^ d
output C
then update (a,b,c,d) with the same four formulas, using ch = C
(cipher feedback — decryption is the identical process: p = C ^ a^b^c^d,
then update state with ch = C)
```

**Trailer** — 4 bytes appended after the ciphertext: the encryption, with
the continuing state, of four 0x43 ('C') bytes. I.e. for i in 0..3:
`chk = a ^ b ^ c ^ d ^ 0x43`; append chk; update state with ch = chk.
Verified from the decode side: `CRCDec` @0x64a44 decrypts inlen-4 data
bytes, then requires each of the last 4 decrypted bytes to equal 0x43
(cmps at 0x64c58–0x64c94) and returns inlen-4 on success, -1 on mismatch.

Python equivalent (validated line-by-line against the disassembly):

```python
T = bytes.fromhex("95e56197830da7f1d305958bdf136def07610d6d7f67172bc1b5130bdf"
                  "8b493b7f07d3026d2f13c56d3dfb0d0b29e94f892fe3e90d836de507538b2595471f29")
def _upd(s, ch):
    a, b, c, d = s
    return (T[((ch % a + b) & 7) * 8 + ((c % d + ch) & 7)],
            T[((ch % b + c) & 7) * 8 + ((d % a + ch) & 7)],
            T[((ch % c + d) & 7) * 8 + ((a % b + ch) & 7)],
            T[((ch % d + a) & 7) * 8 + ((b % c + ch) & 7)])
def crc_enc(data: bytes, key: bytes) -> bytes:
    s = (1, 3, 5, 7)
    for ch in key:            # key is the NUL-terminated crcKey string bytes
        s = _upd(s, ch)
    out = bytearray()
    for p in data:
        C = p ^ s[0] ^ s[1] ^ s[2] ^ s[3]
        out.append(C); s = _upd(s, C)
    for _ in range(4):        # trailer = stream-encryption of "CCCC"
        chk = s[0] ^ s[1] ^ s[2] ^ s[3] ^ 0x43
        out.append(chk); s = _upd(s, chk)
    return bytes(out)
```

## 3. The TCP outer envelope — EVERY TCP packet is wrapped

`cs2p2p_PPPP_Proto_TCPSend_MSG` @0x6d780 takes a complete inner packet
(SessionHeader + body, length L) and puts on the wire:

```
+0  2     inner length L, u16BE
+2  1     outer type = 0x68
+3  1     zero (pad; writer leaves it 0, reader ignores it)
+4  2     keyA: two rand() bytes (one fresh pair per packet)
+6  2     checkCRC over the encrypted payload (below)
+8  L     payload = RelayEnc( PropEnc( inner_packet ) )
```

(`st_cs2p2p_TCPHead`, writer @0x6d6f8, reader @0x6d730 — reader rejects
byte2 != 0x68.) So the §1.2 HDR login, seen on the wire, is actually
8 + 72 = 80 bytes: TCPHead{L=72, 0x68, 0, rand,rand, crc,crc} +
RelayEnc(PropEnc(F1 6E 00 44 ‖ CRCEnc(DevLgnWithDSK))).

Layers, outside-in (receive path `Proto_Read_TCPMSG` @0x6d9a0 /
`…_1` @0x6d8bc confirms the exact inverse order):

1. **CheckCRC_Verify** @0x6550c over the L payload bytes against the
   2 header CRC bytes.
2. **TCPRelay_Proprietary_Decrypt** @0x65420 — the §3.1 cipher keyed by
   the ASCII string `"%02X%02X" % (keyA[0], keyA[1])` (format string at
   .rodata 0x211c4; wrapper `_TCPRelay_Proprietary_Encrypt` @0x65394
   builds that 4-char key from the 2 raw bytes in the header).
3. **_P2P_Proprietary_Decrypt** @0x65044 — the §3.1 cipher keyed by the
   session key string (first arg of every TCPSend_*/Read_TCPMSG call;
   the string stored at session struct +0x17c, passed as arg 0 by all
   callers — the DID string field, 24 bytes, immediately before the DSK
   field at +0x194; see uncertainty note in §7).

### 3.1 The proprietary cipher (PropEnc / PropDec)

`cs2p2p__P2P_Proprietary_Encrypt` @0x64cf8 / `…_Decrypt` @0x65044, table =
the 256-byte S-box at file offset **0x26d75** (phase-1 validated table;
`__P2P_Proprietary_SelectTableElement` @0x64cd8 indexes it directly).
Key string → 4 effective bytes (`CRCSelect4Key`-style mash, identical to
cs2pppp `prop_select4key`):

```
K0 =  Σ k_i            (mod 256)
K1 = -Σ k_i            (mod 256)
K2 =  Σ ((k_i * 0xAB) >> 9)   (mod 256)
K3 =  XOR k_i
```
(strnlen capped at 20; empty/NULL key = memcpy passthrough.)

```
out[0] = SBOX[K0] ^ in[0]
out[i] = SBOX[(K[out[i-1] & 3] + out[i-1]) & 0xFF] ^ in[i]     (encrypt)
```
Decrypt is identical with prev = ciphertext byte. Python (matches
cs2pppp `prop_enc`/`prop_dec` exactly):

```python
SBOX = bytes.fromhex("7c9ce84a13dedcb22f2123e4307b3d8cbc0b270c3cf79ae7087196009785ef"
  "c11fc4dba1c2ebd901faba3b05b81587832872d18b5ad6da9358feaacc6e1bf0a388ab43c00db5453"
  "84f502266207f075b14981d9ba72ab9a8cbf1fc4947063eb10e043a945eee541134dd4df9ecc7c9e3"
  "781a6f706ba4bda95dd5f8e5bb26af4237d8e1020aae5f1cc573094e6924906d12b319ad748a2940f"
  "52dbea559e0f479d24bce8982488425c6912ba2fb8fe9a6b09e3f65f603312eac0f952c5ced39b733"
  "6c567eb4a0fd7a815351868d9f77ff6a80dfe2bf10d775645776f355cdd0c818e6364162cf99f2324"
  "c67606192cad3ea637d16b68ed46835c3529d46441e17")
def prop_key4(key: bytes):
    s = sum(key) & 0xFF
    return (s, (-s) & 0xFF, sum((b * 0xAB) >> 9 for b in key) & 0xFF,
            __import__('functools').reduce(int.__xor__, key, 0))
def prop_enc(data: bytes, key: bytes) -> bytes:
    if not key or key[0] == 0: return bytes(data)
    K = prop_key4(key[:20]); out = bytearray(len(data))
    if not data: return b""
    out[0] = SBOX[K[0]] ^ data[0]
    for i in range(1, len(data)):
        p = out[i-1]; out[i] = SBOX[(K[p & 3] + p) & 0xFF] ^ data[i]
    return bytes(out)
```

### 3.2 CheckCRC (TCPRelay_CheckCRC_Calculate @0x654ac / Verify @0x6550c)

A 2-byte dual-ended rolling XOR over the encrypted payload, seeded
{0x43, 0x53} ('C','S'). Faithful transliteration of Calculate:

```python
def tcprelay_checkcrc(data: bytes) -> bytes:
    o0, o1, s1, s2 = 0x43, 0x53, 0x43, 0x53
    if not data: return bytes([o0, o1])
    i, j = 0, len(data) - 1
    while True:
        t = s1 ^ data[i]; s1 = t ^ s2; o0 = s1
        if i % 2 == 0:
            s2 = data[j] ^ t; o1 = s2
        j -= 1; i += 1
        if j == -1: break
    return bytes([o0, o1])
```

### 3.3 NoEncrypt TCP variant

`Proto_TCPSend_MSG_NoEncrypt` @0x6fa08 / `Proto_Read_TCPMSG_NoEncrypt`
@0x6faf4 exist: no TCPHead, no relay layer, no CheckCRC — the inner
packet is only PropEnc'd (layer 1) on the stream. Used by the
`*_NoEncrypt` senders (e.g. DRW_TCPSend_NoEncrypt @0x6fb18).

## 4. HDR login response (type 0x6F)

Handled in `cs2p2p_PPPP_thread_recv_Proto` @0x55038 (two duplicate code
paths, 0x553c0 and 0x564c0 — UDP-queue and TCP-queue variants). The inner
packet (after §3 unwrap on TCP) is:

```
+0  4     SessionHeader: F1 6F <len u16BE>     len >= 0x28
body (st_cs2p2p_PPPP_HDR_RlyNameList, parsed by Proto_Read_HDR_RlyNameList @0x72b88):
+0x00 8   DID prefix (echo — strncmp'd against own DID prefix, must match)
+0x08 4   DID serial u32BE (echo — compared, must match)
+0x0c 8   DID check (echo — compared, must match)
+0x14 2   relay-name-list length N, u16BE
+0x16 18  not read by the parser (reserved/result area — see §7)
+0x28 N   relay name list: ASCII, comma-separated hostnames
```
Constraint checked in code: payload_len == 0x28 + N.
The name string is copied out and fed to `cs2p2p_HDR_UpdateNameList`
@0x49c3c, which splits on ',' (0x2C) and `HDR_AddHost`s each token into
the global host list (gpHDRNameList_Head/Tail); `thread_HDR_engine`
@0x49f9c then resolves them (HDR_PickUnResolvedHost / HDR_UpdateHost)
for the relay connects. There is **no session token** in this response —
the DID echo + name list is the whole payload. Failure responses are not
distinguished by a result code in the parsed fields; a login that the
server rejects presumably just never yields a 0x6F (the DSK/CRC trailer
would also fail first). The related non-HDR DevLgnAck is inner type
**0x13**: CRCEnc'd body (crcKey), plaintext byte 0 = result (0 = OK,
stored to session +0x211 login-status), handled at recv_Proto 0x55548.

## 5. TCPRlyReq — relay request (after HDR gives a relay host)

Plaintext body `st_cs2p2p_TCPRlyReq` (`Proto_Write_TCPRlyReq` @0x6e7d0),
49 bytes; DSK variant `st_cs2p2p_TCPRlyReqDSK` (@0x6ea68) appends the DSK:

```
+0x00 8   DID prefix (strncpy 7)
+0x08 4   DID serial u32BE
+0x0c 8   DID check (strncpy 7)
+0x14 24  target sockaddr_cs2, converted by htonAddrCS2 @0x68054
          (the address the relay should connect back to / punch toward:
          the camera-side rendezvous address from the session state)
+0x2c 1   flag char (arg4 — same global flag byte as DevLgn +0x14 path)
+0x2d 3   the {0x05,0x06,0x01}-style 3-byte field (arg5, as in DevLgn)
+0x30 1   flag char (arg6)
--- DSK variant only:
+0x34 24  DSK string (strncpy 23)
```

On the wire (senders inline the struct; `Proto_TCPSend_TCPRlyReq`
@0x6e874 / `…_DSK` @0x6eb20), then wrapped in the §3 envelope:

```
plain: inner = F1 53 00 34 ‖ body[52]    (body zero-padded to 52)
DSK:   inner = F1 54 00 4C ‖ body[76]
```
i.e. types **0x53 / 0x54**. Neither sender CRCEnc's — the only crypto is
the §3 envelope (PropEnc + RelayEnc + CheckCRC). Callers:
`cs2p2p_Do_TCPSendRlyReqDSK` @0x4b524 / `…RlyReq` @0x4b740 /
`…RlyPreReq(DSK)` @0x4b398/0x4b200 (pre-request variants exist).

**Ack:** inner type **0x55** → `Proto_Read_TCPRlyReqAck` @0x6ec68 →
`st_cs2p2p_TCPRlyReqAck` = 2 bytes {result, sub-result}
(`Proto_Write_TCPRlyReqAck` @0x6ec5c; ack sender type is also 0x55 via
TCPSend_TCPRlyReqAck @0x6ec7c with len 8?? — see §7). In recv_Proto
(0x55374) a nonzero first byte is stored as the session relay-state byte
(+0x210); 0xFA/0xFB-family values are treated as relay-accept states.
After the ack, the relay bridges the stream: subsequent inner packets
(session/DC traffic, §6) flow over the same TCP connection via the
relay, and `RlyRdyPlus_*` (header reader @0x711f4, writer @0x71154,
PunchGo/PunchTo/PunchAck writers @0x71280+) handles the UDP direct-punch
upgrade attempts in parallel — not needed for a relayed session.

## 6. Post-connect session framing — DC channel & JSON commands

Once relayed/direct session is up, commands ride the **DC (data-command)
channel**: inner packet type **0xDC**, built by
`cs2p2p_PPPP_Proto_DC_Write_Cmd` @0x703f4 / sent by
`Proto_DC_TCPSend_Cmd` @0x704e4 (UDP twin `Proto_DC_Send_Cmd` @0x7064c),
then wrapped in the §3 envelope on TCP. (The sibling DRW channel, inner
type 0xD0 with the 4-byte `DRWHeader` {0xD1, chan, len u16BE} —
`DRW_Write_Header` @0x6ac34, `DRW_TCPSend` @0x6ee54 — carries bulk/AV
data, not JSON commands.)

DC Cmd inner packet (total = 76 + data_len; data_len ≤ 1128):

```
+0  4    SessionHeader: F1 DC <(72 + data_len) u16BE>
+4  64   st_cs2p2p_DC_Header (Proto_Write_DCHeader @0x6feb8):
  +0  1    0xD1 (DC magic)
  +1  1    subtype: 0x11 = Cmd, 0x12 = CmdAck (Write_CmdAck @0x707a8);
           Req/ReqAck/Resp/RespAck use the sibling writers @0x70000+
  +2  2    u16BE: data_len + 8  (bytes after this 64-byte header block)
  +4  40   "name" string, strncpy 39 — the target name the app passes
           (per-session name string; zero-padded)
  +0x2c 8  DID prefix
  +0x34 4  DID serial u32BE
  +0x38 8  DID check
+68 2    u16BE: caller ushort (DC_TCPSend_Cmd arg6 — channel/flags word
         from the GQ layer; 0 in the common command path)
+70 2    u16BE: data_len
+72 4    zero pad
+76 ..   data = JSON text (below)
```
CmdAck is the same frame with subtype 0x12, session length fixed 0x48,
and two result bytes at DC-relative +0x40/+0x41. Receive side:
recv_Proto type 0xDC → `Proto_Read_DCHeader` @0x6ff54 (validates 0xD1,
checks payload_len - 0x40 == header length field) → `cs2p2p_DC_Parser`
@0x… (called at recv_Proto 0x552e4) → GQ layer JSON dispatch. Identity
is re-verified on every DC packet (prefix/check strncmp vs session
+0x213/+0x21b, serial vs +0x224).

### 6.1 JSON payload shape

Built natively by `gq_json_template_build` (symbols in .so). Verified
format strings in .rodata:

- request envelope prefix (0x21ccf):
  `{"version":"1.0","ack":false,"seq":%u,"cmd":%d,"def":"` … the
  per-command **def** JSON fragment and id/user fields are appended by
  the builder (fragments `,"id":"`, `,"user":"` in .rodata).
- response envelope (0x215ae):
  `{"version":"1.0","ack":false,"seq":%u,"cmd":%d,"id":"%s","user":"%s","result":{"code":%d,"message":"%s"}}`
- alt result form: `{"cmd":%d,"result":0,"status":%d,"extend":%s}`

**`cmd` is numeric.** The JNI layer passes command IDs in a 0x138-byte
command struct whose first u32 is the ID (verified in the JNI bodies):
`nativeSetTakePhotosRegularly` @0x3bddc → **cmd 47** =
JSON_CMD_AUTOPHOTO_SET, with its two Java int args stored in the struct
(at +0x74 and +0xa0 — enable + interval, in the app's call order);
`nativeSnapshotImg` @0x3be7c → **cmd 48** = JSON_CMD_SNAPSHOT_IMG, no
payload args (Java calls `nativeSnapshotImg(handle, null)`).
The JSON_CMD_* name strings (61) live in a name↔handler registry table
at .data.rel.ro 0x99180+ (0x20-byte entries: name ptr, handler ptr, …).
So on the wire:

- SNAPSHOT_IMG request data ≈
  `{"version":"1.0","ack":false,"seq":<n>,"cmd":48,"def":"…","id":"…","user":"…"}`
  with an empty/minimal def (no parameters exist at any layer above).
- AUTOPHOTO_SET request data ≈ same envelope with `"cmd":47` and a def
  carrying the two ints (enable, interval) — the exact def key names are
  generated inside `gq_json_template_build` from the command registry
  and were **not** recovered from strings (see §8).

## 7. SDevLgn — UDP super-device login (fallback first contact)

`st_cs2p2p_SDevLgn` is exactly the 20-byte UID
(`Proto_Write_SDevLgn` @0x6b61c / `Proto_Read_SDevLgn` @0x6b670).
`Proto_Send_SDevLgn` @0x6b6d0 sends, via UDP (`cs2p2p_SendMessage`):

```
plain: F1 91 00 14 ‖ UID[20]                                   (24 bytes)
CRC:   F1 92 00 18 ‖ CRCEnc(UID[20], key)                      (28 bytes)
       (Proto_Send_SDevLgn_CRC @0x6b8a4, key = its last arg)
```
Ack: `Proto_Send_SDevLgnAck` @0x6b7cc / `_CRC` @0x6b9dc. This is the
"super device" (app-side) login the directory understands from a client
that logs in *as if* a device — the cheapest first-contact packet in
this fork, worth trying against the directory IPs on UDP 32100/32108
and TCP 443's UDP sibling ports in phase 3.

**RlyRdyPlus header** (direct-punch upgrade, `Proto_Write_RlyRdyPlusHeader`
@0x71154, struct ≥ 0x28): +0 u8 = 0xA1, +1 u8 subtype, +2 u16BE field,
+4 16 bytes address blob (arg uchar*), +0x14 char[8] DID part,
+0x1c u32BE, +0x20 char[8] DID part. Only relevant to the UDP punch
path, not to a relayed session.

## 8. What remains uncertain

1. **PropEnc layer-1 key string (session +0x17c).** Every TCPSend_*/
   Read_TCPMSG caller passes the string at session struct +0x17c as the
   key. It is a 24-byte field immediately before the DSK field (+0x194)
   and is arg 0 ("DID") in every classic Proto_Send_* signature, so it
   is almost certainly the full DID string — but I did not catch the
   store that writes it, so "DID string" is inference, not a sighted
   fact. (If it were empty, PropEnc degrades to memcpy — a phase-3
   capture or a connect-path trace settles it in one step.)
2. **HDR response bytes +0x16..+0x27 (18 bytes)** are not read by
   Read_HDR_RlyNameList. They may carry a result code / relay port /
   session nonce the HDR engine uses elsewhere; the client provably
   ignores them for the name-list flow.
3. **AUTOPHOTO_SET / other commands' `def` JSON fragments**: generated
   by `gq_json_template_build` from the registry; exact key names not
   in .rodata as format strings. Recoverable from libgqipcsdk_v1.so or
   a live capture.
4. **TCPRlyReq sockaddr_cs2 target (+0x14, 24 bytes)**: htonAddrCS2
   byte-swaps family/port/addr of the first 8 bytes and copies the
   remaining 16 verbatim (a second address slot). Which rendezvous
   address the app puts there (camera's relay-side address from the
   session's RlyTo/RlyRdy exchange) is session-state dependent.
   sockaddr_cs2 wire form otherwise = §1.1 sockaddr quirk.
5. **gNetInfo[3]** (DevLgn flag byte): environment-dependent NAT-type
   value from NetworkDetect; not derivable from getP2PInfo.
6. TCPRlyReqAck sender used total length 8 for a 2-byte body struct
   (TCPSend_TCPRlyReqAck @0x6ec7c) — likely 4 header + 2 body + 2 pad;
   not chased further.
7. CRC `_upd` uses plain `%`: safe because the 64-byte table contains
   no zero byte (min 2), so state bytes are never 0 and the ARM
   div-by-zero path (udiv→0, msub→x, = cs2pppp's `_crc_m` guard) is
   unreachable after the first update.

## 9. End-to-end HDR DevLgn packet builder (all pieces validated §2/§3)

```python
import os, struct
# prop_enc, crc_enc, tcprelay_checkcrc: as defined in §2/§3.1/§3.2
def pack_uid(did):  # "PREFIX-serial-CHECK"
    p, s, c = did.split('-')
    return p.encode()[:8].ljust(8, b'\0') + struct.pack('>I', int(s)) + c.encode()[:8].ljust(8, b'\0')
def pack_sockaddr(ip, port):
    import socket
    return struct.pack('>H', 2) + struct.pack('<H', port) + socket.inet_aton(ip)[::-1]
def devlgn_body(did, dsk, local_ip, local_port, netinfo3=0):
    b = bytearray(64)
    b[0:20] = pack_uid(did)
    b[0x14] = netinfo3
    b[0x15:0x18] = bytes([5, 6, 1])
    b[0x18:0x20] = pack_sockaddr(local_ip, local_port)
    b[0x28:0x28+24] = dsk.encode()[:23].ljust(24, b'\0')
    return bytes(b)
def hdr_devlgn_wire(did, dsk, crc_key, local_ip, local_port, session_key):
    inner = b'\xf1\x6e\x00\x44' + crc_enc(devlgn_body(did, dsk, local_ip, local_port), crc_key.encode())
    keyA = os.urandom(2)  # fresh per packet, as the SDK's rand() pair
    layer1 = prop_enc(inner, session_key.encode())
    layer2 = prop_enc(layer1, ('%02X%02X' % (keyA[0], keyA[1])).encode())
    head = struct.pack('>H', len(inner)) + b'\x68\x00' + keyA + tcprelay_checkcrc(layer2)
    return head + layer2
```
Validation performed: `crc_enc` (keyless) and `prop_enc` outputs are
byte-identical to cs2pppp 0.2.11's independent implementations over 200
random trials using the extracted tables; keyed `crc_enc`/`crc_dec`
round-trips; the trailer-0x43 check matches CRCDec's four cmps.
