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
WEEK_TARGETS = {1:211,2:396,3:284,4:380,5:420,6:260,7:460,8:500,9:290,10:150}
WEEK_PHASES  = {1:"Recovery",2:"Build",3:"Build",4:"Build",5:"Build",
                6:"Recovery",7:"Peak",8:"Peak",9:"Taper",10:"Race Week"}
WEEK_FOCUS   = {
    1:"Recovery — easy aerobic only, no intensity",
    2:"First volume step-up — Oregon ROUVY sim, long run",
    3:"Consistent build — back to back bikes, swim consistency",
    4:"First brick week — 60 min ride then 20 min run, threshold swim sets",
    5:"Outdoor ride + long run — first 45-50mi outdoor ride, run 10-11mi",
    6:"Recovery week — volume drops 35%, no intensity",
    7:"Race-specific intensity — Oregon ROUVY sim NP 145-152w, bricks",
    8:"Peak volume week — biggest week, 2hr outdoor brick, 9000m swim",
    9:"Taper — volume drops 40%, short sharp efforts",
    10:"Race week — arrive Salem Jul 13, race Jul 19"
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

prompt = f"""You are an expert Ironman triathlon coach analyzing an athlete's daily training data.

ATHLETE PROFILE:
- Age: 54 years old
- Race: Ironman 70.3 Oregon, Salem OR, July 19 2026 ({overall.get('daysToRace', 66)} days away)
- A-Race: Ironman California 140.6, Sacramento CA, October 18 2026
- Bike: Quintana Roo Kilo tri bike
- Has Perthes Disease (right hip) — stable imaging, competing successfully
- On TRT (Testosterone Cypionate, 3x weekly) and full supplement stack
- Key insight: In 2026 Oceanside 70.3, conservative bike pacing (traded 4:32 on bike) earned a 16-min run PR

RACE TARGETS:
- Bike NP: 145-152w (FTP 221w = 66-69% effort)
- Run pace: sub-9:10/mi
- Overall goal: sub-6:00

CURRENT TRAINING STATUS:
- Today is {DAY_OF_WEEK} — Day {DAYS_INTO_WEEK} of 7 in this training week ({DAYS_LEFT_IN_WEEK} days remaining including today)
- Week {current_week} of 10 ({WEEK_PHASES.get(current_week, 'Build')} phase)
- Week focus: {WEEK_FOCUS.get(current_week, '')}
- Week TSS: {week_actual} of {week_target} target ({week_pct}% complete)
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
  "weekProgress": "1-2 sentences on how the week is tracking vs targets — TSS completion, discipline balance, anything missing",
  "keyInsight": "1 sentence — the single most important coaching observation right now",
  "alerts": ["array of short alert strings if anything needs attention — e.g. 'No brick workout yet this week', 'Run volume light', 'SpO2 below 92% last night' — empty array if all good"],
  "positives": ["array of 2-3 short positive observations from recent training"],
  "recoveryScore": number from 1-10 based on sleep quality and training load (10 = fully recovered),
  "trainingLoadStatus": "one of: Fresh / Optimal / Fatigued / Overreached"
}}

Be specific and data-driven. Reference actual numbers from the data. Keep language direct and coaching-focused — not generic. Respond with valid JSON only, no other text."""

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
        "keyInsight": f"{overall.get('daysToRace', 66)} days to Oregon. Stay consistent.",
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
