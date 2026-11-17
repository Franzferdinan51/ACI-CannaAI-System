#!/usr/bin/env python3
"""ac-infinity MCP server — AC Infinity controllers + Spectron 7 camera.

A Model Context Protocol server over stdio (newline-delimited JSON-RPC 2.0),
implemented with the Python standard library ONLY — no pip dependencies, so
it runs on any python3 >= 3.9 (system python on macOS included).

Read-only by design: every tool only reads from the AC Infinity cloud API.
There are no control/write tools.

Cloud API: https://www.acinfinityserver.com (the same unofficial API the
AC Infinity mobile app uses; see ../SPECTRON-IPC.md for the full dossier).
Auth: header `token` = the `user_id` value in the token file
(env ACI_TOKEN_FILE, default ~/.config/aci/token.json). The token is read
at runtime on each call and is NEVER printed or logged.

Tools:
  aci_status        all controllers: readings + port names/levels
  spectron_sensors  Spectron 7 sensor snapshot (thermal + climate) in
                    human units
  spectron_photos   cloud photo log (day-aligned windows, deduped);
                    optionally downloads the JPEGs
  spectron_snapshot STUB — on-demand P2P snapshot is not available yet;
                    returns a structured "experimental" result. The real
                    client drops into p2p_client.py (same directory).

Run:  python3 server.py        (speaks MCP on stdin/stdout; logs to stderr)
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

BASE = "https://www.acinfinityserver.com"
TOKEN_FILE = os.environ.get(
    "ACI_TOKEN_FILE", os.path.expanduser("~/.config/aci/token.json")
)
USER_AGENT = "okhttp/4.12.0"
CAMERA_DEV_ID = os.environ.get("ACI_CAMERA_DEV_ID", "")  # Spectron 7 — your camera's devId (see README: Setup)
SERVER_NAME = "ac-infinity"
SERVER_VERSION = "1.0.0"
DEFAULT_PROTOCOL = "2024-11-05"

# Album/photo queries use the camera's day; ET day windows are the proven
# shape (see aci-photos.py / SPECTRON-IPC.md). Fixed -05:00 offset matches
# the existing tool exactly.
ET = timezone(timedelta(hours=-5))

AI_CONTROLLER_TYPES = {20, 21, 22}
CONTROLLER_TYPES = {
    11: "Controller 69 Pro (UIS)",
    18: "Controller 69 Pro+ (UIS)",
    20: "Controller AI+ (UIS 89)",
    21: "Controller Outlet AI",
    22: "Controller Outlet AI+",
    10001: "Spectron camera (IPC)",
}
SENSOR_TYPES = {
    0: "probe temp F", 1: "probe temp C", 2: "probe humidity %",
    3: "probe VPD kPa", 4: "controller temp F", 5: "controller temp C",
    6: "controller humidity %", 7: "controller VPD kPa", 10: "soil %",
    11: "CO2 ppm", 12: "light", 20: "water detect",
}
ML_STATES = {0: "paused - AI idle", 1: "AI running", 2: "TentWork ACTIVE"}


def log(*args):
    """Diagnostics go to stderr only — stdout is the MCP channel."""
    print("[ac-infinity-mcp]", *args, file=sys.stderr, flush=True)


class ACIError(Exception):
    pass


# --------------------------------------------------------------------------
# Cloud API (read-only)
# --------------------------------------------------------------------------

def load_token():
    if not os.path.exists(TOKEN_FILE):
        raise ACIError(
            "no token file at %s — run aci-login once on this machine "
            "(it stores only the token)" % TOKEN_FILE
        )
    with open(TOKEN_FILE) as fh:
        data = json.load(fh)
    token = data.get("user_id")
    if not token:
        raise ACIError("token file %s has no user_id value" % TOKEN_FILE)
    return token


def _request(method, path, data=None, token=None, timeout=15):
    """Form/query POST-or-GET against the cloud API (aci.py semantics)."""
    url = BASE + path
    body = None
    headers = {"User-Agent": USER_AGENT}
    if token:
        headers["token"] = token
    if data is not None:
        body = urllib.parse.urlencode(data).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode())
    except Exception as exc:  # network, HTTP, JSON — never includes the token
        raise ACIError("request to %s failed: %s" % (path, exc))
    if payload.get("code") != 200:
        raise ACIError(
            "API error on %s: code %s" % (path, payload.get("code"))
        )
    return payload


def _ipc_post(path, params, token, timeout=30):
    """IPC reads: POST, params in the QUERY STRING, empty body.

    Do NOT send a minversion header here — it reroutes /api/ipc/* to a
    gateway that 404s them (SPECTRON-IPC.md).
    """
    url = BASE + path + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url, data=b"", method="POST", headers={"token": token}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode())
    except Exception as exc:
        raise ACIError("request to %s failed: %s" % (path, exc))
    if payload.get("code") != 200:
        raise ACIError(
            "API error on %s: code %s" % (path, payload.get("code"))
        )
    return payload


def get_controllers(token):
    body = _request(
        "POST", "/api/user/devInfoListAll", {"userId": token}, token=token
    )
    return body.get("data") or []


def get_ml(token, dev_id):
    body = _request("GET", "/api/dev/ml/byDevId/%s" % dev_id, token=token)
    data = body.get("data") or []
    return data[0] if data else None


# --------------------------------------------------------------------------
# Value helpers (API sensor fields are x100 ints)
# --------------------------------------------------------------------------

def _hundredths(value):
    try:
        return float(value) / 100.0
    except (TypeError, ValueError):
        return None


def _c_to_f(celsius):
    return None if celsius is None else celsius * 9.0 / 5.0 + 32.0


def fmt_readings(info):
    """Mirror of aci.py fmt_readings, returning (text, structured)."""
    temp_f = _hundredths(info.get("temperatureF"))
    if temp_f is None:
        temp_f = _c_to_f(_hundredths(info.get("temperature")))
    hum = _hundredths(info.get("humidity"))
    vpd = _hundredths(info.get("vpdnums"))
    structured = {
        "temperatureF": temp_f,
        "temperatureC": _hundredths(info.get("temperature")),
        "humidityPct": hum,
        "vpdKpa": vpd,
    }
    # Controllers with no probe attached report sentinel garbage.
    if (temp_f is not None and not -100.0 < temp_f < 200.0) or (
        hum is not None and not 0.0 <= hum <= 100.0
    ):
        return "sensors not reporting (no probe data)", structured
    parts = []
    if temp_f is not None:
        parts.append("%.1fF" % temp_f)
    if hum is not None:
        parts.append("%.1f%% RH" % hum)
    if vpd is not None:
        parts.append("VPD %.2f kPa" % vpd)
    return (", ".join(parts) if parts else "no readings"), structured


def fmt_sensor(s):
    raw = s.get("sensorData")
    precision = s.get("sensorPrecision") or 0
    value = raw
    if isinstance(raw, (int, float)) and precision > 1:
        value = raw / (10 ** (precision - 1))
    return {
        "accessPort": s.get("accessPort"),
        "sensorType": s.get("sensorType"),
        "sensorTypeName": SENSOR_TYPES.get(
            s.get("sensorType"), "type %s" % s.get("sensorType")
        ),
        "value": value,
    }


def fmt_ml_line(rec):
    if rec is None:
        return "AI: no program record"
    state = rec.get("state")
    label = ML_STATES.get(state, "state %s" % state)
    parts = ["AI: %s" % label]
    if state == 2:
        left = rec.get("tentWorkTimeRemaining") or 0
        parts.append("%d:%02d left in session" % (left // 60, left % 60))
    parts.append(
        "targets %s-%sF, %s-%s%% RH, VPD %.2f-%.2f"
        % (
            rec.get("targetLowTempF"), rec.get("targetHighTempF"),
            rec.get("targetLowHumi"), rec.get("targetHighHumi"),
            (rec.get("targetLowVpd") or 0) / 100.0,
            (rec.get("targetHighVpd") or 0) / 100.0,
        )
    )
    return ", ".join(parts)


# --------------------------------------------------------------------------
# Tools
# --------------------------------------------------------------------------

def tool_aci_status(_args):
    token = load_token()
    controllers = get_controllers(token)
    out_controllers = []
    lines = []
    for c in controllers:
        info = c.get("deviceInfo") or {}
        readings_text, readings = fmt_readings(info)
        ports = []
        for p in info.get("ports") or []:
            ports.append({
                "port": p.get("port"),
                "name": p.get("portName") or "unnamed",
                "level": p.get("speak"),
                "on": bool(p.get("loadState")),
                "online": bool(p.get("online", 1)),
            })
        sensors = [fmt_sensor(s) for s in info.get("sensors") or []]
        entry = {
            "name": c.get("devName"),
            "devId": str(c.get("devId")),
            "devCode": c.get("devCode"),
            "devType": c.get("devType"),
            "devTypeName": CONTROLLER_TYPES.get(
                c.get("devType"), "type %s" % c.get("devType")
            ),
            "online": bool(c.get("online")),
            "firmwareVersion": c.get("firmwareVersion"),
            "readings": readings,
            "readingsText": readings_text,
            "ports": ports,
            "sensors": sensors,
        }
        # Mirror aci.py status: AI controllers also report program state.
        if c.get("devType") in AI_CONTROLLER_TYPES:
            try:
                entry["aiProgram"] = fmt_ml_line(get_ml(token, c["devId"]))
            except ACIError:
                pass
        out_controllers.append(entry)

        lines.append(
            "%s [%s] (%s)"
            % (entry["name"], entry["devCode"],
               "online" if entry["online"] else "OFFLINE")
        )
        lines.append("  %s" % readings_text)
        for p in ports:
            lines.append(
                "  port %s: %-16s level %s (%s)%s"
                % (p["port"], p["name"], p["level"],
                   "on" if p["on"] else "off",
                   "" if p["online"] else " - port offline")
            )
        for s in sensors:
            lines.append(
                "  sensor: port %s %s: %s"
                % (s["accessPort"], s["sensorTypeName"], s["value"])
            )
        if "aiProgram" in entry:
            lines.append("  %s" % entry["aiProgram"])
    return {"controllers": out_controllers}, "\n".join(lines)


def find_camera(controllers, dev_id=None):
    """The camera is the `ipc` object inside a controller record."""
    want = str(dev_id or CAMERA_DEV_ID)
    for c in controllers:
        ipc = c.get("ipc")
        if isinstance(ipc, dict) and str(ipc.get("devId")) == want:
            return c, ipc
    # Fallback: any ipc object at all (single-camera account).
    for c in controllers:
        ipc = c.get("ipc")
        if isinstance(ipc, dict) and ipc.get("deviceInfo"):
            return c, ipc
    raise ACIError("Spectron camera (ipc object) not found in devInfoListAll")


def tool_spectron_sensors(args):
    token = load_token()
    parent, ipc = find_camera(get_controllers(token), args.get("dev_id"))
    info = ipc.get("deviceInfo") or {}
    thermal_c = {
        "center": _hundredths(info.get("thermalCenter")),
        "avg": _hundredths(info.get("thermalAvg")),
        "min": _hundredths(info.get("thermalMin")),
        "max": _hundredths(info.get("thermalMax")),
    }
    temp_c = _hundredths(info.get("temperature"))
    temp_f = _hundredths(info.get("temperatureF"))
    if temp_f is None:
        temp_f = _c_to_f(temp_c)
    leaf_c = thermal_c["center"]
    leaf_f = _hundredths(info.get("insideTempF"))
    if leaf_f is None:
        leaf_f = _c_to_f(leaf_c)
    result = {
        "camera": {
            "name": ipc.get("devName"),
            "devId": str(ipc.get("devId")),
            "devCode": ipc.get("devCode"),
            "online": bool(ipc.get("online")),
            "firmwareVersion": info.get("firmwareVersion") or ipc.get("firmwareVersion"),
            "parentController": parent.get("devName"),
            "parentDevId": str(parent.get("devId")),
        },
        "thermalSensorOnline": bool(info.get("thermalImagingSensorOnline")),
        "climateSensorOnline": bool(info.get("climateSensorOnline")),
        "thermalC": thermal_c,
        "thermalF": {k: _c_to_f(v) for k, v in thermal_c.items()},
        "leafTempC": leaf_c,
        "leafTempF": leaf_f,
        "airTempC": temp_c,
        "airTempF": temp_f,
        "humidityPct": _hundredths(info.get("humidity")),
        "leafVpdKpa": _hundredths(info.get("vpdnums")),
    }
    def f1(v):
        return "n/a" if v is None else "%.1f" % v
    text = (
        "Spectron 7 (parent: %s)\n"
        "  leaf (thermal center): %sF (%sC)  avg %sF  min %sF  max %sF\n"
        "  air: %sF (%sC), humidity %s%% RH, leaf VPD %s kPa\n"
        "  thermal sensor %s, climate sensor %s"
        % (
            result["camera"]["parentController"],
            f1(result["leafTempF"]), f1(result["leafTempC"]),
            f1(result["thermalF"]["avg"]), f1(result["thermalF"]["min"]),
            f1(result["thermalF"]["max"]),
            f1(result["airTempF"]), f1(result["airTempC"]),
            f1(result["humidityPct"]),
            "n/a" if result["leafVpdKpa"] is None
            else "%.2f" % result["leafVpdKpa"],
            "online" if result["thermalSensorOnline"] else "OFFLINE",
            "online" if result["climateSensorOnline"] else "OFFLINE",
        )
    )
    return result, text


def tool_spectron_photos(args):
    token = load_token()
    try:
        days = int(args.get("days") or 1)
    except (TypeError, ValueError):
        raise ACIError("days must be an integer")
    if days < 1 or days > 31:
        raise ACIError("days must be between 1 and 31")
    download_dir = args.get("download_dir") or None
    dev_id = str(args.get("dev_id") or CAMERA_DEV_ID)

    today = datetime.now(ET).replace(hour=0, minute=0, second=0, microsecond=0)
    found = {}
    for back in range(days):
        start = int((today - timedelta(days=back)).timestamp())
        # Day-aligned windows ONLY; categories overlap — dedupe by photoTime.
        for cat in range(6):
            resp = _ipc_post(
                "/api/ipc/photoLogs",
                {"devId": dev_id, "startTime": start,
                 "endTime": start + 86399, "category": cat},
                token,
            )
            for rec in resp.get("data") or []:
                if rec.get("photoTime") is not None:
                    found[rec["photoTime"]] = rec

    records = []
    for t in sorted(found):
        rec = found[t]
        dt_et = datetime.fromtimestamp(t, ET)
        records.append({
            "photoTime": t,
            "photoTimeISO": dt_et.isoformat(),
            "photoTimeUTC": datetime.fromtimestamp(
                t, timezone.utc).isoformat(),
            "downloadUrl": rec.get("downloadUrl"),
            "thumbsUrl": rec.get("thumbsUrl"),
            "rid": rec.get("rid"),
            "temp": rec.get("temp"),
        })

    downloaded = []
    if download_dir and records:
        os.makedirs(download_dir, exist_ok=True)
        for rec in records:
            if not rec["downloadUrl"]:
                continue
            name = os.path.join(
                download_dir, "spectron-%s.jpg" % rec["photoTime"])
            if not os.path.exists(name):
                urllib.request.urlretrieve(rec["downloadUrl"], name)
            rec["localPath"] = name
            downloaded.append(name)

    result = {
        "devId": dev_id,
        "days": days,
        "count": len(records),
        "photos": records,
        "downloadDir": download_dir,
        "downloaded": downloaded,
    }
    if records:
        lines = ["%d photo(s) in the last %d day(s):" % (len(records), days)]
        for rec in records:
            lines.append(
                "%s  %s" % (rec["photoTimeISO"], rec["downloadUrl"] or "")
            )
        if downloaded:
            lines.append("downloaded %d file(s) to %s"
                         % (len(downloaded), download_dir))
        text = "\n".join(lines)
    else:
        text = "no photos in window (last %d day(s))" % days
    return result, text


def tool_spectron_snapshot(args):
    """STUB: the P2P snapshot client lands in p2p_client.py later."""
    dev_id = str(args.get("dev_id") or CAMERA_DEV_ID)
    try:
        import p2p_client
        shot = p2p_client.snapshot(dev_id, args.get("download_dir"))
        result = {"available": True, "experimental": True, "snapshot": shot}
        return result, "snapshot captured: %s" % json.dumps(shot)
    except Exception as exc:  # P2PNotAvailable today; honest error later
        result = {
            "available": False,
            "experimental": True,
            "status": "not_available",
            "tool": "spectron_snapshot",
            "devId": dev_id,
            "message": "experimental: P2P snapshot not yet available",
            "detail": str(exc),
            "note": (
                "On-demand snapshots need the camera's P2P channel "
                "(JSON_CMD_SNAPSHOT_IMG over a TCP DevLgn/relay session). "
                "That client is phase-2 follow-up work and drops into "
                "p2p_client.py next to this server; no server change will "
                "be needed. Cloud photos are available now via "
                "spectron_photos."
            ),
        }
        return result, result["message"] + " — " + result["note"]


TOOLS = [
    {
        "name": "aci_status",
        "description": (
            "All AC Infinity controllers: inside readings (temp F, %RH, "
            "VPD) plus each port's name, level and on/off state. Mirrors "
            "`aci status`. Read-only."
        ),
        "inputSchema": {"type": "object", "properties": {},
                        "additionalProperties": False},
        "handler": tool_aci_status,
    },
    {
        "name": "spectron_sensors",
        "description": (
            "Spectron 7 camera sensor snapshot with human units: thermal "
            "center (= leaf temp) / avg / min / max, air temp, humidity "
            "and leaf VPD, from the camera's ipc object in devInfoListAll. "
            "Read-only."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "dev_id": {"type": "string",
                           "description": "Camera devId (defaults to the "
                                          "Spectron 7)."},
            },
            "additionalProperties": False,
        },
        "handler": tool_spectron_sensors,
    },
    {
        "name": "spectron_photos",
        "description": (
            "Spectron 7 cloud photo log. Queries day-aligned windows "
            "across categories 0-5 and dedupes by photoTime (the API "
            "silently returns [] for wide windows). Returns photoTime "
            "(epoch + ISO) and signed downloadUrl per photo; pass "
            "download_dir to also download the JPEGs. Read-only."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "default": 1, "minimum": 1,
                         "maximum": 31,
                         "description": "How many days back to query "
                                        "(including today)."},
                "download_dir": {"type": "string",
                                 "description": "Optional directory to "
                                                "download JPEGs into."},
                "dev_id": {"type": "string",
                           "description": "Camera devId (defaults to the "
                                          "Spectron 7)."},
            },
            "additionalProperties": False,
        },
        "handler": tool_spectron_photos,
    },
    {
        "name": "spectron_snapshot",
        "description": (
            "STUB / experimental: on-demand Spectron 7 snapshot over the "
            "P2P channel. Not yet available — returns a structured "
            "not_available result. Use spectron_photos for cloud photos."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "dev_id": {"type": "string",
                           "description": "Camera devId (defaults to the "
                                          "Spectron 7)."},
                "download_dir": {"type": "string",
                                 "description": "Where a future snapshot "
                                                "JPEG would be saved."},
            },
            "additionalProperties": False,
        },
        "handler": tool_spectron_snapshot,
    },
]
TOOL_MAP = {t["name"]: t for t in TOOLS}


# --------------------------------------------------------------------------
# MCP stdio transport (JSON-RPC 2.0, newline-delimited)
# --------------------------------------------------------------------------

def _result(req_id, result):
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _error(req_id, code, message):
    return {"jsonrpc": "2.0", "id": req_id,
            "error": {"code": code, "message": message}}


def handle(msg):
    """Return a response dict, or None for notifications."""
    method = msg.get("method")
    req_id = msg.get("id")
    params = msg.get("params") or {}

    if method == "initialize":
        proto = params.get("protocolVersion") or DEFAULT_PROTOCOL
        return _result(req_id, {
            "protocolVersion": proto,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        })
    if method == "ping":
        return _result(req_id, {})
    if method == "tools/list":
        return _result(req_id, {
            "tools": [
                {"name": t["name"], "description": t["description"],
                 "inputSchema": t["inputSchema"]}
                for t in TOOLS
            ]
        })
    if method == "tools/call":
        name = params.get("name")
        tool = TOOL_MAP.get(name)
        if tool is None:
            return _result(req_id, {
                "content": [{"type": "text",
                             "text": "unknown tool: %s" % name}],
                "isError": True,
            })
        args = params.get("arguments") or {}
        try:
            structured, text = tool["handler"](args)
            return _result(req_id, {
                "content": [{"type": "text", "text": text}],
                "structuredContent": structured,
                "isError": False,
            })
        except Exception as exc:
            log("tool %s failed: %s" % (name, exc))
            return _result(req_id, {
                "content": [{"type": "text",
                             "text": "%s: %s" % (type(exc).__name__, exc)}],
                "isError": True,
            })
    if method in ("resources/list",):
        return _result(req_id, {"resources": []})
    if method in ("prompts/list",):
        return _result(req_id, {"prompts": []})
    if req_id is None:
        return None  # notification (e.g. notifications/initialized)
    return _error(req_id, -32601, "method not found: %s" % method)


def main():
    log("starting (token file: %s)" % TOKEN_FILE)
    out = sys.stdout
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            out.write(json.dumps(_error(None, -32700, "parse error")) + "\n")
            out.flush()
            continue
        try:
            resp = handle(msg)
        except Exception as exc:  # never let one bad message kill the server
            log("handler error: %s" % exc)
            resp = _error(msg.get("id"), -32603, "internal error: %s" % exc)
        if resp is not None:
            out.write(json.dumps(resp) + "\n")
            out.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
