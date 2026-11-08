#!/usr/bin/env python3
"""
split_canvas_feed.py  (v2)

Builds one subscribable .ics file per class from your private calendar feeds.

Feeds come from the FEED_URLS environment variable: a JSON list such as

  [
    {"type": "canvas", "url": "https://byu.instructure.com/feeds/calendars/user_X.ics"},
    {"type": "class",  "name": "IS 201", "url": "https://.../learning-suite-feed.ics"}
  ]

  type "canvas": one combined feed; events are split by the trailing
                 "[COURSE CODE]" tag Canvas puts on every event title.
  type "class" : a feed that is already one class; every event goes into
                 a calendar named after "name".

If FEED_URLS is not set, falls back to CANVAS_ICS_URL (a single Canvas feed).

Each run:
  * writes docs/<class-slug>.ics for every class found, plus docs/index.html
    with one-click webcal:// subscribe links (and exams.ics, if present)
  * deletes older *.ics files in docs/ (last semester's classes), EXCEPT
    exams.ics, but only when every feed was fetched successfully
  * never prints feed URLs (they contain private access tokens)
"""

import argparse
import html
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone

from icalendar import Calendar

COURSE_TAG_RE = re.compile(r"\[([^\[\]]+)\]\s*$")
KEEP_FILES = {"exams.ics"}


def slugify(text: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", text.strip().lower())
    return text.strip("-") or "unknown-course"


def fetch_ics(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "canvas-feed-splitter/2.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def load_feed_specs() -> list:
    raw = os.environ.get("FEED_URLS", "").strip()
    if raw:
        specs = json.loads(raw)
    elif os.environ.get("CANVAS_ICS_URL", "").strip():
        specs = [{"type": "canvas", "url": os.environ["CANVAS_ICS_URL"].strip()}]
    else:
        print("ERROR: set FEED_URLS (or CANVAS_ICS_URL).", file=sys.stderr)
        sys.exit(1)

    for i, spec in enumerate(specs, 1):
        if spec.get("type") not in ("canvas", "class") or not str(spec.get("url", "")).startswith("http"):
            print(f"ERROR: feed #{i} is invalid (needs type canvas|class and an http url).", file=sys.stderr)
            sys.exit(1)
        if spec["type"] == "class" and not spec.get("name"):
            print(f"ERROR: feed #{i} is type 'class' but has no name.", file=sys.stderr)
            sys.exit(1)
    return specs


def parse_feed(raw: bytes):
    cal = Calendar.from_ical(raw)
    events = [c for c in cal.walk() if c.name == "VEVENT"]
    timezones = {str(c.get("tzid")): c for c in cal.walk("VTIMEZONE")}
    return events, timezones


def add_to(courses: dict, name: str, events: list, timezones: dict):
    entry = courses.setdefault(name, {"events": [], "tz": {}})
    entry["events"].extend(events)
    entry["tz"].update(timezones)


def collect_courses(specs: list):
    """Returns (courses, failed_count). courses: name -> {"events": [...], "tz": {...}}"""
    courses, failed = {}, 0
    for i, spec in enumerate(specs, 1):
        label = spec.get("name") or f"canvas feed #{i}"
        try:
            events, timezones = parse_feed(fetch_ics(spec["url"]))
        except Exception as exc:  # never print exc text: it can contain the URL
            print(f"  ! {label}: could not be fetched or parsed ({type(exc).__name__})")
            failed += 1
            continue

        if spec["type"] == "class":
            add_to(courses, spec["name"].strip(), events, timezones)
        else:
            by_course = {}
            for ev in events:
                m = COURSE_TAG_RE.search(str(ev.get("summary", "")))
                by_course.setdefault(m.group(1).strip() if m else "Uncategorized", []).append(ev)
            for name, evs in by_course.items():
                add_to(courses, name, evs, timezones)
        print(f"  ok {label}: {len(events)} events")
    return courses, failed


def build_calendar(name: str, entry: dict) -> Calendar:
    cal = Calendar()
    cal.add("prodid", "-//canvas-feed-splitter//v2//")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", name)  # becomes the calendar's name when subscribing
    for tz in entry["tz"].values():
        cal.add_component(tz)
    for ev in entry["events"]:
        cal.add_component(ev)
    return cal


def write_outputs(courses: dict, output_dir: str, base_url, clean_stale: bool):
    os.makedirs(output_dir, exist_ok=True)

    planned, used = [], set()
    for name in sorted(courses):
        slug, n = slugify(name), 2
        while slug in used:
            slug, n = f"{slugify(name)}-{n}", n + 1
        used.add(slug)
        planned.append((name, f"{slug}.ics"))

    if clean_stale:
        keep = KEEP_FILES | {fn for _, fn in planned}
        for fn in os.listdir(output_dir):
            if fn.endswith(".ics") and fn not in keep:
                os.remove(os.path.join(output_dir, fn))
                print(f"  removed stale {fn}")

    rows = []
    for name, fn in planned:
        with open(os.path.join(output_dir, fn), "wb") as f:
            f.write(build_calendar(name, courses[name]).to_ical())
        print(f"  wrote {fn} ({len(courses[name]['events'])} events)")
        rows.append((name, fn, len(courses[name]["events"])))

    if os.path.exists(os.path.join(output_dir, "exams.ics")):
        rows.append(("Exams", "exams.ics", None))

    items = []
    for name, fn, count in rows:
        href = f"{base_url.rstrip('/')}/{fn}" if base_url else fn
        webcal = re.sub(r"^https?://", "webcal://", href)
        extra = f" ({count} events)" if count is not None else ""
        items.append(
            f"<li><strong>{html.escape(name)}</strong>{extra} - "
            f'<a href="{html.escape(webcal)}">subscribe</a> · '
            f'<a href="{html.escape(href)}">https link</a></li>'
        )
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    page = (
        '<!doctype html><html><head><meta charset="utf-8"><title>Class calendars</title></head><body>'
        f"<h1>Class calendars</h1><p>Updated {stamp}. Click subscribe, then pick a color in Calendar.</p>"
        f"<ul>{''.join(items)}</ul></body></html>"
    )
    with open(os.path.join(output_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)
    print("  wrote index.html")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="docs")
    parser.add_argument("--base-url", default=None, help="Public URL where output-dir is hosted")
    args = parser.parse_args()

    specs = load_feed_specs()
    print(f"Fetching {len(specs)} feed(s)...")
    courses, failed = collect_courses(specs)

    if not courses:
        print("ERROR: no classes found; leaving docs/ untouched.", file=sys.stderr)
        sys.exit(1)
    if failed:
        print(f"WARNING: {failed} feed(s) failed; keeping old files (no cleanup this run).")

    write_outputs(courses, args.output_dir, args.base_url, clean_stale=(failed == 0))


if __name__ == "__main__":
    main()
