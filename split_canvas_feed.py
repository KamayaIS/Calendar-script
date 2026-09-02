#!/usr/bin/env python3
"""
split_canvas_feed.py

Fetches a combined Canvas .ics calendar feed (the one tied to your user
account, containing every course) and splits it into one .ics file per
course, so each course can be subscribed to separately in a calendar app
and given its own color.

Course is detected from the trailing "[COURSE CODE]" tag Canvas puts at
the end of every event SUMMARY, e.g. "Quiz: Syllabus [ANTHR 110-002]".

Usage:
    CANVAS_ICS_URL="https://byu.instructure.com/feeds/calendars/user_XXXX.ics" \
        python3 split_canvas_feed.py --output-dir docs

Environment:
    CANVAS_ICS_URL   Required. Your personal Canvas calendar feed URL.
                      Kept out of source code / git history on purpose --
                      pass it as an env var (e.g. a GitHub Actions secret).

Output:
    <output-dir>/<course-slug>.ics   one feed per course
    <output-dir>/index.html          a simple page listing each feed's URL
"""

import argparse
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone

from icalendar import Calendar, Event

COURSE_TAG_RE = re.compile(r"\[([^\[\]]+)\]\s*$")


def slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "unknown-course"


def fetch_ics(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "canvas-feed-splitter/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def split_by_course(raw_ics: bytes):
    """Returns dict: course_name -> list[Event]"""
    cal = Calendar.from_ical(raw_ics)
    by_course = {}

    for component in cal.walk():
        if component.name != "VEVENT":
            continue
        summary = str(component.get("summary", ""))
        match = COURSE_TAG_RE.search(summary)
        course = match.group(1).strip() if match else "Uncategorized"
        by_course.setdefault(course, []).append(component)

    return by_course


def build_course_calendar(course_name: str, events: list, source_calname: str) -> Calendar:
    cal = Calendar()
    cal.add("prodid", "-//canvas-feed-splitter//split-by-course//")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", f"{source_calname} — {course_name}")
    for ev in events:
        cal.add_component(ev)
    return cal


def write_outputs(by_course: dict, output_dir: str, source_calname: str, base_url: str | None):
    os.makedirs(output_dir, exist_ok=True)
    written = []

    for course_name, events in sorted(by_course.items()):
        slug = slugify(course_name)
        filename = f"{slug}.ics"
        path = os.path.join(output_dir, filename)
        cal = build_course_calendar(course_name, events, source_calname)
        with open(path, "wb") as f:
            f.write(cal.to_ical())
        written.append((course_name, filename, len(events)))
        print(f"  wrote {filename}  ({len(events)} events) — {course_name}")

    # simple index page with subscribe links, useful when hosted via GitHub Pages
    index_path = os.path.join(output_dir, "index.html")
    rows = []
    for course_name, filename, count in written:
        href = f"{base_url.rstrip('/')}/{filename}" if base_url else filename
        webcal_href = href.replace("https://", "webcal://").replace("http://", "webcal://")
        rows.append(
            f"<li><strong>{course_name}</strong> ({count} events) — "
            f'<a href="{href}">https link</a> · '
            f'<a href="{webcal_href}">webcal link (click to subscribe)</a></li>'
        )

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Canvas feeds by course</title></head>
<body>
<h1>Canvas calendar feeds, split by course</h1>
<p>Generated {generated}. Subscribe to whichever courses you want in Apple Calendar
(File &gt; New Calendar Subscription) using the webcal link, then set a distinct color per calendar.</p>
<ul>
{''.join(rows)}
</ul>
</body></html>"""
    with open(index_path, "w") as f:
        f.write(html)
    print(f"  wrote index.html")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="docs", help="Directory to write split .ics files into")
    parser.add_argument("--base-url", default=None, help="Public base URL where output-dir will be hosted (for index.html links)")
    args = parser.parse_args()

    source_url = os.environ.get("CANVAS_ICS_URL")
    if not source_url:
        print("ERROR: set the CANVAS_ICS_URL environment variable to your Canvas feed URL.", file=sys.stderr)
        sys.exit(1)

    print(f"Fetching {source_url} ...")
    raw = fetch_ics(source_url)

    source_cal = Calendar.from_ical(raw)
    source_calname = str(source_cal.get("x-wr-calname", "Canvas Calendar"))

    by_course = split_by_course(raw)
    print(f"Found {len(by_course)} course(s):")
    write_outputs(by_course, args.output_dir, source_calname, args.base_url)


if __name__ == "__main__":
    main()
