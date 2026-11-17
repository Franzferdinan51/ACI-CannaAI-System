"""p2p_client — Spectron 7 on-demand snapshot via the vendor's own SDK.

SOLVED 2026-11-16 (see ../SPECTRON-IPC.md, "Genuine-SDK session"): our
reimplemented protocol client reproduced every packet byte-for-byte yet
the vendor's relay servers refused the data phase. The genuine
libgqipcsdk.so (extracted from the AC Infinity app) connects in ~0.1-1 s,
6/6 sessions — the missing piece was session orchestration inside the
library: PPCS-style init with the account init string, and a connect
call whose credential is the COMPOSITE `intstr + ":" + key` with flags
122, exactly as the app's SmartCameraViewModel/GqPlayer pass them.

This module runs that library the way the solving run did
(~/workspace/spectron-pppp/harness/README.md is the full recipe):

  1. preflight (token file, SDK library, tools, free memory)
  2. ephemeral rig: RAM disk -> Android SDK root (cmdline-tools copied
     in, emulator + android-34 google_apis arm64 image installed) ->
     AVD -> harness APK (built from rig/harness sources, cached)
  3. boot the emulator, install + launch the harness, feed credentials
     in-process from getP2PInfo over an adb-forwarded loopback socket
     (values live only in this process + the harness; never on disk,
     never logged — only field lengths and return codes)
  4. harness replays the app's call sequence (openLog -> init ->
     create -> callbacks 0/1/4/5 -> connect(composite, 122) ->
     snapshotImg -> subSnapshotImg(0) -> teardown) and writes the
     stills to its private files dir
  5. pull photo_type4_*.jpg (main, 3840x2160) and photo_type5_*.jpg
     (sub, 1920x1080) via `adb exec-out run-as`
  6. tear the rig down: emulator killed (adb emu kill, TERM at most —
     never kill -9), RAM disk detached. Nothing is left running.

A resident rig (persistent emulator on real disk) is a small change:
point RIG_SDK_ROOT / AVD_HOME at a permanent location and make the
setup/teardown steps no-ops — every parameter lives in the config
block below.

Failures raise SnapshotError with the step and the EXACT SDK return
codes from the harness status log, so callers can report honestly.

Stdlib only, like server.py. macOS only (the rig host is the Mac).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Rig configuration — a future resident rig changes only this block.
# ---------------------------------------------------------------------------
RAM_DISK_NAME = "RAMDisk"
RAM_DISK_GB = 14                       # as-run size; whole stack lives here
RAM_DISK_MOUNT = "/Volumes/" + RAM_DISK_NAME
RIG_SDK_ROOT = RAM_DISK_MOUNT + "/sdk"         # ephemeral SDK root
AVD_HOME = RAM_DISK_MOUNT + "/avd"             # ephemeral AVD home
AVD_NAME = "gq"
AVD_DEVICE = "pixel_6"
AVD_DATA_PARTITION = "2147483648"              # 2 GB userdata (fits the RAM disk)
SYSTEM_IMAGE = "system-images;android-34;google_apis;arm64-v8a"
SDK_PACKAGES = ["emulator", "platforms;android-34", SYSTEM_IMAGE]
EMULATOR_PORT = 5554
EMULATOR_MEMORY_MB = 2048
EMULATOR_CORES = 4
FEED_PORT = 18777                      # harness loopback credential socket
HARNESS_PACKAGE = "com.juno.gqharness"

ON_DISK_SDK = os.path.expanduser("~/Library/Android/sdk")
CMDLINE_TOOLS_SRC = os.path.join(ON_DISK_SDK, "cmdline-tools")
SDK_LIB = os.path.expanduser("~/pppp-dig/libgqipcsdk.so")  # genuine vendor .so
JAVA_HOME = "/opt/homebrew/opt/openjdk@21"
ADB_CANDIDATES = ["/opt/homebrew/bin/adb",
                  os.path.join(ON_DISK_SDK, "platform-tools", "adb")]

HERE = os.path.dirname(os.path.abspath(__file__))
RIG_DIR = os.path.join(HERE, "rig")
HARNESS_DIR = os.path.join(RIG_DIR, "harness")
HARNESS_APK = os.path.join(HARNESS_DIR, "build", "gqharness.apk")
HARNESS_DEX = os.path.join(HARNESS_DIR, "build", "classes.dex")
DEFAULT_DEST_DIR = os.path.expanduser("~/spectron-photos")

BASE = "https://www.acinfinityserver.com"
TOKEN_FILE = os.environ.get(
    "ACI_TOKEN_FILE", os.path.expanduser("~/.config/aci/token.json")
)

MIN_FREE_BYTES = 8 * 1024 ** 3         # refuse to boot the rig below this
BOOT_TIMEOUT_S = 240                   # as-run boot was ~19 s
SETUP_TIMEOUT_S = 1200                 # sdkmanager downloads dominate
CAPTURE_TIMEOUT_S = 300                # connect+capture was ~5 s
TEARDOWN_TIMEOUT_S = 60


class SnapshotError(Exception):
    """Snapshot failure with the failing step and exact SDK codes."""


def _log(*args):
    print("[p2p_client]", *args, file=sys.stderr, flush=True)


def _run(cmd, timeout=120, env=None, input_bytes=None, check=True):
    full_env = dict(os.environ)
    full_env["JAVA_HOME"] = JAVA_HOME
    full_env["PATH"] = (JAVA_HOME + "/bin:/opt/homebrew/bin:"
                        + full_env.get("PATH", ""))
    if env:
        full_env.update(env)
    proc = subprocess.run(cmd, timeout=timeout, env=full_env,
                          input=input_bytes, capture_output=True)
    if check and proc.returncode != 0:
        raise SnapshotError(
            "command failed (rc=%d): %s\nstdout: %s\nstderr: %s"
            % (proc.returncode, " ".join(str(c) for c in cmd),
               proc.stdout.decode(errors="replace")[-800:],
               proc.stderr.decode(errors="replace")[-800:]))
    return proc


def _adb(adb, *args, timeout=120, check=True, binary=False):
    proc = _run([adb, "-s", "emulator-%d" % EMULATOR_PORT, *args],
                timeout=timeout, check=False)
    if check and proc.returncode != 0:
        raise SnapshotError(
            "adb %s failed (rc=%d): %s"
            % (" ".join(args), proc.returncode,
               proc.stderr.decode(errors="replace")[-400:]))
    return proc.stdout if binary else proc.stdout.decode(errors="replace")


# ---------------------------------------------------------------------------
# Cloud side — credentials, in-process only (mirrors harness/feed.py)
# ---------------------------------------------------------------------------

def _load_token():
    if not os.path.exists(TOKEN_FILE):
        raise SnapshotError(
            "no token file at %s — run aci-login once on this machine"
            % TOKEN_FILE)
    with open(TOKEN_FILE) as fh:
        token = json.load(fh).get("user_id")
    if not token:
        raise SnapshotError("token file %s has no user_id value" % TOKEN_FILE)
    return token


def _cloud_post(path, token, form=None):
    body = b""
    headers = {"token": token}
    if form is not None:
        body = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(BASE + path, data=body, method="POST",
                                 headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except Exception as exc:
        raise SnapshotError("cloud request %s failed: %s" % (path, exc))


def _find_camera_devid(node):
    if isinstance(node, dict):
        if node.get("devType") == 10001 and node.get("devId"):
            return str(node["devId"])
        for v in node.values():
            hit = _find_camera_devid(v)
            if hit:
                return hit
    elif isinstance(node, list):
        for v in node:
            hit = _find_camera_devid(v)
            if hit:
                return hit
    return None


def _fetch_p2p_credentials(token, dev_id):
    """Return {did, intstr, key} for the camera. Values never leave RAM."""
    if dev_id:
        cam = str(dev_id)
    else:
        devs = _cloud_post("/api/user/devInfoListAll", token,
                           form={"userId": token})
        cam = _find_camera_devid(devs)
        if not cam:
            raise SnapshotError("camera (devType 10001) not found in "
                                "devInfoListAll")
    info = _cloud_post("/api/ipc/getP2PInfo?devId=" + cam, token)
    data = info.get("data", info) if isinstance(info, dict) else {}
    creds = {k: str(data.get(k, "")) for k in ("did", "intstr", "key")}
    _log("getP2PInfo ok (field lengths: %s)"
         % {k: len(v) for k, v in creds.items()})
    if not all(creds.values()):
        raise SnapshotError("getP2PInfo returned empty field(s): %s"
                            % {k: len(v) for k, v in creds.items()})
    return creds


# ---------------------------------------------------------------------------
# Rig setup / teardown
# ---------------------------------------------------------------------------

def _free_bytes():
    out = _run(["vm_stat"], timeout=30).stdout.decode(errors="replace")
    page = 16384
    m = re.search(r"page size of (\d+) bytes", out)
    if m:
        page = int(m.group(1))
    free = 0
    for key in ("Pages free", "Pages inactive", "Pages speculative"):
        m = re.search(re.escape(key) + r":\s+(\d+)\.", out)
        if m:
            free += int(m.group(1))
    return free * page


def _preflight(adb):
    if not os.path.exists(TOKEN_FILE):
        raise SnapshotError("no token file at %s" % TOKEN_FILE)
    if not os.path.exists(SDK_LIB):
        raise SnapshotError("vendor SDK library missing: %s" % SDK_LIB)
    if not os.path.isdir(CMDLINE_TOOLS_SRC):
        raise SnapshotError("cmdline-tools missing: %s" % CMDLINE_TOOLS_SRC)
    if not os.path.isdir(HARNESS_DIR):
        raise SnapshotError("harness sources missing: %s" % HARNESS_DIR)
    free = _free_bytes()
    _log("preflight: %.1f GB free memory" % (free / 1024 ** 3))
    if free < MIN_FREE_BYTES:
        raise SnapshotError(
            "only %.1f GB free memory — refusing to boot the emulator rig "
            "(needs >= %.0f GB)" % (free / 1024 ** 3, MIN_FREE_BYTES / 1024 ** 3))


def _create_ram_disk():
    if os.path.exists(RAM_DISK_MOUNT):
        raise SnapshotError(
            "%s already exists — a previous rig may still be up; "
            "refusing to clobber it" % RAM_DISK_MOUNT)
    sectors = RAM_DISK_GB * 1024 * 1024 * 1024 // 512
    out = _run(["hdiutil", "attach", "-nomount", "ram://%d" % sectors],
               timeout=60).stdout.decode(errors="replace")
    device = out.split()[0]
    _run(["diskutil", "erasevolume", "HFS+", RAM_DISK_NAME, device],
         timeout=120)
    _log("RAM disk created: %s (%d GB)" % (device, RAM_DISK_GB))
    return device


def _setup_sdk():
    os.makedirs(RIG_SDK_ROOT, exist_ok=True)
    if not os.path.exists(os.path.join(RIG_SDK_ROOT, "cmdline-tools")):
        shutil.copytree(CMDLINE_TOOLS_SRC,
                        os.path.join(RIG_SDK_ROOT, "cmdline-tools"))
    pt_link = os.path.join(RIG_SDK_ROOT, "platform-tools")
    if not os.path.exists(pt_link):
        os.symlink(os.path.join(ON_DISK_SDK, "platform-tools"), pt_link)
    sdkmanager = os.path.join(RIG_SDK_ROOT, "cmdline-tools", "latest",
                              "bin", "sdkmanager")
    _run([sdkmanager, "--sdk_root=" + RIG_SDK_ROOT, "--licenses"],
         timeout=300, input_bytes=b"y\n" * 200, check=False)
    _run([sdkmanager, "--sdk_root=" + RIG_SDK_ROOT] + SDK_PACKAGES,
         timeout=SETUP_TIMEOUT_S, input_bytes=b"y\n" * 200)
    _log("SDK root ready at %s" % RIG_SDK_ROOT)


def _create_avd():
    os.makedirs(AVD_HOME, exist_ok=True)
    env = {"ANDROID_AVD_HOME": AVD_HOME, "ANDROID_SDK_ROOT": RIG_SDK_ROOT}
    avdmanager = os.path.join(RIG_SDK_ROOT, "cmdline-tools", "latest",
                              "bin", "avdmanager")
    _run([avdmanager, "create", "avd", "-n", AVD_NAME, "-k", SYSTEM_IMAGE,
          "-d", AVD_DEVICE, "--force"],
         timeout=300, env=env, input_bytes=b"no\n")
    config = os.path.join(AVD_HOME, AVD_NAME + ".avd", "config.ini")
    with open(config) as fh:
        text = fh.read()
    if "disk.dataPartition.size" in text:
        text = re.sub(r"disk\.dataPartition\.size=.*",
                      "disk.dataPartition.size=" + AVD_DATA_PARTITION, text)
    else:
        text += "\ndisk.dataPartition.size=%s\n" % AVD_DATA_PARTITION
    with open(config, "w") as fh:
        fh.write(text)
    _log("AVD %s created (data partition %s)" % (AVD_NAME, AVD_DATA_PARTITION))


def _apk_stale():
    if not (os.path.exists(HARNESS_APK) and os.path.exists(HARNESS_DEX)):
        return True
    apk_mtime = os.path.getmtime(HARNESS_APK)
    newest = os.path.getmtime(SDK_LIB)
    for root, _dirs, files in os.walk(HARNESS_DIR):
        if os.sep + "build" in root:
            continue
        for name in files:
            newest = max(newest, os.path.getmtime(os.path.join(root, name)))
    return apk_mtime < newest


def _build_apk():
    if not _apk_stale():
        _log("harness APK up to date: %s" % HARNESS_APK)
        return
    _log("building harness APK (rig build.sh)…")
    proc = subprocess.run(["/bin/zsh", "build.sh"], cwd=HARNESS_DIR,
                          timeout=600, capture_output=True,
                          env={**os.environ,
                               "JAVA_HOME": JAVA_HOME,
                               "PATH": JAVA_HOME + "/bin:/opt/homebrew/bin:"
                                       + os.environ.get("PATH", "")})
    if proc.returncode != 0 or not os.path.exists(HARNESS_APK):
        raise SnapshotError(
            "harness build failed (rc=%d): %s"
            % (proc.returncode,
               (proc.stdout + proc.stderr).decode(errors="replace")[-800:]))
    _log("harness APK built")


def _boot_emulator(adb):
    emulator = os.path.join(RIG_SDK_ROOT, "emulator", "emulator")
    log_path = os.path.join(RIG_DIR, "emulator.log")
    env = dict(os.environ)
    env.update({"ANDROID_AVD_HOME": AVD_HOME,
                "ANDROID_SDK_ROOT": RIG_SDK_ROOT,
                "JAVA_HOME": JAVA_HOME})
    with open(log_path, "ab") as logf:
        proc = subprocess.Popen(
            [emulator, "-avd", AVD_NAME, "-no-window", "-no-audio",
             "-no-boot-anim", "-gpu", "swiftshader_indirect",
             "-memory", str(EMULATOR_MEMORY_MB), "-cores",
             str(EMULATOR_CORES), "-no-snapshot", "-wipe-data",
             "-port", str(EMULATOR_PORT)],
            stdout=logf, stderr=subprocess.STDOUT, env=env)
    deadline = time.time() + BOOT_TIMEOUT_S
    while time.time() < deadline:
        if proc.poll() is not None:
            raise SnapshotError(
                "emulator exited during boot (rc=%s); see %s"
                % (proc.returncode, log_path))
        out = _adb(adb, "shell", "getprop", "sys.boot_completed",
                   timeout=30, check=False).strip()
        if out == "1":
            _log("emulator booted (pid %d)" % proc.pid)
            return proc
        time.sleep(3)
    raise SnapshotError("emulator did not finish booting within %ds"
                        % BOOT_TIMEOUT_S)


def _install_and_verify_apk(adb):
    _adb(adb, "install", "-r", HARNESS_APK, timeout=300)
    # README gotcha: `install -r` once silently kept a stale package —
    # verify the installed dex md5 against the build's before trusting it.
    with open(HARNESS_DEX, "rb") as fh:
        want = hashlib.md5(fh.read()).hexdigest()
    path = _adb(adb, "shell", "pm", "path", HARNESS_PACKAGE).strip()
    m = re.search(r"package:(\S+)", path)
    if not m:
        raise SnapshotError("pm path returned nothing for %s"
                            % HARNESS_PACKAGE)
    import tempfile
    import zipfile
    with tempfile.TemporaryDirectory() as td:
        local = os.path.join(td, "installed.apk")
        _adb(adb, "pull", m.group(1), local, timeout=120)
        with zipfile.ZipFile(local) as zf:
            got = hashlib.md5(zf.read("classes.dex")).hexdigest()
    if got != want:
        raise SnapshotError(
            "installed dex md5 %s != build dex md5 %s — stale package; "
            "refusing to run" % (got, want))
    _log("harness installed, dex md5 verified")


def _harness_files(adb, *names):
    out = {}
    for name in names:
        proc = _run([adb, "-s", "emulator-%d" % EMULATOR_PORT,
                     "exec-out", "run-as", HARNESS_PACKAGE, "cat",
                     "files/" + name],
                    timeout=60, check=False)
        out[name] = proc.stdout
    return out


def _harness_status(adb):
    raw = _harness_files(adb, "status.txt")["status.txt"]
    return raw.decode(errors="replace")


def _feed_credentials(adb, creds):
    _run([adb, "-s", "emulator-%d" % EMULATOR_PORT, "forward",
          "tcp:%d" % FEED_PORT, "tcp:%d" % FEED_PORT], timeout=60)
    line = (json.dumps(creds) + "\n").encode()
    deadline = time.time() + 120
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", FEED_PORT),
                                          timeout=5) as s:
                s.sendall(line)
            _log("credentials fed to harness over loopback")
            return
        except OSError:
            time.sleep(2)
    raise SnapshotError("harness never listened on port %d" % FEED_PORT)


_STATUS_PATTERNS = {
    "init": r"INIT ret=(-?\d+)",
    "create": r"CREATE ok handleNonZero=(\w+)",
    "callbacks": r"CALLBACKS enabled",
    "connect": r"CONNECT ret=(-?\d+)",
    "connectMs": r"CONNECT ret=-?\d+ elapsedMs=(\d+)",
    "check": r"CHECK ret=(-?\d+)",
    "heartbeat": r"HEARTBEAT ret=(-?\d+)",
    "snapshotRet": r"SNAPSHOT ret=(-?\d+)",
    "snapshotAck": r"SNAPSHOT ack arrived=\w+ code=(-?\d+)",
    "mainPhotos": r"SNAPSHOT photoData count=(\d+)",
    "subRet": r"SUBSNAPSHOT ret=(-?\d+)",
    "subPhotos": r"SUBSNAPSHOT photoData type5count=(\d+)",
    "liveStop": r"LIVE_STOP ret=(-?\d+)",
    "disconnect": r"DISCONNECT ret=(-?\d+)",
    "cleanup": r"CLEANUP ret=(-?\d+)",
}


def _parse_status(text):
    codes = {}
    for key, pat in _STATUS_PATTERNS.items():
        m = re.search(pat, text)
        if m:
            if not m.groups():
                codes[key] = True
            else:
                try:
                    codes[key] = int(m.group(1))
                except ValueError:
                    codes[key] = m.group(1)
    return codes


KEEP_RIG = os.environ.get("ACI_SNAPSHOT_KEEP_RIG") == "1"


def _save_diagnostics(adb, status_text):
    """Persist harness status + logcat next to the rig for post-mortem.

    Local machine only (never published): the harness status carries
    codes/metadata; logcat may carry the device DID in SDK debug lines.
    """
    try:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        dest = os.path.join(RIG_DIR, "last-failure-" + stamp)
        os.makedirs(dest, exist_ok=True)
        with open(os.path.join(dest, "status.txt"), "w") as fh:
            fh.write(status_text)
        proc = _run([adb, "-s", "emulator-%d" % EMULATOR_PORT,
                     "logcat", "-d"], timeout=60, check=False)
        with open(os.path.join(dest, "logcat.txt"), "wb") as fh:
            fh.write(proc.stdout)
        tail = status_text.strip().splitlines()[-6:]
        _log("diagnostics saved to %s; status tail: %s" % (dest, tail))
        return dest
    except Exception as exc:
        _log("diagnostics save failed: %s" % exc)
        return None


def _jpeg_size(data):
    """(width, height) from JPEG SOF markers, or (None, None)."""
    if len(data) < 4 or data[0] != 0xFF or data[1] != 0xD8:
        return None, None
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xC0, 0xC1, 0xC2):
            h = (data[i + 5] << 8) | data[i + 6]
            w = (data[i + 7] << 8) | data[i + 8]
            return w, h
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        seglen = (data[i + 2] << 8) | data[i + 3]
        if seglen < 2:
            return None, None
        i += 2 + seglen
    return None, None


def _pull_stills(adb, dest_dir):
    listing = _run([adb, "-s", "emulator-%d" % EMULATOR_PORT,
                    "exec-out", "run-as", HARNESS_PACKAGE, "ls", "files"],
                   timeout=60).stdout.decode(errors="replace").split()

    def highest(prefix):
        best = None
        for name in listing:
            m = re.fullmatch(re.escape(prefix) + r"_(\d+)\.jpg", name)
            if m and (best is None or int(m.group(1)) > best[0]):
                best = (int(m.group(1)), name)
        return best[1] if best else None

    os.makedirs(dest_dir, exist_ok=True)
    epoch = int(time.time())
    stills = {}
    for kind, prefix in (("main", "photo_type4"), ("sub", "photo_type5")):
        name = highest(prefix)
        if not name:
            raise SnapshotError(
                "harness produced no %s still (files: %s)"
                % (kind, ", ".join(sorted(listing))[:300]))
        data = _harness_files(adb, name)[name]
        if len(data) < 10000:
            raise SnapshotError("%s still suspiciously small: %d bytes"
                                % (kind, len(data)))
        path = os.path.join(
            dest_dir, "spectron-ondemand-%d-%s.jpg" % (epoch, kind))
        with open(path, "wb") as fh:
            fh.write(data)
        w, h = _jpeg_size(data)
        stills[kind] = {"path": path, "bytes": len(data),
                        "width": w, "height": h, "sourceFile": name}
        _log("%s still: %s (%d bytes, %sx%s)" % (kind, path, len(data), w, h))
    return stills


def _teardown(adb, emu_proc, ram_device):
    """Emulator down (graceful, TERM at most), RAM disk detached."""
    try:
        if adb:
            _run([adb, "-s", "emulator-%d" % EMULATOR_PORT, "emu", "kill"],
                 timeout=30, check=False)
    except Exception:
        pass
    if emu_proc is not None:
        deadline = time.time() + TEARDOWN_TIMEOUT_S
        while time.time() < deadline and emu_proc.poll() is None:
            time.sleep(2)
        if emu_proc.poll() is None:
            _log("emulator still up after emu kill — sending TERM")
            emu_proc.terminate()
            try:
                emu_proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                _log("WARNING: emulator survived TERM; leaving it for "
                     "manual cleanup (kill -9 is never used)")
    if ram_device:
        for _ in range(5):
            proc = _run(["hdiutil", "detach", ram_device], timeout=60,
                        check=False)
            if proc.returncode == 0:
                _log("RAM disk detached (%s)" % ram_device)
                return
            time.sleep(3)
        _log("WARNING: RAM disk %s did not detach cleanly" % ram_device)


# ---------------------------------------------------------------------------
# Public entry point (server.py contract)
# ---------------------------------------------------------------------------

def snapshot(dev_id=None, dest_dir=None):
    """Capture on-demand main + sub stills from the Spectron camera.

    Returns a dict: {"path", "bytes", "taken_at", "main", "sub", "sdk",
    "timings", ...} — "path"/"bytes" describe the main still, per the
    original contract. Raises SnapshotError with exact SDK codes on
    failure. Credentials are fetched in-process and never persisted.
    """
    started = time.time()
    adb = next((p for p in ADB_CANDIDATES if os.path.exists(p)), None)
    if adb is None:
        raise SnapshotError("adb not found in %s" % ADB_CANDIDATES)
    dest_dir = dest_dir or DEFAULT_DEST_DIR

    _preflight(adb)
    token = _load_token()
    creds = _fetch_p2p_credentials(token, dev_id)

    ram_device = None
    emu_proc = None
    timings = {}
    failed = False
    status_text = ""
    try:
        t = time.time()
        ram_device = _create_ram_disk()
        _setup_sdk()
        _create_avd()
        _build_apk()
        timings["setupS"] = round(time.time() - t, 1)

        t = time.time()
        emu_proc = _boot_emulator(adb)
        timings["bootS"] = round(time.time() - t, 1)

        t = time.time()
        _install_and_verify_apk(adb)
        _adb(adb, "shell", "am", "start", "-n",
             HARNESS_PACKAGE + "/.MainActivity",
             "--es", "mode", "snapshot", timeout=60)
        # Wait until the harness is listening, then feed credentials.
        deadline = time.time() + 120
        while time.time() < deadline:
            if "LISTENING" in _harness_status(adb):
                break
            time.sleep(2)
        else:
            raise SnapshotError("harness never reached LISTENING state")
        _feed_credentials(adb, creds)
        creds = None  # drop our copy; the harness holds its own in RAM

        deadline = time.time() + CAPTURE_TIMEOUT_S
        while time.time() < deadline:
            status_text = _harness_status(adb)
            if "\n" in status_text and " DONE" in status_text:
                break
            if "CONNECT_FAILED" in status_text or "FATAL" in status_text:
                break
            time.sleep(3)
        codes = _parse_status(status_text)
        tail = status_text.strip().splitlines()[-4:]
        if codes.get("connect") not in (0, None) or "CONNECT_FAILED" in status_text:
            raise SnapshotError(
                "SDK connect failed: codes=%s status tail: %s"
                % (codes, tail))
        if codes.get("init") != 0:
            raise SnapshotError("SDK init/connect codes: %s status tail: %s"
                                % (codes, tail))
        if codes.get("connect") != 0:
            raise SnapshotError("SDK connect codes: %s status tail: %s"
                                % (codes, tail))
        if codes.get("mainPhotos", 0) < 1:
            raise SnapshotError(
                "no main still arrived (JSON_CMD_SNAPSHOT_IMG): codes=%s"
                % codes)
        if codes.get("subPhotos", 0) < 1:
            raise SnapshotError(
                "no sub still arrived: codes=%s" % codes)
        stills = _pull_stills(adb, dest_dir)
        timings["captureS"] = round(time.time() - t, 1)
    except Exception:
        failed = True
        if emu_proc is not None and emu_proc.poll() is None:
            if not status_text:
                try:
                    status_text = _harness_status(adb)
                except Exception:
                    pass
            _save_diagnostics(adb, status_text)
        raise
    finally:
        if failed and KEEP_RIG:
            _log("ACI_SNAPSHOT_KEEP_RIG=1 — rig left UP for inspection "
                 "(emulator pid %s, RAM disk %s); tear down manually"
                 % (emu_proc.pid if emu_proc else None, ram_device))
        else:
            _teardown(adb, emu_proc, ram_device)

    timings["totalS"] = round(time.time() - started, 1)
    taken_at = datetime.now(timezone.utc).isoformat()
    return {
        "path": stills["main"]["path"],
        "bytes": stills["main"]["bytes"],
        "taken_at": taken_at,
        "main": stills["main"],
        "sub": stills["sub"],
        "sdk": codes,
        "timings": timings,
        "rig": "ephemeral RAM-disk Android emulator + genuine vendor SDK "
               "(torn down after capture)",
        "note": "SDK-triggered stills are delivered to the session only; "
                "they do not appear in the cloud photo log.",
    }
