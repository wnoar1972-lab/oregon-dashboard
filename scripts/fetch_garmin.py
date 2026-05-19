"""
fetch_garmin.py
Pulls activities from Intervals.icu (for proper TSS across all disciplines)
and sleep data from Garmin Connect, saves to data/ folder.
"""

import json, os, sys, urllib.request, urllib.parse, base64, subprocess
subprocess.run(['pip', 'install', 'requests', '-q'], check=False)
import requests
from datetime import date, timedelta

TODAY      = date.today()
START_DATE = date(2026, 4, 21)

# ── CREDENTIALS ───────────────────────────────────────────────────────────────
GARMIN_EMAIL    = os.environ.get("GARMIN_EMAIL")
GARMIN_PASSWORD = os.environ.get("GARMIN_PASSWORD")
INTERVALS_KEY   = os.environ.get("INTERVALS_API_KEY")
INTERVALS_ID    = os.environ.get("INTERVALS_ATHLETE_ID")

os.makedirs("data", exist_ok=True)

def disc(t):
    t = str(t).upper()
    if any(x in t for x in ["SWIM","POOL","OPEN_WATER","OPENWATER"]): return "swim"
    if any(x in t for x in ["RIDE","CYCLING","VIRTUAL","BIKE","ROUVY",
                              "VELODROME","INDOOR","VIRTUALRIDE","CYCLE",
                              "EBIKE","MTB","ROAD","GRAVEL"]): return "bike"
    if any(x in t for x in ["RUN","RUNNING","TRAIL","TREADMILL","WALK"]): return "run"
    return "other"

def sf(v, d=0):
    try: return round(float(v), 1) if v else d
    except: return d

# ── INTERVALS.ICU ACTIVITIES ──────────────────────────────────────────────────
activities = []
if INTERVALS_KEY and INTERVALS_ID:
    try:
        print(f"Fetching activities from Intervals.icu ({START_DATE} to {TODAY})...")
        url = (f"https://intervals.icu/api/v1/athlete/{INTERVALS_ID}/activities"
               f"?oldest={START_DATE}&newest={TODAY}&cols=name,type,start_date_local,"
               f"distance,moving_time,tss,normalized_power,average_heartrate,icu_training_load,load")
        resp = requests.get(url, auth=("API_KEY", INTERVALS_KEY))
        print(f"Intervals.icu status: {resp.status_code}")
        resp.raise_for_status()
        raw = resp.json()
        print(f"Got {len(raw)} activities from Intervals.icu")

        # Debug — print all activity types so we can see what ROUVY sends
        print("=== ACTIVITY TYPES ===")
        for a in raw:
            print(f"  {a.get('start_date_local','')[:10]} | type={a.get('type','?')} | name={str(a.get('name',''))[:30]} | tss={a.get('tss')} | load={a.get('icu_training_load')}")
        print("=== END TYPES ===")

        for a in raw:
            act_type = a.get("type", "")
            d = disc(act_type)
            tss = sf(a.get("tss") or a.get("icu_training_load") or a.get("load"))
            np  = sf(a.get("normalized_power"))
            dt  = str(a.get("start_date_local",""))[:10]
            activities.append({
                "date":     dt,
                "title":    str(a.get("name","Activity"))[:40],
                "type":     act_type[:8],
                "disc":     d,
                "tss":      tss,
                "np":       np,
                "avgHR":    sf(a.get("average_heartrate")),
                "distance": sf(a.get("distance")),
                "duration": sf(a.get("moving_time")),
            })
        activities.sort(key=lambda x: x["date"])
        with open("data/activities.json","w") as f:
            json.dump(activities, f, indent=2)
        print(f"Saved {len(activities)} activities with full TSS")
        for d_type in ["swim","bike","run","other"]:
            acts = [a for a in activities if a["disc"]==d_type]
            total_tss = sum(a["tss"] for a in acts)
            print(f"  {d_type}: {len(acts)} sessions, {total_tss:.0f} TSS")

    except Exception as e:
        print(f"Intervals.icu error: {e}")
        import traceback; traceback.print_exc()
else:
    print("No Intervals.icu credentials — skipping activity fetch")

# ── GARMIN SLEEP ──────────────────────────────────────────────────────────────
sleep_data = []
if GARMIN_EMAIL and GARMIN_PASSWORD:
    try:
        from garminconnect import Garmin
        print("Logging in to Garmin Connect for sleep data...")
        client = Garmin(GARMIN_EMAIL, GARMIN_PASSWORD)
        client.login()
        print("Logged in")

        def quality(score):
            if score>=80: return "Good"
            if score>=60: return "Fair"
            if score>0:   return "Poor"
            return "—"

        cur = TODAY - timedelta(days=60)
        while cur <= TODAY:
            ds = cur.strftime("%Y-%m-%d")
            try:
                raw = client.get_sleep_data(ds)
                if ds == "2026-05-17":  # Debug one recent night
                    import json as _json
                    print("SLEEP DEBUG:", _json.dumps({k:v for k,v in raw.items() if k in ["dailySleepDTO","sleepScores","overallSleepScore","sleepScore","wellnessEpochRespirationDataDTOList"]}, default=str)[:2000])
                if raw and isinstance(raw, dict):
                    dto = raw.get("dailySleepDTO") or {}
                    score = 0
                    for src in [dto, raw]:
                        for k in ["sleepScores","overallSleepScore","sleepScore"]:
                            v = src.get(k)
                            if v is None: continue
                            if isinstance(v,(int,float)) and v>0: score=int(v); break
                            if isinstance(v,dict):
                                for sk in ["overallScore","totalScore","value","score","overall"]:
                                    sv = v.get(sk)
                                    if sv:
                                        try: score=int(sv); break
                                        except: pass
                        if score: break
                    spo2 = 0
                    for src in [dto, raw]:
                        for k in ["averageSpO2Value","avgSPO2","spo2","averageSpo2"]:
                            v = src.get(k)
                            if v:
                                try: spo2=round(float(v),1); break
                                except: pass
                        if spo2: break
                    if not spo2:
                        s2 = raw.get("spo2SleepSummary") or {}
                        for k in ["averageSPO2","avg","average","averageValue"]:
                            v = s2.get(k)
                            if v:
                                try: spo2=round(float(v),1); break
                                except: pass
                    if not spo2:
                        ep = raw.get("wellnessEpochSPO2DataDTOList",[]) or []
                        vals=[x.get("spo2Reading",0) for x in ep if x.get("spo2Reading")]
                        if vals: spo2=round(sum(vals)/len(vals),1)
                    rhr = 0
                    for src in [dto, raw]:
                        for k in ["restingHeartRate","avgRestingHeartRate","averageRestingHeartRate"]:
                            v = src.get(k)
                            if v:
                                try: rhr=int(v); break
                                except: pass
                        if rhr: break
                    total = int(dto.get("sleepTimeSeconds") or dto.get("totalSleepSeconds") or 0)
                    deep  = int(dto.get("deepSleepSeconds") or 0)
                    rem   = int(dto.get("remSleepSeconds") or 0)
                    if total > 3600 or spo2 > 0:
                        sleep_data.append({
                            "date":    ds,
                            "score":   score,
                            "total":   round(total/3600,1),
                            "deep":    round(deep/60),
                            "rem":     round(rem/60),
                            "spo2":    spo2,
                            "rhr":     rhr,
                            "quality": quality(score)
                        })
            except Exception: pass
            cur += timedelta(days=1)

        sleep_data.sort(key=lambda x:x["date"])
        with open("data/sleep.json","w") as f:
            json.dump(sleep_data, f, indent=2)
        print(f"Saved {len(sleep_data)} sleep nights")

    except Exception as e:
        print(f"Garmin sleep error: {e}")
        import traceback; traceback.print_exc()

# ── SUMMARY ───────────────────────────────────────────────────────────────────
week_ranges = [
    (1,"2026-04-21","2026-04-27"),(2,"2026-04-28","2026-05-03"),
    (3,"2026-05-04","2026-05-10"),(4,"2026-05-11","2026-05-17"),
    (5,"2026-05-18","2026-05-24"),(6,"2026-05-25","2026-05-31"),
    (7,"2026-06-01","2026-06-07"),(8,"2026-06-08","2026-06-14"),
    (9,"2026-06-15","2026-06-21"),(10,"2026-07-13","2026-07-19")
]
wt = {1:211,2:396,3:284,4:380,5:420,6:260,7:460,8:500,9:290,10:150}

weeks = []
for wn, ws, we in week_ranges:
    wa = [a for a in activities if ws <= a["date"] <= we]
    bn = [a for a in wa if a["disc"]=="bike" and a["np"]>0]
    swim_tss = round(sum(a["tss"] for a in wa if a["disc"]=="swim"))
    bike_tss = round(sum(a["tss"] for a in wa if a["disc"]=="bike"))
    run_tss  = round(sum(a["tss"] for a in wa if a["disc"]=="run"))
    total_tss = round(sum(a["tss"] for a in wa))
    weeks.append({
        "week":wn,"start":ws,"end":we,"target":wt[wn],
        "actual":total_tss,
        "bikeTSS":bike_tss,
        "swimTSS":swim_tss,
        "runTSS":run_tss,
        "swimN":len([a for a in wa if a["disc"]=="swim"]),
        "bikeN":len([a for a in wa if a["disc"]=="bike"]),
        "runN":len([a for a in wa if a["disc"]=="run"]),
        "avgNP":round(sum(a["np"] for a in bn)/len(bn),1) if bn else 0,
        "done":we < TODAY.strftime("%Y-%m-%d")
    })

bn_all = [a["np"] for a in activities if a["disc"]=="bike" and a["np"]>0]
overall = {
    "lastUpdated":   TODAY.strftime("%B %d, %Y"),
    "totalActs":     len(activities),
    "avgBikeNP":     round(sum(bn_all)/len(bn_all),1) if bn_all else 0,
    "currentWeek":   next((w["week"] for w in weeks if not w["done"]),10),
    "weeksComplete": sum(1 for w in weeks if w["done"] and w["actual"]>0),
    "daysToRace":    (date(2026,7,19)-TODAY).days,
    "totalSwimTSS":  round(sum(a["tss"] for a in activities if a["disc"]=="swim")),
    "totalBikeTSS":  round(sum(a["tss"] for a in activities if a["disc"]=="bike")),
    "totalRunTSS":   round(sum(a["tss"] for a in activities if a["disc"]=="run")),
    "totalBikeSessions": len([a for a in activities if a["disc"]=="bike"]),
    "totalSwimSessions": len([a for a in activities if a["disc"]=="swim"]),
    "totalRunSessions":  len([a for a in activities if a["disc"]=="run"]),
}

with open("data/summary.json","w") as f:
    json.dump({"overall":overall,"weeks":weeks}, f, indent=2)
print(f"Done: {len(activities)} activities, {len(sleep_data)} sleep nights")
print(f"TSS — Swim: {overall['totalSwimTSS']}, Bike: {overall['totalBikeTSS']}, Run: {overall['totalRunTSS']}")
