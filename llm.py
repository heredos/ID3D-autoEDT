#!/bin/python
# %%
from enum import Enum
from datetime import date, time, timedelta, datetime

from openai import OpenAI, pydantic_function_tool
from pydantic import BaseModel, Field

import csv
from urllib.request import urlretrieve
import pickle

# %%
url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQAGARClvI2oikN7uhQOQfaZTYFfW6RhjDZzl7kcW0VUiQjqJwyg-cnOLlkMH3PBmxraMY_9WVF0tM6/pub?output=csv&gid=677852406"
filename = "output.csv"



# %%
#print("init types")
class ClassroomType(str, Enum):
	"""The descriptor for the class type.
	Accepts either CM (lecture) or TP (hands-on practice)"""
	CM = "CM"
	TP = "TP"

class Event(BaseModel):
	"""The Event Class
	conains most information about an event"""
	type: ClassroomType
	name: str
	timeslot: time

class Events(BaseModel):
	"""the event class is a list of events, most commonly, a CM followed by a TD"""
	events: list[Event]
# load preparsed events
preparsedEvents = {}
try:
	with open("ppe.pkl", "rb") as f:
		preparsedEvents = pickle.load(f)
except FileNotFoundError:
	pass

# %%
def parseEvents(cellContent, time)->Events:
	global preparsedEvents
	if cellContent in preparsedEvents:
		return preparsedEvents[cellContent]

	prompts = {
		"morning" : """You are given a cell from a timetable. The cell is for a morning class, usually ranging from 9 AM to 12:30 unless specified otherwise. extract the content into the specified schema.
		the time slot might be split in two events, a CM and a TD. if that's the case, register the CM until 10:30 and the TD after that. make sure they do not overlap.""",
		"noon" : "You are given a cell from a timetable. The cell is for the lunch break, it is empty most of the time unless specified otherwise. It is okay to return an empty event list",
		"afternoon": """You are given a cell from a timetable. The cell is for an afternoon class, usually ranging from 13:30 to 17:45 unless specified otherwise. extract the content into the specified schema.
				the time slot might be split in two events, a CM and a TD. if that's the case, register the CM until 15:00 and the TD after that. make sure they do not overlap."""
	}

    client = OpenAI(base_url="http://localhost:11434")
	response = client.chat.completions.parse(
		model="minicpm5",
		messages=[
			{
				"role": "system",
				"content": """You will be given a cell from a timetable. The cell is for a morning class, usually ranging from 9 AM to 12:30 unless specified otherwise. extract the content into the specified schema.
				the time slot might be split in two events, a CM and a TD. if that's the case, register the CM until 10:30 and the TD after that. make sure they do not overlap.""",
			},
			{"role": "user", "content": cellContent},
		],
		response_format=Events,
	)
	#print(response.to_json())
	print(response.choices[0].message)
	itemlist = Events(events=[])
	if response.choices[0].message.parsed!=None:
		for item in response.choices[0].message.parsed.events:
			itemlist.events+=[item]
	preparsedEvents[cellContent]= itemlist
	# save preparsedEvents to a file
	with open("ppe.pkl", "wb") as f:
		pickle.dump(preparsedEvents, f)
	return itemlist




# %%
def eventsToIcal(events:Events, day, OGdesc):
	td = timedelta(hours=-2)
	ical = ""
	for i in events.events:
		start = datetime.combine(day, i.timeslot)
		tz = i.timeslot.tzinfo.utcoffset(time(0,0))
		seconds = -((86400)*tz.days + tz.seconds)
		nexTime = time(seconds//3600,seconds%3600//60,seconds%60)
		end = datetime.combine(day, nexTime)
		ical+=f"""\nBEGIN:VEVENT
UID:{i.timeslot}{day}@m2id3d-timetable
DTSTAMP:{day.strftime("%Y%m%dT%H%M%SZ")}
DTSTART;TZID=Europe/Paris:{(start+td).strftime("%Y%m%dT%H%M%SZ")}
DTEND;TZID=Europe/Paris:{(end+td).strftime("%Y%m%dT%H%M%SZ")}
SUMMARY:{i.name} {i.type.value}
DESCRIPTION: {OGdesc.replace("\n", "\\n").replace(":",";")}
END:VEVENT\n"""

	return ical

# %%
# download the csv
#print("downloading csv...")
urlretrieve(url, filename)
csvfile = open(filename, "r")
csvContent = csv.reader(csvfile)
timetable = []
for i in csvContent:
	timetable.append(i)
csvfile.close()

# %%
# start parsing
day = date(2026, 8, 31)
icalContents = """
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//M2 ID3D Timetable//EN
CALSCALE:GREGORIAN
METHOD:PUBLISH
X-WR-CALNAME:M2 ID3D 2026-27
X-WR-TIMEZONE:Europe/Paris

BEGIN:VTIMEZONE
TZID:Europe/Paris
BEGIN:STANDARD
DTSTART:19701025T030000
RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU
TZOFFSETFROM:+0200
TZOFFSETTO:+0100
TZNAME:CET
END:STANDARD
BEGIN:DAYLIGHT
DTSTART:19700329T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU
TZOFFSETFROM:+0100
TZOFFSETTO:+0200
TZNAME:CEST
END:DAYLIGHT
END:VTIMEZONE\n"""
#print(icalContents)
# we have 25 weeks but the first week starts column 4
for weekcol in range(4, 29):
	# we have 7 days a week, starting line 4, each day spanning 8 lines
	for dayline in range(4, 44, 8):
		#print(f"\t-----{day}-----",end="\n")
		# aggregate all cellsmorning = ""
		if timetable[dayline+1][weekcol]!="":
			morning = timetable[dayline+1][weekcol]+"\n"
		morning += timetable[dayline+2][weekcol]+"\n"+timetable[dayline+3][weekcol]
		noon = timetable[dayline+4][weekcol]
		afternoon = timetable[dayline+5][weekcol]+"\n"+timetable[dayline+6][weekcol]

		if morning!="\n":
			#print("---morning---")
			#print(morning)
			evts = parseEvents(morning, "morning")
			icalContents+= eventsToIcal(evts, day, morning)

		if noon!="":
			#print("---noon---")
			#print(noon)
			evts = parseEvents(noon, "noon")
			icalContents+= eventsToIcal(evts, day, noon)

		if afternoon!="\n":
			#print("---afternoon---")
			#print(afternoon)
			evts = parseEvents(afternoon, "afternoon")
			icalContents+= eventsToIcal(evts, day, afternoon)


		day=day+timedelta(days=1)
	day=day+timedelta(days=2)

# %%
tz = preparsedEvents["\nRéunion  rentrée à 10h30 "].events[0].timeslot.tzinfo.utcoffset(time(0,0))
seconds = -((86400)*tz.days + tz.seconds)
nexTime = time(seconds//3600,seconds%3600//60,seconds%60)
#print(f"{seconds//3600}:{seconds%3600//60}:{seconds%60}")
#print(nexTime)

# %%
icalContents+="END:VCALENDAR"
with open("output.ics", "wb") as file:
	file.write(icalContents.encode("utf-8"))
