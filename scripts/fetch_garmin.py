"""
fetch_garmin.py
Pulls latest activities and sleep data from Garmin Connect
and writes JSON files used by the dashboard.
"""

import json
import os
import sys
from datetime import datetime, timedelta, date

# garminconnect is the community library for Garmin Connect API
try:
    from garminconnect import Garmin
except ImportError:
    print("Installing garminconnect...")
    os.system(f"{sys.executable} -m pip install garminconnect")
    from garminconnect import Garmin

# ── CREDENTIALS from environment variables (set in GitHub Secrets) ──────────
EMAIL    = os.environ.get("GARMIN_EMAIL")
PASSWORD = os.environ.get("GARMIN_PASSWORD")

if not EMAIL or not PASSWORD:
    print("ERROR: Set GARMIN_EMAIL and GARMIN_PASSWORD environment variables")
    sys.exit(1)

# ── DATE RANGE ────────────────────────────────────────────────────────────────
TODAY      = date.today()
START_DATE = date(2026, 4, 21)   # Oregon build start
END_DATE   = TODAY

print(f"Fetching Garmin data: {START_DATE} → {END_DATE}")

# ── LOGIN ─────────────────────────────────────────────────────────────────────
try:
    client = Garmin(EMAIL, PASSWORD)
    client.login()
    print("✓ Logged in to Garmin Connect")
except Exception as e:
    print(f"ERROR logging in: {e}")
    sys.exit(1)

# ── ACTIVITIES ────────────────────────────────────────────────────────────────
def disc(activity_type):
    t = str(activity_type).upper()
    if "SWIM" in t or "POOL" in t or "OPEN_WATER" in t: return "swim"
    if "CYCLING" in t or "VIRTUAL" in t or "BIKE" in t: return "bike"
    if "RUNNING" in t or "RUN" in t: return "run"
    return "other"

def safe_float(val, default=0):
    try: return round(float(val), 1) if val else default
    except: return default

try:
    raw_acts = client.get_activities_by_date(
        START_DATE.strftime("%Y-%m-%d"),
        END_DATE.strftime("%Y-%m-%d")
    )
    print(f"✓ Fetched {len(raw_acts)} activities")

    activities = []
    for a in raw_acts:
        act_type = a.get("activityType", {}).get("typeKey", "unknown")
        d = disc(act_type)
        activities.append({
            "date":     a.get("startTimeLocal", "")[:10],
            "title":    a.get("activityName", "Activity")[:40],
            "type":     act_type[:8],
            "disc":     d,
            "tss":      safe_float(a.get("trainingStressScore")),
            "np":       safe_float(a.get("normalizedPower")),
            "avgHR":    safe_float(a.get("averageHR")),
            "distance": safe_float(a.get("distance")),
            "duration": safe_float(a.get("duration")),
        })

    # Sort by date ascending
    activities.sort(key=lambda x: x["date"])

    # Write activities JSON
    os.makedirs("data", exist_ok=True)
    with open("data/activities.json", "w") as f:
        json.dump(activities, f, indent=2)
    print(f"✓ Wrote data/activities.json ({len(activities)} activities)")

except Exception as e:
    print(f"WARNING: Could not fetch activities: {e}")
    activities = []

# ── SLEEP DATA ────────────────────────────────────────────────────────────────
try:
    # Fetch last 60 days of sleep
    sleep_start = (TODAY - timedelta(days=60)).strftime("%Y-%m-%d")
    sleep_end   = TODAY.strftime("%Y-%m-%d")

    sleep_data = []
    current = TODAY - timedelta(days=60)
    while current <= TODAY:
        ds = current.strftime("%Y-%m-%d")
        try:
            s = client.get_sleep_data(ds)
            if s and s.get("dailySleepDTO"):
                dto = s["dailySleepDTO"]
                spo2 = 0
                if s.get("wellnessEpochSPO2DataDTOList"):
                    vals = [x.get("spo2Reading",0) for x in s["wellnessEpochSPO2DataDTOList"] if x.get("spo2Reading")]
                    spo2 = round(sum(vals)/len(vals), 1) if vals else 0

                total_sec = (dto.get("sleepTimeSeconds") or 0)
                deep_sec  = (dto.get("deepSleepSeconds") or 0)
                rem_sec   = (dto.get("remSleepSeconds") or 0)
                score     = dto.get("sleepScores", {})
                if isinstance(score, dict):
                    score = score.get("overallScore", 0)
                else:
                    score = 0

                sleep_data.append({
                    "date":     ds,
                    "score":    int(score) if score else 0,
                    "total":    round(total_sec/3600, 1),
                    "deep":     round(deep_sec/60),
                    "rem":      round(rem_sec/60),
                    "spo2":     spo2,
                    "rhr":      int(dto.get("restingHeartRate") or 0),
                })
        except Exception:
            pass
        current += timedelta(days=1)

    sleep_data = [s for s in sleep_data if s["score"] > 0 or s["total"] > 0]
    sleep_data.sort(key=lambda x: x["date"])

    with open("data/sleep.json", "w") as f:
        json.dump(sleep_data, f, indent=2)
    print(f"✓ Wrote data/sleep.json ({len(sleep_data)} nights)")

except Exception as e:
    print(f"WARNING: Could not fetch sleep data: {e}")

# ── SUMMARY STATS ─────────────────────────────────────────────────────────────
week_ranges = [
    (1,"2026-04-21","2026-04-27"), (2,"2026-04-28","2026-05-03"),
    (3,"2026-05-04","2026-05-10"), (4,"2026-05-11","2026-05-17"),
    (5,"2026-05-18","2026-05-24"), (6,"2026-05-25","2026-05-31"),
    (7,"2026-06-01","2026-06-07"), (8,"2026-06-08","2026-06-14"),
    (9,"2026-06-15","2026-06-21"), (10,"2026-07-13","2026-07-19"),
]

week_targets = {1:211,2:396,3:284,4:380,5:420,6:260,7:460,8:500,9:290,10:150}

weeks_summary = []
for wn, ws, we in week_ranges:
    week_acts = [a for a in activities if ws <= a["date"] <= we]
    bike_tss  = sum(a["tss"] for a in week_acts if a["disc"] == "bike")
    total_tss = sum(a["tss"] for a in week_acts)
    swim_n    = len([a for a in week_acts if a["disc"] == "swim"])
    bike_n    = len([a for a in week_acts if a["disc"] == "bike"])
    run_n     = len([a for a in week_acts if a["disc"] == "run"])
    avg_np    = 0
    bike_acts = [a for a in week_acts if a["disc"] == "bike" and a["np"] > 0]
    if bike_acts:
        avg_np = round(sum(a["np"] for a in bike_acts) / len(bike_acts), 1)

    weeks_summary.append({
        "week":       wn,
        "start":      ws,
        "end":        we,
        "target":     week_targets[wn],
        "actual":     round(total_tss),
        "bikeTSS":    round(bike_tss),
        "swimN":      swim_n,
        "bikeN":      bike_n,
        "runN":       run_n,
        "avgNP":      avg_np,
        "done":       we < TODAY.strftime("%Y-%m-%d"),
    })

# Overall stats
bike_nps = [a["np"] for a in activities if a["disc"] == "bike" and a["np"] > 0]
overall = {
    "lastUpdated":  TODAY.strftime("%B %d, %Y"),
    "totalActs":    len(activities),
    "avgBikeNP":    round(sum(bike_nps)/len(bike_nps), 1) if bike_nps else 0,
    "currentWeek":  next((w["week"] for w in weeks_summary if not w["done"]), 10),
    "weeksComplete":sum(1 for w in weeks_summary if w["done"] and w["actual"] > 0),
    "daysToRace":   (date(2026,7,19) - TODAY).days,
}

with open("data/summary.json", "w") as f:
    json.dump({"overall": overall, "weeks": weeks_summary}, f, indent=2)
print(f"✓ Wrote data/summary.json")
print("\n✅ All Garmin data fetched and saved successfully")
