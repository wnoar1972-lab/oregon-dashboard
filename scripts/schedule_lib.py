"""
schedule_lib.py
Shared helper for resolving a specific date's planned session(s) from the
single source of truth at config/schedule.json (weekly_template merged with
any dated week_overrides). Used by analyze_training.py; index.html applies
the equivalent merge logic in JS after fetching the same file.
"""

import json
from datetime import timedelta

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def load_schedule(path="config/schedule.json"):
    with open(path) as f:
        return json.load(f)


def resolve_day(schedule, d):
    """d: a datetime.date. Returns {'rest': bool, 'planned': [...]}."""
    monday = (d - timedelta(days=d.weekday())).isoformat()
    week = schedule.get("week_overrides", {}).get(monday) or schedule.get("weekly_template", {})
    dow = str((d.weekday() + 1) % 7)  # Python Mon=0..Sun=6 -> schedule keys Sun=0..Sat=6
    return week.get(dow, {"rest": False, "planned": []})


def day_label(day):
    """Flatten a resolved day into a single human-readable string."""
    parts = []
    for s in day.get("planned", []):
        label = s.get("label", "")
        note = s.get("note", "")
        parts.append(f"{label} ({note})" if note else label)
    return " + ".join(parts) if parts else "Rest"


def resolve_week(schedule, monday_date):
    """Returns {day_name: label_string} for the 7 days starting at monday_date."""
    out = {}
    for i, name in enumerate(DAY_NAMES):
        out[name] = day_label(resolve_day(schedule, monday_date + timedelta(days=i)))
    return out
