#!/usr/bin/python3
"""AC Infinity dashboard feed -- API edition.

Writes ~/dashboard-bridge/acinfinity.json in the exact shape the old
Moto G scrape collector produced ({fetched_at, devices, alerts}), but
reads the controllers through the AC Infinity cloud API (the `aci`
tool's library) instead of foregrounding the AC Infinity app on the
phone. No phone, no ADB, no app flipping.

Replaced the scrape as the feed source on 2026-11-03 at the author's
order (the flipping was wigging out the Muse app on the Moto G).
The scrape script (~/bin/acinfinity-collect.sh) stays on disk as a
manual fallback. On any API failure this exits nonzero and leaves
the previous feed file untouched.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.expanduser("~/ac-infinity-tools"))
import aci  # noqa: E402

OUT = os.path.expanduser("~/dashboard-bridge/acinfinity.json")
# The phone app shows a prefixed device code; the API's devCode lacks
# the prefix. Keep the ids the dashboard has always seen.
ID_PREFIX = {"TENTCODE": "H-TENTCODE", "CHAMBERCODE": "G-CHAMBERCODE"}


def _outside(info):
    t = aci._hundredths(info.get("temperatureF"))
    if t is None:
        tc = aci._hundredths(info.get("temperature"))
        t = None if tc is None else tc * 9.0 / 5.0 + 32.0
    h = aci._hundredths(info.get("humidity"))
    v = aci._hundredths(info.get("vpdnums"))
    # No-probe controllers report sentinel garbage in deviceInfo; the
    # old feed shipped null for them (Clone Chamber outside == null).
    if (t is not None and not -100.0 < t < 200.0) or (
        h is not None and not 0.0 <= h <= 100.0
    ):
        return None
    if t is None and h is None and v is None:
        return None
    return {"temp_f": t, "rh": h, "vpd_kpa": v}


def _inside(info):
    # The probe on accessPort 1: sensorType 0 = temp F, 2 = humidity,
    # 3 = VPD (same decode as aci.fmt_sensor).
    inside = {"temp_f": None, "rh": None, "vpd_kpa": None}
    for s in info.get("sensors") or []:
        if s.get("accessPort") != 1:
            continue
        raw = s.get("sensorData")
        prec = s.get("sensorPrecision") or 0
        val = raw
        if isinstance(raw, (int, float)) and prec > 1:
            val = raw / (10 ** (prec - 1))
        st = s.get("sensorType")
        if st == 0:
            inside["temp_f"] = val
        elif st == 2:
            inside["rh"] = val
        elif st == 3:
            inside["vpd_kpa"] = val
    return inside


def _mode_label(token, dev_id, port, load_state):
    try:
        data = aci.get_mode_settings(token, dev_id, port)
        label = aci.AT_TYPES.get(data.get("atType"))
        if label:
            return label
    except Exception:
        pass
    return "ON" if load_state else "OFF"


def build(token):
    devices = []
    for c in aci.get_controllers(token):
        info = c.get("deviceInfo") or {}
        ports = []
        for p in sorted(info.get("ports") or [],
                        key=lambda x: x.get("port") or 0):
            n = p.get("port")
            if not p.get("online", 1):
                ports.append({"name": p.get("portName"), "mode": None,
                              "level": None, "port": n})
                continue
            ports.append({
                "name": p.get("portName"),
                "mode": _mode_label(token, c["devId"], n,
                                    p.get("loadState")),
                "level": p.get("speak"),
                "port": n,
            })
        code = c.get("devCode")
        devices.append({
            "name": c.get("devName"),
            "id": ID_PREFIX.get(code, code),
            "inside": _inside(info),
            "outside": _outside(info),
            "ports": ports,
        })
    return {"fetched_at": time.time(), "devices": devices, "alerts": []}


def main():
    token = aci.load_token()
    payload = build(token)
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump(payload, f)
    os.rename(tmp, OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
