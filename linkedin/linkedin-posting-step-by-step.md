# LinkedIn Posting — Step-by-Step Field Guide
### Posts · Articles · SEO · Algorithm · MCP Automation · AWS Bedrock · First-Timer Gotchas · Weekly Rhythm
**Author:** Srinivasan Sethuraman · LLMWiki Series

---

> **You have already done the hardest part.** You built something real, you have the content
> written, and you have 12 professional images ready. This guide turns that into a publishing
> habit — and with the MCP + Bedrock setup in Part 0, Claude can assist you directly
> inside Claude Code for every weekly post. Follow it once and it becomes muscle memory.
> You will look back at Week 12 and wonder why you waited.

---

## How to Use This Guide

| Situation | Go to |
|---|---|
| **Set up Claude Code + MCP to assist with posting** | **Part 0** ← start here |
| Setting up LinkedIn for the first time | Part 1 |
| Publishing your first post (Post 001 today) | Part 2 |
| Understanding why things are done this way | Part 3 — Algorithm |
| Writing and publishing a LinkedIn Article | Part 4 |
| SEO — making content findable on Google | Part 5 |
| Weekly rhythm for the 12-week sprint | Part 6 |
| Gotchas and common first-timer mistakes | Part 7 |
| Quick reference checklists | Part 8 |

---

## Part 0 — MCP + AWS Bedrock: Let Claude Code Assist Every Weekly Post

You already have Claude Code running on **AWS Bedrock** (`CLAUDE_CODE_USE_BEDROCK=true`,
model `us.anthropic.claude-3-7-sonnet-20250219-v1:0`). That means Claude's intelligence
is already inside your terminal — connected to your AWS account, your files, your images.

Two MCP servers turn this from "Claude answers questions" into
**"Claude reads your files, drafts the post, and opens LinkedIn ready for you to paste"**:

| MCP Server | What it does for LinkedIn posting |
|---|---|
| **Filesystem MCP** | Claude can read `linkedin/` directly — the post text, images, multiweek plan — without you copy-pasting anything |
| **Playwright MCP** | Claude can drive a real browser: open LinkedIn, navigate to the post composer, paste text, attach the image — you just review and click Post |

Both are free, open-source, and run locally. Nothing leaves your machine.

---

### Step 0.1 — Install the Filesystem MCP (5 minutes)

The Filesystem MCP lets Claude Code read and write files in specified directories.
For LinkedIn posting, this means Claude can read `linkedin/llmwiki-linkedin-multiweek-post.md`,
pull out the week's post text and image path, and hand them to you — or to Playwright.

**Install:**
```bash
npm install -g @modelcontextprotocol/server-filesystem
```

**Register with Claude Code:**
```bash
claude mcp add filesystem -- npx -y @modelcontextprotocol/server-filesystem \
  "/mnt/c/Users/859600/OneDrive - Cognizant/AWSLab/LLMWiki/linkedin"
```

This gives Claude read/write access to only the `linkedin/` directory — nothing else.

**Verify it registered:**
```bash
claude mcp list
# Should show: filesystem  npx -y @modelcontextprotocol/server-filesystem ...
```

**What you can now say to Claude Code:**

```
Read linkedin/llmwiki-linkedin-multiweek-post.md and give me the ready-to-paste
post text and image filename for Week 3 (Fri Jul 25).
```

Claude reads the file directly and returns:
- The exact post text, formatted, ready to paste
- The filename: `linkedin_w3_neuro_san.png`
- The hashtags
- The first-comment text for posting immediately after

---

### Step 0.2 — Install the Playwright MCP (10 minutes)

Playwright MCP lets Claude Code control a real browser. For LinkedIn posting:
Claude opens Chrome, navigates to LinkedIn, clicks "Start a post", pastes your text,
attaches the image, and waits for you to review before clicking Post.

> ⚠️ **You remain in control.** Claude never clicks "Post" on its own — it stops and
> asks you to review. The final Post click is always yours. This prevents accidental
> publishing of draft content.

**Install:**
```bash
npm install -g @playwright/mcp
# Install browsers (only needed once — ~200MB):
npx playwright install chromium
```

**Register with Claude Code:**
```bash
claude mcp add playwright -- npx @playwright/mcp --browser chromium
```

**Verify:**
```bash
claude mcp list
# Should show both: filesystem and playwright
```

**What you can now say to Claude Code:**

```
/linkedin-post week3
```

Or more explicitly:

```
Open LinkedIn in a browser and prepare the Week 3 post for me.
Read the post text from linkedin/llmwiki-linkedin-multiweek-post.md,
navigate to linkedin.com, open the post composer, paste the text,
and attach linkedin/linkedin_w3_neuro_san.png. Stop before clicking Post.
```

Claude will:
1. Read the multiweek plan file (Filesystem MCP)
2. Open `linkedin.com` in Chromium (Playwright MCP)
3. Log in (uses your saved browser session — see Step 0.3)
4. Click "Start a post"
5. Paste the post text
6. Attach the correct week's image
7. **Stop and show you a screenshot** — you review, then click Post yourself

---

### Step 0.3 — Log Into LinkedIn in the Playwright Browser (Once)

Playwright uses its own browser profile. You need to log in once so it remembers your session.

```bash
# Launch Playwright browser manually to log in:
npx playwright open --browser chromium https://www.linkedin.com
```

1. The Chromium browser opens
2. Log into LinkedIn normally (your usual credentials)
3. Complete any 2FA if prompted
4. Close the browser — Playwright saves the session

After this, Claude can open LinkedIn without logging in again (until the session expires,
usually ~30 days).

> ⚠️ **If LinkedIn asks for 2FA mid-session:** Claude will pause and show you the 2FA
> screen. Complete it manually, then tell Claude to continue.

---

### Step 0.4 — Verify the Full Setup

Run this in your Claude Code session to confirm everything works:

```
Can you read linkedin/llmwiki-linkedin-multiweek-post.md and tell me 
the post title, image filename, and hashtags for Week 4 (Mon Jul 28)?
```

Expected response: Claude reads the file and returns the exact Week 4 details
without you having to open the file yourself.

Then:
```
Open linkedin.com in the browser and click "Start a post" — just stop there,
don't fill anything in yet.
```

Expected: Chromium opens, LinkedIn loads, post composer appears. If both work —
your MCP stack is fully operational.

---

### Step 0.5 — The Weekly Posting Command (Once Everything Is Set Up)

**Every Monday/Wednesday/Friday morning, you run one command:**

```
Prepare and pre-fill my LinkedIn post for today. 
Read linkedin/llmwiki-linkedin-multiweek-post.md, find the post scheduled for today,
open LinkedIn, fill the composer with the post text and image, 
then stop for my review before posting.
```

Claude will:
1. Check today's date against the sprint schedule
2. Pull the correct post text, image, hashtags, and first-comment text
3. Open LinkedIn → composer → paste everything → attach image
4. Display a preview summary: hook, word count, hashtags, image filename
5. Wait for you to say "post it" or "tweak the hook"

**If you want to adjust the hook before posting:**
```
Change the hook to: "Most enterprises lose 10,000 hours a year to this single problem."
Then re-fill the composer.
```

Claude rewrites the hook, re-pastes in the browser, you review again.

**After posting:**
```
Post is live. Post the first comment now:
"Full Neuro-SAN architecture breakdown coming Monday. 
What questions do you have about multi-agent orchestration?"
```

Claude pastes that into the comment field. You click "Post comment."

---

### Step 0.6 — AWS Bedrock Connection: What You Already Have

Your Claude Code is already on Bedrock — confirmed from `~/.claude/settings.json`:

```json
"CLAUDE_CODE_USE_BEDROCK": "true",
"ANTHROPIC_MODEL": "us.anthropic.claude-3-7-sonnet-20250219-v1:0"
```

This means:
- **No Anthropic API key needed** — Claude authenticates via your AWS credentials
- **Billing goes through AWS** — same account (392568849512) as the rest of LLMWiki
- **Model is Claude 3.7 Sonnet** — same generation powering your Neuro-SAN agents

The Bedrock connection is already working — you are using it right now.

**What the Bedrock connection adds for LinkedIn posting specifically:**

| Capability | How it helps |
|---|---|
| Claude reads `linkedin/` files directly (via Filesystem MCP) | No copy-pasting — Claude sees the source of truth |
| Claude can call `invoke_model` on Bedrock Claude 3.7 | Same intelligence as claude.ai, inside your terminal |
| AWS IAM governs access | The MCP filesystem access is controlled by your IAM role — enterprise-grade |
| Cost on AWS invoice | Everything in one bill — no separate Anthropic subscription |

**Optionally — use Bedrock directly for post generation (without the proxy):**

If you want to call Bedrock's Claude directly from a script (for automation or testing):

```python
import boto3, json

bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")

response = bedrock.invoke_model(
    modelId="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
    body=json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1000,
        "messages": [{
            "role": "user",
            "content": "Write a LinkedIn hook for a post about Sly Data — structural prompt injection defence in multi-agent AI systems. 2 lines, specific, practitioner voice."
        }]
    }),
    contentType="application/json",
    accept="application/json"
)

result = json.loads(response["body"].read())
print(result["content"][0]["text"])
```

Run via: `python3 scripts/bedrock_linkedin_hook.py`

This is useful for generating hook variations quickly before deciding which angle to use.

---

### Step 0.7 — Optional: Create a `/linkedin-week` Skill

Add this to `.claude/commands/linkedin-week.md` to make weekly posting a one-word command:

```markdown
# /linkedin-week — Prepare This Week's LinkedIn Post

Read linkedin/llmwiki-linkedin-multiweek-post.md.
Find the post entry for the nearest upcoming sprint date.
Return:
1. The full post text, formatted and ready to paste
2. The image filename from linkedin/
3. The hashtags (last line)
4. The first-comment text to post immediately after publishing
5. The teaser line for the next week

Then ask: "Open LinkedIn and pre-fill the composer? (yes/no)"
If yes: use Playwright MCP to open linkedin.com, navigate to Start a post,
paste the text, attach the image, and stop for review.
```

Save it, then use it every week:
```
/linkedin-week
```

That single command reads your plan, finds today's post, and pre-fills LinkedIn.
The entire weekly prep becomes one command plus a review click.

---

---

## Part 1 — One-Time Profile Setup (Do This First — 15 Minutes)

These are set once and never touched again. Skip them and every post underperforms.

---

### Step 1.1 — Turn On Creator Mode

**What it does:** Switches your profile from "Connect" to "Follow" mode, unlocks post analytics,
enables LinkedIn Newsletter, and signals to the algorithm that you are a content creator.

> ⚠️ **CRITICAL — Do this before your first post.** Without Creator Mode, visitors see
> "Connect" not "Follow". You want followers, not just connections.

**How to do it:**
1. Go to your LinkedIn profile (your own page, not the feed)
2. Scroll down to the **"Resources"** section in the left column
3. Click **"Creator mode"** → toggle **On**
4. A dialog appears asking for your **creator topics** — add these 5 exactly:
   - `Artificial Intelligence`
   - `Amazon Web Services`
   - `Cloud Architecture`
   - `Enterprise Software`
   - `Knowledge Management`
5. Click **Done**

**What changes immediately:**
- Profile now shows **"Follow"** button prominently
- Your posts section moves to the top of your profile
- Analytics tab appears on your posts
- You can now create a Newsletter

---

### Step 1.2 — Optimise Your Profile Headline

Your headline appears under every post you publish. It is the first thing anyone reads
after your name. A weak headline kills post credibility.

**Current vs target:**

| Weak (generic) | Strong (specific) |
|---|---|
| "Senior Software Engineer at Cognizant" | "Building agentic knowledge systems on AWS · LLMWiki · Multi-agent AI · Bedrock" |

**How to edit:**
1. Click the pencil icon on your profile
2. Find **Headline** (the line right under your name)
3. Write: `Building agentic knowledge systems on AWS · LLMWiki · Multi-agent AI · Bedrock`
4. 220 character limit — use it fully

> ⚠️ **SEO GOTCHA:** LinkedIn search indexes your headline. The keywords "agentic knowledge",
> "AWS Bedrock", "multi-agent AI" are what your ICP (VP Engineering, CTOs) search. Put them
> here, not just in posts.

---

### Step 1.3 — Write a Strong "About" Section

The About section is indexed by **Google**. This is free SEO real estate that most people waste.

**Formula:**
```
Line 1–2: What you build and who it helps (the hook — same rules as a post hook)
Lines 3–5: The specific problem you solve
Lines 6–8: Credentials / proof points (years, companies, results)
Line 9: CTA — what you want them to do
```

**Draft for Srini:**
```
I build production AI agents that turn document chaos into instant, cited answers.

For 25 years I watched enterprises lose institutional knowledge every time a senior
engineer resigned. SharePoint didn't fix it. Confluence didn't fix it. So I built LLMWiki —
a multi-agent knowledge platform on AWS Bedrock that makes that knowledge queryable forever.

Tech stack: AWS Bedrock · S3 Vectors · Neuro-SAN agents · Claude Code · Lambda · DynamoDB.
25 years across healthcare IT, insurance, government, construction.

Building in public. 12-week series: the full architecture, security model, and business case.

👉 DM me if you want a live demo on your own documents.
```

> ⚠️ **Google indexes About sections.** Keywords to include: `agentic knowledge management`,
> `AWS Bedrock`, `multi-agent AI`, `RAG architecture`, `enterprise AI`. These are what
> potential clients type into Google, not just LinkedIn search.

---

### Step 1.4 — Create Your LinkedIn Newsletter

**What it does:** Every person who subscribes gets an **email notification** when you publish.
This bypasses the algorithm entirely — a direct line to your audience.

> ⚠️ **DO THIS before posting Week 1.** The first post creates your first batch of subscribers.
> If the Newsletter doesn't exist yet, that subscriber moment is lost forever.

**How to create it:**
1. Click **"Write article"** on your LinkedIn home feed
2. In the article editor, click **"Manage"** in the top right
3. Click **"Create newsletter"**
4. Fill in:
   - **Name:** `LLMWiki: Building Agentic Knowledge Systems`
   - **Description:** `Weekly technical deep-dives on multi-agent AI, AWS Bedrock architecture, and enterprise knowledge management — by Srinivasan Sethuraman`
   - **Cover image:** Upload `linkedin/linkedin_w1_the_problem.png`
   - **Frequency:** Weekly
5. Click **Done**

LinkedIn will now offer readers the option to subscribe when you publish any Article linked
to this Newsletter.

---

### Step 1.5 — Set Profile to Open Profile

**What it does:** Allows anyone on LinkedIn (even non-connections) to send you a free message.
Your posts end with "DM me" — this removes the barrier.

**How to do it:**
1. Click your profile photo → **Settings & Privacy**
2. Navigate to **Visibility** → **Profile viewing options**
3. Scroll to **Open Profile** → toggle **On**

Cost: free with Basic or Premium.

---

## Part 2 — Publishing Your First Post (Post 001 — Step by Step)

**Post 001 text is in:** `~/.claude/commands/linkedin-post.md` → Proven Post Library → Post 001

**Image is ready at:** `linkedin/linkedin_w1_the_problem.png`

---

### Step 2.1 — The Night Before: Prepare

Do this the evening before your scheduled post day (Sun evening for Mon Jul 21):

1. Open `linkedin/llmwiki-linkedin-multiweek-post.md` → Week 1 entry
2. Read the post text once — refresh yourself on the story arc
3. Copy the full Post 001 text to your clipboard (or a text file)
4. Line up 3 people to seed engagement:
   - Message them: *"I'm posting my first LinkedIn post tomorrow at 8am on LLMWiki —
     would you leave a comment? Even one sentence helps the algorithm push it out."*
   - Choose people who are on LinkedIn regularly and will see it within the hour

---

### Step 2.2 — Post Day: 8:00am

**Time window matters.** The algorithm measures engagement in the **first 60 minutes**.
Posting at 8–9am local time (Tue–Thu) hits your ICP when they check LinkedIn with their morning coffee.

**Exact sequence:**

**Step 1 — Open LinkedIn and start a new post**
1. Click **"Start a post"** on the home feed (NOT "Write article" — that's for Articles)
2. The post composer opens

**Step 2 — Paste the post text**
1. Paste the full Post 001 text
2. Preview it — check that blank lines between paragraphs are preserved
3. The hook (first 2 lines) must be visible **before** the "...see more" cut
   - LinkedIn shows roughly 3–4 lines before truncating. Your hook must be in line 1–2.

> ⚠️ **CRITICAL GOTCHA:** If your first line is too long or there is no blank line after
> the hook, LinkedIn wraps it and the "see more" cut happens mid-sentence. This kills click-through.
> Post 001's hook: *"When a senior engineer resigns, they don't just take their badge."*
> is deliberately short so the hook lands completely above the fold.

**Step 3 — Add the image**
1. Click the **photo icon** (camera) in the composer toolbar
2. Navigate to `linkedin/linkedin_w1_the_problem.png`
3. Upload it — it should preview in the composer
4. **Do NOT add alt text that repeats the post text** — write a brief description for accessibility:
   `"LLMWiki architecture diagram: old way vs AWS pipeline with five production pillars"`

**Step 4 — Check for external links — REMOVE THEM**

> ⚠️ **ALGORITHM KILLER:** Any URL in the post body (github.com, aws.amazon.com, any link)
> causes LinkedIn to reduce distribution by ~50%. The algorithm penalises posts that push
> traffic off the platform.

- Post 001 text has no URLs — you are safe
- If you ever want to share a link: post it in the **first comment** after publishing

**Step 5 — Add hashtags**
Post 001 already ends with: `#LLMWiki #AWSBedrock #EnterpriseAI #AIAgents #GenerativeAI`

Hashtag rules:
- 3–5 only (more looks spammy, hurts reach)
- Last line of the post, on their own line
- Mix: 1 broad (`#GenerativeAI`) + 2 mid-tier (`#AWSBedrock`, `#EnterpriseAI`) + 1–2 niche (`#LLMWiki`, `#AIAgents`)

**Step 6 — Do NOT schedule (post immediately)**
Click **"Post"** at 8:00am sharp. The algorithm rewards immediate engagement. Scheduled posts
sometimes get lower initial distribution.

---

### Step 2.3 — 8:01am: Post Your First Comment Immediately

The moment the post publishes, **immediately post a comment yourself**:

```
Full AWS architecture breakdown coming Wednesday — S3 → Textract → Bedrock → S3 Vectors → Lambda.

Drop your questions below. I'll answer every one.
```

**Why this matters:**
- Your first comment re-surfaces the post in the commenter's network
- It signals to the algorithm that this post generates conversation
- It also gives you a place to put a link if you have one: `"Full write-up: [link]"`

> ⚠️ **GOTCHA:** Do not put the link in the post body, even in the first comment on your
> own post. Put it in the first comment — this is the accepted workaround that all creators use.

---

### Step 2.4 — 8:00–9:00am: The First Hour Is Everything

For 60 minutes after posting, stay available to respond:

**What to watch:**
- Notification bell on LinkedIn — reply to every comment within minutes
- Even a one-word reply ("Exactly." / "Great point — DM me.") counts as an engagement event

**What to do with each comment:**
- Reply with something specific (not just "Thanks!")
- Ask a follow-up question to keep the thread alive
- Tag the commenter if relevant: `"@[Name] — yes, exactly — the S3 Vectors cost decision is the one people are most surprised by"`

**The 3 seeds:**
- Your 3 pre-messaged colleagues should comment in this window
- A comment from someone with 500+ connections has 3× the algorithmic weight of a like
- After they comment, reply publicly AND send them a thank-you DM — builds the relationship

---

### Step 2.5 — 48 Hours Later: Check Analytics and Log

**How to access analytics:**
1. Go to your post on your profile
2. Click **"N impressions"** below the post
3. You will see: impressions, reactions, comments, reposts, follows from this post

**What to record** (in `linkedin/llmwiki-linkedin-multiweek-post.md` Part 7 Posted Log):
- Impressions at 48h
- Reactions, comments, DMs received
- Profile views triggered (from Premium analytics if active)
- Top commenter job title (tells you which audience resonated)
- LinkedIn URL of the post (copy from browser bar)

**What to do with this data:**
- Impressions > 500 on first post → series is working, keep the format
- Impressions < 200 → next post: stronger hook (more specific number or before/after)
- DMs received → reply within 24h, these are warm leads

---

## Part 3 — Why These Steps Work: The Algorithm

Understanding the algorithm makes every decision obvious. Here is exactly how LinkedIn decides
who sees your post.

### The 3-Stage Distribution Model

```
STAGE 1 (0–60 min): Algorithm shows post to ~100–300 of your followers
         ↓ measures: engagement rate (reactions + comments ÷ impressions)
         
STAGE 2 (if rate > ~3%): Post pushed to 2nd-degree connections and hashtag followers
         ↓ measures: dwell time (how long people read it), save rate
         
STAGE 3 (if viral): Pushed broadly — potential for 10,000+ impressions
```

### What the Algorithm Rewards (in order of weight)

| Signal | Weight | How to get it |
|---|---|---|
| Comments | Very high | Reply to every comment → creates thread depth |
| Saves | High | Educational, reference content (your posts qualify) |
| Dwell time | High | Detailed content with diagrams — people spend time reading |
| Reactions | Medium | Follows naturally from good content |
| Shares/reposts | Very high | Hard to engineer — happens when content is genuinely novel |
| Clicks on "see more" | Medium | Strong hook above the fold → forces the click |

### What the Algorithm Penalises

| Action | Penalty | Why |
|---|---|---|
| External link in post body | ~50% reach reduction | Takes traffic off LinkedIn |
| Tagging people who don't engage | Soft penalty | Looks like spam if they ignore it |
| Posting and then deleting/editing heavily | Resets distribution | Algorithm re-evaluates the "new" post |
| Too many hashtags (>5) | Slight penalty | Signals low-quality content |
| Very short post (<100 words) | Low distribution | Insufficient dwell time |

---

## Part 4 — Publishing a LinkedIn Article (Deep Dive + SEO)

LinkedIn Articles are different from Posts. Here is when to use each and exactly how
to write and publish an Article.

### Post vs Article — When to Use Which

| Situation | Use |
|---|---|
| Weekly series content (12-week sprint) | **Post** — algorithm distributes to feed |
| Deep technical reference (2,000+ words) | **Article** — permanent, Google-indexed |
| Content you want to rank on Google | **Article** — posts are not indexed |
| Sharing a diagram, carousel, image | **Post** — Articles have limited image support |
| Building audience with zero followers | **Post first** — Articles have no algorithm push |

### For LLMWiki, the first Article to write:
**"The Complete LLMWiki Architecture on AWS"** — write it after Week 2 post generates comments.
Keyword target: `"AWS Bedrock agentic knowledge architecture"`

---

### Step 4.1 — Plan the Article Before You Write It

**Title formula:** `"[How to / Why / The] [specific thing] [for/with] [specific context]"`

Examples:
- ✅ `"How to Build a Prompt-Injection-Resistant AI Agent on AWS Bedrock"`
- ✅ `"The Complete LLMWiki Architecture: Multi-Agent Knowledge Systems on AWS"`
- ❌ `"Building Better AI Agents"` (too vague — no one searches this)

**The title is your Google headline.** Write it for someone who would type it into Google,
not for someone who already knows what LLMWiki is.

> ⚠️ **SEO RULE:** Put your target keyword in the title, AND in the first paragraph,
> AND in at least one H2 header. This is the minimum for Google to understand what
> the article is about.

**Article structure template:**
```
# Title (keyword-rich)

## The Problem (130–160 chars — this becomes Google's meta description)
2–3 sentence summary of the problem. Google reads this as the article preview.

## [Main section 1 — keyword-rich H2]
Content...

## [Main section 2]
Content...

## [Main section 3]
Content...

## Conclusion + CTA
"If you're building X and want to see Y, DM me / subscribe to the newsletter"

*This is part N of the LLMWiki series. Next: [link to next article]*
```

---

### Step 4.2 — Write and Publish the Article

**How to open the Article editor:**
1. Click **"Write article"** on the home feed
2. The editor opens — it looks like a blog editor, not a post composer
3. Click into **"Headline"** at the top — this is your article title (NOT the same as your post hook)

**Adding content:**
- Paste your text
- Use the formatting toolbar: Bold, H2, H3, bullet lists, quotes
- **Use H2 and H3 headers liberally** — they are crawled by Google and signal structure

**Adding images:**
- Click the **image icon** in the editor
- Upload from `linkedin/` — use the relevant week's image as the article header image
- Add alt text to every image: `"LLMWiki AWS architecture diagram showing S3 to Lambda pipeline"`

> ⚠️ **SEO RULE:** Image alt text is indexed by Google. Describe what the image shows
> using your keywords. Do not write "image" or leave it blank.

**Adding the cover image:**
- At the top of the article editor, there is a **"Add a cover photo"** button
- Use the same image as the related weekly post (e.g., `linkedin_w2_aws_architecture.png` for the architecture article)
- This appears as the thumbnail when the article is shared

**Linking to other articles:**
At the bottom of every article, add:
```
*Previous: [Post/Article title and link]*
*Next in the series: coming [date]*
*Full series: [Newsletter URL]*
```

> ⚠️ **Internal linking is real SEO.** Google follows these links. Each link from one
> article to another tells Google both articles are authoritative on related topics.

---

### Step 4.3 — Publish the Article

1. Click **"Publish"** in the top right
2. A dialog appears — **"Notify your followers"** — click **Yes**
3. A separate post is auto-generated — it will be short. **Edit it** before posting:
   - Replace the auto-generated text with your own hook (same rules as a post hook)
   - Add the image
   - Add hashtags
   - The link to the article will be in this post — that is fine (Articles are on LinkedIn)
4. Click **Post**

> ⚠️ **IMPORTANT:** The auto-notification post LinkedIn creates is generic and boring.
> Edit it manually — this is the post that goes in your feed, and your feed post is
> what drives article reads. A good post hook → clicks into article → article reads → Google signals.

---

### Step 4.4 — After Publishing: Promote the Article via a Post

The same day you publish an Article, also post a separate Post that teases it:

```
I wrote the full LLMWiki architecture breakdown.

Every design decision behind the AWS pipeline — why S3 Vectors and not OpenSearch,
why serverless-first, why Neuro-SAN agents instead of a single LLM.

5,000 words. Full diagrams. Real code.

Article link in comments ↓

#AWSBedrock #LLMWiki #CloudArchitecture
```

This is the pattern every major technical creator uses:
- **Post** drives algorithm distribution (feed reach)
- **Article** drives Google search + Newsletter subscribers
- Post links to Article via comments → Google sees external links to the Article

---

## Part 5 — SEO: Everything That Matters for LLMWiki Content

### What LinkedIn Content Gets Indexed by Google

| Content type | Google indexed? | How long it stays |
|---|---|---|
| LinkedIn Posts | No | — |
| LinkedIn Articles | **Yes** | Permanently |
| Your profile headline | **Yes** | While you are on LinkedIn |
| Your About section | **Yes** | While you are on LinkedIn |
| Article titles | **Yes** | Permanently |
| Article H2/H3 headers | **Yes** | Permanently |

### Your Target Keywords — Low Competition, High Intent

These are terms your ICP (CTOs, VPs Engineering, Enterprise Architects) actually search.
Low competition = you can rank on page 1 with a well-written Article.

| Keyword | Intent | Target article |
|---|---|---|
| `agentic knowledge management AWS` | Builder/buyer | LLMWiki Architecture |
| `multi-agent RAG architecture` | Technical | Architecture + Agents article |
| `prompt injection defence enterprise AI` | Security | Sly Data article |
| `RAG data poisoning prevention` | Security | Data Poisoning article |
| `HITL AI agent governance` | Compliance/enterprise | Governance article |
| `AWS Bedrock knowledge base architecture` | Builder | Architecture article |
| `Neuro-SAN multi-agent framework` | Technical | Agents article |
| `LLM knowledge base security` | Security | Either security article |

### Where to Place Keywords

| Location | Priority | Notes |
|---|---|---|
| Article title | Critical | Contains primary keyword |
| First 160 chars of article | Critical | Google's meta description |
| At least one H2 header | High | Signals article is about this topic |
| Article body (2–3 times naturally) | Medium | Don't stuff — write naturally |
| Image alt text | Medium | Describes the image in keyword terms |
| LinkedIn profile headline | High | Indexed, appears in Google results |
| LinkedIn About section | Medium | Indexed, free SEO real estate |
| Post hashtags | Low LinkedIn / No Google | Posts not indexed — hashtags are for LinkedIn search only |

### The One SEO Action With the Highest Leverage

**Write your first Article's title and first paragraph before anything else.**

The title and first 160 characters are what appear in Google search results. If these
are clear and keyword-rich, Google ranks the article. If they are vague or lead with
"Welcome to my blog", Google ignores the article.

**Test:** After writing your title and first paragraph, ask yourself:
*"If someone searched [keyword], would clicking this article answer their question?"*
If yes: the SEO is working. If no: rewrite the first paragraph.

---

## Part 6 — Weekly Rhythm During the 12-Week Sprint

The sprint runs Mon/Wed/Fri (3 posts per week) through July 21 – August 15.
Each post takes 20 minutes to prepare and 60 minutes to monitor. Here is the exact rhythm.

### Sunday Evening (~20 min): Prepare Next Week's Posts

```
□  Open linkedin/llmwiki-linkedin-multiweek-post.md → next week's entries
□  Read the crispy details and the hook for each day
□  Open linkedin/ folder — confirm the image for each day is ready
□  For carousel weeks (W2=Jul 23, W11=Aug 13): confirm PDF is ready
    If not: run /auto-validate to generate the carousel PDF
□  Copy each post's text to a text file or notes app — ready to paste Monday morning
□  Message 2–3 people for each post day (Mon/Wed/Fri separately)
```

### Morning of Each Post Day (~5 min to post, 60 min to monitor)

```
8:00am  Open LinkedIn → Start a post → Paste text → Upload image → CHECK no URLs → Post
8:01am  Immediately post your first comment (teaser for next week + question)
8:02am  Message your 3 seeds: "Just posted — please leave a comment when you get a chance"
8:00–9:00am  Reply to every comment within minutes
9:00am  Open Premium "Who Viewed Your Profile" → log any ICP matches
```

### 48 Hours After Each Post (~5 min)

```
□  Open the post → click "N impressions" → record in Posted Log (Part 7 of multiweek doc)
□  Note: impressions, reactions, comments, DMs received, profile views
□  If ICP match found in Premium viewers: send connection request (not InMail — save those)
□  Identify top commenter job title → record in log
□  If impressions > 500: reply to top comment with a teaser: "Next post [day] goes even deeper..."
```

### After Week 2 Post (Jul 23): Write Anchor Article 1

After your W2 post generates 5+ comments, questions in the comments become the article outline:
1. Open `linkedin-posting-step-by-step.md` Part 4
2. Target keyword: `AWS Bedrock agentic knowledge architecture`
3. Use W2 post content as the skeleton — expand each bullet into a section
4. Add the diagrams from `linkedin_w2_aws_architecture.png` as embedded images
5. Publish as an Article, linked to your Newsletter

---

## Part 7 — Gotchas: Common First-Timer Mistakes to Avoid

These are the mistakes that quietly kill posts. Every one of them is easy to avoid once you know.

---

**Gotcha 1 — Editing the post after publishing**

> ⚠️ **Never edit a post within the first 60 minutes.** Editing triggers a re-evaluation
> by the algorithm, which can reset distribution. If you spot a typo immediately after posting,
> wait at least 2 hours before fixing it. A small typo in a well-performing post is less
> damaging than an edit that kills the momentum.

---

**Gotcha 2 — Posting on a Friday or over the weekend**

LinkedIn's B2B audience is not on the platform Friday afternoon through Sunday.
Posts published then get 40–60% lower reach.

Best days: **Tuesday, Wednesday, Thursday** — 8–9am or 5–6pm local time.

The sprint schedule (Mon/Wed/Fri) uses Monday as an acceptable fallback.
If you miss a Monday, push to Tuesday rather than skipping.

---

**Gotcha 3 — No hook above the fold**

LinkedIn shows 3–4 lines before truncating with "...see more". If your hook is
not in the first 2 lines, most people never click.

**Test before posting:** In the composer, count the lines. Your strongest
claim must be complete before the 4th line.

Post 001's hook: *"When a senior engineer resigns, they don't just take their badge. They take 25 years of decisions, patterns, and hard-won answers with them."* — 2 lines, complete, compelling. Copy this structure.

---

**Gotcha 4 — Tagging people who won't engage**

If you tag someone and they don't react or comment within 2 hours, the algorithm
interprets the tag as a low-quality signal. Only tag:
- People you have already messaged who confirmed they will comment
- People directly referenced in the content (e.g., a colleague who contributed)

---

**Gotcha 5 — Hashtag overload**

More than 5 hashtags looks like spam. LinkedIn's algorithm does not reward hashtag quantity.
3–5 is the proven sweet spot. Post 001 uses exactly 5.

---

**Gotcha 6 — Publishing the Article and expecting it to go viral**

Articles do not appear in the feed algorithm the same way Posts do. An Article published
with no companion Post = almost zero reads in the first 24 hours.

Always: write an Article, then publish a **short teaser Post** the same day that says
"Full article — link in comments ↓". The Post drives the traffic.

---

**Gotcha 7 — Not replying to comments**

Every unanswered comment is a missed signal. The algorithm counts reply threads.
A post with 10 comments and 10 replies → 20 engagement events.
A post with 10 comments and 0 replies → 10 engagement events.

Even in your first week with 3 comments: reply to all 3. It trains the algorithm
to push your content further.

---

**Gotcha 8 — Carousel uploaded as images instead of PDF**

LinkedIn carousels (W2 and W11) must be uploaded as a **PDF file**, not as individual images.
If you upload images separately, they appear as a photo gallery — no swipe, no carousel behaviour, no 3× reach boost.

Upload sequence for carousel posts:
1. Click **"Start a post"**
2. Click the **document icon** (not the photo icon) — it looks like a page with a corner folded
3. Upload the PDF
4. LinkedIn will render it as a swipeable carousel

> ⚠️ The document icon is different from the photo icon. Using the wrong one is the most
> common carousel mistake.

---

**Gotcha 9 — Not posting your own first comment**

The single highest-leverage action after posting is your own first comment.
It appears at the top of the comment section, giving readers a reason to engage,
and it re-surfaces the post when others comment after it.

Every post in this series should have this comment posted within 60 seconds of publishing.

---

**Gotcha 10 — Giving up after Week 1**

Your first post will get fewer impressions than Week 6. That is normal and expected.
The algorithm needs data points to understand your audience. Posts 1–3 train the algorithm.
Posts 4–6 are when distribution starts to compound.

If Week 1 gets 150 impressions: that is fine. Stay on the cadence.
The sprint compounds — Week 12 will reach 5–10× Week 1's audience.

---

## Part 8 — Quick Reference Checklists

Print these or keep them open when posting.

---

### Pre-Post Checklist (run before every "Post" click)

```
□  Hook is in line 1–2, complete above the fold
□  Blank line after the hook
□  No external URLs in the post body
□  Image uploaded (correct week's file from linkedin/)
□  Hashtags on own line, 3–5 only, last line of post
□  Text is 150–300 words
□  3 people messaged to seed engagement
□  Post time is 8–9am Tue/Wed/Thu (or Monday at latest)
```

---

### Immediate Post-Publish Checklist (first 5 minutes)

```
□  First comment posted (teaser for next week + question)
□  Seeds messaged: "Just posted — please comment"
□  Notifications open — ready to reply for 60 minutes
□  If carousel: verified it shows as swipeable, not image gallery
```

---

### Article Pre-Publish Checklist

```
□  Title contains target keyword
□  First paragraph (≤160 chars) clearly states the article's value
□  At least one H2 header contains the keyword
□  Cover image uploaded with descriptive alt text
□  Internal links to previous/next articles added at bottom
□  Companion post ready to publish same day (link in comments)
□  Newsletter selected (so subscribers get email notification)
```

---

### Weekly Maintenance Checklist (10 min every Sunday)

```
□  Next week's 3 posts prepared (text copied, images confirmed)
□  Posted Log updated for last week's posts (impressions at 48h)
□  Premium viewer list checked — connection requests sent to ICP matches
□  InMail credits reviewed — any W5/W6 viewers to reach out to?
□  Article writing schedule on track (see multiweek doc anchor article dates)
```

---

## The Mindset That Makes This Work

You are not posting to go viral. You are posting to **build a compounding audience**.

The same principle that makes LLMWiki valuable — knowledge compounds — applies to your
LinkedIn presence. Each post adds to the signal. Each article adds to the SEO footprint.
Each comment thread grows the algorithm's understanding of your audience.

By Week 12, you will have:
- 12 published posts with a coherent narrative arc
- 4 Google-indexed Articles on high-intent keywords
- A newsletter subscriber list
- A warm lead list from Premium profile viewers
- Enough analytics to know exactly what your audience wants to read next

None of that is possible if you skip Week 3 because Week 1 only got 150 impressions.

**The only thing that ends this is stopping.**

Post this week. Then next week. Then the week after.
The wiki compounds. So does the audience.

---

*All images for the series are in `linkedin/` · Series plan in `linkedin/llmwiki-linkedin-multiweek-post.md`*
*Post text for all 12 weeks is in `~/.claude/commands/linkedin-post.md` → Proven Post Library*
