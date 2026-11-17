#!/usr/bin/env python3
"""Pause the tent's AI program the way the app does:
POST /api/dev/ml with ONLY the NetMlInfo wire fields, state=0.
portDetails/portSensors go as their *Str JSON companions, like the app.
Everything else copied verbatim from the fresh GET record."""
import json, os, urllib.request, urllib.parse

BASE = "https://www.acinfinityserver.com"
DEVID = os.environ.get("ACI_TENT_DEV_ID", "")  # your controller's devId (see README: Setup)
tok = json.load(open("/Users/YOURNAME/.config/aci/token.json"))["user_id"]

WIRE = """aiInsightMapStr aiSelectMode aiSelectModeUpdatedTime clipFanLevelRaisedTime
dayOrNight devId durationTime dynamicSunCollection dynamicSunStartTime enCtrNight
endTimeNight growBoxGrade growLightLevelDimmedTime growStageSeq highHumiDurationTime
highHumiStartTime highTempDurationTime highTempStartTime humidEmergency
humidEmergencyNight humidFirst humidFirstNight idealCo2LevelsTime
interchangeForStop interchangeSensor isDel likeType modeType name pauseReason
plantType portDetailsStr portSelected portSensorsStr runMode sensorType seq
smartCo2Monitoring startTime startTimeNight state sunStartCollectingTime targetCo2
targetHighHumi targetHighHumiNight targetHighTemp targetHighTempF
targetHighTempFNight targetHighTempNight targetHighVpd targetHighVpdNight
targetLighting targetLowHumi targetLowHumiNight targetLowTemp targetLowTempF
targetLowTempFNight targetLowTempNight targetLowVpd targetLowVpdNight
tempEmergency tempEmergencyNight tempFirst tempFirstNight tempTargetHigh
tempTargetHighF tempTargetLow tempTargetLowF tentWorkTimeRemaining tentworkTime
unit updatedTime vpdEmergHighHumi vpdEmergHighHumiNight vpdEmergHighTemp
vpdEmergHighTempF vpdEmergHighTempFNight vpdEmergHighTempNight vpdEmergLowHumi
vpdEmergLowHumiNight vpdEmergLowTemp vpdEmergLowTempF vpdEmergLowTempFNight
vpdEmergLowTempNight vpdTargetHighHumiDay vpdTargetHighHumiNight
vpdTargetHighTempDay vpdTargetHighTempFDay vpdTargetHighTempFNight
vpdTargetHighTempNight vpdTargetLowHumiDay vpdTargetLowHumiNight
vpdTargetLowTempDay vpdTargetLowTempFDay vpdTargetLowTempFNight
vpdTargetLowTempNight id""".split()

def req(method, path, data=None):
    headers = {"User-Agent": "okhttp/4.12.0", "token": tok}
    body = None
    if data is not None:
        body = urllib.parse.urlencode(data).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    r = urllib.request.Request(BASE + path, data=body, headers=headers, method=method)
    with urllib.request.urlopen(r, timeout=15) as resp:
        return json.loads(resp.read().decode())

d = req("GET", "/api/dev/ml/byDevId/" + DEVID)
rec = (d.get("data") or [{}])[0]
print("GET keys:", " ".join(sorted(rec.keys())))
print("BEFORE state=%s updatedTime=%s" % (rec.get("state"), rec.get("updatedTime")))

form = {}
for k in WIRE:
    if k in rec and rec[k] is not None:
        form[k] = rec[k]
# lists ride as their *Str JSON companions, the way the app builds them
if "portDetails" in rec and "portDetailsStr" not in form:
    form["portDetailsStr"] = json.dumps(rec["portDetails"], separators=(",", ":"))
if "portSensors" in rec and "portSensorsStr" not in form:
    form["portSensorsStr"] = json.dumps(rec["portSensors"], separators=(",", ":"))
for k in form:
    if isinstance(form[k], bool):
        form[k] = "true" if form[k] else "false"
    elif not isinstance(form[k], str):
        form[k] = str(form[k])
form["state"] = "0"
print("sending %d fields" % len(form))

resp = req("POST", "/api/dev/ml", form)
print("POST resp:", json.dumps(resp)[:200])

d2 = req("GET", "/api/dev/ml/byDevId/" + DEVID)
rec2 = (d2.get("data") or [{}])[0]
print("AFTER state=%s" % rec2.get("state"))
for k in ("targetLowTemp", "targetHighTemp", "targetLowHumi", "targetHighHumi",
          "targetLowVpd", "targetHighVpd", "portSelected", "tentworkTime",
          "aiSelectMode", "tempFirst", "enCtrNight"):
    if rec.get(k) != rec2.get(k):
        print("CHANGED %s: %s -> %s" % (k, rec.get(k), rec2.get(k)))
print("settings-check done")
