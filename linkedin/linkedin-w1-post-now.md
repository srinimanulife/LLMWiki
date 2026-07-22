# Week 1 — Post This Today (Mon Jul 21)
## The Problem — Your Very First LinkedIn Post, Step by Step

> **This is your first post. Ever. That makes it special and slightly nerve-wracking.**
> Both feelings are correct. Here is the truth: nobody is watching for you to fail.
> The people who see it are exactly the people who should see it.
> Follow the steps below in order. The whole thing takes about 20 minutes the first time.
> Week 2 will take 5 minutes.

---

## What You Have Ready

| Item | Status | Where it is |
|---|---|---|
| Post text | ✅ Below | Copy from this file |
| Image | ✅ Generated | `linkedin/linkedin_w1_the_problem.png` |
| First comment | ✅ Below | Copy from this file |

> Week 1 is a **regular Post + Image** — no PDF, no carousel, no special upload.

---

## How the MCP Setup Helps You (Read This First)

You have two MCP servers running inside Claude Code:

```
filesystem  ✔  Reads linkedin/ files → Claude knows your post text, image, schedule
playwright  ✔  Controls a real Chromium browser → Claude pre-fills LinkedIn for you
```

**What this means for Week 1:**

| Without MCP | With MCP |
|---|---|
| You open a browser manually | Claude opens LinkedIn for you |
| You copy-paste post text | Claude pastes it into the composer |
| You pick the image file | Claude attaches it for you |
| You hunt for the first comment text | Claude gives it to you post-publish |
| You remember when to post | `/linkedin-week` finds today's post automatically |

You still click **Post** yourself — Claude stops and waits for your review.
You are always in control. Claude just removes all the friction.

---

## Step 0 — One-Time LinkedIn Login in the Playwright Browser (Do This Once, Ever)

> ⚠️ **This is the only time you will ever need to log into LinkedIn manually.**
> After this step, Claude reuses your saved session for every week's post — W1 through W12
> and beyond. You will never be asked to log in again unless you clear the profile.

The Playwright MCP uses a persistent browser profile stored at:
`~/.playwright-linkedin-profile`

This profile is empty right now. LinkedIn has never seen it. You need to log in once
to save your cookies into it.

**How to do it — run this in your terminal:**

```bash
export PATH="$HOME/.npm-global/bin:$PATH"
npx playwright open --browser chromium \
  --user-data-dir ~/.playwright-linkedin-profile \
  https://www.linkedin.com
```

> ℹ️ **What happens:** A Chromium browser window opens on your screen
> (via WSLg — the same display system your WSL2 uses for GUI apps).
> It opens linkedin.com.

**In the browser window that opens:**
1. Type your LinkedIn email and password
2. Click **Sign in**
3. If LinkedIn shows a **verification code** screen (2FA):
   - Check your email or phone for the code
   - Type it in and click **Verify**
4. You should now see your LinkedIn home feed — the post stream
5. **Close the browser window**

That is it. LinkedIn session is now saved to `~/.playwright-linkedin-profile`.
Every time Claude opens a browser through the Playwright MCP, it opens this same profile —
already logged in.

**Verify it worked:**
Run the same command again:
```bash
npx playwright open --browser chromium \
  --user-data-dir ~/.playwright-linkedin-profile \
  https://www.linkedin.com
```
If you see your LinkedIn feed immediately (no login screen) → session saved correctly.
Close the browser.

> ⚠️ **If you see the login screen again:** The session didn't save. This can happen if
> LinkedIn forced a full logout. Just log in again — it will save this time.

> ⚠️ **If the browser window doesn't appear at all:** WSLg may not be running.
> Check that your Windows WSL2 is up to date (`wsl --update` from Windows PowerShell).
> Alternatively, use the manual posting path (Step 3b below) — everything still works,
> you just paste text yourself instead of having Claude paste it.

---

## FIRST — One-Time Profile Setup (Do This Before Posting — 15 min)

**You only do this once.** After this, you never touch these settings again.
Skip them and every post you publish this month underperforms.

---

### Profile Step 1 — Turn On Creator Mode

**What it does:** Switches your profile from "Connect" mode to "Follow" mode.
Unlocks post analytics, LinkedIn Newsletter, and signals to the algorithm that
you are a content creator. Without this, visitors see "Connect" — you want "Follow"
so strangers can subscribe without a connection request.

1. Open **your own LinkedIn profile** (click your photo top-left → "View Profile")
2. Scroll down the left column until you see a section called **"Resources"**
3. Inside Resources, click **"Creator mode"**
4. A toggle appears — switch it **On**
5. A dialog asks you to pick **topics** — add these 5:
   - `Artificial Intelligence`
   - `Amazon Web Services`
   - `Cloud Architecture`
   - `Enterprise Software`
   - `Knowledge Management`
6. Click **Done**

**You'll know it worked when:** Your profile now shows a **"Follow"** button
instead of just "Connect". Your posts section moves to the top of your profile.

> ⚠️ **Do this before you post.** The first post creates profile visitors.
> Without Creator Mode, they see "Connect" and most won't bother.
> With Creator Mode, they see "Follow" and many will — growing your audience passively.

---

### Profile Step 2 — Update Your Headline

Your headline appears under your name on every post. Right now it probably says
your job title. That is wasted space.

1. On your profile, click the **pencil / edit icon** near your name
2. Find the **Headline** field (the text directly under your name)
3. Replace whatever is there with:
   ```
   Building agentic knowledge systems on AWS · LLMWiki · Multi-agent AI · Bedrock
   ```
4. Click **Save**

> ⚠️ **Why this matters for SEO:** LinkedIn's search engine indexes headlines.
> When a CTO searches "AWS Bedrock multi-agent" on LinkedIn, your headline
> is what surfaces you. Your current job title surfaces nobody.

---

### Profile Step 3 — Create Your LinkedIn Newsletter

**What it does:** Every person who subscribes gets an **email** when you publish
an Article. This bypasses the algorithm — a direct line to your audience.
Create it now so the option to subscribe appears on your first post.

1. On the LinkedIn home feed, click **"Write article"** (top of feed, next to "Start a post")
2. The article editor opens — you are NOT writing an article yet, just creating the newsletter
3. In the top-right corner click **"Manage"**
4. Click **"Create newsletter"**
5. Fill in:
   - **Name:** `LLMWiki: Building Agentic Knowledge Systems`
   - **Description:** `Weekly technical deep-dives on multi-agent AI, AWS Bedrock architecture, and enterprise knowledge management — by Srinivasan Sethuraman`
   - **Frequency:** Weekly
   - **Cover image:** Click the image area → upload `linkedin/linkedin_w1_the_problem.png`
6. Click **Done**
7. Close the article editor — you don't need to publish anything yet

> ⚠️ **Do this before your first post.** LinkedIn shows a "Subscribe to newsletter"
> prompt to people who read your posts. If the newsletter doesn't exist yet, that
> moment is lost. Takes 3 minutes.

---

### Profile Step 4 — Enable Open Profile

This allows anyone on LinkedIn to message you for free, even if you're not connected.
Your post ends with "DM me" — this removes the barrier.

1. Click your profile photo → **Settings & Privacy**
2. Go to **Visibility** → **Profile viewing options**
3. Scroll to **Open Profile** → toggle **On**

Done. Anyone who reads your post can now DM you without friction.

---

## Now — Message 3 People to Seed Engagement

> ⚠️ **Do this before you open the post composer.**
> The algorithm judges your post in the first 60 minutes.
> Having 3 comments arrive early is the difference between 200 impressions and 2,000.

Open LinkedIn messages and send this to 3 people — colleagues, former teammates,
anyone in your network who is on LinkedIn:

> *"Hey — I'm publishing my first LinkedIn post this morning on LLMWiki, an AI knowledge
> platform I built on AWS. Would you mind leaving a comment when you see it?
> Even one line helps the algorithm push it out. Really appreciate it."*

**Who to pick:**
- People who check LinkedIn in the mornings
- People in tech — they are your target audience and their comment carries more weight
- Former Cognizant colleagues, AWS community contacts, anyone who has seen you present

Send the messages, then come back here and continue.

---

## Posting — The Exact Sequence

You have two paths. **Path A uses Claude + Playwright MCP** (recommended).
**Path B is manual** — use it if the browser window doesn't appear.

---

### Path A — Claude Pre-fills LinkedIn for You (Recommended)

**In your Claude Code terminal, type:**

```
/linkedin-week
```

Claude reads the sprint plan, finds Week 1, and shows you the full post package.
Then it asks:

```
Open LinkedIn and pre-fill the composer? (yes / no)
```

**Type: yes**

**What you will see happen (Claude drives, you watch):**
1. A Chromium browser window opens on your screen
2. Your LinkedIn home feed loads — already logged in from Step 0
3. Claude clicks **"Start a post"**
4. Claude pastes the full post text into the composer
5. Claude clicks the photo icon and attaches `linkedin_w1_the_problem.png`
6. **Claude stops. The Post button is not clicked.**
7. In your terminal:
   ```
   ✅ LinkedIn composer is ready.
   Review the text and image in the browser.
   Click Post when you are happy with it.
   Come back here after posting and say "posted".
   ```

**You review the browser:**
- Read the post text — does the hook appear first before "...see more"?
- Check the image preview — dark background, split panel, AWS flow, five pillars?
- Click **Post** when ready

> ✅ **Claude never clicks Post for you.** You are always the publisher.

After clicking Post, come back to Claude Code and type **"posted"** — Claude will
give you the first comment text to paste immediately.

---

### Path B — Manual Posting (if the browser window does not open)

### Step 1 — Open the post composer

1. Go to **linkedin.com** in your own browser
2. At the top of the feed you'll see a box that says **"Start a post"**
3. Click it — a composer window opens

---

### Step 2 — Paste the post text

Click inside the composer text area. Paste the following text exactly as shown:

---

```
When a senior engineer resigns, they don't just take their badge.
They take 25 years of decisions, patterns, and hard-won answers with them.

I watched this happen across enterprises for 25 years.
SharePoint didn't fix it. Confluence didn't fix it. Wiki pages didn't fix it.

So I built LLMWiki — a production-grade agentic knowledge platform on AWS.
Here is the full picture.

─────────────────────────────
THE OLD WAY  (still running at most enterprises today)
─────────────────────────────

📁  Critical docs buried in shared drives no one searches
🧠  SME tribal memory as the only reliable source of truth
📧  Email thread to find the expert — 2 days for a cited answer
🚪  Answer walks out the door with the person who held it

─────────────────────────────
THE NEW WAY  (LLMWiki on AWS)
─────────────────────────────

PDFs / Office / Runbooks / Scanned docs
           ↓
        Amazon S3  ←  event trigger on upload
           ↓
     AWS Textract  ←  converts any format to structured text
           ↓
  Amazon Bedrock (Claude)  ←  chunks, embeds, understands
           ↓
       S3 Vectors  ←  vector store, no OpenSearch cost
           ↓
   Lambda Query Layer  ←  RAG retrieval + Claude synthesis
           ↓
  Neuro-SAN Multi-Agent Network
           ↓
  Cited Answer  +  Confidence Score  +  Gap Detection

─────────────────────────────
THE FIVE PILLARS  (production, not a demo)
─────────────────────────────

🔵  Distributed     Event-driven ingestion + retrieval,
                    independent components, no bottleneck

🟢  Fault-tolerant  Idempotent Lambdas, DLQs, DynamoDB
                    state persistence, automatic retry

🔴  Secured         KMS encryption at rest + in transit,
                    IAM least-privilege, VPC isolation,
                    full audit trail

🟡  Scalable        Serverless-first — scales to zero,
                    scales to millions of documents

🟣  Validated       22 unit tests generated by Codex
                    via Claude Code fusion harness
                    First-pass: 22 passed. 0 failed.

─────────────────────────────
THIS IS NOT ONE INDUSTRY'S PROBLEM
─────────────────────────────

The same architecture deploys to:

→  Healthcare IT   — implementation runbooks, clinical protocols
→  Construction    — 200,000 project documents per job site
→  Insurance       — policy lookups that take adjusters 45 minutes
→  Legal           — case strategy that leaves with every partner
→  Manufacturing   — SOPs and failure patterns in engineer heads
→  Public sector   — municipal codes, permit procedures, regulations

Every industry that runs on documents and people — not systems —
has this problem. LLMWiki is the fix.

─────────────────────────────
THE INSIGHT THAT TOOK 25 YEARS TO ACT ON
─────────────────────────────

Your best people are not expensive because of what they know.

They are expensive because they are the only ones who can find it.

LLMWiki makes that knowledge queryable by everyone — permanently.
The wiki compounds. Every document uploaded makes every future
answer better. It does not reset when someone resigns.

If your organisation is still relying on tribal knowledge to operate,
I will show you what this looks like on your own documents.

30 minutes. Your documents. Live demo. DM me.

#LLMWiki #AWSBedrock #EnterpriseAI #AIAgents #GenerativeAI
```

---

After pasting, look at the text preview in the composer. The very first thing visible
before the "...see more" cut should be:

> *"When a senior engineer resigns, they don't just take their badge."*

If you see anything before that line — a blank line, a space — delete it.

---

### Step 3 — Add the image

1. Look at the bottom of the composer for the icon row:
   ```
   📷 Photo/Video   📄 Document   🎬 Celebrate   ...
   ```
2. Click **📷 Photo/Video** (the camera icon)
3. A file picker opens — navigate to:
   `C:\Users\859600\OneDrive - Cognizant\AWSLab\LLMWiki\linkedin\`
4. Select: `linkedin_w1_the_problem.png`
5. Click **Open**
6. The image preview appears in the composer — dark background, before/after split panel,
   AWS architecture flow, five pillar badges, quote strip at the bottom

**Optional — add alt text:**
After the image uploads, LinkedIn shows an **"Add alt text"** link under it.
Click it and type:
```
LLMWiki architecture: before state showing tribal knowledge problem versus
AWS pipeline with S3, Textract, Bedrock, S3 Vectors, Lambda and five production pillars
```
This helps accessibility and is indexed by LinkedIn search.

---

### Step 4 — Run the 4-point check before posting

Go through this list top to bottom. 30 seconds total.

```
□  First line of post is the hook — "When a senior engineer resigns..."
   (nothing before it, not even a blank line)

□  No URLs anywhere in the post text
   (no http://, no linkedin.com/, no aws.amazon.com/ — nothing)

□  Hashtags are on the very last line:
   #LLMWiki #AWSBedrock #EnterpriseAI #AIAgents #GenerativeAI

□  Image is showing in the preview below the text
   (dark split-panel image, not a broken icon)
```

All 4 checked? → Click **Post**.

---

### Step 5 — Post your first comment immediately (within 60 seconds)

This is the move that separates creators who grow from creators who post into the void.

1. Your post now appears in your feed
2. Scroll to it — click the **comment field** under the post
3. Paste this:

```
Next week: the full AWS architecture that makes this possible.

S3 → Textract → Bedrock → S3 Vectors → Lambda — and why we chose S3 Vectors
over OpenSearch to save $400/month on day one.

What's your biggest question about institutional knowledge management?
Drop it below — I'll answer every one.
```

4. Click **Post comment**

> ⚠️ **This comment does two things:**
> 1. Re-surfaces your post in the feed of anyone who sees the comment thread
> 2. Gives your 3 seeds something to reply to — a thread is more visible than a standalone post

---

### Step 6 — Send the post link to your 3 seeds

1. Click on the timestamp of your post (e.g., "just now" or "1m")
2. This opens the post on its own page — copy the URL from the browser
3. Message each of your 3 seeds:
   > *"Just posted! Here's the link: [https://www.linkedin.com/posts/srinivasan-sethuraman-b942173_llmwiki-awsbedrock-enterpriseai-share-7485444461800386560-S59w/?utm_source=share&utm_medium=member_desktop&rcm=ACoAAACQzuABKJsTqfeBYfA1SZn0QPnGUv1JXPQ] — would love your comment when you get a chance."*

---

## The Next 60 Minutes — The Algorithm Window

Set a phone timer for **60 minutes**.

For the next hour, keep LinkedIn open and reply to every notification:

**When someone likes:**
- No action needed (likes are worth less than comments algorithmically)

**When someone comments:**
- Reply within 5 minutes
- Write something specific, not just "Thanks!"
- Example replies:
  - *"Exactly — the tribal knowledge problem is the one everyone recognises but nobody has solved systematically. DM me if you want to see how LLMWiki handles it."*
  - *"Great question — the S3 Vectors vs OpenSearch decision was the biggest architectural choice. I'll cover it in detail next week."*
  - *"25 years of watching this happen — and the fix turned out to be simpler than I expected. Full architecture breakdown Wednesday."*

**When someone follows you:**
- Send a thank-you message: *"Thanks for following — full AWS architecture breakdown coming Wednesday."*

**At 9am — check who viewed your profile:**
If you have LinkedIn Premium activated, go to:
Profile → Analytics → Who viewed your profile

Anyone who viewed your profile after your post appeared is a warm lead.
Write down names and companies for follow-up.

---

## 48 Hours Later — Log Your Results

Go to your post → click **"N impressions"** at the bottom left.

Record in `linkedin/llmwiki-linkedin-multiweek-post.md` → Part 7 Posted Log:

| Metric | Where to find it |
|---|---|
| Impressions | "N impressions" link under post |
| Reactions | Reaction emoji count |
| Comments | Comment count |
| DMs | LinkedIn messaging inbox |
| Profile views | Premium analytics (if active) |
| Top commenter title | Check their profile |

Also copy the post URL from the browser and paste it into the log.

---

## What to Expect — First Post Reality Check

| Metric | Typical first post | What it means |
|---|---|---|
| Impressions | 100–500 | Algorithm is learning your audience |
| Reactions | 5–20 | Perfectly normal |
| Comments | 2–8 | Good if you seeded 3 people |
| DMs | 0–2 | Any DM is a win on post 1 |
| New followers | 5–30 | These compound — every future post reaches them |

> **The number that actually matters at Week 1 is not impressions — it is followers gained.**
> Every person who follows you after this post sees every future post.
> 20 new followers today means 20 more people in the Week 2 audience.
> By Week 6 (the security posts), your audience will be 5–10× what it is today.
> **The sprint compounds. Stay on schedule.**

---

## What's Next

| Day | Action |
|---|---|
| Today (Mon Jul 21) | Post W1 ← you are here |
| Tomorrow (Tue Jul 22) | Check 24h analytics. Reply to any new comments. |
| Wednesday (Jul 23) | Post W2 — AWS Architecture carousel |
| Thursday (Jul 24) | Run `/linkedin-week` to prepare W3 post package |
| Friday (Jul 25) | Post W3 — Neuro-SAN & AAOSA Protocol |

For Wednesday: open `linkedin/linkedin-w2-post-now.md` — everything is ready including the PDF carousel.

---

## You've Got This

You have 25 years of hard-won experience in this post.
You built a production system that solves a real problem.
You have a professional image, a prepared post, and a plan.

The only thing between you and the first post is clicking Post.

Go do it.

---

*Image: `linkedin/linkedin_w1_the_problem.png` · Series plan: `linkedin/llmwiki-linkedin-multiweek-post.md`*
*Week 2 guide: `linkedin/linkedin-w2-post-now.md`*
