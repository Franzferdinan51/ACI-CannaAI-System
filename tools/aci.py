#!/usr/bin/env python3
"""aci - AC Infinity cloud API command line tool.

Unofficial API (the same one the AC Infinity mobile app uses), implemented
from the community reference client in dalinicus/homeassistant-acinfinity.

Auth: aci-login (run once, interactively) stores the account token at
~/.config/aci/token.json (mode 600). The password is never stored.

Commands:
  aci status                     all controllers: readings + port states
                                 (plus the AI program state on AI controllers)
  aci controllers                controller list with ids and types
  aci port <match> <n>           full mode settings for one port
  aci set <match> <n> --level N  set a port's on-speed (0-10)
  aci set <match> <n> --on       switch a port's mode to ON
  aci set <match> <n> --off      switch a port's mode to OFF
  aci ml <match>                 the AI (ML) program: state + targets
  aci tentwork <match>           start a TentWork session (a timed AI
                                 work burst; the AI stays ON after it)
  aci on <match>                 turn the AI program ON (state 1)
  aci pause <match>              pause the AI program (state 0) + all
                                 ports OFF - the tent goes idle and dark
  aci raw                        raw devInfoListAll JSON (debugging)

AI controllers (devType 20/21/22) run an "ML" program on top of the port
modes, and while it runs it overrides the port modes entirely. Its state
field is the real switch (decompiled from the app, v2.1.1): 0 = paused,
1 = AI running, 2 = TentWork session (which settles into state 1 when
the countdown ends). The app flips it by POSTing the whole program
record to /api/dev/ml as a form field map - but only the NetMlInfo wire
fields; echoing the GET record verbatim (extra keys, JSON lists) is
rejected with code 999999. The record is GET /api/dev/ml/byDevId/{devId};
the Tent Work button is PUT /api/dev/ml/tentWork?devId=...

<match> is a case-insensitive substring of the controller name, its
device code, or its full device id.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request

BASE = "https://www.acinfinityserver.com"
TOKEN_FILE = os.environ.get(
    "ACI_TOKEN_FILE", os.path.expanduser("~/.config/aci/token.json")
)
USER_AGENT = "okhttp/4.12.0"

AI_CONTROLLER_TYPES = {20, 21, 22}  # UIS 89 AI+, Outlet AI, Outlet AI+
CONTROLLER_TYPES = {
    11: "Controller 69 Pro (UIS)",
    18: "Controller 69 Pro+ (UIS)",
    20: "Controller AI+ (UIS 89)",
    21: "Controller Outlet AI",
    22: "Controller Outlet AI+",
}
AT_TYPES = {
    1: "OFF", 2: "ON", 3: "AUTO", 4: "TIMER_TO_ON", 5: "TIMER_TO_OFF",
    6: "CYCLE", 7: "SCHEDULE", 8: "VPD", 9: "CO2", 10: "CO2_FAN",
    11: "MOISTURE", 12: "WATER_TEMP", 13: "PH", 14: "EC", 15: "WATER_DETECT",
}

# Every key the API round-trips on a standard (addDevMode) control write.
# Mirrors DeviceControlKey in the reference client: a write must send the
# port's full current settings with only the intended fields changed.
DEVICE_CONTROL_KEYS = [
    "devId", "externalPort", "modeSetid", "modeType", "masterPort", "surplus",
    "onSpead", "offSpead", "onSelfSpead", "atType", "powerState", "power",
    "loadState", "loadType", "speak", "abnormalState", "toward",
    "schedStartTime", "schedEndtTime", "acitveTimerOn", "acitveTimerOff",
    "activeCycleOn", "activeCycleOff", "activeHtVpd", "activeHtVpdNums",
    "activeLtVpd", "activeLtVpdNums", "vpdstatus", "vpdnums", "vpdSettingMode",
    "targetVpd", "targetVpdSwitch", "isUpdateVpdNums", "devHt", "activeHt",
    "devLt", "activeLt", "temperature", "targetTemp", "targetTSwitch",
    "insideTemp", "outsideTemp", "devHtf", "devLtf", "temperatureF",
    "targetTempF", "devHh", "activeHh", "devLh", "activeLh", "humidity",
    "targetHumi", "targetHumiSwitch", "photocellSwitch", "trend", "tTrend",
    "hTrend", "insideTrend", "outsideTrend", "unit", "ecOrTds", "ecUnit",
    "tdsUnit", "ecTdsSettingMode", "ecTdsAccuracy", "ecTdsTargetSwitch",
    "isOpenAutomation", "settingMode", "onlyUpdateSpeed", "restore",
    "ecTdsTargetValueEcUs", "ecTdsTargetValueEcMs", "ecTdsTargetValueTdsPpm",
    "ecTdsTargetValueTdsPpt", "ecTdsHighSwitch", "ecTdsHighValueEcUs",
    "ecTdsHighValueEcMs", "ecTdsHighValueTdsPpm", "ecTdsHighValueTdsPpt",
    "ecTdsLowSwitchEc", "ecTdsLowSwitchTds", "ecTdsLowValueEcUs",
    "ecTdsLowValueEcMs", "ecTdsLowValueTdsPpm", "ecTdsLowValueTdsPpt",
    "phSettingMode", "phAccuracy", "phTargetSwitch", "phTargetValue",
    "phHighSwitch", "phHighValue", "phLowSwitch", "phLowValue",
    "co2SettingMode", "co2Accuracy", "co2TargetSwitch", "co2TargetValue",
    "co2HighSwitch", "co2HighValue", "co2LowSwitch", "co2LowValue",
    "co2FanSettingMode", "co2FanAccuracy", "co2FanTargetSwitch",
    "co2FanTargetValue", "co2FanHighSwitch", "co2FanHighValue",
    "co2FanLowSwitch", "co2FanLowValue", "moistureSettingMode",
    "moistureAccuracy", "moistureTargetSwitch", "moistureTargetValue",
    "moistureHighSwitch", "moistureHighValue", "moistureLowSwitch",
    "moistureLowValue", "waterLevelSettingMode", "waterLevelAccuracy",
    "waterLevelTargetSwitch", "waterLevelTargetValue", "waterLevelHighSwitch",
    "waterLevelHighValue", "waterLevelLowSwitch", "waterLevelLowValue",
    "waterTempSettingMode", "waterTempAccuracy", "waterTempTargetSwitch",
    "waterTempTargetValue", "waterTempHighSwitch", "waterTempHighValue",
    "waterTempLowSwitch", "waterTempLowValue", "waterTempTargetValueF",
    "waterTempHighValueF", "waterTempLowValueF",
    "devSetting",
]

# Keys round-tripped on an AI-controller (modeAndSetting) write.
MODE_AND_SETTING_KEYS = [
    "devId", "port", "externalPort", "modeType", "masterPort",
    "modeAndSettingIdStr", "subDeviceId", "subDeviceType", "subDeviceVersion",
    "devCompany", "loadType", "powerState", "power", "loadState", "speak",
    "abnormalState", "toward", "onSpead", "offSpead", "onSelfSpead", "atType",
    "surplus", "schedStartTime", "schedEndtTime", "acitveTimerOn",
    "acitveTimerOff", "activeCycleOn", "activeCycleOff", "activeHtVpd",
    "activeHtVpdNums", "activeLtVpd", "activeLtVpdNums", "vpdstatus",
    "vpdnums", "vpdSettingMode", "targetVpd", "targetVpdSwitch",
    "isUpdateVpdNums", "devHt", "activeHt", "devLt", "activeLt", "temperature",
    "targetTemp", "targetTSwitch", "insideTemp", "outsideTemp", "devHtf",
    "devLtf", "temperatureF", "targetTempF", "devHh", "activeHh", "devLh",
    "activeLh", "humidity", "targetHumi", "targetHumiSwitch", "trend",
    "tTrend", "hTrend", "insideTrend", "outsideTrend", "unit", "isOpenAutomation",
    "settingMode", "onlyUpdateSpeed", "restore", "onTimeSwitch", "onTime",
    "onMinTime", "onMaxTime", "isOnMinMaxTime", "offDoseTime", "onDoseTime",
    "isOpenDoseTime", "photocellSwitch", "devLight",
]

# modeAndSettingIdStr per mode, from the reference client.
AI_MODE_IDS = {
    1: "[16,17]",        # OFF
    2: "[16,18]",        # ON
    3: "[112,16,19,32,98,99]",  # AUTO
    4: "[16,20,21]", 5: "[16,20,21]",   # TIMER
    6: "[16,22,23,40]", 7: "[16,22,23,40]",  # CYCLE / SCHEDULE
    8: "[16,81,32,98,99]",      # VPD
}


class ACIError(Exception):
    pass


def _request(method, path, data=None, token=None, min_version=False):
    url = BASE + path
    body = None
    headers = {"User-Agent": USER_AGENT}
    if token:
        headers["token"] = token
    if min_version:
        headers["minversion"] = "3.5"
    if data is not None:
        body = urllib.parse.urlencode(data).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = json.loads(resp.read().decode())
    except Exception as exc:  # network, HTTP, JSON
        raise ACIError("request to %s failed: %s" % (path, exc))
    if payload.get("code") != 200:
        raise ACIError("API error on %s: %s" % (path, json.dumps(payload)[:300]))
    return payload


def load_token():
    if not os.path.exists(TOKEN_FILE):
        raise ACIError(
            "no token yet - run aci-login once on the Mac "
            "(it prompts for the AC Infinity password and stores only the token)"
        )
    with open(TOKEN_FILE) as fh:
        return json.load(fh)["user_id"]


def get_controllers(token):
    body = _request(
        "POST", "/api/user/devInfoListAll", {"userId": token}, token=token
    )
    return body["data"] or []


def get_mode_settings(token, dev_id, port):
    body = _request(
        "POST", "/api/dev/getdevModeSettingList",
        {"devId": dev_id, "port": port}, token=token,
    )
    return body["data"] or {}


def find_controller(controllers, match):
    m = match.lower()
    hits = [
        c for c in controllers
        if m in str(c.get("devName", "")).lower()
        or m in str(c.get("devCode", "")).lower()
        or m == str(c.get("devId", "")).lower()
    ]
    if not hits:
        raise ACIError("no controller matches %r" % match)
    if len(hits) > 1:
        names = ", ".join(str(c.get("devName")) for c in hits)
        raise ACIError("%r matches several controllers: %s" % (match, names))
    return hits[0]


def _hundredths(value):
    try:
        return float(value) / 100.0
    except (TypeError, ValueError):
        return None


def fmt_readings(info):
    temp_f = _hundredths(info.get("temperatureF"))
    if temp_f is None:
        temp_c = _hundredths(info.get("temperature"))
        temp_f = None if temp_c is None else temp_c * 9.0 / 5.0 + 32.0
    hum = _hundredths(info.get("humidity"))
    vpd = _hundredths(info.get("vpdnums"))
    # controllers with no probe attached report sentinel garbage
    if (temp_f is not None and not -100.0 < temp_f < 200.0) or (
        hum is not None and not 0.0 <= hum <= 100.0
    ):
        return "sensors not reporting (no probe data)"
    parts = []
    if temp_f is not None:
        parts.append("%.1fF" % temp_f)
    if hum is not None:
        parts.append("%.1f%% RH" % hum)
    if vpd is not None:
        parts.append("VPD %.2f kPa" % vpd)
    return ", ".join(parts) if parts else "no readings"


def cmd_status(token):
    for c in get_controllers(token):
        info = c.get("deviceInfo") or {}
        online = "online" if c.get("online") else "OFFLINE"
        print("%s [%s] (%s)" % (c.get("devName"), c.get("devCode"), online))
        print("  %s" % fmt_readings(info))
        for p in info.get("ports") or []:
            state = "on" if p.get("loadState") else "off"
            print(
                "  port %s: %-16s level %s (%s)%s"
                % (
                    p.get("port"),
                    p.get("portName") or "unnamed",
                    p.get("speak"),
                    state,
                    "" if p.get("online", 1) else " - port offline",
                )
            )
        for s in info.get("sensors") or []:
            print("  sensor: %s" % fmt_sensor(s))
        if c.get("devType") in AI_CONTROLLER_TYPES:
            try:
                print("  %s" % fmt_ml_line(get_ml(token, c["devId"])))
            except ACIError:
                pass


SENSOR_TYPES = {
    0: "probe temp F", 1: "probe temp C", 2: "probe humidity %",
    3: "probe VPD kPa", 4: "controller temp F", 5: "controller temp C",
    6: "controller humidity %", 7: "controller VPD kPa", 10: "soil %",
    11: "CO2 ppm", 12: "light", 20: "water detect",
}


def fmt_sensor(s):
    raw = s.get("sensorData")
    precision = s.get("sensorPrecision") or 0
    value = raw
    if isinstance(raw, (int, float)) and precision > 1:
        value = raw / (10 ** (precision - 1))
    return "port %s %s: %s" % (
        s.get("accessPort"),
        SENSOR_TYPES.get(s.get("sensorType"), "type %s" % s.get("sensorType")),
        value,
    )


def cmd_controllers(token):
    for c in get_controllers(token):
        print(
            "%s | id %s | code %s | %s | fw %s | %s"
            % (
                c.get("devName"),
                c.get("devId"),
                c.get("devCode"),
                CONTROLLER_TYPES.get(c.get("devType"), "type %s" % c.get("devType")),
                c.get("firmwareVersion"),
                "online" if c.get("online") else "OFFLINE",
            )
        )


def cmd_port(token, match, port):
    c = find_controller(get_controllers(token), match)
    data = get_mode_settings(token, c["devId"], port)
    at = data.get("atType")
    print("%s port %s" % (c.get("devName"), port))
    print("  mode: %s (atType %s)" % (AT_TYPES.get(at, "?"), at))
    for key in (
        "onSpead", "offSpead", "speak", "powerState", "loadState",
        "devHtf", "devLtf", "devHh", "devLh", "targetTempF", "targetHumi",
        "targetVpd", "isOpenAutomation",
    ):
        if key in data:
            print("  %s: %s" % (key, data[key]))
    known = set(DEVICE_CONTROL_KEYS) | set(MODE_AND_SETTING_KEYS)
    known |= {"devSetting", "port"}
    extras = sorted(k for k in data if k not in known)
    if extras:
        print("  other keys: %s" % ", ".join(extras))
    print(json.dumps(data, indent=1, sort_keys=True))


# ---------------------------------------------------------------- AI (ML)

# ML program states (Controller AI+, devType 20) - the app's own state
# machine (DetailModel.onOnExecute / onPauseExecute / onTentWorkExecute):
# 0 = paused, 1 = AI running, 2 = TentWork session (settles into 1).
ML_STATES = {0: "paused - AI idle", 1: "AI running", 2: "TentWork ACTIVE"}

# The fields the app sends when it saves the program record
# (NetMlInfo wire bean). The server rejects the write (code 999999) if
# the GET record is echoed verbatim; lists ride as *Str JSON companions.
ML_WIRE_FIELDS = """
aiInsightMapStr aiSelectMode aiSelectModeUpdatedTime clipFanLevelRaisedTime
dayOrNight devId durationTime dynamicSunCollection dynamicSunStartTime
enCtrNight endTimeNight growBoxGrade growLightLevelDimmedTime growStageSeq
highHumiDurationTime highHumiStartTime highTempDurationTime
highTempStartTime humidEmergency humidEmergencyNight humidFirst
humidFirstNight idealCo2LevelsTime id interchangeForStop interchangeSensor
isDel likeType modeType name pauseReason plantType portDetailsStr
portSelected portSensorsStr runMode sensorType seq smartCo2Monitoring
startTime startTimeNight state sunStartCollectingTime targetCo2
targetHighHumi targetHighHumiNight targetHighTemp targetHighTempF
targetHighTempFNight targetHighTempNight targetHighVpd targetHighVpdNight
targetLighting targetLowHumi targetLowHumiNight targetLowTemp
targetLowTempF targetLowTempFNight targetLowTempNight targetLowVpd
targetLowVpdNight tempEmergency tempEmergencyNight tempFirst
tempFirstNight tempTargetHigh tempTargetHighF tempTargetLow tempTargetLowF
tentWorkTimeRemaining tentworkTime unit updatedTime vpdEmergHighHumi
vpdEmergHighHumiNight vpdEmergHighTemp vpdEmergHighTempF
vpdEmergHighTempFNight vpdEmergHighTempNight vpdEmergLowHumi
vpdEmergLowHumiNight vpdEmergLowTemp vpdEmergLowTempF
vpdEmergLowTempFNight vpdEmergLowTempNight vpdTargetHighHumiDay
vpdTargetHighHumiNight vpdTargetHighTempDay vpdTargetHighTempFDay
vpdTargetHighTempFNight vpdTargetHighTempNight vpdTargetLowHumiDay
vpdTargetLowHumiNight vpdTargetLowTempDay vpdTargetLowTempFDay
vpdTargetLowTempFNight vpdTargetLowTempNight
""".split()

ML_WATCH_FIELDS = (
    "targetLowTemp", "targetHighTemp", "targetLowHumi", "targetHighHumi",
    "targetLowVpd", "targetHighVpd", "portSelected", "tentworkTime",
    "aiSelectMode", "tempFirst", "enCtrNight",
)


def set_ml_state(token, dev_id, state):
    """Save the ML record back with a new state - the app's pause/on.
    Verifies the state landed and no watched setting moved."""
    rec = get_ml(token, dev_id)
    if rec is None:
        raise ACIError("no ML program record for devId %s" % dev_id)
    form = {}
    for key in ML_WIRE_FIELDS:
        if key in rec and rec[key] is not None:
            form[key] = rec[key]
    if "portDetails" in rec and "portDetailsStr" not in form:
        form["portDetailsStr"] = json.dumps(
            rec["portDetails"], separators=(",", ":"))
    if "portSensors" in rec and "portSensorsStr" not in form:
        form["portSensorsStr"] = json.dumps(
            rec["portSensors"], separators=(",", ":"))
    for key, value in list(form.items()):
        if isinstance(value, bool):
            form[key] = "true" if value else "false"
        elif not isinstance(value, str):
            form[key] = str(value)
    form["state"] = str(state)
    _request("POST", "/api/dev/ml", form, token=token)
    after = get_ml(token, dev_id) or {}
    if after.get("state") != state:
        raise ACIError(
            "ML state write did not land (reads %s, wanted %s)"
            % (after.get("state"), state))
    for key in ML_WATCH_FIELDS:
        if rec.get(key) != after.get(key):
            raise ACIError(
                "ML setting %s changed during state write: %s -> %s"
                % (key, rec.get(key), after.get(key)))
    return after


def get_ml(token, dev_id):
    body = _request("GET", "/api/dev/ml/byDevId/%s" % dev_id, token=token)
    data = body.get("data") or []
    return data[0] if data else None


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


def cmd_ml(token, match):
    c = find_controller(get_controllers(token), match)
    rec = get_ml(token, c["devId"])
    print("%s" % c.get("devName"))
    if rec is None:
        print("  no ML program record (not an AI controller?)")
        return
    print("  %s" % fmt_ml_line(rec))
    print(
        "  session length %s min, pauseReason %s"
        % (rec.get("tentworkTime"), rec.get("pauseReason"))
    )
    selected = rec.get("portSelected") or 0
    ports = [str(i + 1) for i in range(8) if selected & (1 << i)]
    print("  AI-selected ports: %s" % (", ".join(ports) or "none"))
    print(
        "  night targets %s-%sF, %s-%s%% RH (night control %s)"
        % (
            rec.get("targetLowTempFNight"), rec.get("targetHighTempFNight"),
            rec.get("targetLowHumiNight"), rec.get("targetHighHumiNight"),
            "on" if rec.get("enCtrNight") else "off",
        )
    )


def cmd_tentwork(token, match):
    import time

    c = find_controller(get_controllers(token), match)
    dev_id = c["devId"]
    _request("PUT", "/api/dev/ml/tentWork?devId=%s" % dev_id, token=token)
    rec = {}
    for attempt in range(7):
        rec = get_ml(token, dev_id) or {}
        if rec.get("state") == 2:
            break
        if attempt < 6:
            time.sleep(10)
    print("%s: %s" % (c.get("devName"), fmt_ml_line(rec)))
    if rec.get("state") == 2:
        print("note: when the session ends the AI stays ON (state 1); "
              "use 'aci pause' to stop it")
    if rec.get("state") != 2:
        print(
            "WARNING: TentWork did not read back as active after ~60s",
            file=sys.stderr,
        )


def cmd_pause(token, match):
    import time

    controllers = get_controllers(token)
    c = find_controller(controllers, match)
    try:
        rec = get_ml(token, c["devId"])
    except ACIError:
        rec = None
    if rec is not None:
        set_ml_state(token, c["devId"], 0)
    info = c.get("deviceInfo") or {}
    ports = [
        p.get("port")
        for p in info.get("ports") or []
        if p.get("online", 1) and p.get("port") is not None
    ]
    for port in ports:
        cmd_set(token, match, port, {"atType": 1})
    if rec is not None:
        print("%s: AI program paused (state 0), all ports OFF."
              % c.get("devName"))
    else:
        print("%s: paused - all ports OFF." % c.get("devName"))
    time.sleep(5)
    cmd_status(token)


def cmd_on(token, match):
    controllers = get_controllers(token)
    c = find_controller(controllers, match)
    try:
        rec = get_ml(token, c["devId"])
    except ACIError:
        rec = None
    if rec is None:
        raise ACIError(
            "%s has no AI program - use 'aci set %s <port> --on' instead"
            % (c.get("devName"), match))
    after = set_ml_state(token, c["devId"], 1)
    print("%s: %s" % (c.get("devName"), fmt_ml_line(after)))


def _transfer(keys, new_values, existing):
    updated = {}
    for key in keys:
        value = new_values.get(key, existing.get(key, 0))
        if value is None:
            updated[key] = 0
        elif isinstance(value, (dict, list)):
            updated[key] = json.dumps(value)
        elif isinstance(value, bool):
            updated[key] = str(value).lower()
        else:
            updated[key] = value
    return updated


def cmd_set(token, match, port, overrides):
    c = find_controller(get_controllers(token), match)
    dev_id = c["devId"]
    existing = get_mode_settings(token, dev_id, port)
    if c.get("devType") in AI_CONTROLLER_TYPES:
        flat = dict(existing.get("devSetting") or {})
        flat.update(existing)
        new_values = dict(overrides)
        at = new_values.get("atType", flat.get("atType"))
        if at in AI_MODE_IDS:
            new_values["modeAndSettingIdStr"] = AI_MODE_IDS[at]
        updated = _transfer(MODE_AND_SETTING_KEYS, new_values, flat)
        updated["devId"] = dev_id
        updated["port"] = port
        query = urllib.parse.urlencode(updated)
        _request(
            "PUT", "/api/dev/modeAndSetting?" + query,
            token=token, min_version=True,
        )
    else:
        updated = _transfer(DEVICE_CONTROL_KEYS, overrides, existing)
        updated["devId"] = dev_id
        if not updated.get("externalPort"):
            updated["externalPort"] = port
        query = urllib.parse.urlencode(updated)
        _request("POST", "/api/dev/addDevMode?" + query, token=token)
    # verify on the server, not on our own say-so. Mode writes sync
    # through the cloud slowly (observed ~1 min), so poll for a while
    # before believing either success or failure.
    import time

    want_at = overrides.get("atType")
    after = {}
    for attempt in range(7):
        after = get_mode_settings(token, dev_id, port)
        if want_at is None or after.get("atType") == want_at:
            break
        if attempt < 6:
            time.sleep(15)
    print(
        "%s port %s now: mode %s (atType %s), onSpead %s"
        % (
            c.get("devName"), port,
            AT_TYPES.get(after.get("atType"), "?"), after.get("atType"),
            after.get("onSpead"),
        )
    )
    if want_at is not None and after.get("atType") != want_at:
        print(
            "WARNING: read-back still shows atType %s after ~90s - "
            "the write may not have taken" % after.get("atType"),
            file=sys.stderr,
        )


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd = argv[1]
    try:
        token = load_token()
        if cmd == "status":
            cmd_status(token)
        elif cmd == "controllers":
            cmd_controllers(token)
        elif cmd == "raw":
            print(json.dumps(get_controllers(token), indent=1, sort_keys=True))
        elif cmd == "ml":
            cmd_ml(token, argv[2])
        elif cmd == "tentwork":
            cmd_tentwork(token, argv[2])
        elif cmd == "on":
            cmd_on(token, argv[2])
        elif cmd == "pause":
            cmd_pause(token, argv[2])
        elif cmd == "port":
            cmd_port(token, argv[2], int(argv[3]))
        elif cmd == "set":
            match, port = argv[2], int(argv[3])
            overrides = {}
            args = argv[4:]
            i = 0
            while i < len(args):
                if args[i] == "--level":
                    overrides["onSpead"] = int(args[i + 1])
                    i += 2
                elif args[i] == "--on":
                    overrides["atType"] = 2
                    i += 1
                elif args[i] == "--auto":
                    overrides["atType"] = 3
                    i += 1
                elif args[i] == "--off":
                    overrides["atType"] = 1
                    i += 1
                else:
                    raise ACIError("unknown set option %r" % args[i])
            if not overrides:
                raise ACIError("set needs --level N, --on, --off, or --auto")
            cmd_set(token, match, port, overrides)
        else:
            print(__doc__)
            return 2
    except ACIError as exc:
        print("aci: %s" % exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
