# GQ harness — genuine-SDK Spectron session (WORKING, 2026-11-16 late)

Runs the vendor's own `libgqipcsdk.so` (extracted from the AC Infinity app
v2.1.1) inside a minimal Android harness and replays the app's exact JNI
call sequence. Result: live P2P session, live HEVC stream, and on-demand
4K main + 1080p sub-camera stills — **no phone involved**. This is the
recipe to wire into the MCP `spectron_snapshot` slot.

## Why this works (and the hand-rolled client didn't)

Our reimplemented protocol client produced byte-identical packets
(Unicorn golden-verified) yet the vendor servers refused every data-phase
packet. The genuine library connects in ~0.1–1.1 s, 6/6 sessions. The
difference is session orchestration inside the library — its own connect
state machine, the composite connect credential (`intstr + ":" + key`,
below), and the flags value 122 — not packet bytes.

## Host rig (as run on the Mac, 2026-11-16)

Mac disks are nearly full (internal ~6.9 G free, Sabrent ~2.1 G), so the
whole Android stack lived on a **14 GB RAM disk** (`/Volumes/RAMDisk`),
created with `hdiutil attach -nomount ram://29360128` +
`diskutil erasevolume HFS+ RAMDisk <dev>`, and detached afterwards —
zero disk footprint. A permanent install needs ~6 GB somewhere.

- sdkmanager (from the on-disk SDK's cmdline-tools) with
  `--sdk_root=/Volumes/RAMDisk/sdk`: packages `emulator`,
  `platforms;android-34`, `system-images;android-34;google_apis;arm64-v8a`.
  (Copy cmdline-tools INTO the RAM sdk before running avdmanager — it
  resolves the SDK root relative to its own location.)
- AVD `gq`: pixel_6, `disk.dataPartition.size = 2147483648` (default 6 GB
  userdata does not fit the RAM disk alongside the image), placed under
  `ANDROID_AVD_HOME=/Volumes/RAMDisk/avd` (move `gq.ini`/`gq.avd` there
  and fix the `path=` in `gq.ini`). Symlink the on-disk SDK's
  `platform-tools` into the RAM sdk or the emulator rejects the SDK root.
- Boot: `emulator -avd gq -no-window -no-audio -no-boot-anim
  -gpu swiftshader_indirect -memory 2048 -cores 4 -no-snapshot
  -wipe-data -port 5554` (boots in ~19 s on the Mac Studio).
- Build tools note: build-tools **34.0.0's d8 crashes** (R8 NPE) on these
  classes; 35.0.0 works. `build.sh` uses 35.0.0.
- adb gotcha: `adb install -r` silently failed to replace the package
  twice; verify the installed dex md5 against the build's before
  trusting a run (`pm path` → pull → unzip classes.dex → md5).

## The harness APK

`build.sh` (javac + d8 + aapt2, no Gradle) builds `com.juno.gqharness`
from `src/`:

- `com/eternal/media/client/GqSdk.java`, `GqClient.java`,
  `GqProtocolHead.java` — minimal re-declarations of the app's own JNI
  facade classes with identical package/class/method signatures
  (including the native→Java entries `_onNativeData(int,
  GqProtocolHead, byte[])`, `_onNativeCmdResult(Object, int, byte[])`,
  `_onNativeReconnect(long, int, int)`), so the genuine library binds
  and calls back exactly as it does for the real app.
- `libgqipcsdk.so` (from Mac `~/pppp-dig/`) packaged at
  `lib/arm64-v8a/`.
- `com/juno/gqharness/MainActivity.java` — the sequence runner + data
  sink (writes stream/stills + a codes-only status log to its files dir).

## Credential flow (nothing sensitive ever touches disk)

`feed.py` (Mac, stdlib only): reads the aci token in-process →
`POST /api/user/devInfoListAll` (form `userId=<token>`) → camera devId
(the devType 10001 device) → `POST /api/ipc/getP2PInfo?devId=...` →
{did (17), intstr (88), key (16)} → `adb -s emulator-5554 forward
tcp:18777 tcp:18777` → sends one JSON line to the harness's loopback
socket. Values live only in the two processes' memory; logs carry field
lengths and return codes only.

## The exact call sequence (all return codes verified live)

1. `GqSdk.openLog(5)`
2. `nativeInit(0 /* ClientType.SY */, "Android_" + ANDROID_ID, intstr, false)` → **0**
3. `nativeCreate()` → handle ≠ 0; then `nativeSetAutoReconnect(h, true, -1)`,
   `nativeSetCmdTimeout(h, 10000)` (mirrors the app constructor)
4. `nativeSetCallbackEnabled(h, 0|1|4|5, true)` (CMD, LIVE, PHOTO, SUB_PHOTO)
5. `nativeConnect(h, did, intstr + ":" + key, 122, null)` → **0** in 108–1132 ms
   (credential composite and the 122 flags value are exactly what
   `SmartCameraViewModel`/`GqPlayer` pass via `configureConnection`;
   byServerString is null at every app call site)
6. `nativeCheckConnection(h)` → 0, `nativeHeartbeat(h)` → 0
7. **Main still:** `nativeSnapshotImg(h, cb)` → 0; cmd callback ack JSON
   `{"cmd":786,"def":"JSON_CMD_SNAPSHOT_IMG","result":{"code":200}}`
   in ~0.2 s; the still arrives ~3 s later via `_onNativeData` **type 4**:
   one callback, head enc=1 (JPEG), **3840×2160, ~2.0–2.1 MB**.
8. **Live:** `nativeLiveStart(h)` → 0; `_onNativeData` **type 1** frames:
   HEVC, 1920×1080, ~15 fps (I-frame ~130 KB, P-frames ~1–2 KB,
   head enc=2, frameType 1=I / 2=P). Concatenated payloads are a clean
   Annex-B stream — ffprobe/ffmpeg read it directly.
9. **Sub still:** `nativeSubSnapshotImg(h, 0, cb)` → 0; ack JSON
   `{"cmd":804,"result":{"code":200}}`; still via **type 5**: **1920×1080
   JPEG, ~238 KB**, ~0.2 s after the ack. (Passing int=1 instead →
   camera replies `{"cmd":804,"result":{"code":408,"message":"TIMEOUT"}}`
   and the JNI call returns -408. The app passes 0.)
10. Teardown: `nativeLiveStop(h)` → 0, `nativeDisconnect(h)` → 0,
    `nativeDestroy(h)`, `GqSdk.cleanup()` → 0.

Snapshot works both before live start and while live is running.
SDK-triggered stills are delivered to the session only — they did NOT
appear in the cloud photo log (checked 2026-11-16 ~23:52; log's last
entry was the 23:20 timed shot).

## Evidence (this directory)

- `frame-live-2345.png` — frame 25 of the run-1 live stream; in-frame
  overlay reads 11/16/2026 11:44:25 PM, matching wall clock at capture.
- `snapshot-2347.jpg` — on-demand main still, overlay 11:47:18 PM.
- `snapshot-sub-2354.jpg` — on-demand sub-camera still (soil-level view).
- `status_run5.txt`, `frames_photo_run5.txt` — codes/metadata logs of
  the full-sequence run (connect 108 ms; main stills 2,104,841 B and
  2,054,251 B; sub still 237,840 B).

## For the MCP wiring

`spectron_snapshot` can now be implemented as: ensure emulator+harness
up → run feed.py → launch harness (parameterize: snapshot-only mode
skips the live collect) → pull `photo_type4_*.jpg` (and
`photo_type5_*.jpg` for the side camera) from the app's files dir via
`adb exec-out run-as` → return. Session setup ≈ 25 s (boot) + ~5 s
(connect+capture). A resident emulator removes the boot cost.
