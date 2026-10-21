from datetime import datetime
from zoneinfo import ZoneInfo


def within_hours(hours, now=None):
    if not hours:
        return False
    try:
        zone = ZoneInfo(hours.get("timezone", "UTC"))
        current = (now or datetime.now(zone)).astimezone(zone)
        start, end = hours["start"], hours["end"]
        clock = current.strftime("%H:%M")
        return start == end or (start <= clock <= end if start < end else clock >= start or clock <= end)
    except (KeyError, ValueError, TypeError):
        return False
