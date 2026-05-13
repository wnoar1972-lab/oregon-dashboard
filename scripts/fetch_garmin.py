"""
fetch_garmin.py - Updated with flexible field parsing for Garmin API
"""
import json, os, sys
from datetime import datetime, timedelta, date

try:
    from garminconnect import Garmin
except ImportError:
    os.system(f"{sys.executable} -m pip install garminconnect")
    from garminconnect import Garmin

EMAIL    = os.environ.get("GARMIN_EMAIL")
PASSWORD = os.environ.get("GARMIN_PASSWORD")
if not EMAIL or not PASSWORD:
    print("ERROR: Set GARMIN_EMAIL and GARMIN_PASSWORD"); sys.exit(1)

TODAY = date.today()
START_DATE = date(2026,4,21)

print(f"Fetching {START_DATE} to {TODAY}")

try:
    client = Garmin(EMAIL, PASSWORD)
    client.login()
    print("Logged in")
except Exception as e:
    print(f"Login error: {e}"); sys.exit(1)

def disc(t):
    t=str(t).upper()
    if any(x in t for x in ["SWIM","POOL","OPEN_WATER"]): return "swim"
    if any(x in t for x in ["CYCLING","VIRTUAL","BIKE"]): return "bike"
    if any(x in t for x in ["RUNNING","RUN"]): return "run"
    return "other"

def sf(v,d=0):
    try: return round(float(v),1) if v else d
    except: return d

def parse_score(raw, dto):
    for obj in [dto, raw]:
        for k in ["sleepScores","overallSleepScore","sleepScore"]:
            v = obj.get(k)
            if v is None: continue
            if isinstance(v,(int,float)) and v>0: return int(v)
            if isinstance(v,dict):
                for sk in ["overallScore","totalScore","value","score","overall","qualityScore"]:
                    sv = v.get(sk)
                    if sv: return int(sv)
    return 0

def parse_spo2(raw, dto):
    for obj in [dto, raw]:
        for k in ["averageSpO2Value","avgSPO2","spo2","averageSpo2","avgSpo2"]:
            v = obj.get(k)
            if v:
                try: return round(float(v),1)
                except: pass
    for k in ["spo2SleepSummary","spo2Summary"]:
        s = raw.get(k,{})
        if s:
            for sk in ["averageSPO2","avg","average","averageValue"]:
                v = s.get(sk)
                if v:
                    try: return round(float(v),1)
                    except: pass
    ep = raw.get("wellnessEpochSPO2DataDTOList",[])
    if ep:
        vals=[x.get("spo2Reading",0) for x in ep if x.get("spo2Reading")]
        if vals: return round(sum(vals)/len(vals),1)
    return 0

def parse_rhr(raw, dto):
    for obj in [dto, raw]:
        for k in ["restingHeartRate","avgRestingHeartRate","averageRestingHeartRate","restingHR"]:
            v = obj.get(k)
            if v:
                try: return int(v)
                except: pass
    return 0

def quality(score):
    if score>=80: return "Good"
    if score>=60: return "Fair"
    if score>0:   return "Poor"
    return "—"

# ACTIVITIES
try:
    raw_acts = client.get_activities_by_date(START_DATE.strftime("%Y-%m-%d"), TODAY.strftime("%Y-%m-%d"))
    print(f"Got {len(raw_acts)} activities")
    activities = []
    for a in raw_acts:
        at = a.get("activityType",{}).get("typeKey","unknown")
        activities.append({
            "date":  a.get("startTimeLocal","")[:10],
            "title": a.get("activityName","Activity")[:40],
            "type":  at[:8], "disc": disc(at),
            "tss":   sf(a.get("trainingStressScore")),
            "np":    sf(a.get("normalizedPower")),
            "avgHR": sf(a.get("averageHR")),
            "distance": sf(a.get("distance")),
        })
    activities.sort(key=lambda x:x["date"])
    os.makedirs("data",exist_ok=True)
    with open("data/activities.json","w") as f: json.dump(activities,f,indent=2)
    print(f"Saved {len(activities)} activities")
except Exception as e:
    print(f"Activities error: {e}"); activities=[]

# SLEEP
try:
    sleep_data=[]
    cur = TODAY - timedelta(days=60)
    debug_done = False
    while cur <= TODAY:
        ds = cur.strftime("%Y-%m-%d")
        try:
            raw = client.get_sleep_data(ds)
            if raw:
                dto = raw.get("dailySleepDTO") or raw.get("sleepDTO") or {}
                if not debug_done and dto:
                    print(f"DEBUG sleep DTO keys: {list(dto.keys())[:30]}")
                    print(f"DEBUG raw keys: {list(raw.keys())[:20]}")
                    debug_done = True
                score = parse_score(raw, dto)
                spo2  = parse_spo2(raw, dto)
                rhr   = parse_rhr(raw, dto)
                total = int(dto.get("sleepTimeSeconds") or dto.get("totalSleepSeconds") or 0)
                deep  = int(dto.get("deepSleepSeconds") or 0)
                rem   = int(dto.get("remSleepSeconds") or 0)
                if total>0 or spo2>0:
                    sleep_data.append({
                        "date":ds,"score":score,
                        "total":round(total/3600,1),
                        "deep":round(deep/60),"rem":round(rem/60),
                        "spo2":spo2,"rhr":rhr,
                        "quality":quality(score)
                    })
        except Exception: pass
        cur += timedelta(days=1)
    sleep_data.sort(key=lambda x:x["date"])
    with open("data/sleep.json","w") as f: json.dump(sleep_data,f,indent=2)
    print(f"Saved {len(sleep_data)} sleep nights")
    if sleep_data: print(f"Latest sleep: {sleep_data[-1]}")
except Exception as e:
    print(f"Sleep error: {e}")
    import traceback; traceback.print_exc()

# SUMMARY
week_ranges=[(1,"2026-04-21","2026-04-27"),(2,"2026-04-28","2026-05-03"),(3,"2026-05-04","2026-05-10"),(4,"2026-05-11","2026-05-17"),(5,"2026-05-18","2026-05-24"),(6,"2026-05-25","2026-05-31"),(7,"2026-06-01","2026-06-07"),(8,"2026-06-08","2026-06-14"),(9,"2026-06-15","2026-06-21"),(10,"2026-07-13","2026-07-19")]
wt={1:211,2:396,3:284,4:380,5:420,6:260,7:460,8:500,9:290,10:150}
weeks=[]
for wn,ws,we in week_ranges:
    wa=[a for a in activities if ws<=a["date"]<=we]
    bn=[a for a in wa if a["disc"]=="bike" and a["np"]>0]
    weeks.append({"week":wn,"start":ws,"end":we,"target":wt[wn],"actual":round(sum(a["tss"] for a in wa)),"bikeTSS":round(sum(a["tss"] for a in wa if a["disc"]=="bike")),"swimN":len([a for a in wa if a["disc"]=="swim"]),"bikeN":len([a for a in wa if a["disc"]=="bike"]),"runN":len([a for a in wa if a["disc"]=="run"]),"avgNP":round(sum(a["np"] for a in bn)/len(bn),1) if bn else 0,"done":we<TODAY.strftime("%Y-%m-%d")})
bn_all=[a["np"] for a in activities if a["disc"]=="bike" and a["np"]>0]
overall={"lastUpdated":TODAY.strftime("%B %d, %Y"),"totalActs":len(activities),"avgBikeNP":round(sum(bn_all)/len(bn_all),1) if bn_all else 0,"currentWeek":next((w["week"] for w in weeks if not w["done"]),10),"weeksComplete":sum(1 for w in weeks if w["done"] and w["actual"]>0),"daysToRace":(date(2026,7,19)-TODAY).days}
with open("data/summary.json","w") as f: json.dump({"overall":overall,"weeks":weeks},f,indent=2)
print(f"Done. {len(activities)} activities, {len(sleep_data)} sleep nights")
