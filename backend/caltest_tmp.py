from datetime import date
from zoneinfo import ZoneInfo

from jb_workplace.calendar_api import _expand, _parse_calendar

ics = """BEGIN:VCALENDAR
X-WR-CALNAME:내 일정
BEGIN:VEVENT
UID:a
DTSTART;TZID=Asia/Seoul:20261117T093000
DTEND;TZID=Asia/Seoul:20261117T103000
SUMMARY:스탠드업
RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE
EXDATE;TZID=Asia/Seoul:20261118T093000
BEGIN:VALARM
TRIGGER:-PT10M
SUMMARY:alarm
END:VALARM
END:VEVENT
BEGIN:VEVENT
UID:a
RECURRENCE-ID;TZID=Asia/Seoul:20261124T093000
DTSTART;TZID=Asia/Seoul:20261124T140000
DTEND;TZID=Asia/Seoul:20261124T150000
SUMMARY:스탠드업(변경)
END:VEVENT
BEGIN:VEVENT
UID:b
DTSTART;VALUE=DATE:20261120
DTEND;VALUE=DATE:20261122
SUMMARY:워크숍\\, 제주
LOCATION:제주
END:VEVENT
BEGIN:VEVENT
UID:c
DTSTART:20200101T000000Z
DTEND:20200101T010000Z
RRULE:FREQ=MONTHLY;BYDAY=-1FR
SUMMARY:월말 회고
END:VEVENT
BEGIN:VEVENT
UID:d
DTSTART;VALUE=DATE:20150315
RRULE:FREQ=YEARLY
SUMMARY:생일
END:VEVENT
END:VCALENDAR
"""
tz = ZoneInfo("Asia/Seoul")
name, evs = _parse_calendar(ics, tz)
print(name, len(evs))
for e in _expand(evs, date(2026, 11, 1), date(2026, 11, 30), tz, 0, name):
    print(e["start"], e["end_date"], e["all_day"], e["title"])
print([e["start"] for e in _expand(evs, date(2027, 3, 1), date(2027, 3, 31), tz, 0, name)])
