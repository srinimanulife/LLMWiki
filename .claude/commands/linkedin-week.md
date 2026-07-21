# /linkedin-week — Prepare This Week's LinkedIn Post

Reads the sprint plan, finds today's scheduled post, returns everything needed
to publish, and optionally pre-fills the LinkedIn composer via Playwright MCP.

## Usage
```
/linkedin-week              ← find and prepare today's (or next upcoming) post
/linkedin-week 3            ← explicitly prepare Week 3
/linkedin-week preview      ← show post text only, no browser
```

---

## Instructions for Claude

### Step 1 — Find the right week

Read `linkedin/llmwiki-linkedin-multiweek-post.md`.

Map today's date against the sprint schedule:
```
Mon Jul 21 → W1   Wed Jul 23 → W2   Fri Jul 25 → W3
Mon Jul 28 → W4   Wed Jul 30 → W5   Fri Aug 1  → W6
Mon Aug 4  → W7   Wed Aug 6  → W8   Fri Aug 8  → W9
Mon Aug 11 → W10  Wed Aug 13 → W11  Fri Aug 15 → W12
```

If today exactly matches a sprint date → use that week.
If today is between sprint dates → use the NEXT upcoming sprint date.
If a week number was passed as argument → use that week regardless of date.

### Step 2 — Extract and display the post package

Pull from the week's entry in the multiweek doc:

```
## 📋 Week {N} Post Package — {Sprint Date}

**Topic:** {topic title}
**Format:** {Post + Image / Carousel PDF}
**Image:** linkedin/{filename}

### Post Text (copy-ready)
---
{full post text including hashtags}
---

### First Comment (post within 60 seconds of publishing)
---
{teaser for next week + question to audience}
---

### Hashtags
{hashtags line}

### Checklist before posting
□  Hook visible above "...see more" fold (first 2 lines complete)
□  No external URLs in post body
□  Image file confirmed: linkedin/{filename}
□  3 colleagues messaged to seed engagement
□  Posting time: 8–9am local, Tue/Wed/Thu preferred
```

### Step 3 — Offer browser automation

After displaying the package, ask:

```
Open LinkedIn and pre-fill the composer with this post? 
Playwright MCP will paste the text and attach the image — you review before posting.
(yes / no / preview-only)
```

If **yes** and Playwright MCP is available:
1. Open `https://www.linkedin.com` in the browser
2. Wait for the home feed to load
3. Click "Start a post" button
4. Paste the post text into the composer
5. Click the image/media icon and attach `linkedin/{filename}`
6. **STOP** — do NOT click Post
7. Display:
```
## ✅ LinkedIn Composer Ready

The post is pre-filled. Please:
1. Review the text in the browser
2. Confirm the image looks correct
3. Click **Post** when ready

After posting, come back and say "posted" — I'll give you the first comment to paste.
```

If Playwright MCP is **not available**, say:
```
Playwright MCP is not configured. To enable browser automation, run:
  npm install -g @playwright/mcp
  npx playwright install chromium
  claude mcp add playwright -- npx @playwright/mcp --browser chromium

For now, the post text above is ready to paste manually into LinkedIn.
```

### Step 4 — Post-publish flow

When the user says "posted" or "live":

```
## 📣 First Comment — Post This Now (within 60 seconds)

{teaser for next week's post}

---
Steps:
1. Click the comment field below your post
2. Paste the comment above
3. Click Post comment

Then set a timer for 60 minutes to reply to all incoming comments.
```

Then remind:
```
## ⏱ Next 60 Minutes — Algorithm Window

Reply to every comment. Even one line.
Check Premium "Who Viewed Your Profile" at 9am.
Log impressions at 48h in linkedin/llmwiki-linkedin-multiweek-post.md Part 7.
```
