#!/bin/bash
# acinfinity-collect.sh — scrape the AC Infinity app's DEVICES screen on
# the author's Moto G (adb YOUR_PHONE_SERIAL, USB) and write the readings to
# ~/dashboard-bridge/acinfinity.json for the dashboard bridge to serve.
#
# Politeness contract: only runs when the phone is awake AND unlocked
# (someone is around / the desk phone is in use), steals the foreground
# for ~6-8s, then relaunches whatever app was in front. When any gate
# fails it exits 0 without touching the phone or the JSON.
#
# Keyguard signal: `dumpsys trust` reports deviceLocked=0 for the
# current user when the keyguard is unlocked. Chosen over
# `dumpsys window policy` (KeyguardServiceDelegate showing=) because
# trust reflects the actual per-user lock state and stays correct when
# an app is showing over the lock screen.
#
# Alerts: the AC Infinity device DETAIL screen never reaches UI idle
# (live-updating charts), so uiautomator cannot dump it — verified
# 2026-10-12 with repeated attempts incl. --compressed. No alert text
# is parseable anywhere on the DEVICES screen or in Android
# notifications, so `alerts` ships as [] until a better source exists.
export PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin
SERIAL="YOUR_PHONE_SERIAL"
PKG="com.eternal.acinfinity"
OUT="$HOME/dashboard-bridge/acinfinity.json"
LOG="$HOME/acinfinity-collect.log"
XML_LOCAL="/tmp/acinfinity-dump.xml"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG"; }

# Gate 1: phone present on adb.
adb devices 2>/dev/null | grep -q "^${SERIAL}[[:space:]]*device" || exit 0

# Gate 2: screen awake.
adb -s "$SERIAL" shell dumpsys power 2>/dev/null | grep -q "mWakefulness=Awake" || exit 0

# Gate 3: keyguard unlocked (deviceLocked=0 for user 0).
adb -s "$SERIAL" shell dumpsys trust 2>/dev/null | grep -q "deviceLocked=0" || exit 0

# Remember the foreground package so we can hand it back.
PREV=$(adb -s "$SERIAL" shell dumpsys activity activities 2>/dev/null \
    | grep -m1 "topResumedActivity" \
    | sed -n 's/.* u0 \([^/ ]*\)\/.*/\1/p')

if [ "$PREV" != "$PKG" ]; then
    adb -s "$SERIAL" shell monkey -p "$PKG" -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1
    sleep 5
fi

adb -s "$SERIAL" shell uiautomator dump /sdcard/acinfinity.xml >/dev/null 2>&1
adb -s "$SERIAL" pull /sdcard/acinfinity.xml "$XML_LOCAL" >/dev/null 2>&1

# Hand the foreground back before doing any slow work.
if [ -n "$PREV" ] && [ "$PREV" != "$PKG" ]; then
    adb -s "$SERIAL" shell monkey -p "$PREV" -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1
fi

if [ ! -s "$XML_LOCAL" ]; then
    log "FAIL: no dump pulled"
    exit 1
fi

python3 - "$XML_LOCAL" "$OUT" <<'PYEOF'
import json, os, re, sys, time

xml_path, out_path = sys.argv[1], sys.argv[2]
try:
    xml = open(xml_path, encoding="utf-8", errors="replace").read()
except Exception as e:
    print(f"read failed: {e}", file=sys.stderr)
    sys.exit(1)

# uiautomator XML: scrape the text attributes in document order. The
# DEVICES screen lays out each device card as a flat sequence:
#   name, id, date stamp, LABEL value unit x6 (inside+outside) or x3
#   (plain layout), then port rows of name [mode] level.
tokens = [t for t in re.findall(r'text="([^"]*)"', xml) if t]

ID_RE = re.compile(r"^[A-Z]-[A-Z0-9]{4,}$")
DATE_RE = re.compile(r"^(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)"
                     r"\s+\d{1,2},\s+\d{4},")
PORT_RE = re.compile(r"^(\d+:\s+.+|Port\s+\d+)$")
MODES = {"AI", "OFF", "ON", "AUTO"}

ENV = {
    "INSIDE TEMP": ("inside", "temp_f"), "INSIDE HUMID": ("inside", "rh"),
    "INSIDE VPD": ("inside", "vpd_kpa"),
    "OUTSIDE TEMP": ("outside", "temp_f"),
    "OUTSIDE HUMID": ("outside", "rh"), "OUTSIDE VPD": ("outside", "vpd_kpa"),
    # Plain layout (no inside/outside split — sensors read as inside).
    "TEMPERATURE": ("inside", "temp_f"), "HUMIDITY": ("inside", "rh"),
    "VPD": ("inside", "vpd_kpa"),
}


def is_device_start(i):
    return (i + 2 < len(tokens)
            and ID_RE.match(tokens[i + 1]) is not None
            and DATE_RE.match(tokens[i + 2]) is not None)


def num(tok):
    if tok is None or tok == "--":
        return None
    try:
        return float(tok)
    except ValueError:
        return None


devices = []
i = 0
while i < len(tokens):
    if not is_device_start(i):
        i += 1
        continue
    name, dev_id = tokens[i], tokens[i + 1]
    j = i + 3  # skip the date stamp
    inside = {"temp_f": None, "rh": None, "vpd_kpa": None}
    outside = None
    ports = []
    # Environment triples: LABEL value unit.
    while j < len(tokens) and not PORT_RE.match(tokens[j]) \
            and not is_device_start(j):
        lab = tokens[j]
        if lab in ENV and j + 1 < len(tokens):
            scope, key = ENV[lab]
            if scope == "outside":
                if outside is None:
                    outside = {"temp_f": None, "rh": None, "vpd_kpa": None}
                outside[key] = num(tokens[j + 1])
            else:
                inside[key] = num(tokens[j + 1])
            j += 3
        else:
            j += 1
    # Port rows until the next device card.
    while j < len(tokens) and not is_device_start(j):
        if PORT_RE.match(tokens[j]):
            mnum = re.match(r"^(\d+):\s*", tokens[j])
            mport = re.match(r"^Port\s+(\d+)$", tokens[j])
            pnum = int(mnum.group(1)) if mnum else \
                (int(mport.group(1)) if mport else None)
            pname = re.sub(r"^\d+:\s*", "", tokens[j])
            mode, level = None, None
            k = j + 1
            if k < len(tokens) and tokens[k] in MODES:
                mode = tokens[k]
                k += 1
            if k < len(tokens) and (tokens[k].isdigit() or tokens[k] == "--"):
                level = None if tokens[k] == "--" else int(tokens[k])
                k += 1
            ports.append({"name": pname, "mode": mode, "level": level,
                          "port": pnum})
            j = k
        else:
            j += 1
    devices.append({"name": name, "id": dev_id, "inside": inside,
                    "outside": outside, "ports": ports})
    i = j

if not devices:
    print("no devices parsed", file=sys.stderr)
    sys.exit(1)

payload = {"fetched_at": time.time(), "devices": devices, "alerts": []}
tmp = out_path + ".tmp"
with open(tmp, "w") as f:
    json.dump(payload, f)
os.replace(tmp, out_path)
print(f"wrote {len(devices)} device(s): "
      + ", ".join(d["name"] for d in devices))
PYEOF
RC=$?
if [ $RC -eq 0 ]; then
    log "ok: $(python3 -c "import json;d=json.load(open('$OUT'));print(len(d['devices']),'devices')" 2>/dev/null || echo '?')"
    # Dual-post (best-effort): feed the same 3x3 Tent reading into
    # CannaAI's sensor store via POST /api/sensors/ac-infinity, whose
    # zod schema wants {deviceId, deviceName, temperature (F), humidity,
    # vpd?, ports?: [{port, speed?, mode?, on?}], timestamp?}. CannaAI's
    # /api/sensors then has real readings for the bridge's Grow flow.
    # A failure here never fails the collector — the JSON above is the
    # dashboard's source and is already written.
    POSTOUT=$(python3 - "$OUT" <<'POSTEOF'
import json, sys, urllib.request
from datetime import datetime, timezone

try:
    d = json.load(open(sys.argv[1]))
    dev = next((x for x in d["devices"] if x["name"] == "3x3 Tent"), None)
    if dev is None:
        dev = next((x for x in d["devices"]
                    if x["inside"].get("temp_f") is not None), None)
    ins = dev["inside"] if dev else {}
    if not dev or ins.get("temp_f") is None or ins.get("rh") is None:
        print("post: no complete tent reading, skipped")
        sys.exit(0)
    ports = []
    for p in dev.get("ports", []):
        if p.get("port") is None:
            continue
        entry = {"port": p["port"]}
        if p.get("level") is not None:
            entry["speed"] = p["level"]
            entry["on"] = p["level"] > 0
        if p.get("mode"):
            entry["mode"] = p["mode"]
            if p["mode"] == "OFF":
                entry["on"] = False
        ports.append(entry)
    payload = {
        "deviceId": dev.get("id"),
        "deviceName": dev.get("name"),
        "temperature": ins["temp_f"],
        "temperatureUnit": "F",
        "humidity": ins["rh"],
        "ports": ports,
        "timestamp": datetime.fromtimestamp(
            d["fetched_at"], timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    if ins.get("vpd_kpa") is not None:
        payload["vpd"] = ins["vpd_kpa"]
    req = urllib.request.Request(
        "http://GROWBOX_TAILNET_IP:3000/api/sensors/ac-infinity",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = json.loads(resp.read())
    print(f"post: cannaai ingest ok readingId={body.get('readingId')}")
except Exception as e:
    print(f"post: FAILED (best-effort): {e}")
POSTEOF
)
    log "$POSTOUT"
else
    log "FAIL: parser exit $RC (previous JSON kept)"
fi
exit $RC
