'''
    Program guards:
    1. Conflicting schedules/events by checking my google calendar
    2. Female-only shifts
    3. Certification requirements by checking if levels mentioned in email are in "restricted"
    4. Last second coverage requests by checking if the time the shift starts is less than "min_notice_minutes" from starting
    5. Undesired roles by checking "preferred_role"
    6. Undesired shifts by checking "min_hours", different for each location
'''

import json
import pytz
from datetime import datetime

TIMEZONE = pytz.timezone("America/Toronto")

LEVEL_ALIASES = {
    "bronze medallion": ["bm"],
    "bronze cross": ["bc"],
    "national lifeguard": ["nl", "nls"],
    "aquafit": ["aqua fit"],
}

def to_datetime_str(date: str, time: str) -> str:
    # convert from string to datetime obj to convert using pytz timezone
    dt = datetime.strptime(f"{date}T{time}", "%Y-%m-%dT%H:%M") 
    dt_local = TIMEZONE.localize(dt)     
    return dt_local.isoformat()

def has_conflict(calendar_service, shift: dict) -> bool:
    start = to_datetime_str(shift["date"], shift["start_time"])
    end = to_datetime_str(shift["date"], shift["end_time"])

    # get all events from primary calendar between start and end
    events = calendar_service.events().list(
        calendarId="primary",
        timeMin=start,
        timeMax=end,
        singleEvents=True,
    ).execute() # fire HTTP request

    # if there are any items/events, then there is a conflict
    # returns T if conflict, or F if no conflict
    return len(events.get("items", [])) > 0 

def is_restricted(shift: dict, prefs: dict) -> bool:
    level = (shift.get("level") or "").lower().strip()
    if not level:
        return False
    for canonical in prefs.get("restricted", []):
        aliases = [canonical] + LEVEL_ALIASES.get(canonical, [])
        if any(alias in level for alias in aliases):
            return True
    return False

def final_check(calendar_service, path: str, shift: dict) -> bool:
    # guard 1: calendar conflict
    if has_conflict(calendar_service, shift):
        print(f"Rejected (calendar conflict): {shift}")
        return False

    with open(path) as f:
        prefs = json.load(f)

    # guard 2: female-only shift
    if shift.get("female_only"):
        print(f"Rejected (female only): {shift}")
        return False

    # guard 3: restricted certification level
    if is_restricted(shift, prefs):
        print(f"Rejected (restricted level): {shift}")
        return False

    # guard 4: not enough notice
    min_notice = prefs.get("min_notice_minutes")
    if min_notice is not None:
        shift_start = TIMEZONE.localize(datetime.strptime(f"{shift['date']}T{shift['start_time']}", "%Y-%m-%dT%H:%M"))
        minutes_until = (shift_start - datetime.now(TIMEZONE)).total_seconds() / 60
        if minutes_until < min_notice:
            print(f"Rejected (not enough notice — {int(minutes_until)}min): {shift}")
            return False

    # guard 5: undesired role (not in preferred_role list)
    role = shift.get("role")
    if role and role not in prefs.get("preferred_role", []):
        print(f"Rejected (role): {shift}")
        return False

    # guard 6: shift too short for location
    location = shift.get("location")
    location_prefs = prefs.get("locations", {})
    if location and location in location_prefs:
        min_hours = location_prefs[location]["min_hours"]
        start = datetime.strptime(shift["start_time"], "%H:%M")
        end = datetime.strptime(shift["end_time"], "%H:%M")
        duration_hours = (end - start).seconds / 3600
        if duration_hours < min_hours:
            print(f"Rejected (too short — {duration_hours:.2f}h, min {min_hours}h): {shift}")
            return False

    return True