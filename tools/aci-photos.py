#!/usr/bin/env python3
"""aci-photos — pull Spectron 7 photos from the AC Infinity cloud API.

Contract (cracked 2026-11-16 by decompiling the app):
  POST https://www.acinfinityserver.com/api/ipc/photoLogs
       ?devId=<id>&startTime=<epoch s>&endTime=<epoch s>&category=<0..5>
  header: token = the user_id stored by aci-login (~/.config/aci/token.json).
  Empty POST body. Records carry downloadUrl / thumbsUrl / photoTime.

CRITICAL: the server only answers DAY-ALIGNED windows — one calendar day
per query, startTime = local midnight, endTime = start + 86399 (this is
exactly how the app's album queries). A wide multi-day window silently
returns []. Categories are overlapping filters (the same photo appears
under several), so dedupe by photoTime. Both the main camera and the
under-canopy (UVC) camera land in the same log.

Usage:
  aci-photos [--days N] [--download DIR]
"""
import argparse, json, os, time, urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta

BASE = "https://www.acinfinityserver.com"
CAM = os.environ.get("ACI_CAMERA_DEV_ID", "")  # Spectron 7 — your camera's devId (see README: Setup)
ET = timezone(timedelta(hours=-5))  # album queries use the camera's day;
# ET day windows verified to return the records.

def token():
    t = json.load(open(os.path.expanduser("~/.config/aci/token.json")))
    return t["user_id"]

def post(path, params):
    url = BASE + path + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, data=b"", method="POST",
                                 headers={"token": token()})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--download", metavar="DIR", default=None)
    a = ap.parse_args()
    today = datetime.now(ET).replace(hour=0, minute=0, second=0,
                                      microsecond=0)
    found = {}
    for back in range(a.days):
        start = int((today - timedelta(days=back)).timestamp())
        for cat in range(6):
            resp = post("/api/ipc/photoLogs",
                        {"devId": CAM, "startTime": start,
                         "endTime": start + 86399, "category": cat})
            for rec in resp.get("data") or []:
                found[rec["photoTime"]] = rec
    if not found:
        print("no photos in window")
        return
    for t in sorted(found):
        rec = found[t]
        ts = datetime.fromtimestamp(t, ET).strftime("%Y-%m-%d %H:%M:%S ET")
        print(f"{ts}  {rec.get('downloadUrl', '')[:80]}...")
    if a.download:
        os.makedirs(a.download, exist_ok=True)
        for t, rec in sorted(found.items()):
            name = os.path.join(a.download, f"spectron-{t}.jpg")
            if not os.path.exists(name):
                urllib.request.urlretrieve(rec["downloadUrl"], name)
            print("downloaded", name)

if __name__ == "__main__":
    main()
