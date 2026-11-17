# Spectron PPPP — TCP envelope key findings (libgqipcsdk.so)

Binary: Mac `~/pppp-dig/libgqipcsdk.so`, arm64, 635,840 B,
sha256 `7f5a8e65ba56873f33a698ad60fee8b78ee92b56a74e3d5e48dd0d8706d9043e`
(identity confirmed via REA `open_binary`).

Method note: REA/Ghidra through Juno's connector client is one-shot per
invocation (each `client.py` call spawns a fresh `rea mcp`; `open_binary`
succeeds but the session does not persist into the next call, so
`batch_decompile` returns `target_unavailable: No app is open`). Per the
task's fallback clause, all evidence below is from the full objdump
disassembly (Mac `/tmp/dis.txt`) read instruction-by-instruction, plus the
jadx Java sources on the Mac (`~/aci-re/out11`). Every hop of both chains
was verified in the raw instructions — no step rests on a symbol name alone.

---

## ANSWER 1 — PropEnc layer-1 key (TCPSend_MSG arg0, session+0x17c)

**The layer-1 key is the getP2PInfo `key` field (the DSK) — specifically the
substring after the first `:` of the string `"<intstr>:<key>"`, copied with a
printable-ASCII filter, max 20 chars, into the 24-byte field at
session+0x17c.**

### The full chain, with evidence

1. **Java (app)** — `MainModel.java:2069-2070` / `MainViewAdapter.java:225,346,761`:
   ```java
   bVar.m1.set(netDevice.intstr);   // m1 = intstr
   bVar.l1.set(netDevice.key);      // l1 = key (DSK)
   gqClient.configureConnection(did, m1 + ":" + l1, 122, null);
   ```
   So `keyStr = intstr + ":" + key`, `enableLanSearch = 122`,
   `byServerString = null`. (`model/b.java:986` confirms l1 is bound to
   "ipc_key" and m1 to "ipc intstr".)

2. **JNI** — `Java_..._GqClient_nativeConnect` @0x3a6e8 packs a 0x381-byte
   params struct: DID @+0x00 (strncpy 127), keyStr @+0x80 (strncpy 255),
   byServerString @+0x181 (strncpy 511), enableLanSearch byte @+0x188, and
   calls `gq_client_connect` (vtable dispatch) → SY client connect impl in
   `sy_client.c` (function at 0x43a28, inside the create_sy_client region).

3. **SY connect impl** @0x43a94–0x43b00: because byServerString is empty, it
   builds one from keyStr:
   ```c
   snprintf(byServerString, 512, "{\"InitString\":\"%s\",\"0x7X_Timeout\":%d}", keyStr, 10);
   PPCS_ConnectByServer(DID, enableLanSearch /*122*/, 0, byServerString);
   ```
   (format string at file offset 0x260bc, verbatim:
   `{"InitString":"%s","0x7X_Timeout":%d}`.)

4. **cs2p2p_PPPP_ConnectByServer** @0x5ec48 parses the DID
   (`PREFIX-######-CHECKCODE` split on `-`: prefix → local buf, middle →
   `atoi` = SN, suffix → checkcode buf) and calls
   `cs2p2p_PPPP_Connect_Do(flag=1, handle, prefix, SN, checkcode,
   enableLanSearch, timeout, byServerString, stackArg)` where
   stackArg = (DID contains ':' ? after-colon ptr : NULL) — NULL for a
   normal DID (csinc semantics verified empirically on the Mac).

5. **cs2p2p_PPPP_Connect_Do** @0x5accc, key-writing block @0x5b67c–0x5b808:
   - `cs2p2p_PPPP___JSON_value(byServerString, "InitString", 0, buf)` →
     buf = `"intstr:key"` (the raw keyStr). ("BindInterface" is extracted
     the same way just before, @0x5b67c; absent → defaults.)
   - `strchr(buf, ':')` @0x5b730; if found, the loop @0x5b754–0x5b79c zeroes
     session+0x17c[24] (three 8-byte zero stores at +0x17c/+0x184/+0x18c)
     and copies from `colon+1`: up to **20 chars** (`cmp x8, #0x14`),
     keeping only bytes in **0x21..0x7E** (the `sub w12,w11,#0x7f; cmn
     w12,#0x5e; b.lo` test = `0x21 <= c <= 0x7e`), stopping at the first
     non-printable byte (incl. NUL).
   - Same block writes the sibling identity fields used by every sender:
     session+0x213 = prefix (strncpy 8), session+0x21b = checkcode
     (strncpy 8), session+0x224 = SN (uint32), session+0x194 = stackArg
     (strncpy 23) — **empty in the app flow** (DID has no colon).

   Result: **session+0x17c = the DSK** (16 printable chars, unchanged by the
   filter).

6. **Senders** pass exactly this field as TCPSend_MSG arg0:
   `cs2p2p_Do_TCPSendRlyPreReqDSK` @0x4b200 (key add at 0x4b2f4/0x4b328:
   `add x0, x8, #0x17c` where x8 = session base), `cs2p2p_Do_TCPSendRlyReqDSK`
   @0x4b524 (0x4b684), `cs2p2p_Do_TCPSendDevLgnDSK` @0x4ae48 (0x4af0c),
   `cs2p2p_Do_TCPSendDevLgn` @0x4b070 area, and `cs2p2p_Do_TCPRecv` @0x4baac
   uses it to decrypt replies.
   **Correction to the coordinator's framing:** the key is at
   **session+0x17c plain**. The `+0x4d38` in the same functions is a
   *separate* value — the offset of the TCPSessionInfo\* pointer array
   inside the session (x28 = idx*0x5500 + 0x4d38) — not part of the key
   pointer. The ARP2P punch sender's `session_base + 0x17c` is the **same**
   logical field, not a second one.

### Same rule, two other places (consistency check)

- `cs2p2p_PPPP_Initialize` @0x4e4d8, @0x4eb58–0x4ed08: `strchr(InitString,
  ':')`; if present, the identical unrolled copy (printable filter, 20
  chars, 24-byte zeroed field) fills the global **`cs2p2p_gP2PKeyString`**
  (char[24] in .bss @0xa4888; GOT slot 0x9d940). In the app flow this does
  **not** fire: `gq_sy_init` @0x42120 builds
  `{"InitString":"%s","MaxNumSess":%d,"SessAliveSec":%d,"APILogFile":"%s"}`
  (fmt @0x24def) around the bare intstr from
  `GqSdk.init(SY, APP_ID, intstr, false)` — no colon — so gP2PKeyString
  stays all-zero. (Initialize also strncpy's the InitString into
  `cs2p2p_gServerString` @0x4e9bc, and parses the decoded server list into
  `cs2p2p_gP2PServerName` slots of 256 B at @0x4ea3c–0x4ea7c.)
- `cs2p2p_PPPP_Listen_Do` @0x59108–0x5913c: for listen sessions,
  session+0x17c = `__strncpy_chk2(dst, gP2PKeyString, 20, 24, 24)` — same
  source string, device side.

### Dead ends ruled out

- `cs2p2p_ResetTCPrSessionInfo` @0x4ab58's `__strcpy_chk(..., 12)` is
  **not** a key default: it preserves the TCPSessionInfo **name field**
  (offset +0x00) across a reset — malloc(12), copy name out, zero the
  0x50-byte struct, restore name with `__strncpy_chk2(..., 7, 8, 12)`,
  restore sockaddr (+0x0c, 24 B), tick (+0x2c), buffer ptr (+0x30),
  bufsize (+0x38), sockfd = -1.
- `cs2p2p_AllocTCPSessionInfo` @0x4aa94: calloc(1, 0x50); its strncpy is
  `strncpy(info, arg0_name, 7)` into that same name field, sockaddr built
  from arg1 via `cs2_SA_SetSockAddr(2, ip, port, info+0x0c)`; it rejects
  the literal IP string `"0.0.0.0"` (@0x21279) via strcmp → NULL.

---

## ANSWER 2 — CRCEnc key (cs2p2p_gCRCKey, GOT 0x9d820, var @0xa4880)

**On the client (viewer) path the SDK actually runs, gCRCKey is never
installed — it stays NULL — and CRCEnc therefore runs with its built-in
empty-key schedule. It is NOT the getP2PInfo `crcKey` field. The app never
references `crcKey` anywhere in its Java code (grep of `~/aci-re/out11`
`com/eternal/**`: zero hits), so nothing ever hands it to the SDK.**

### Where gCRCKey *would* be installed

`DO_APILicenseCheck_PPPP` @0x583c4 (and its generic/RTOS/IoTWIFI twins
@0x58908/0x57e80/0x5793c), called **only from `cs2p2p_PPPP_Listen_Do`**
@0x591c8–0x59240 with `(session+0x213 /*prefix*/, session+0x224 /*SN*/,
licenseString)` where licenseString is a Listen argument:

```c
// DO_APILicenseCheck_PPPP @0x583c4, instructions @0x58400–0x58498
free(gCRCKey);
if ((colon = strchr(licenseString, ':')) != NULL) {
    gCRCKey = malloc(strlen(licenseString)); memset(gCRCKey, 0, ...);
    memcpy(localLicense, licenseString, colon - licenseString); // ≤16, before ':'
    memcpy(gCRCKey, colon + 1, strlen(licenseString) - strlen(localLicense) - 1);
} else {
    strncpy(localLicense, licenseString, 15);
    gCRCKey = malloc(4); *gCRCKey = 0;                          // empty string
}
return strcmp(localLicense, APILicenseCalculate_PPPP(prefix, SN, out, 16)) ? -1 : 0;
```

So the CRC key is **the part after the first `:` of the license string**
passed to Listen — the before-colon part is the license check-code validated
against `APILicenseCalculate_PPPP` over the APILicenseMatrix tables. This is
a device/listen-side mechanism; no caller exists on the connect path (the
exported `APILicenseCheck_*` wrappers @0x5835c etc. have no internal
callers, and `cs2p2p_PPPP_Initialize` / `gq_init` @0x3f99c /
`GqSdk.nativeInit` @0x39f98 never touch gCRCKey — Initialize's JSON keys
are only MaxNumSess, SessAliveSec, P2PPunchRange, AllowARP2P, AllowHDR,
QuickListen, HDR_ResolveInterval, APILogFile, InitString).
`cs2p2p_PPPP_DeInitialize` @0x4f46c frees `*gCRCKey` and NULLs it,
confirming it is a heap `char*`.

### What NULL means on the wire

`cs2p2p_PPPP_CRCEnc` @0x64768: at @0x6478c, `cbz x4, 0x64940` (key == NULL)
and @0x64794 `cbz w15, 0x64940` (key[0] == 0) both jump to the
**default-schedule branch** @0x64940, which sets the fixed strides
(1, 3, 5, 7) and encrypts with the CRC table at file offset 0x26d35 — i.e.
exactly cs2pppp's CRCEnc with an **empty key**. It does not skip the
transform and it does not use any secret.
`cs2p2p_Do_TCPSendDevLgnDSK` @0x4ae48 passes `*gCRCKey` (= NULL in the app
flow) as the CRC-key argument to `Proto_TCPSend_DevLgn_DSK` (stack pair
`stp x25, x27, [sp]` @0x4af14, x27 = loaded gCRCKey value; x25 =
session+0x194, the empty field above).

**Implication for the failed live probes:** trials that CRCEnc'd the
DevLgn/RlyReq bodies with the getP2PInfo `crcKey` (8 chars) used a key the
real client never uses. The real client CRCEncs those bodies with the
**empty key**. (The layer-1 key trials that used the DSK were, per Answer
1, using the right string — so if a DSK + crcKey trial failed, the CRCEnc
key is the prime suspect for that failure, followed by body fields:
+0x194 empty, prefix/SN/checkcode taken from the DID parse.)

---

## ANSWER 3 — First packets on the TCP 443 connection

In Connect_Do's TCP-relay section @0x5caf4–0x5cb34 (reached when the DSK
flag `[sp,#0x78]` is set, which is the app's case):

```c
cs2p2p_Do_TCPConnect(sessionIdx, 4, timeout, bindAddr);   // type 4 = DSK mode
cs2p2p_Do_TCPSendRlyPreReqDSK(sessionIdx);                // TCPRlyReqDSK pre-request
cs2p2p_Do_TCPSendRlyReqDSK(sessionIdx);                   // TCPRlyReqDSK
cs2p2p_Do_TCPRecv(sessionIdx);
```

(The non-DSK branch uses Do_TCPConnect type 3 and the non-DSK
RlyPreReq/RlyReq pair.) So the client sends **TCPRlyPreReqDSK first, then
TCPRlyReqDSK** — no DevLgn precedes them on this connection.
`cs2p2p_Do_TCPSendDevLgnDSK`'s only caller is at 0x59e2c, inside the
Listen/device-side flow — DevLgn is the *camera's* login packet, not the
viewer's first packet. Both Rly senders build their bodies from the
session fields above (key @+0x17c as PropEnc layer-1 key, prefix @+0x213,
checkcode @+0x21b, SN @+0x224, empty @+0x194, NetInfo byte
`gNetInfo[3]`) and CRCEnc the body with gCRCKey = NULL → empty-key
schedule.

---

## One-line summary for the reimplementation

- PropEnc layer-1 key = **DSK** (getP2PInfo `key`; in SDK terms: after-`:`
  part of `intstr:key`, printable-filtered, ≤20 chars).
- CRCEnc key = **empty** (gCRCKey is NULL on the client path; the
  getP2PInfo `crcKey` field is unused by this SDK/app).
- First wire packets to the server: **TCPRlyPreReqDSK, then TCPRlyReqDSK**,
  over a type-4 TCP session.
