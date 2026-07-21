"""
analyze_training.py
Reads latest Garmin data and calls Claude API to generate
daily coaching analysis saved to data/analysis.json
"""

import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, date, timedelta

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    print("ERROR: Set ANTHROPIC_API_KEY environment variable")
    sys.exit(1)

import datetime as _dt
TODAY = _dt.datetime.now(_dt.timezone(_dt.timedelta(hours=-7))).date()
DAY_OF_WEEK = TODAY.strftime('%A')  # e.g. Wednesday
DAYS_INTO_WEEK = (TODAY.weekday() + 1) % 7  # Mon=1, Tue=2... Sun=0 -> 7
if DAYS_INTO_WEEK == 0: DAYS_INTO_WEEK = 7
DAYS_LEFT_IN_WEEK = 7 - DAYS_INTO_WEEK

# ── LOAD DATA FILES ───────────────────────────────────────────────────────────
def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        print(f"Warning: could not load {path}: {e}")
        return None

activities  = load_json("data/activities.json") or []
sleep_data  = load_json("data/sleep.json") or []
summary     = load_json("data/summary.json") or {}
overall     = summary.get("overall", {})
weeks       = summary.get("weeks", [])

# ── TRAINING PLAN ─────────────────────────────────────────────────────────────
WEEK_TARGETS = {1:250,2:350,3:420,4:480,5:520,6:300,7:560,8:600,9:560,10:400,11:480,12:250,13:150}
WEEK_PHASES  = {1:"Recovery",2:"Base",3:"Base",4:"Build",5:"Build",
                6:"Recovery",7:"Peak",8:"Peak",9:"Peak",10:"Build",
                11:"Taper",12:"Taper",13:"Race Week"}
WEEK_FOCUS   = {
    1:"Recovery — easy aerobic only, no intensity",
    2:"First volume step-up — Oregon ROUVY sim, long run",
    3:"Consistent build — back to back bikes, swim consistency",
    4:"First brick week — 60 min ride then 20 min run, threshold swim sets",
    5:"Outdoor ride + long run — first 45-50mi outdoor ride, run 10-11mi",
    6:"Recovery week — volume drops 35%, no intensity",
    7:"Race-specific intensity — Oregon ROUVY sim NP 145-152w, bricks",
    8:"Peak volume week — biggest week, 2hr outdoor brick, 9000m swim",
    9:"Transition — volume -35%, one quality swim set, step down not shutdown",
    10:"Final build — Oregon ROUVY full course at race NP 145-152w + brick run",
    11:"Sharpener — last race-pace efforts, 4x200 swim, 3x8min bike, nothing hard after Wed",
    12:"True taper — volume -60%, bike packed Thu, drive to Salem Sun Jul 13",
    13:"Race week — arrive Salem Jul 13, race Jul 19"
}

# ── WEEKLY SCHEDULE (default template + week-specific overrides) ──────────────
# DEFAULT_SCHEDULE is the recurring template. To change a single week, add a
# block to WEEK_OVERRIDES keyed by the MONDAY (ISO date) of that week. Any week
# not listed falls back to DEFAULT_SCHEDULE. Keep this in sync with the
# WEEK_OVERRIDES block in index.html so the dashboard and AI coaching match.
DEFAULT_SCHEDULE = {
    "Monday":    "Pool swim 3,000m aerobic",
    "Tuesday":   "ROUVY bike + brick run + tri club run (6-7mi)",
    "Wednesday": "ROUVY bike + brick run + pool swim 3,000m",
    "Thursday":  "Run 6mi easy-moderate",
    "Friday":    "Pool swim 3,000m aerobic",
    "Saturday":  "Long ride 50-60mi outdoor + optional swim",
    "Sunday":    "Long run 9-11mi + open water swim",
}

WEEK_OVERRIDES = {
    "2026-06-01": {
        "Monday":    "Bike ride + brick run",
        "Tuesday":   "Swim + Run Club run",
        "Wednesday": "Bike ride + brick run",
        "Thursday":  "Run",
        "Friday":    "Bike ride + brick run",
        "Saturday":  "Long bike ride + swim",
        "Sunday":    "Easy long run — scaled to ~60-70% of planned, all easy aerobic; cut shorter or skip if morning RHR is still elevated",
    },
    "2026-06-08": {
        "Monday":    "Bike ride + brick run",
        "Tuesday":   "Swim (morning) + LONG RUN ~10 miles easy at Run Club tonight — well under 9:10 race pace; first long run after a gap, cut to 8 if hip or legs object",
        "Wednesday": "Bike ride + SHORT easy brick run (trimmed because the 10-mile long run was done Tuesday night)",
        "Thursday":  "REST DAY — complete rest (long run was moved to Tuesday). Walk/mobility and good food only, no training stress",
        "Friday":    "Swim",
        "Saturday":  "Long bike ride",
        "Sunday":    "Run + open water swim",
    },
    "2026-06-15": {
        "Monday":    "Bike 45 min + brick run 20 min off the bike (easy pace)",
        "Tuesday":   "Pool swim 2,000m aerobic (morning or after Run Club)",
        "Wednesday": "Bike 50 min + brick run 20 min off the bike (easy pace)",
        "Thursday":  "Pool swim 2,500m — 4x100 at race pace, stay sharp",
        "Friday":    "Easy run 3–4mi (protect hip, no intensity) + open water swim 1,500m at La Jolla Shores",
        "Saturday":  "Long bike 50–55mi outdoor (NP under 150w) + brick run 20 min easy",
        "Sunday":    "Easy run 3–4mi — all easy, protect hip",
    },
    "2026-06-22": {
        "Monday":    "Bike 50–55 min easy-moderate on ROUVY — no brick, spin the legs fresh (no Run Club this week)",
        "Tuesday":   "Pool swim 2,500m — 4x100 at race pace, stay sharp",
        "Wednesday": "Pool swim 2,000m easy — stay loose, no intensity",
        "Thursday":  "Bike 45 min + short brick run 15 min easy off the bike",
        "Friday":    "Complete REST — protect everything for Sunday's race",
        "Saturday":  "Shakeout only: 20 min easy spin + 10 min easy jog — nothing more, save the legs",
        "Sunday":    "RACE DAY — San Diego International Triathlon (SDIT). International distance: 1K swim / 30K bike / 10K run. Hilly bike course ~1,112ft gain over 2 loops. Goal sub-2:15. Push swim hard from the gun, ride controlled on climbs (don't blow up T2 legs), run strong. This is a dress rehearsal for Oregon execution.",
    },
    "2026-06-29": {
        "Monday":    "Full REST — post-SDIT recovery. Walk, stretch, eat well. No training stress.",
        "Tuesday":   "Easy recovery spin 30 min only — legs should feel heavy, that is normal. No intensity.",
        "Wednesday": "Pool swim 2,000m easy + short run 3mi easy — back to light training if hip and legs feel ready",
        "Thursday":  "Bike 45 min with 3x8 min at race effort NP 145–152w — last race-pace bike stimulus before Oregon taper",
        "Friday":    "Bike ride easy-moderate — shake out the legs, no intensity, save it for tomorrow's 10K.",
        "Saturday":  "4th of July 10K RACE — strong tempo effort, target 8:00–8:15/mi. Not all-out — Oregon is 15 days away. Protect the hip on any downhills.",
        "Sunday":    "Open water swim — easy aerobic, La Jolla Shores. Enjoy it, no intensity, recover from Saturday 10K.",
    },
    "2026-07-06": {
        "Monday":    "Bike 40 min easy-moderate ROUVY (NP under 140w) + short brick run 15 min off the bike. Easy pace, no intensity.",
        "Tuesday":   "Pool swim 2,000m with 4x100 at race pace, stay sharp. Then Run Club — easy group run, enjoy it.",
        "Wednesday": "Bike 40 min easy ROUVY (NP under 140w) + pool swim 1,500m easy aerobic. Stay loose.",
        "Thursday":  "Bike 30 min very easy spin only. Skip the run — protect the legs heading into race week.",
        "Friday":    "Complete rest. No training stress. Protect everything.",
        "Saturday":  "Open water swim 1,500m easy aerobic at La Jolla Shores. No intensity.",
        "Sunday":    "Easy run 2–3mi. Very easy, final tune-up, nothing more.",
    },
    "2026-07-13": {
        "Monday":    "Pool swim 1,500m easy with 4x50 at race pace. Stay sharp. Last pool session before Oregon.",
        "Tuesday":   "Pool swim 2,000yd easy aerobic, stay loose + easy run 3mi easy pace. Feel fresh, no effort.",
        "Wednesday": "OW swim 1,000m easy open water. Last swim before Oregon — confidence builder.",
        "Thursday":  "TRAVEL DAY ✈️ — fly to Oregon. Stay off your feet, hydrate well, arrive ready.",
        "Friday":    "QR Kilo reassembly and bike check — short 20 min spin to confirm shifting and brakes are dialed.",
        "Saturday":  "Athlete briefing and course preview swim if available. Race rehearsal — goggles, wetsuit, nutrition check.",
        "Sunday":    "RACE EVE — full rest. Gear laid out, nutrition prepped, goggles prepped, sleep early. RACE TOMORROW.",
    },
    "2026-07-21": {
        "Monday":    "Day 1 post-race — full rest. Walk only, eat well, celebrate 5:39:04 PR.",
        "Tuesday":   "Day 2 — still sore. Full rest. Skip Run Club and swim. No training.",
        "Wednesday": "Day 3 — full rest. Hydrate, sleep, let the body absorb the race.",
        "Thursday":  "Day 4 — rest. Skip swim. Only move if feeling significantly better. Book bike fit this week.",
        "Friday":    "Day 5 — first easy movement only if hip feels okay. Easy swim 20 min max. No intensity.",
        "Saturday":  "Day 6 — easy OW swim 20 min at La Jolla Shores if feeling good. Aerobic only.",
        "Sunday":    "Day 7 — easy spin 20 min or rest. Listen to the body. Sacramento build starts tomorrow.",
    },
    "2026-07-28": {
        "Monday":    "ROUVY 60 min easy Z2 (NP 130–140w) + easy run 3mi walk/run 9/1.",
        "Tuesday":   "Pool swim 2,000m easy (4x100 steady) + Run Club (walk/run protocol).",
        "Wednesday": "ROUVY 60 min easy Z2 (NP 130–140w).",
        "Thursday":  "Pool swim 2,000m easy + easy run 3mi walk/run 9/1. Protect hip.",
        "Friday":    "Rest.",
        "Saturday":  "Outdoor ride 60 min easy Z2 if weather allows — start getting aero position time on QR Kilo. ROUVY if necessary.",
        "Sunday":    "Easy run 3mi walk/run 9/1 — third run of week. Frequency is the goal.",
    },
    "2026-08-03": {
        "Monday":    "ROUVY 60 min (NP 135–145w) + easy run 3mi walk/run 9/1.",
        "Tuesday":   "Pool swim 2,500m (4x100 steady) + Run Club (walk/run protocol).",
        "Wednesday": "Outdoor ride 75 min + brick run 25 min (walk/run 9/1) — first brick of Sacramento block. Outdoor preferred — aero position conditioning starts now. ROUVY only if weather forces it.",
        "Thursday":  "Pool swim 2,500m (4x100 steady) + easy run 4mi walk/run 9/1.",
        "Friday":    "Rest.",
        "Saturday":  "Outdoor ride 90 min Z2 — get outside, aero position. Your back needs to adapt to 112mi in aero. ROUVY only if necessary.",
        "Sunday":    "Easy run 3mi walk/run 9/1.",
    },
    "2026-08-10": {
        "Monday":    "ROUVY 75 min (NP 140–148w) + easy run 4mi walk/run 9/1.",
        "Tuesday":   "Pool swim 3,000m (4x200 steady) + Run Club (walk/run protocol).",
        "Wednesday": "Outdoor ride 90 min + brick run 30 min at 11:00/mi (walk/run 9/1) — outdoor mandatory for aero conditioning. Back and hip flexors need time in aero position before the run.",
        "Thursday":  "Pool swim 3,000m + easy run 4mi walk/run 9/1. Protect hip.",
        "Friday":    "Rest.",
        "Saturday":  "Outdoor long ride 50mi at ~17mph — first post-bike-fit outdoor ride on QR Kilo.",
        "Sunday":    "Easy run 4mi walk/run 9/1 — third run of week.",
    },
    "2026-08-17": {
        "Monday":    "ROUVY 90 min (NP 140–148w) + easy run 4mi walk/run 9/1.",
        "Tuesday":   "Pool swim 3,000m (4x200 threshold) + Run Club (walk/run protocol).",
        "Wednesday": "Outdoor ride 100 min + brick run 35 min at 11:00/mi (walk/run 9/1) — outdoor mandatory. Aero position for 100 min then run — this is Sacramento simulation. Aid station walk every mile.",
        "Thursday":  "Pool swim 3,200m threshold sets + easy run 4mi walk/run 9/1.",
        "Friday":    "Rest — recovery before big weekend.",
        "Saturday":  "Outdoor long ride 60–65mi at ~17mph — practice Sacramento pacing, nutrition every 20 min.",
        "Sunday":    "Easy run 5mi walk/run 9/1 — max distance, protect hip.",
    },
    "2026-08-24": {
        "Monday":    "Rest — recovery week begins. Absorb 5 weeks of work.",
        "Tuesday":   "Pool swim 2,000m easy aerobic + Run Club (easy, walk/run, enjoy it).",
        "Wednesday": "ROUVY 60 min easy — Z2 only, NP under 135w.",
        "Thursday":  "Pool swim 2,000m easy + easy run 3mi walk/run 9/1.",
        "Friday":    "Rest.",
        "Saturday":  "Easy ride 60 min — outdoor if possible even in recovery week, keep the aero adaptation going. ROUVY if needed.",
        "Sunday":    "Easy run 3mi walk/run — conversational, recovery week run.",
    },
    "2026-08-31": {
        "Monday":    "ROUVY 90 min (NP 142–150w) + easy run 4mi walk/run 9/1.",
        "Tuesday":   "Pool swim 3,200m (4x200 race effort) + Run Club (walk/run, pick up effort).",
        "Wednesday": "Outdoor ride 3hr at ~17mph + brick run 45 min at 11:00/mi (walk/run 9/1) — KEY SESSION. Must be outdoor — 3 hours in aero is the whole point. ROUVY cannot replicate this back and hip flexor load.",
        "Thursday":  "Pool swim 3,000m race effort + easy run 4mi walk/run 9/1. Recover from Wednesday.",
        "Friday":    "Rest — recovery before peak weekend.",
        "Saturday":  "Outdoor long ride 65mi at ~17mph — race-pace discipline, nutrition dialed.",
        "Sunday":    "Easy run 4mi walk/run 9/1.",
    },
    "2026-09-07": {
        "Monday":    "ROUVY 100 min (NP 142–150w) + easy run 4mi walk/run 9/1.",
        "Tuesday":   "Pool swim 3,000m threshold sets + Run Club (walk/run, peak week).",
        "Wednesday": "Outdoor 65mi at ~17mph + brick run 60 min at 11:00/mi (walk/run 9/1) — closest thing to Sacramento race day.",
        "Thursday":  "Pool swim 3,000m race effort + easy run 4mi walk/run 9/1. Recover from Wednesday.",
        "Friday":    "Rest — protect the legs before Sunday.",
        "Saturday":  "ROUVY 90 min NP 142–150w — maintain stimulus.",
        "Sunday":    "Easy run 5mi walk/run 9/1 — max distance, protect hip.",
    },
    "2026-09-14": {
        "Monday":    "ROUVY 90 min (NP 142–150w) + easy run 4mi walk/run 9/1.",
        "Tuesday":   "Pool swim 3,000m (4x200 race effort) + Run Club (walk/run, peak week energy).",
        "Wednesday": "Outdoor ride 90 min at ~17mph + brick run 50 min at 11:00/mi (walk/run 9/1) — outdoor mandatory, full race nutrition practice. Aero for 90 min then run.",
        "Thursday":  "Pool swim 3,000m race effort + easy run 4mi walk/run 9/1.",
        "Friday":    "Rest.",
        "Saturday":  "Outdoor long ride 65mi at ~17mph — second consecutive peak long bike.",
        "Sunday":    "Easy run 4mi walk/run 9/1 — end of peak block.",
    },
    "2026-09-21": {
        "Monday":    "ROUVY 75 min (NP 140–148w) + easy run 3mi walk/run 9/1.",
        "Tuesday":   "Pool swim 2,500m (4x100 race pace) + Run Club (walk/run, step down week).",
        "Wednesday": "Outdoor ride 75 min + brick run 35 min at 11:00/mi (walk/run 9/1) — outdoor preferred even in step-down week.",
        "Thursday":  "Pool swim 2,500m race pace + easy run 3mi walk/run 9/1.",
        "Friday":    "Rest.",
        "Saturday":  "Outdoor ride 60 min easy — step down week but keep the outdoor aero habit.",
        "Sunday":    "Easy run 3mi walk/run 9/1 — easy end to step down week.",
    },
    "2026-09-28": {
        "Monday":    "ROUVY 60 min (NP 140–148w) + easy run 3mi walk/run 9/1. Taper begins.",
        "Tuesday":   "Pool swim 2,000m (4x100 race pace) + Run Club (walk/run, taper week, enjoy it).",
        "Wednesday": "Easy outdoor or ROUVY 45 min — taper, NP under 140w. Short enough that trainer is fine.",
        "Thursday":  "Pool swim 2,000m race pace + easy run 3mi walk/run, 4x30 sec strides, feel sharp.",
        "Friday":    "Rest.",
        "Saturday":  "OW swim easy 1,500m at La Jolla — easy aerobic, enjoy the water.",
        "Sunday":    "Easy run 2mi walk/run — very easy, taper is working.",
    },
    "2026-10-05": {
        "Monday":    "ROUVY 30 min easy + easy jog 2mi (4 strides, feel fresh). Race week prep begins.",
        "Tuesday":   "Pool swim 1,500m (4x50 race pace) — last quality swim + Run Club (easy, last run club before Sacramento).",
        "Wednesday": "Bike reassembly check 20 min — QR Kilo packed for Sacramento. Confirm shifting and brakes.",
        "Thursday":  "Pool swim 1,000m easy shakeout + easy jog 15 min (4 strides, feel fast, no effort).",
        "Friday":    "Travel to Sacramento — fly or drive, stay off feet, hydrate, arrive ready.",
        "Saturday":  "Shakeout swim Sacramento River — preview swim course, easy 800m, wetsuit check.",
        "Sunday":    "Easy jog 10 min. Athlete check-in, rack bike, transition setup. Rest all day.",
    },
    "2026-10-12": {
        "Monday":    "Pool or OW swim 1,200m easy — 4x50 at race pace. Last swim before Sacramento.",
        "Tuesday":   "Easy spin 20 min + easy jog 15 min (4x20 sec strides, feel fast, no effort).",
        "Wednesday": "Sacramento River shakeout swim — easy 800m, final open water, confidence builder.",
        "Thursday":  "Rest — off feet, hydrate, eat well, gear check.",
        "Friday":    "Bike check 10 min — confirm shifting, brakes, nutrition loaded.",
        "Saturday":  "Athlete briefing and course preview. Transition walk-through. Early night.",
        "Sunday":    "RACE DAY — IM California! Swim 1:20, Bike 17mph, Run walk/run 9/1, sub-13:00. You have done the work.",
    },
}

# Monday (ISO) of the current week — used to look up any override for this week
_this_monday = (TODAY - timedelta(days=TODAY.weekday())).strftime("%Y-%m-%d")
this_week_schedule = WEEK_OVERRIDES.get(_this_monday, DEFAULT_SCHEDULE)
today_planned = this_week_schedule.get(DAY_OF_WEEK, "see weekly schedule")
schedule_line = ", ".join(f"{d[:3]}={s}" for d, s in this_week_schedule.items())

# ── FIND YESTERDAY AND RECENT WORKOUTS ───────────────────────────────────────
yesterday = (TODAY - timedelta(days=1)).strftime("%Y-%m-%d")
last7days = [(TODAY - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]

yesterday_acts = [a for a in activities if a["date"] == yesterday]
last7_acts     = [a for a in activities if a["date"] in last7days]
last7_sleep    = [s for s in sleep_data if s["date"] in last7days]

# Current week number
current_week = overall.get("currentWeek", 4)
current_week_data = next((w for w in weeks if w["week"] == current_week), {})
week_target  = WEEK_TARGETS.get(current_week, 380)
week_actual  = current_week_data.get("actual", 0)
week_pct     = round(week_actual / week_target * 100) if week_target else 0

# Discipline counts total
total_bike = len([a for a in activities if a["disc"] == "bike"])
total_swim = len([a for a in activities if a["disc"] == "swim"])
total_run  = len([a for a in activities if a["disc"] == "run"])
total_bike_tss = round(sum(a["tss"] for a in activities if a["disc"] == "bike"))

# Brick detection — same day bike + run
from collections import defaultdict
day_discs = defaultdict(set)
for a in activities:
    day_discs[a["date"]].add(a["disc"])
brick_days = [d for d, discs in day_discs.items() if "bike" in discs and "run" in discs]

# Recent sleep stats
recent_spo2   = [s["spo2"] for s in last7_sleep if s["spo2"] > 0]
recent_scores = [s["score"] for s in last7_sleep if s["score"] > 0]
avg_spo2  = round(sum(recent_spo2)/len(recent_spo2), 1) if recent_spo2 else 0
avg_score = round(sum(recent_scores)/len(recent_scores)) if recent_scores else 0
low_spo2_nights = len([s for s in recent_spo2 if s < 92])

# ── BUILD PROMPT ──────────────────────────────────────────────────────────────
yesterday_summary = ""
if yesterday_acts:
    for a in yesterday_acts:
        dist_mi = round(a["distance"] / 1609.34, 1) if a["distance"] else 0
        yesterday_summary += f"- {a['title']} ({a['disc']}) | TSS: {a['tss']} | HR: {a['avgHR']} | Distance: {dist_mi}mi\n"
else:
    yesterday_summary = "- Rest day (no activities logged)"

last7_summary = ""
for a in sorted(last7_acts, key=lambda x: x["date"], reverse=True):
    dist_mi = round(a["distance"] / 1609.34, 1) if a["distance"] else 0
    last7_summary += f"- {a['date']} | {a['title']} ({a['disc']}) | TSS: {a['tss']} | HR: {a['avgHR']} | {dist_mi}mi\n"

sleep_summary = ""
for s in sorted(last7_sleep, key=lambda x: x["date"], reverse=True):
    sleep_summary += f"- {s['date']} | Score: {s['score']} | Duration: {s['total']}h | SpO2: {s['spo2']}% | RHR: {s['rhr']} | Deep: {s['deep']}min | REM: {s['rem']}min\n"

prompt = f"""You are an expert Ironman triathlon coach analyzing an athlete's daily training data. You are preparing this athlete for their first full Ironman — Sacramento 140.6 on October 18, 2026. 

COACHING STYLE: Be direct, honest, and specific. Do not sugar-coat. Do not over-encourage. If the athlete is behind on training, say so clearly. If a session was weak, say so. If something is a red flag for Sacramento readiness, name it directly. This athlete needs accurate feedback to be ready for a full Ironman — false reassurance is more harmful than hard truths. At the same time, acknowledge genuine progress when it is earned. Think like a coach who wants this athlete to finish Sacramento strong, not just feel good day to day.

ATHLETE PROFILE:
- Age: 54 years old
- Race: Ironman California 140.6, Sacramento CA, October 18 2026 ({overall.get('daysToRace', 89)} days away)
- Oregon 70.3 COMPLETED July 20 2026: 5:39:04 PR (18:24 PR). Swim 25:05 (downstream current), T1 6:24, Bike 2:56:51 (19mph avg — ~6 min lost to handlebar stop mi 1-5 + bathroom stop), T2 3:44, Run 2:07:01 (61st division — best split placement). Run fade miles 10-13 caused by zero run calories (~130g carbs missing) + hip/back/foot pain from bike position. HR data was optical sensor artifact. Cardiovascular fitness held up well.
- Now building for first full IM — Sacramento 140.6
- Bike: Quintana Roo Kilo tri bike (needs professional bike fit before Sacramento build — back and foot pain on Oregon run traced to bike position)
- Has Perthes Disease (right hip) — stable imaging, competing successfully
- On TRT (Testosterone Cypionate, 3x weekly) and full supplement stack

RACE TARGETS (Sacramento 140.6):
- Swim: ~1:20 (2.4mi, wetsuit legal in October)
- Bike: ~17mph / 6:37 (112mi, flat 2-loop course — patience is the key)
- Run: ~4:45 with walk/run 9 min run / 1 min walk every mile + walk every aid station
- Overall goal: sub-13:00
- Bike NP target: TBD pending bike fit (old Oregon target of 145-152w does not apply)
- Run pace target: 10:50-11:30/mi (walk/run protocol)
- Key Sacramento fixes from Oregon: (1) professional bike fit to fix back and feet, (2) gels every 20-25 min on the run — zero run calories was the primary cause of the Oregon run fade, (3) walk/run 9/1 from mile 1 of the marathon
- CRITICAL: Athlete has no aero bars on bike trainer (ROUVY). All Wednesday brick rides and Saturday long rides must be OUTDOOR on the QR Kilo to build aero position endurance. Lower back pain on Oregon run was partly caused by insufficient aero conditioning. Flag if scheduled outdoor rides are missed or replaced with ROUVY for long sessions.

CURRENT TRAINING STATUS:
- Today is {DAY_OF_WEEK}. {DAYS_LEFT_IN_WEEK} day(s) remain in this training week, including today.
- Sacramento 140.6 build: WEEK {current_week} OF 13. Full Ironman — 2.4mi swim / 112mi bike / 26.2mi run. Goal: sub-13:00. Key focuses: (1) bike fit to fix back and foot pain, (2) run frequency 3x/week over distance, (3) brick consistency with 60min run off long bikes in peak weeks. Walk/run protocol: 9 min run / 1 min walk. Max single run 5mi to protect hip (Perthes Disease). Bike NP target TBD pending bike fit.
- WEEK 1 SPECIAL RULE: If current_week == 1, Week 1 (Jul 21-27) is MANDATORY POST-RACE RECOVERY after Oregon 70.3 on Jul 20. Low or zero TSS this week is 100% intentional and correct. Do NOT flag as concerning, behind, or at risk under any circumstances. The athlete is sore and resting — this is the plan. Do not suggest adding training. Only encourage rest, recovery, hydration, and booking a bike fit.
- Week focus: {WEEK_FOCUS.get(current_week, '')}
- Week TSS so far: {week_actual} of {week_target} target ({week_pct}% complete). IMPORTANT: weekly TSS is heavily back-loaded — the Saturday long ride and the midweek brick are by far the largest sessions — so being at a LOW percentage of the weekly target on {DAY_OF_WEEK} (with {DAYS_LEFT_IN_WEEK} days still left including today) is NORMAL and on-track, NOT a concern. Do NOT describe the week as "concerning", "behind", or "at risk" based on cumulative percentage alone. Only flag the week if a scheduled session was actually skipped, or if it is Thursday or later AND the remaining days realistically cannot reach the target.
- This week's schedule: {schedule_line}
- TODAY ({DAY_OF_WEEK}) planned session: {today_planned}
- Total activities in build: {overall.get('totalActs', 0)} ({total_bike} bike, {total_swim} swim, {total_run} run)
- Total bike TSS: {total_bike_tss}
- Brick workouts completed: {len(brick_days)} (dates: {', '.join(brick_days) if brick_days else 'none yet'})

YESTERDAY'S WORKOUT ({yesterday}):
{yesterday_summary}

LAST 7 DAYS OF TRAINING:
{last7_summary if last7_summary else 'No activities in last 7 days'}

LAST 7 NIGHTS SLEEP:
{sleep_summary if sleep_summary else 'No sleep data available'}
7-day avg sleep score: {avg_score}/100
7-day avg SpO2: {avg_spo2}%
Nights below 92% SpO2: {low_spo2_nights} (note: may be affected by night sweating)

When writing todayRecommendation, base it on the TODAY planned session listed above — do not assume a different workout.

Please provide a structured daily coaching analysis in JSON format with exactly these fields:

{{
  "date": "{TODAY.strftime('%B %d, %Y')}",
  "overallStatus": "one of: On Track / Needs Attention / Great Week / Recovery Mode",
  "statusColor": "one of: green / yellow / red / blue",
  "yesterdayAnalysis": "2-3 sentences analyzing yesterday's workout — what was done, how it fits the plan, any concerns or positives",
  "todayRecommendation": "1-2 sentences on what today's training should focus on based on fatigue, plan, and week targets",
  "weekProgress": "1-2 sentences on how the week is tracking vs targets — TSS completion, discipline balance, anything missing. Always describe the current week as 'Week {current_week} of 13' — never a different week number and never a total other than 13. Judge progress relative to how many days have elapsed and the back-loaded schedule; a low cumulative TSS percentage early in the week (Mon-Wed) is expected and should be framed as on-track, not behind.",
  "keyInsight": "1 sentence — the single most important coaching observation right now",
  "alerts": ["array of short alert strings if anything needs attention — e.g. 'No brick workout yet this week', 'Run volume light', 'SpO2 below 92% last night' — empty array if all good. Do NOT add a 'behind on TSS' / 'low weekly volume' style alert before Thursday unless a scheduled session was actually skipped."],
  "positives": ["array of 2-3 short positive observations from recent training"],
  "recoveryScore": number from 1-10 based on sleep quality and training load (10 = fully recovered),
  "trainingLoadStatus": "one of: Fresh / Optimal / Fatigued / Overreached"
}}

Be specific and data-driven. Reference actual numbers from the data. Be direct and honest — do not soften bad news or over-praise average work. Sacramento is a full Ironman and the athlete needs accurate coaching to be ready. Respond with valid JSON only, no other text."""

# ── CALL CLAUDE API ───────────────────────────────────────────────────────────
print(f"Calling Claude API for training analysis ({TODAY})...")

payload = json.dumps({
    "model": "claude-sonnet-4-5",
    "max_tokens": 1000,
    "messages": [{"role": "user", "content": prompt}]
}).encode()

req = urllib.request.Request(
    "https://api.anthropic.com/v1/messages",
    data=payload,
    headers={
        "Content-Type": "application/json",
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01"
    },
    method="POST"
)

try:
    with urllib.request.urlopen(req) as response:
        result = json.loads(response.read().decode())
        text = result["content"][0]["text"].strip()

        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        text = text.strip()

        analysis = json.loads(text)
        analysis["generatedAt"] = TODAY.strftime("%Y-%m-%d")
        analysis["daysToRace"]  = overall.get("daysToRace", 66)
        analysis["currentWeek"] = current_week
        analysis["weekPhase"]   = WEEK_PHASES.get(current_week, "Build")

        with open("data/analysis.json", "w") as f:
            json.dump(analysis, f, indent=2)

        print(f"Analysis saved successfully")
        print(f"Status: {analysis.get('overallStatus')}")
        print(f"Key insight: {analysis.get('keyInsight')}")

except urllib.error.HTTPError as e:
    error_body = e.read().decode()
    print(f"Claude API error {e.code}: {error_body}")
    # Save a fallback analysis so dashboard doesn't break
    fallback = {
        "date": TODAY.strftime("%B %d, %Y"),
        "overallStatus": "On Track",
        "statusColor": "green",
        "yesterdayAnalysis": "Analysis temporarily unavailable — check back tomorrow.",
        "todayRecommendation": "Follow your scheduled training plan for today.",
        "weekProgress": f"Week {current_week} — {week_actual} of {week_target} TSS ({week_pct}% complete).",
        "keyInsight": f"{overall.get('daysToRace', 89)} days to Sacramento. First full IM. Oregon done 5:39:04 PR. Priority: bike fit, run frequency, brick consistency.",
        "alerts": [],
        "positives": ["Training is progressing", "Consistency is key"],
        "recoveryScore": 7,
        "trainingLoadStatus": "Optimal",
        "generatedAt": TODAY.strftime("%Y-%m-%d"),
        "daysToRace": overall.get("daysToRace", 66),
        "currentWeek": current_week,
        "weekPhase": WEEK_PHASES.get(current_week, "Build")
    }
    with open("data/analysis.json", "w") as f:
        json.dump(fallback, f, indent=2)
    print("Saved fallback analysis")

except Exception as e:
    print(f"Unexpected error: {e}")
    import traceback; traceback.print_exc()

print("Analysis complete")
