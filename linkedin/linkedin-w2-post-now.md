# Week 2 — Post This Wednesday (Jul 23)
## The AWS Architecture Carousel — Your Exact Step-by-Step Guide

> **You are doing this for the first time. That is completely fine.**
> Every step below is a numbered action with a screenshot description so you know
> exactly what you are looking at. Nothing will go wrong if you follow the order.
> Take your time — the post takes about 5 minutes to publish once you sit down.

---

## What You Have Ready

| Item | Status | Where it is |
|---|---|---|
| Carousel PDF (8 slides) | ✅ Generated | `linkedin/linkedin_w2_carousel.pdf` |
| Cover image | ✅ Ready | `linkedin/linkedin_w2_aws_architecture.png` |
| Post text | ✅ Below | Copy from this file |
| First comment | ✅ Below | Copy from this file |

---

## The Night Before (Tuesday Evening — 10 min)

### Step 1 — Message 3 people to seed engagement

This is the single most important action for a new creator. The LinkedIn algorithm
needs early engagement to push your post out. You need 3 people to comment
(not just like — comment) within the first hour.

Open LinkedIn messages and send this to 3 colleagues or connections:

> *"Hey — I'm posting my second LinkedIn post tomorrow morning at 8am on LLMWiki's
> AWS architecture. Would you mind leaving a comment when you see it? Even one line
> helps the algorithm push it out. Really appreciate it."*

**Who to pick:** People who are on LinkedIn regularly and will actually see it.
Former colleagues, current teammates, anyone in tech who owes you a favour.

> ⚠️ **Do this the night before, not morning-of.** You want them to be primed.
> A DM at 8am asking for a comment looks desperate. A DM the night before looks planned.

---

### Step 2 — Open the PDF and check it looks right

1. Navigate to: `linkedin/linkedin_w2_carousel.pdf`
2. Open it — 8 slides should appear
3. Quick check each slide:
   - Slide 1: Hook text visible, dark background, pipeline preview at bottom
   - Slide 6: Two boxes — OpenSearch (red) vs S3 Vectors (green) cost comparison
   - Slide 8: "DM me" CTA + follower prompt
4. If anything looks off — come back to Claude Code and say "fix slide N"

---

## Wednesday Morning — Post Day (8:00am)

Keep this file open on one screen. LinkedIn on the other.

---

### Step 3 — Open LinkedIn

1. Go to **linkedin.com** in your browser
2. Log in if needed
3. You should see your home feed — the stream of posts from people you follow

**You should see this at the top of the feed:**
```
┌─────────────────────────────────────────────┐
│  Start a post                               │
│  📷 Photo  📄 Video  ✍️ Write article       │
└─────────────────────────────────────────────┘
```

---

### Step 4 — Click the Document icon (NOT the Photo icon)

> ⚠️ **THIS IS THE MOST COMMON CAROUSEL MISTAKE.**
> You must upload the PDF as a **Document** post, not as a photo.
> If you click the Photo icon and upload the PDF, LinkedIn will not render it
> as a carousel — it will show as a broken attachment.

**Where the Document icon is:**

1. Click **"Start a post"** — the composer box opens
2. Look at the bottom of the composer box. You will see a row of icons:
   ```
   📷 Photo/Video   📄 Document   🎬 Celebrate   ...
   ```
3. Click the **📄 Document icon** (looks like a page with a folded corner)
4. A file picker opens

> **If you don't see the Document icon:** click the "+" or "More" button at the
> end of the icon row — it is sometimes hidden on smaller screens.

---

### Step 5 — Upload the carousel PDF

1. In the file picker, navigate to:
   `C:\Users\859600\OneDrive - Cognizant\AWSLab\LLMWiki\linkedin\`
2. Select: `linkedin_w2_carousel.pdf`
3. Click Open
4. LinkedIn will process the PDF — this takes 10–30 seconds
5. You will see a preview showing Slide 1 of the carousel with "1 / 8" indicator

**What you should see:**
```
┌──────────────────────────────────────────┐
│  [Slide 1 preview — dark background]     │
│  "We saved $400/month on day one..."     │
│                              1 / 8  →   │
└──────────────────────────────────────────┘
```

If you see a PDF icon instead of a visual preview → LinkedIn didn't render it.
Click the X to remove it and try uploading again.

---

### Step 6 — Add the document title

After upload, LinkedIn asks for a **document title**. This is visible above the carousel.

Type exactly:
```
LLMWiki AWS Architecture — Why We Chose S3 Vectors Over OpenSearch
```

This title is searchable on LinkedIn. It reinforces the SEO keyword "S3 Vectors" and
gives people who see the post a clear reason to click through.

---

### Step 7 — Paste the post text

Click into the text area **above** the carousel preview (not below it).
Paste the following:

---

```
We saved $400/month on day one by NOT using the obvious choice.
Here is the full LLMWiki architecture on AWS — and every decision behind it.

─────────────────────────────
THE INGESTION PIPELINE
─────────────────────────────

Any document. Any format. 3 minutes to queryable.

S3 upload → EventBridge trigger → AWS Textract (PDF/Office/scanned images → Markdown)
→ Amazon Bedrock (chunk, embed, index) → S3 Vectors

Not polling. Pure event-driven. Zero idle cost.

─────────────────────────────
THE QUERY PIPELINE
─────────────────────────────

User question → Lambda → Bedrock Knowledge Base → Claude synthesis
→ Cited answer + Confidence: HIGH / MEDIUM / LOW

Every query logged in DynamoDB. Every source tracked. Full audit trail.

─────────────────────────────
THE COST DECISION
─────────────────────────────

OpenSearch Serverless: $700+/month minimum — whether you use it or not.
S3 Vectors: pay per query. Zero base cost.

Same vector search capability. 1/∞ the floor cost.

─────────────────────────────
THE FIVE PILLARS
─────────────────────────────

🔵 Distributed    Event-driven, no bottleneck
🟢 Fault-tolerant Idempotent Lambdas, DLQs, automatic retry
🔴 Secured        KMS at rest + in transit, IAM least-privilege, VPC
🟡 Scalable       Serverless-first — scales to zero, scales to millions
🟣 Validated      22 unit tests, first-pass green

Full slide deck in the carousel. Every architecture decision explained.

If you're building document-heavy AI and want to see this on your own data —
DM me. 30 minutes. Live demo.

#AWSBedrock #ServerlessArchitecture #CloudArchitecture #AIEngineering #LLMWiki
```

---

### Step 8 — Check these 4 things before clicking Post

Go through this list in order. Each one takes 10 seconds.

**Check 1 — Hook visible above the fold**
Look at the text preview. The first line should read:
> *"We saved $400/month on day one by NOT using the obvious choice."*
This must be the very first thing visible. If there is a blank line or anything before it,
delete it.

**Check 2 — No URLs in the post body**
Scroll through the text. There should be no `http://`, `https://`, or `www.` anywhere
in the post text. If you see one — delete it. You will put any links in the first comment
after posting.

**Check 3 — Hashtags are on the last line**
The last line of the text should be:
`#AWSBedrock #ServerlessArchitecture #CloudArchitecture #AIEngineering #LLMWiki`
Nothing after the hashtags.

**Check 4 — Carousel preview is showing**
You should see the slide 1 preview below the text box with the "1 / 8" page indicator.

---

### Step 9 — Click Post

> ✅ If all 4 checks pass — click **Post**.

The post will appear in your feed within a few seconds.

> ⚠️ **Do NOT navigate away immediately.** Stay on the page.

---

### Step 10 — Post your first comment (within 60 seconds)

This is urgent. The sooner your first comment appears, the better.

1. Your post should now be visible in your feed or at the top of your profile
2. Click the **comment field** under your post
3. Paste this exactly:

```
Next week: this architecture gains a brain.

I'll show you how Neuro-SAN's AAOSA protocol lets 5 specialist agents collaborate
on a single customer question — without any agent ever seeing the sensitive data.

What's your biggest question about the architecture above? Drop it below — I'll answer every one.
```

4. Click **Post comment**

**Why this matters:** Your first comment re-surfaces the post in your followers' feeds.
It also signals to the algorithm that the post is generating conversation before
anyone else has commented. It is the highest-leverage action after clicking Post.

---

### Step 11 — Message your 3 seeds

Immediately after posting, send each of the 3 people you messaged last night:

> *"Just posted! linkedin.com/feed — would love your comment whenever you get a moment."*

Include the direct link to your post (copy it from the browser URL bar after clicking
on your post's timestamp).

---

## The Next 60 Minutes — Stay Engaged

Set a timer for 60 minutes. For the next hour:

**Every time a notification appears:**
- Click it
- Reply to the comment — even one sentence is fine:
  - *"Exactly — the S3 Vectors cost saving was the most surprising part."*
  - *"Great question — the confidence scoring is what makes it enterprise-ready."*
  - *"Thanks for sharing this. DM me if you want to see it live."*

**Why replies matter:** Every reply = another engagement event = algorithm re-surfaces
the post to the commenter's network. 5 comments with 5 replies = 10 engagement events.

**At 9:00am — check Premium viewer list:**
Settings → Premium → Who viewed your profile.
Write down anyone who works at a company that matches your ICP
(healthcare IT, insurance, construction, legal, government).
These are warm leads from this post.

---

## 48 Hours Later — Log the Results

Go to your post → click **"N impressions"** at the bottom.
Record these numbers in `linkedin/llmwiki-linkedin-multiweek-post.md` Part 7 Posted Log:

| What to record | Where to find it |
|---|---|
| Impressions | "N impressions" link under the post |
| Reactions | Reaction count under the post |
| Comments | Comment count under the post |
| Profile views triggered | Premium → Who viewed (Premium only) |
| DMs received | LinkedIn messaging inbox |
| Top commenter job title | Look at the profile of whoever commented most |

Then add the LinkedIn URL of the post to the log (copy from browser bar).

---

## What Success Looks Like for Week 2

| Metric | Good | Great |
|---|---|---|
| Impressions at 48h | 300+ | 800+ |
| Reactions | 15+ | 40+ |
| Comments | 3+ | 10+ |
| Profile views | 20+ | 60+ |
| DMs | 1+ | 3+ |

> **If numbers are lower than expected:** That is completely normal for Week 2.
> The algorithm is still learning your audience. Weeks 5 and 6 (security posts)
> are where carousels typically see their biggest jumps. Stay on the schedule.

---

## You Are Done for This Week

Next post: **Friday Jul 25 — Neuro-SAN & the AAOSA Protocol**

Run `/linkedin-week` on Thursday evening to get the post package for Friday.

---

*PDF: `linkedin/linkedin_w2_carousel.pdf` · Image: `linkedin/linkedin_w2_aws_architecture.png`*
*Series plan: `linkedin/llmwiki-linkedin-multiweek-post.md`*
