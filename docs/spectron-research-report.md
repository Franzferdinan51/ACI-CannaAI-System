# AC Infinity Spectron Cameras (Spectron 3 / Spectron 7) — Programmatic Access Research

Research date: 2026-11-16. Method: targeted web-index searches and page reads (`browser_search` / `browser_open`). **Almost all sources are index reads, not verified live in the research browser.** One live-browser attempt on fccid.io hit a Cloudflare security check and was abandoned without solving it; FCC facts below come from the web index and are flagged "index".

**Important framing:** The mission premise — that acinfinityserver.com has an undocumented camera ("IPC") API under `/api/ipc/` (`photoLogs`, `getSettingInfo`, `getP2PInfo`, `setting`), that reads work with a `token` header, that writes to `/api/ipc/setting` return HTTP 500 from a third-party client, and that the app syncs settings over a P2P channel via an SDK client called "GqClient" with device IDs like `XXXX-000000-XXXXX` — comes from the requesting agent's own reverse-engineering work. **None of it is corroborated by any public source found.** It is treated below as unverified premise, and the report distinguishes it from what the public record actually supports.

## Summary

- **No public documentation of the AC Infinity camera/IPC API exists that could be found.** No docs, GitHub project, Home Assistant integration, forum thread, or blog post mentions `/api/ipc/`, `photoLogs`, `getSettingInfo`, `getP2PInfo`, or Spectron camera settings writes. All public AC Infinity cloud-API work covers **controllers only** (Q1, Q6).
- **No one in the Home Assistant / grow community has publicly gotten Spectron photos or streams out of the app ecosystem.** The only documented exit path is the official microSD workflow; the only scraping workaround found is a generic Android `adb screencap` approach not specific to Spectron (Q2).
- **The device-ID format `XXXX-000000-XXXXX` (4 letters – 6 digits – 5 letters) is diagnostic of the PPPP protocol family (CS2 Networks lineage), not TUTK/ThroughTek Kalay** (whose UIDs are 20 undashed characters). The verification-code letter set (no A/I/O/Q) and the cloud-issued license/key both match CS2's documented fingerprints. "GqClient" has **zero** public footprint and is most likely an internal/proprietary wrapper name in the AC Infinity app. Open-source PPPP/CS2 clients exist (cs2pppp, aiopppp, go2rtc, cam-reverse), but none has been tested on Spectron, and Spectron's vendor-specific command layer would still need reversing (Q3).
- **Spectron 3 and Spectron 7 are, per AC Infinity's own FCC filing, electrically identical hardware**: the model-confirmation letter for FCC ID 2AXMF-APM states the circuit design, layout, components, and internal wiring are identical across AC-APM7 (Spectron 7), AC-APC7 (Spectron 3), and a dozen sibling models — only the model number differs. They share one user manual and are built by ODM Guangdong Seneasy Intelligent Technology. The specific chipset/SoC is **not public** (schematics/block diagrams were permanently withheld from the FCC filing) (Q4).
- **Auto Photo / timed-photo behaviour is barely documented publicly.** One reviewer reports setting photos every six hours; timelapse is microSD-centric in all official material. Whether cloud "Auto Photo" uploads each shot (vs SD-only) and whether the app/cloud must trigger each shot is **not publicly documented**. No public report was found of timed photos failing to start after enabling or of settings being reset by firmware updates (Q5).
- **No working public example exists of writing IPC camera settings via the cloud API, and no community AC Infinity project uses the newer refresh-token flow** (`/api/auth/refresh`, `/api/auth/newToken`). All public projects still use the legacy `appUserLogin` → `appId` → `token` header flow (Q6).

Confidence: moderate-to-high on the negative results (multiple independent targeted searches, all returning nothing on the IPC API); high on the FCC platform facts (primary regulatory documents); moderate on the PPPP/CS2 attribution (strong format/fingerprint match, but the definitive discriminator — init string or native library name — is not public).

---

## Findings

### Q1. Public documentation of the AC Infinity camera/IPC API (`/api/ipc/`)

**Answer: None found. This is the core negative result.**

Targeted searches — `"acinfinityserver.com" api ipc photoLogs`, `"/api/ipc" camera`, `"getP2PInfo" OR "photoLogs" OR "getSettingInfo"`, `site:github.com acinfinity camera OR spectron OR ipc`, and variants — returned **zero** public documentation, repositories, forum threads, or blog posts mentioning `/api/ipc/`, `photoLogs`, `getSettingInfo`, `getP2PInfo`, or camera settings writes for either the Spectron 3 or Spectron 7. Both cameras are 2026 releases, which partly explains the scarcity, but as of 2026-11-16 the IPC API appears to be documented nowhere public.

What public AC Infinity cloud-API work does exist covers **controllers only**:

- `dalinicus/homeassistant-acinfinity` (github.com/dalinicus/homeassistant-acinfinity) — the foundational Home Assistant integration and the original reverse engineering of the AC Infinity cloud API; credited as the basis by forks and by the ioBroker adapter `raspilaurent/ioBroker.acinfinity` (https://github.com/raspilaurent/iobroker.acinfinity). Controller/sensor scope only.
- `ober37/ac-infinity-mcp` — described by a sibling project as "the most complete public reference"; its `docs/API.md` catalogues dozens of API quirks (39 in one version; a fork's copy shows the count growing 25→27). Guide: https://ober37.github.io/ac-infinity-mcp/GUIDE.html
- `misterboe/acinfinity-mcp`, CLAUDE.md (https://github.com/misterboe/acinfinity-mcp/blob/HEAD/CLAUDE.md) — documents the legacy auth flow in detail: login is `POST /api/user/appUserLogin` with form fields `appEmail` and `appPasswordl` (the trailing "l" is intentional), password truncated to the first 25 characters; the response's `data.appId` is sent as the `token` header on subsequent calls; clients should always send `User-Agent: okhttp/4.12.0`; `POST /api/user/devInfoListAll` lists controllers. The API is HTTP-only (no HTTPS) — the ober37 guide says the same.
- `keithah/homebridge-acinfinity` (https://github.com/keithah/homebridge-acinfinity) — Homebridge plugin; host default `http://www.acinfinityserver.com`; supported devices are controllers/sensors only, no camera.
- Fork `JoshuaSeidel/homeassistant-acinfinity` README — supported devices: Controller AI+ (CTR89Q), Outlet AI+/AI, 69 Pro+/WiFi, plus external USB sensors (CO2+light, soil, water, pH, EC). **No Spectron/camera support.**

Nothing found covers photo logs, timed/auto photos, timelapse, or camera settings writes via the cloud API.

### Q2. Community extraction of Spectron photos/streams (Home Assistant / grow community)

**Answer: No working extraction found. No HA camera entity, no RTSP/ONVIF claim, no scrape or API project for Spectron 3/7 surfaced in any search.**

Closest items:

- **Overgrow "Unofficial AC Infinity UIS Suite" thread** (https://overgrow.com/t/unofficial-the-ac-infinity-uis-suite/222936?page=4): community members were beta-testing the Spectron 3; per one poster it "integrates to the Controller AI+ not through any UIS wire, but connects to it through WiFi" (the poster was unsure about Bluetooth). The thread also notes Home Assistant can expose extra Controller AI+ sensor data not shown in the app — that is controller data, not camera images.
- **Generic screen-scrape workaround (not Spectron-specific):** a CannaAI/OpenClaw document by Franzferdinan51 on GitHub describes running the AC Infinity app on an Android phone and capturing `adb screencap -p /sdcard/ac-infinity.png` every 5 minutes, plus `adb am start -a android.media.action.IMAGE_CAPTURE` for plant photos. This is a screen-scraping pattern that would work with any app view, but it is not a Spectron integration and was not presented as one.
- **Official SD-card workflow is the only documented exit path:** 4K timelapse writes to microSD (card not included); live view, stills, and alerts work without a card (per retailer summaries of the official specs, e.g. the Quick Bloom Lights Spectron 7 page).

### Q3. P2P protocol/SDK behind `USAA-XXXXXX-XXXXX` IDs and cloud-issued license/key

**Answer (inference from strong public fingerprints): the PPPP family, CS2 Networks lineage — not TUTK. "GqClient" itself is unidentified publicly.**

Primary reference: Palant, "An overview of the PPPP protocol for IoT cameras" (2025-11-05), read in full — https://palant.info/2025/11/05/an-overview-of-the-pppp-protocol-for-iot-cameras/

- **ID format matches PPPP exactly.** The canonical PPPP device ID is `ABC-123456-VWXYZ` (prefix – 6 digits – 5-letter verification code); other public examples use 4-letter prefixes: hacked.camera (https://hacked.camera) shows `FFFF-123456-ABCDE`; LookCam uses `GHBB-000001-NRLXW`. The mission's `XXXX-000000-XXXXX` (4–6–5) fits this shape precisely.
- **CS2 fingerprints match.** Per Palant's variant table, CS2 Networks' implementation ships as `libPPCS_API.so` / `libobject_jni.so` / `librtapi.so` with `PPPP_Initialize` / `PPPP_ConnectByServer`. CS2 verification codes use only 22 letters — **A, I, O, and Q never appear** — and `XXXXX` is consistent (none of A/I/O/Q). CS2 init strings encode server IPs plus an optional `:SECRETKEY`, and **`libPPCS_API` expects the key in the device "license", following a colon after a six-uppercase-letter license code**; `APILicenseCalculate` produces a six-letter `tnp_license`. This matches the mission premise of a cloud-returned license/key pair unusually well.
- **TUTK/ThroughTek Kalay is ruled out by ID shape.** A TUTK UID is a 20-byte/20-character identifier with no dashes (see the CVE-2021-28372 description, Tenable: https://www.tenable.com/cve/CVE-2021-28372). `USAA000000XXXXX` stripped of dashes is 15 characters.
- **Legacy iLnk is unlikely; AJCloud is ruled out.** Legacy iLnk verification codes consist only of letters A–F (MD5-hex-derived; CVE-2019-11219) — `XXXXX` contains H, Z, R. Newer iLnk networks can use all letters, so iLnk-new cannot be 100% excluded without the init string or library name. AJCloud IDs are undashed (e.g. `PPPA1B2C3D4E5F6G`), so AJCloud does not fit.
- **Transport facts (Palant):** UDP 32108 LAN discovery broadcast, UDP 32100 server, TCP 443 fallback (obfuscated, not TLS). Application data rides `MSG_DRW` channels 0–7 — commands and video share one session — and the IOCTRL command vocabulary is vendor-specific, i.e. even with the transport solved, Spectron's snapshot/settings commands would need their own reversing.
- **"GqClient": zero public footprint.** Multiple searches (`"GqClient" camera`, `"GQ P2P" OR "gqclient" ipc`, `GqClient P2P camera SDK GQ`) returned only unrelated results (GraphQL, LDAP, GoQuiet). Working conclusion, stated as inference: "GqClient" is a proprietary/internal wrapper or class name inside the AC Infinity app (Android package `com.eternal.acinfinity`), not a known public SDK brand. **The definitive discriminator between CS2 proper, the Yi fork, and iLnk-new is the init string, the license format (e.g. `XXXXXX:KEY`), or the native library name from `getP2PInfo`/the APK — none of which is public.**

Open-source PPPP/CS2 clients and libraries (all for generic cameras; **none tested on Spectron**):

| Project | What it does | Caveat |
|---|---|---|
| `cs2pppp` (PyPI, https://pypi.org/project/cs2pppp/0.1.0/, Aug 2026) | Stdlib-only Python CS2 PPPP client: directory lookup, HELLO → hole-punch/relay → RDY → ALIVE → DRW | Ships **no** directory IPs, init strings, or credentials — the caller must supply them (i.e. exactly what `getP2PInfo` presumably returns) |
| `aiopppp` (PyPI, https://pypi.org/project/aiopppp/0.2.3/) | asyncio Python PPPP library for A9/X5-class cameras: live streaming, snapshots, settings (settings TBD). Built on DavidVentura/cam-reverse, magicus/PPPP, hyc/a9serv, magicus/pppp-dissector (Wireshark) | Targeted at A9/X5-class devices |
| `adlerweb/cam-reverse.py` / DavidVentura/cam-reverse | iLnk/iLnkP2P/PPPP reimplementation for X5/A9 cameras | Different device class |
| `elastic/camera-hacks` | Elastic Security Labs' PPPP client implementing the connection handshake (Wansview/AJCloud context) | Research tooling, AJCloud-flavoured |
| `AlexxIT/go2rtc` | Lists private protocols `cs2` (PPPP) and `tutk` (P2P); snapshots served via `/api/frame.jpeg`. Refs: https://pkg.go.dev/github.com/AlexxIT/go2rtc/pkg and a CS2-transport + MISS analysis at https://www.lazyharu.com/en/xiaomi-c100-protocol/ (Xiaomi source splits newer `cs2`/`cs2+tcp`/`cs2+udp`, MISS command layer, ~2020+ cameras, from legacy `tutk`; Wyze source is TUTK) | Would need Spectron's init string/license and command layer |
| `jphein/eyeplus-icam365-camera` (https://github.com/jphein/eyeplus-icam365-camera/blob/HEAD/docs/driving-the-camera.md) | Worked example of driving a CS2 "PPCS" camera (`libPPCS_API.so`, `com.p2p.pppp_api`): explicitly "not TUTK" on transport, but the application vocabulary (`IOTYPE_*`, `AVIOCTRLDEFs`) is copied from TUTK; control on channel 0; `PASSWORD_REQ` IOCTRL 32770 must be sent first; the session dies after ~60 s of silence without `MSG_ALIVE` | Best public template for how a Spectron P2P client would be built **if** Spectron is CS2 |

### Q4. Spectron 3 vs Spectron 7 — same platform?

**Answer: Yes — strong primary-source evidence of one shared platform. Chipset/SoC is not public. No teardown was found.**

- **One manual covers both models.** The Spectron Series user guide (Manuals+ mirror: https://manuals.plus/ac-infinity/spectron-series-ai-grow-cameras-for-indoor-plant-monitoring-manual, published 2026-10-10) lists "Models: AC-APC7, AC-APM7, Manual Code: APC2806X1". It documents: primary-camera install; the Spectron 7 secondary camera connecting to the primary (the climate-sensor port only supports the included antenna sensor); app pairing (hold SETUP for pairing mode; factory reset = hold SETUP 10 s until a three-tone beep); LED states (flashing green = firmware updating); Option A "Solo Connect" vs Option B "Link With Controller" pairing with AI controllers; and a 2.4 GHz-only warning.
- **Two FCC grants under grantee code 2AXMF** (index: https://fccid.io/2AXMF):
  - `2AXMF-APC`, granted **2025-12-01** (MiCOM Labs): 2402–2480 MHz @ 0.00119 W (Bluetooth-like) + 2412–2462 MHz WiFi @ 0.03565 W. No 5 GHz.
  - `2AXMF-APM`, granted **2026-09-30** (Eurofins): 2.4 GHz @ 0.305 W **plus** 5 GHz UNII bands 5180–5240 / 5260–5320 / 5500–5700 / 5745–5825 MHz.
- **The APM model-confirmation letter is the decisive document** (PDF: https://fccid.io/m/bc6501d874b9668f4098c7659b5c06ca1ea5daff52c906ab16efa31f69f6120b.pdf). It lists models AC-APM7, AC-APC7, AC-APC3, AC-APC5, AC-APC9, AC-APF3/5/7/9, AC-APK3/5/7/9, AC-APM3/5/9 and states in substance: **"Their electrical circuit design, layout, components used and internal wiring are identical, Only the Model No. were different."** Spectron 3 (AC-APC7) and Spectron 7 (AC-APM7) are therefore in the same electrically-identical FCC family.
- **APM 2.4 GHz test report** CQASZ20260601191E-01, issued 2026-09-21 (PDF: https://fccid.io/m/d14e66096e6109806041f591e8ef98932e053aaf02a3e6f6e4bacdb49d379be3.pdf): test model AC-APM7; **factory = Guangdong Seneasy Intelligent Technology Co., Ltd, Huizhou** (the ODM; it makes cameras/webcams/doorbells and offers OEM/ODM/JDM services); **Software Version V1.3.2, Hardware Version V1.1**; adapter KA12C-0502000US, 5 V/2 A; WiFi 802.11b/g/n/ax (HE20/HE40), 2412–2462 MHz; FPC antenna 4.76 dBi.
- **Chipset unknown, by design:** the APM confidentiality request dated 2026-09-01 (PDF: https://fccid.io/m/d2b9df4f6fa18c793f15ead531a7bae82752ab53a87b48d1ef8a8c137b622b4d.pdf) asks for permanent withholding of the Schematic Diagram, Block Diagram, and Operational Description. No teardown of either model was found in any search.
- **Spec comparison (official product pages, crawled 2026-11-16):**
  - Spectron 3: model AC-APC7, UPC 819137025158, $89.99, IP67 — https://acinfinity.com/spectron-3-ai-powered-grow-camera-4k-advanced-plant-health-and-growth-monitoring/?utm_source=forum&utm_medium=banner&utm_campaign=420giveaway&utm_id=rollitup
  - Spectron 7: model AC-APM7, UPC 819137025387, $159.00, IP65 — https://acinfinity.com/spectron-7-ai-powered-grow-camera-4k-with-thermal-imaging-and-under-canopy-vision/
  - Shared: 4K / 8 MP stills, 2.5K live view (retailer pages), M12 lens f/2.7, 940 nm IR night vision to 32 ft (10 m), 2.4 GHz WiFi per marketing, main unit 2.00 × 2.04 in footprint (Spectron 7 main-unit height 1.22 in vs 3's 2.04 in per official tables).
  - Spectron 7 only: thermal imaging; onboard climate sensors (temperature / humidity / leaf temperature / true VPD); corded under-canopy support camera (2K stills/timelapse per the Hydrobuilder comparison table; support unit 3.06 × 1.57 × 27.71 in).
  - **Tension flagged, not resolved:** marketing and the manual say 2.4 GHz only, yet the APM FCC grant covers 5 GHz and the shared manual's ISED warning mentions operation in 5150–5250 MHz. This suggests the hardware family may be dual-band capable; it is not proof that retail Spectron units run 5 GHz.

### Q5. "Auto Photo" / timed-photo behaviour and failure reports

**Answer: The public record is thin. One concrete interval data point; cloud-vs-SD behaviour undocumented; the specific failure modes asked about have no public reports.**

- **Only concrete interval data point:** the HowWeedGrow Spectron 7 review (https://www.howweedgrow.com/ac-infinity-spectron-7-review/, updated 2026-11-09) — the reviewer "set it to take photos every six hours and played with the timer", lists "scheduled photos" among the likes, saved needed photos to phone storage, and confirms a microSD card is required for 4K timelapses (card not included). **No published list of interval options/units was found anywhere.**
- **Timelapse/hyperlapse is SD-centric in all official and retailer material** ("4K timelapses (MicroSD not inc.)"). Whether the cloud "Auto Photo" feature uploads each shot to the cloud (as the requester's photoLogs premise implies) versus writing SD-only, and whether the app or cloud must trigger each shot versus the camera running the schedule on-device, is **not publicly documented**. Keep the two features distinct: scheduled stills and timelapse video are separate features in the public material, and conflating them would be speculation.
- **Failure reports found** (Trustpilot, AC Infinity reviews: https://www.trustpilot.com/review/www.acinfinity.com):
  - 14 Oct 2026, Spectron 3 owner: "constant stutter on live view, disconnect problems… Hyperlapse dont save… night mode doesnt auto kick in."
  - 13 Apr 2026, Spectron 3 pre-order buyer: camera underperformed its claims; the AC Infinity logo/name is watermarked on every photo/video and cannot be removed.
- **Not found:** any public report specifically of timed/Auto Photos not starting after enabling, or of camera settings being reset by a firmware update. This is stated as "searched, none found" — absence of reports is not proof the behaviour doesn't occur.

### Q6. Working examples of IPC settings writes, or refresh-token auth in community projects

**Answer: None found for either.**

- Searches for `"/api/auth/refresh" OR "newToken" AC Infinity` and related terms returned only generic/unrelated auth documentation. **No community AC Infinity project was found using `/api/auth/refresh` or `/api/auth/newToken`.** All public projects (dalinicus HA integration, ober37/misterboe MCP servers, homebridge-acinfinity, ioBroker.acinfinity) still use the legacy flow documented in Q1: `POST /api/user/appUserLogin` (`appEmail` / `appPasswordl`, password truncated to 25 chars) → `data.appId` → sent as the `token` header, with `User-Agent: okhttp/4.12.0`, over plain HTTP.
- **No working public example exists of writing camera settings via `/api/ipc/setting`** (or of any `/api/ipc/` call) in any language.
- **Analogous controller write pattern (for contrast only — not a camera recipe):** standard controllers use full-object read-modify-write via `addDevMode` / `updateAdvSetting`; AI controllers (devType 20–22) use `PUT modeAndSetting` with `minversion: 3.5` (per misterboe's CLAUDE.md, URL in Q1). This is controller-only evidence; nothing indicates the IPC `setting` endpoint follows the same pattern, and the mission premise says third-party writes to it return HTTP 500.

---

## Could not verify

- **Chipset / SoC / image sensor** of either model — schematics, block diagram, and operational description were permanently withheld from the FCC filing; no teardown exists publicly.
- **Definitive P2P attribution (CS2 proper vs Yi fork vs iLnk-new)** — requires the init string, license format, or native library name from `getP2PInfo` or the APK; none is public. The CS2 conclusion is a fingerprint match, not a confirmation.
- **"GqClient"** — no public trace; cannot confirm what SDK it wraps.
- **Full Auto Photo interval options/units**, whether each scheduled shot is uploaded to the cloud or SD-only, and whether the app/cloud must be reachable to trigger each shot.
- **Reports of timed photos not starting after enabling, or settings reset by firmware updates** — searched; none found.
- **Any `/api/ipc/` write example or refresh-token (`/api/auth/refresh`, `/api/auth/newToken`) usage** in community projects — searched; none found.
- **Whether retail Spectron units actually use 5 GHz WiFi** — the APM grant covers it and marketing says 2.4 GHz only; unresolved.
- The mission premise itself (existence/behaviour of the `/api/ipc/` endpoints, HTTP 500 on writes, P2P settings sync) could not be corroborated from public sources; it stands as the requester's own reverse-engineering result.

## Sources

All read via web index on 2026-11-16 unless dated otherwise; none verified live in the research browser (fccid.io live access was blocked by a Cloudflare check, not solved).

1. Palant — "An overview of the PPPP protocol for IoT cameras" (2025-11-05) — https://palant.info/2025/11/05/an-overview-of-the-pppp-protocol-for-iot-cameras/
2. hacked.camera (PPPP ID example `FFFF-123456-ABCDE`) — https://hacked.camera
3. Tenable — CVE-2021-28372 (TUTK UID format) — https://www.tenable.com/cve/CVE-2021-28372
4. cs2pppp 0.1.0, PyPI — https://pypi.org/project/cs2pppp/0.1.0/
5. aiopppp 0.2.3, PyPI — https://pypi.org/project/aiopppp/0.2.3/
6. AlexxIT/go2rtc package docs — https://pkg.go.dev/github.com/AlexxIT/go2rtc/pkg
7. LazyHaru — Xiaomi C100 protocol (CS2 transport + MISS) — https://www.lazyharu.com/en/xiaomi-c100-protocol/
8. jphein/eyeplus-icam365-camera — "Driving the camera" (CS2/PPCS worked example) — https://github.com/jphein/eyeplus-icam365-camera/blob/HEAD/docs/driving-the-camera.md
9. misterboe/acinfinity-mcp — CLAUDE.md (legacy auth flow, controller write patterns) — https://github.com/misterboe/acinfinity-mcp/blob/HEAD/CLAUDE.md
10. ober37/ac-infinity-mcp — Guide — https://ober37.github.io/ac-infinity-mcp/GUIDE.html
11. keithah/homebridge-acinfinity — https://github.com/keithah/homebridge-acinfinity
12. raspilaurent/ioBroker.acinfinity — https://github.com/raspilaurent/iobroker.acinfinity
13. dalinicus/homeassistant-acinfinity — github.com/dalinicus/homeassistant-acinfinity (foundational HA integration; controller scope)
14. Overgrow — "Unofficial AC Infinity UIS Suite" thread, p.4 — https://overgrow.com/t/unofficial-the-ac-infinity-uis-suite/222936?page=4
15. Manuals+ — Spectron Series user guide (AC-APC7 / AC-APM7, APC2806X1; published 2026-10-10) — https://manuals.plus/ac-infinity/spectron-series-ai-grow-cameras-for-indoor-plant-monitoring-manual
16. FCC grantee page, AC Infinity Inc. (2AXMF) — grants 2AXMF-APC (2025-12-01) and 2AXMF-APM (2026-09-30) — https://fccid.io/2AXMF
17. FCC 2AXMF-APM model-confirmation letter (electrically-identical statement) — https://fccid.io/m/bc6501d874b9668f4098c7659b5c06ca1ea5daff52c906ab16efa31f69f6120b.pdf
18. FCC 2AXMF-APM 2.4 GHz test report CQASZ20260601191E-01 (Seneasy factory; SW V1.3.2 / HW V1.1) — https://fccid.io/m/d14e66096e6109806041f591e8ef98932e053aaf02a3e6f6e4bacdb49d379be3.pdf
19. FCC 2AXMF-APM confidentiality request (2026-09-01; schematics/block diagram withheld) — https://fccid.io/m/d2b9df4f6fa18c793f15ead531a7bae82752ab53a87b48d1ef8a8c137b622b4d.pdf
20. AC Infinity — Spectron 3 product page (AC-APC7, $89.99, IP67) — https://acinfinity.com/spectron-3-ai-powered-grow-camera-4k-advanced-plant-health-and-growth-monitoring/?utm_source=forum&utm_medium=banner&utm_campaign=420giveaway&utm_id=rollitup
21. AC Infinity — Spectron 7 product page (AC-APM7, $159.00, IP65) — https://acinfinity.com/spectron-7-ai-powered-grow-camera-4k-with-thermal-imaging-and-under-canopy-vision/
22. Happy Hydro — Spectron 7 page (retailer spec summary; notes unpublished items) — https://happyhydro.com/products/ac-infinity-spectron-7
23. HowWeedGrow — Spectron 7 review (updated 2026-11-09; six-hour photo interval) — https://www.howweedgrow.com/ac-infinity-spectron-7-review/
24. Trustpilot — AC Infinity reviews (Spectron 3 owner reports, Apr & Oct 2026) — https://www.trustpilot.com/review/www.acinfinity.com
