# /linkedin-post — Weekly LinkedIn Post Generator

Generate one high-performing, audience-building LinkedIn post per week.
Tuned to Srini's content areas: LLMWiki · K8s agent sandbox · Claude Code fusion harness ·
multi-agent AI · healthcare IT · AWS Bedrock.

Uses an interactive Q&A → 3 angle options → full formatted post with hook, body, CTA, hashtags.
Optionally generates a Codex variant (Builder perspective) for a fused final post.

---

## Usage
```
/linkedin-post
/linkedin-post "topic or story idea"
/linkedin-post "topic" fusion    ← also generates a Codex variant then fuses them
```

---

## Instructions for Claude

When invoked with `$ARGUMENTS`:

---

### Phase 0 — Parse arguments

- If `$ARGUMENTS` contains the word `fusion` → set FUSION_MODE = true
- Extract the topic/story hint from `$ARGUMENTS` if present; set as TOPIC_HINT
- If no TOPIC_HINT provided → suggest one from the Topic Bank below (rotate weekly)

---

### Phase 1 — Interactive Q&A (always run this)

Ask the user ALL of the following in a single block (not one at a time):

```
## 📝 LinkedIn Post Brief

Answer these — or skip any with "skip":

1. **Topic / story** — What happened, what did you build, what did you learn?
   (Current hint: <TOPIC_HINT if set, else "not specified — pick from Topic Bank">)

2. **The specific result or moment** — A number, a before/after, a surprising outcome,
   a line of code that worked, a demo reaction. The more specific, the better the hook.

3. **Audience** — Who should this resonate with most?
   (a) Engineers building AI agents
   (b) Business leaders / founders exploring AI
   (c) Healthcare IT / enterprise IT professionals
   (d) All of the above

4. **Goal for this post** — What do you want to happen?
   (a) Build personal brand / thought leadership
   (b) Generate interest / inbound leads for a product
   (c) Educate — share a framework or lesson
   (d) Start a conversation / get comments

5. **Tone** — How do you want to sound?
   (a) Builder / practitioner — "here's what I actually did"
   (b) Contrarian — "everyone does X but here's why Y is better"
   (c) Storyteller — narrative arc with a lesson at the end
   (d) Framework / list — "the 5 things I learned building X"
```

Wait for the user's answers. Then proceed to Phase 2.

---

### Phase 2 — Generate 3 angles

Based on the answers, generate 3 distinct angle options. Each angle = a hook + a one-line summary of the post direction. Do NOT write the full post yet.

Display:

```
## 🎯 3 Angles — Pick One (or say "mix A+C" etc.)

**Angle A — [Hook type name]**
Hook (first 2 lines that appear before "...more"):
> [Hook line 1]
> [Hook line 2]
Direction: [One sentence on how the post develops]

**Angle B — [Hook type name]**
Hook:
> [Hook line 1]
> [Hook line 2]
Direction: [One sentence]

**Angle C — [Hook type name]**
Hook:
> [Hook line 1]
> [Hook line 2]
Direction: [One sentence]

Which angle? (A / B / C / mix / rewrite one):
```

Wait for user's angle choice.

---

### Phase 3 — Write the full post

Write the full LinkedIn post using the chosen angle.

**Formatting rules — follow exactly:**
- Line 1–2: The hook. Must work as a standalone statement — no context needed.
  Hook patterns that perform:
  - Specific result: *"We cut 15 hours of consultant work to 10 seconds."*
  - Contrarian opener: *"Most AI agents are demos. Here's what a real one looks like."*
  - Personal moment: *"At 11pm on a Friday, the agent answered a question I didn't expect it to."*
  - Number + claim: *"22 unit tests. 0 written by hand. 1 command."*
- Line 3: blank line (paragraph break — always)
- Body: 4–8 short paragraphs. Max 2–3 sentences each. One idea per paragraph.
  Never more than 3 lines in a row without a blank line.
- No bullet walls. If using bullets, max 4 items, each one line.
- Second-to-last paragraph: the lesson or key takeaway — the "so what"
- Last paragraph: CTA. One of:
  - Question to the audience (*"What's the biggest knowledge management problem in your team?"*)
  - Invitation (*"DM me if you want to see the demo."*)
  - Reframe (*"The wiki compounds. The tool doesn't — that's the difference."*)
- Hashtags: 3–5, on their own line at the very end. Mix broad + niche.
  Srini's hashtag pool: #AIAgents #LLMWiki #ClaudeCode #AWSBedrock #HealthcareIT
  #MultiAgentAI #KubernetesAI #NeuroSAN #GenerativeAI #AIEngineering #EnterprisAI
  #BuildInPublic #SoftwareEngineering #FusionHarness #DocumentAI

**Length:** 150–300 words. LinkedIn penalises very short and very long posts equally.
**No jargon in the hook.** Technical depth goes in the body, not the opening.
**Write in first person.** Conversational, not corporate.

Display the post as:

```
## ✍️ LinkedIn Post — [Angle name]

---

[Full formatted post here]

---

**Character count:** ~N
**Estimated read time:** N seconds
**Hook type:** [name]
**Best time to post:** Tuesday–Thursday, 8–10am or 5–6pm local time
```

---

### Phase 3b — Generate the post image (always run after Phase 3)

After the post is written, automatically generate a LinkedIn image using gpt-image-2 via Azure proxy.

**Step 1 — Build the image prompt from the post content:**

Analyse the post and extract:
- PANEL_LEFT_THEME: the "old way" / before state described in the post
- PANEL_RIGHT_THEME: the "new way" / after state — key services or architecture mentioned
- ARCHITECTURE_SERVICES: list of specific tools/services named in the post (e.g. S3, Bedrock, Lambda, Textract)
- FIVE_PILLARS: any pillars or key qualities mentioned (default: Distributed, Fault-Tolerant, Secured, Scalable, Validated)
- QUOTE_LINE: the single most powerful line from the post (second-to-last paragraph)
- AUTHOR_NAME: Srinivasan Sethuraman

Construct IMAGE_PROMPT:
```
Professional LinkedIn post image, split-panel design, dark near-black background.
LEFT PANEL with warm amber-red tones: <PANEL_LEFT_THEME visual description>.
Text overlay: THE OLD WAY.
RIGHT PANEL with electric blue and green tones: <PANEL_RIGHT_THEME visual — architecture
flowchart showing: <ARCHITECTURE_SERVICES joined by arrows>>.
Five colored circular badges at the bottom: blue <PILLAR_1>, green <PILLAR_2>,
red <PILLAR_3>, yellow <PILLAR_4>, purple <PILLAR_5>.
Centre dividing element: bold arrow pointing right.
Bottom full-width dark strip with quote: "<QUOTE_LINE>" — <AUTHOR_NAME>.
Style: dark corporate tech editorial, clean vector-style infographic, high contrast, professional.
```

**Step 2 — Call gpt-image-2:**

POST to `http://127.0.0.1:18080/openai/deployments/gpt-image-2/images/generations`:
```json
{
  "prompt": "<IMAGE_PROMPT>",
  "n": 1,
  "size": "1792x1024",
  "quality": "high",
  "output_format": "png"
}
```
Header: `Authorization: Bearer a51a2bac408a4087821ccd00f7c35d3e`

**Step 3 — Save the image:**

The response contains `data[0].b64_json`. Run this via Bash:
```bash
curl -s -X POST "http://127.0.0.1:18080/openai/deployments/gpt-image-2/images/generations" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer a51a2bac408a4087821ccd00f7c35d3e" \
  -d '<JSON_PAYLOAD>' | python3 -c "
import sys, json, base64, re
raw = sys.stdin.read()
data = json.loads(raw)
b64 = data['data'][0]['b64_json']
img_bytes = base64.b64decode(b64)
# Derive filename from topic slug
slug = '<TOPIC_SLUG>'  # e.g. llmwiki_architecture, unit_test, k8s_sandbox
filename = f'/mnt/c/Users/859600/OneDrive - Cognizant/AWSLab/LLMWiki/linkedin_{slug}.png'
with open(filename, 'wb') as f:
    f.write(img_bytes)
print(f'Saved: {filename} ({len(img_bytes):,} bytes)')
"
```

TOPIC_SLUG = lowercase, underscored, 2–4 word summary of the topic.

**Step 4 — Display result:**

```
## 🖼️ Generated Image

**Saved to:** /mnt/c/Users/859600/OneDrive - Cognizant/AWSLab/LLMWiki/linkedin_<TOPIC_SLUG>.png
**Size:** 1792×1024px  |  gpt-image-2  |  High quality

Upload this image when posting on LinkedIn.
```

If the image generation fails (non-200 response or missing b64_json), display:
```
## 🖼️ Image Generation Failed
Error: <error message>
Use the manual Canva brief in the Post Options section instead.
```
and continue to Phase 4 without blocking.

---

### Phase 4 — FUSION_MODE (only if fusion was requested)

If FUSION_MODE = true, also call Codex for a Builder variant:

POST to `http://127.0.0.1:18080/openai/responses`:
```json
{
  "model": "gpt-5.3-codex-2",
  "input": "You are a LinkedIn content strategist who specialises in technical practitioner posts.\n\nWrite a compelling LinkedIn post on this topic:\n[TOPIC from user's answers]\n\nContext:\n- Author background: AWS/Bedrock engineer, built LLMWiki (document-to-agent knowledge system), runs Claude Code fusion harness with Azure Codex\n- Target audience: [AUDIENCE from user's answers]\n- Goal: [GOAL from user's answers]\n- Tone: [TONE from user's answers]\n\nRules:\n- Hook in first 2 lines (no context needed to understand it)\n- Short paragraphs, blank lines between them\n- End with a question or CTA\n- 150-250 words\n- 3-5 hashtags on last line\n- Practitioner voice — show the work, not the concept\n\nReturn ONLY the post text. No explanation.",
  "reasoning": { "effort": "high" }
}
```
Header: `Authorization: Bearer a51a2bac408a4087821ccd00f7c35d3e`

Display:
```
## ⚡ Codex Builder Variant

---
[Codex post]
---
```

Then synthesise both into a fused final post:

```
## 🔀 FUSED POST
*Best hook from one, best body flow from the other, best CTA from one*

---
[Fused post]
---

### What was taken from each
| Element | Source |
|---------|--------|
| Hook | [Claude / Codex] |
| Key insight paragraph | [Claude / Codex] |
| CTA | [Claude / Codex] |
```

---

### Phase 5 — Post options

After delivering the post (or fused post), always display:

```
## 📋 Post Options

- **Post as-is** — copy above
- **Rewrite hook** → say "new hook: [your idea]"
- **Change tone** → say "make it more [contrarian / story / list]"
- **Add a carousel outline** → say "carousel" — I'll give you 8 slide descriptions
- **Shorten to 120 words** → say "short version"
- **Codex variant** → say "codex" (if not already in fusion mode)
- **Regenerate image** → say "new image: [different style or emphasis]" — calls gpt-image-2 again with revised prompt
- **Square image** → say "square image" — regenerates at 1024×1024 for mobile feed
```

---

## Topic Bank (rotate weekly — use when no topic is provided)

Srini's proven content territories — each maps to a real thing you've built or know deeply:

| Week | Topic seed | Angle suggestion |
|------|-----------|-----------------|
| W1 | LLMWiki: document → agent knowledge in minutes | Specific result: "dropped a PDF, got a queryable agent in 8 minutes" |
| W2 | Claude Code fusion harness: Claude as Architect + Codex as Builder | Contrarian: "I stopped writing code. I architect. Codex builds. Here's the split." |
| W3 | `/unit-test` skill: 22 tests, 0 written by hand | Number hook: "22 tests. 0 written. 1 command. Here's what Codex generated." |
| W4 | K8s agent sandbox: running neuro-san agents in Kubernetes | Builder story: "Local Docker → K8s in one afternoon. Here's the why." |
| W5 | LLMWiki agentic architecture: 10 agent use cases, S2S first | Framework: "The 10 moments in an enterprise implementation where an agent saves the day" |
| W6 | `/auto-validate`: gate-first development with Codex | Contrarian: "Most AI-generated code is untested. Here's how I gate every build." |
| W7 | Multi-agent S2S lifecycle (SOW signed → wiki activated) | Story: "The moment a SOW is signed, an agent starts building the knowledge base" |
| W8 | S3 Vectors vs OpenSearch: why we chose the cheaper path | Decision post: "We almost spent $400/month on OpenSearch. Here's what stopped us." |
| W9 | LLMWiki for 7 industries: the same platform, 7 markets | Insight: "The same code that serves healthcare IT also serves GCs and law firms" |
| W10 | The fusion harness: 3 agents in one Claude Code session | How-to: "Architect → Builder → Merge. No subprocess. No IPC. One session." |
| W11 | Real unit test generated by Codex for LLMWiki base tool | Proof: "I asked Codex to test my code. 22 tests, first-pass green. Here's one." |
| W12 | Building a knowledge moat: why the wiki compounds | Philosophy: "The product gets more valuable every week without a single new feature" |

---

## Hook Patterns Reference (use these when writing angles)

| Hook type | Pattern | Example |
|-----------|---------|---------|
| Specific number | "[N] [thing] in [time/action]" | "22 unit tests in 1 command." |
| Before/After | "[Old way]. [New way]. Here's why." | "PDF in a folder. Agent in 8 minutes. Here's the stack." |
| Contrarian | "Everyone [does X]. I [do Y] instead." | "Everyone is demoing AI. I'm running it in production." |
| Personal moment | "At [specific moment], [unexpected thing happened]." | "At 11pm on a Friday, the agent caught an answer I'd have missed." |
| The question | "[Question your audience is asking]" | "What happens to institutional knowledge when your best consultant leaves?" |
| The cost reveal | "[Thing people do] costs [surprising amount]." | "Answering the same RFI question manually costs a GC $2,000 a month." |
| The admission | "I used to [wrong thing]. Then [event changed it]." | "I used to write all my tests by hand. Then I ran /unit-test." |

---

## Proven Post Library

Reference posts — produced and approved. Use as quality benchmarks and structural templates
for future posts on the same topics. When a new post covers similar ground, open the
relevant entry here and tell Claude: *"Match this quality and structure, different angle."*

---

### Post 001 — LLMWiki Architecture + Unit Test Validation
**Date:** 2026-07-20
**Topic seed:** W1 + W11 combined — LLMWiki on AWS full stack + 22 Codex-generated tests
**Mode:** Fusion (Claude Architect + Codex Builder merged)
**Tone:** Storyteller + Framework + Practitioner
**Audience:** All — CTOs, VPs Engineering, Enterprise Architects, Business Leaders
**Goal:** Thought leadership + inbound demo interest
**Performance target:** 500+ impressions, 30+ reactions, 5+ DMs

---

#### Full Post (copy-ready)

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

#### Fusion Attribution Map

| Element | Source |
|---|---|
| Opening hook (resignation + 25 years) | Claude |
| "SharePoint/Confluence didn't fix it" contrarian challenge | Claude |
| Architecture flow diagram (S3 → Textract → Bedrock → S3 Vectors → Lambda → Neuro-SAN) | Claude (expanded) |
| Pillar bullet format with AWS service specifics | Codex |
| "Idempotent Lambdas, DLQs" technical depth in pillars | Codex |
| Industry breadth list (6 verticals) | Claude |
| "Validated — 22 tests, first-pass green via fusion harness" | Codex |
| "Knowledge doesn't leave anymore" closing philosophy | Claude |
| "30 minutes. Your documents. Live demo. DM me." CTA | Claude |

---

#### Image Brief (Post 001)

**Format:** 1200 × 627px (LinkedIn feed) or 1080 × 1080px (square)

**Style:** Dark background (#0a0a14), electric blue + white + green accents.
AWS architecture diagram aesthetic meets editorial design. No stock photos.

**Layout — two panels divided by a centre arrow:**

LEFT PANEL — "Before" (amber/red tones)
```
Label: THE OLD WAY

[Icon: person silhouette + briefcase walking out a door]
"25 years of decisions walking out the door"

Three icons in a row:
📁 SharePoint    📧 Email threads    🧠 Tribal memory
```

RIGHT PANEL — "After" (electric blue/green tones)
```
Label: LLMWiki ON AWS

Vertical flow:
[ S3 ] → [ Textract ] → [ Bedrock ]
              ↓
        [ S3 Vectors ]
              ↓
     [ Lambda + Claude ]
              ↓
  [ Multi-Agent Network ]
              ↓
  ✅ Cited Answer in Seconds

Five badges along bottom:
🔵 Distributed  🟢 Fault-Tolerant  🔴 Secured  🟡 Scalable  🟣 Validated
```

**Centre dividing element:** Vertical arrow pointing right → labelled **"25 years → solved"**

**Bottom strip (full width, dark overlay):**
```
"The knowledge doesn't leave anymore."   — Srinivasan Sethuraman
```

**Generated image file:** `llmwiki_linkedin_post_001.png` (1792×1024, gpt-image-2, high quality)

**Image endpoint used:**
`POST http://127.0.0.1:18080/openai/deployments/gpt-image-2/images/generations`
Size: `1792x1024` · Quality: `high` · Output: `png` · Response: `b64_json`

**Result:** Split-panel — amber silhouette (old way: tribal knowledge, SharePoint, email)
→ electric blue AWS flowchart (S3 → Textract → Bedrock → S3 Vectors → Lambda →
Multi-Agent Network → Cited Answer) → five coloured pillar badges →
quote strip "The knowledge does not leave anymore." — fully auto-generated, no manual design needed.

---

#### Reuse notes
- **Next post on LLMWiki:** Lead with a specific customer story or demo result — this post
  established the architecture; the next one should show it working on real data.
- **Next post on unit testing:** The "22 tests, 0 written" hook is strong standalone —
  use W11 topic seed with the admission hook pattern.
- **Carousel version:** This post maps directly to an 8-slide carousel:
  Slide 1 = hook, Slide 2 = old way, Slides 3–4 = architecture diagram,
  Slides 5–6 = five pillars, Slide 7 = industries, Slide 8 = CTA.
  Say `carousel` on next invocation to generate slide-by-slide copy.
