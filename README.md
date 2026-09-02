# Canvas Feed Splitter

Splits your single Canvas "all courses" .ics calendar feed into one .ics
file per course, so you can subscribe to each course separately in Apple
Calendar (or any calendar app) and color-code them individually.

## One-time setup (about 5 minutes)

1. **Create a new GitHub repo**
   Go to github.com → New repository → name it e.g. `canvas-feeds` →
   keep it **Public** (GitHub Pages on free accounts needs a public repo,
   but this repo will only ever contain due-date/assignment-title data,
   not your login credentials) → Create.

2. **Upload these two files** (via the GitHub web UI "Add file" > "Upload files",
   or `git push` if you use git locally), keeping this folder structure:
   ```
   split_canvas_feed.py
   .github/workflows/update-feeds.yml
   ```

3. **Add your Canvas feed URL as a secret** (keeps it out of the public repo)
   Repo → Settings → Secrets and variables → Actions → New repository secret
   - Name: `CANVAS_ICS_URL`
   - Value: your feed URL, e.g.
     `https://byu.instructure.com/feeds/calendars/user_XXXXXXXX.ics`

4. **Turn on GitHub Pages**
   Repo → Settings → Pages → Source: "Deploy from a branch" → Branch: `main`,
   folder: `/docs` → Save.

5. **Run the workflow once manually**
   Repo → Actions tab → "Update split Canvas feeds" → Run workflow.
   After ~30 seconds it'll commit a `docs/` folder containing one `.ics`
   file per course plus an `index.html` with subscribe links.

6. **Find your feed URLs**
   Visit `https://<your-username>.github.io/<repo-name>/` — it'll list a
   webcal link for each course.

## Subscribing in Apple Calendar

For each course:
- Calendar app → File → New Calendar Subscription
- Paste that course's `.ics` URL (from the index page)
- Set Auto-refresh to "Every hour" or similar
- Rename the calendar to the course name and pick a distinct color

## How it stays up to date

The GitHub Action re-runs every 3 hours automatically (see the cron
schedule in `update-feeds.yml`), re-fetching your Canvas feed and
re-publishing the split files. Apple Calendar's own auto-refresh setting
then picks up those changes on its own schedule. You can change the
cron interval or trigger it manually anytime from the Actions tab.

## Notes

- Courses are detected from the `[COURSE CODE]` tag Canvas appends to
  each event title (e.g. "Quiz: Syllabus [ANTHR 110-002]"). If a new
  course is added, it'll automatically get its own file next run.
- Your Canvas feed URL contains an access token — keeping it in a GitHub
  *secret* (not in the code) means it's never exposed in the public repo.
