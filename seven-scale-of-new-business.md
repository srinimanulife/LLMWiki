# Seven Businesses at Seven Levels of Scale
### Mapped to your background — AWS · Bedrock · multi-agent AI · healthcare IT · Claude Code fusion harness

---

## Your Unfair Advantages (the honest inventory)

| Capability | Why it matters for scale |
|---|---|
| LLMWiki — document → queryable agent knowledge | Your core IP; redeployable to any document-heavy industry |
| Neuro-san multi-agent orchestration | You can ship agent networks others would take 6 months to design |
| Claude Code fusion harness | 10× implementation velocity; Codex builds while you architect |
| Healthcare IT lifecycle (TriZetto, 10 UC pattern) | Deep domain — you know where the pain is and who pays |
| AWS Bedrock + IaC (Terraform) | Full production stack you can clone into a new vertical in days |
| `/unit-test` + `/auto-validate` harness | Quality gate baked in — you can guarantee correctness to enterprise buyers |

The pattern underneath all 7 businesses below is the same:
> **Industry has mountains of locked documents → humans answer the same questions manually → you replace that with an agentic knowledge fabric → charge per seat, per query, or per outcome.**

Each business is chosen because: (a) the automation gap is real and large, (b) your existing stack maps directly, and (c) Claude Code collapses the time to Level 1.

---

## Business 1 — Healthcare Implementation Intelligence SaaS
*Productise what you already built*

### The Gap
Every Cognizant/TriZetto implementation runs the same 10-use-case lifecycle manually. Consultants re-answer the same questions across every engagement. No client has a queryable knowledge layer — they have SharePoint folders and tribal knowledge.

### The Product
LLMWiki deployed as a white-label SaaS for healthcare IT implementation firms and payers. Pre-loaded with your 10-UC agent network (S2S → Env → IAM → BizConfig → DataMigration → SIT → E2E → Cutover → PTO → Hypercare). Each client gets their own wiki that compounds across their project.

### Claude Code Role
`/fusion` generates domain-specific agent HOCON registries. `/auto-validate` gates every new UC agent against a real acceptance test before it touches client data. `/unit-test` keeps Lambda handlers green as clients request customisations.

### 7 Levels Map

| Level | Milestone | What it looks like for you |
|---|---|---|
| 1 — Sell 10 | Land 3 implementation firms as paid pilots | $2K–5K/month per firm; you personally onboard them |
| 2 — Growth Flywheel | Referral engine: one firm's PM recommends to another | LinkedIn case study → inbound demo request loop |
| 3 — Business OS | Playbook for onboarding a new client in <48 hrs | Terraform module + HOCON template per vertical |
| 4 — Double Pay | Exit Cognizant or take it as a side entity at $20K MRR | Financially secure enough to go full-time |
| 5 — Advisory Board | 1 ex-TriZetto CTO, 1 health plan CISO, 1 SaaS GTM operator | Doors to 50-person implementation firms |
| 6 — Acquisition | Acquire a struggling healthcare IT consulting boutique | Instant client base + their tribal knowledge fed into the wiki |
| 7 — Exit / Legacy | Become the knowledge OS for healthcare IT implementations nationally | Acqui-hire target for Epic, Veeva, Cognizant itself |

**Revenue ceiling:** $5M–15M ARR (healthcare IT SaaS, 200–400 seat market)

### Sales & Marketing

**Ideal Customer Profile (ICP)**
- Title: VP of Delivery, Director of Implementation, Project PMO Lead
- Company: 20–200 person healthcare IT consulting firm, payer IT team, or system integrator running TriZetto/Epic/Facets implementations
- Pain signal: They are billing consultants at $150–300/hr to answer questions that a wiki could answer in seconds

**How to get the first 10 customers**
1. **Warm network first** — You have years of Cognizant/TriZetto contacts. Message 20 PMs and delivery leads you have worked with directly. Ask: *"We're launching a pilot for implementation teams — would you spend 30 min seeing if it solves the re-answer problem?"* No deck, no pitch — just a live demo with their own document type.
2. **LinkedIn thought leadership** — Post one short story per week: *"We ran the same implementation 12 times and answered the same 40 questions every time. Here's what that costs."* Tag TriZetto, Epic, Cognizant communities. Your credibility is the hook.
3. **HIMSS conference** — Attend as a speaker or exhibitor in year 2. For year 1, attend and do 10 coffee meetings with pre-scheduled warm leads.

**Core message (one line)**
> *"Your best implementation consultants carry the answers in their heads. We put those answers into an agent that every team member can query — cited, confident, instant."*

**Pilot → Paid conversion path**
- Offer a free 30-day pilot on one active project (low risk for them)
- Success metric you define upfront: *"How many hours per week does your team spend searching for answers?"* — measure before and after
- Convert at $2K–5K/month after pilot ends; frame as cheaper than 20 hours of consultant time

**Cold lead generation from zero (no warm network needed)**
1. **LinkedIn Sales Navigator** — Filter: Title = "VP of Delivery" OR "Director of Implementation" OR "Program Manager", Industry = "Hospital & Health Care" OR "Information Technology and Services", Company size = 50–500. Send 20 personalised connection requests/day: *"I built an AI agent for implementation teams — it answers the same questions your consultants answer manually. Free pilot on one active project. Worth 15 min?"*
2. **HIMSS conference attendee list** — HIMSS publishes exhibitor and speaker lists publicly. Cross-reference with LinkedIn to find implementation and delivery leads. Pre-book coffee meetings 2–3 weeks before the conference.
3. **Apollo.io cold email sequence** — Search for "TriZetto implementation" OR "Epic implementation" OR "healthcare IT consulting" companies. 4-email drip: Problem → Demo video (Loom) → ROI number → Last call. Expect 2–4% reply rate; 10 emails/day = 1–2 conversations/week.
4. **Healthcare IT communities** — HIStalk, CHIME (College of Healthcare Information Management Executives), and LinkedIn groups like "Healthcare IT Professionals" — post genuinely useful content about implementation knowledge management. No pitch, just expertise.
5. **Upwork/Toptal project postings** — Healthcare IT firms post implementation projects there. Reach out to the posting company directly: *"We have an AI tool specifically for implementation teams — free pilot?"*

**Content / inbound engine**
- LinkedIn: Weekly post on implementation failure patterns (frame as educational, not promotional)
- Case study after first win: *"How [Firm X] cut 15 hours/week of consultant rework"* — submit to HIStalk, Health IT Answers
- Niche SEO: Target "healthcare IT implementation knowledge management" — almost no competition

**Why it's sticky**
The wiki compounds: every project adds more knowledge. Churning means losing that asset. Switching cost grows every month.

---

## Business 2 — Construction Project Intelligence Platform
*Biggest untouched document mountain in the world*

### The Gap
A mid-size commercial construction project generates 50,000–200,000 documents: RFIs, submittals, change orders, specs, drawings, meeting minutes. General Contractors and subs manually search these to answer "was this already approved?" or "what does spec 03300 say about rebar spacing?" — an activity that consumes 15–20% of a project manager's week. No AI product meaningfully addresses this today for SMB GCs.

### The Product
LLMWiki for construction sites. Drop project docs into S3 → Bedrock ingests → project team asks natural language questions → cited answers with section references. Add a "change order risk agent" that flags when a proposed change contradicts an existing spec or approved submittal.

### Claude Code Role
`/fusion` lets you prototype the RFI-response agent (Claude as spec expert + Codex as formatter) in one session. The same Terraform base from LLMWiki deploys a new client environment in under 2 hours.

### 7 Levels Map

| Level | Milestone | What it looks like for you |
|---|---|---|
| 1 — Sell 10 | 3 GCs on a $500/month pilot during active projects | Manual outreach via LinkedIn to project managers |
| 2 — Growth Flywheel | GCs refer subs; subs refer their next GC | Network effect inside a single job site ecosystem |
| 3 — Business OS | Self-serve onboarding: upload Procore export → live in 1 hr | Procore/Autodesk integration as a growth unlock |
| 4 — Double Pay | $30K MRR from 10 paying GCs | Hire a part-time customer success person |
| 5 — Advisory Board | 1 ex-Procore PM, 1 large GC operations VP, 1 construction attorney | Spec compliance and claims defence use cases emerge |
| 6 — Acquisition | Acquire a small construction document management SaaS | Merge client base + their UI with your AI backend |
| 7 — Exit / Legacy | Category leader: "the AI brain for construction projects" | Acquisition target for Procore, Autodesk, Oracle Construction |

**Revenue ceiling:** $20M–80M ARR (construction tech is massive, underserved at SMB)

### Sales & Marketing

**Ideal Customer Profile (ICP)**
- Title: Project Manager, VP of Operations, Estimator, Site Superintendent
- Company: General Contractor with $10M–$200M annual revenue running 3–20 active projects
- Pain signal: They use Procore or Bluebeam but still have staff emailing each other to find specs, submittals, and prior RFI answers

**Cold lead generation from zero**
1. **LinkedIn Sales Navigator** — Filter: Title = "Project Manager" OR "VP Operations", Industry = "Construction", Company size = 50–500. Send 20 connection requests/day with a note: *"I built a tool that lets GC teams ask natural language questions against their project docs — saves ~3 hrs/week per PM. Would you see a 10-min demo?"* Expect 5–10% reply rate.
2. **Procore community + forums** — Procore has an active user community. Post genuinely helpful content about document management pain. Don't pitch — be the expert who shows up.
3. **Cold email to GC owner/ops VP** — Find emails via Apollo.io or Hunter.io. 3-line email: *"Your PMs spend hours searching specs and RFIs for answers that should take seconds. I built an AI agent that answers those questions with citations — free pilot on your next active project. Worth 15 minutes?"*
4. **Local AGC (Associated General Contractors) chapter** — Every major city has a chapter. Sponsor a breakfast meeting ($500–1,000). Demo to 30 GCs at once.

**Core message (one line)**
> *"Ask your project documents a question, get a cited answer in 10 seconds — no more spec hunting."*

**Pilot → Paid conversion path**
- Offer a free pilot tied to one active project (natural urgency — project ends, so does free access)
- Success metric: time saved searching documents per week
- Live demo using their actual Procore export or a sample project package

**Content / inbound engine**
- YouTube shorts: *"Watch this GC answer a spec question in 8 seconds"* — screen recording demos are viral in construction communities
- Reddit r/Construction, r/civilengineering — answer questions, establish presence
- Construction Dive, ENR (Engineering News-Record) — pitch a contributed article on AI in construction docs

**Why it's sticky**
Documents are project-specific. Every project is a new engagement. But the GC becomes dependent on the tool across all their projects — churning means rebuilding their search capability from scratch.

---

## Business 3 — Insurance Adjuster Knowledge Agent
*High-frequency, high-cost manual lookups replaced by agents*

### The Gap
Every insurance adjuster resolves claims by manually reading policy documents, endorsements, exclusions, and state regulations to answer: "Is this covered? How much? Under which clause?" This takes 30–90 minutes per claim. Insurers handle millions of claims. No SMB insurer or TPA (Third Party Administrator) has an AI agent for this — they have PDF readers and phone calls to senior adjusters.

### The Product
An agentic policy oracle. Upload all policy forms, endorsements, state regulations → agents answer coverage questions with clause citations and confidence scores. Add a "gap detection" agent that flags when a claim question has no clear policy answer (your existing `gaps_detected` field from LLMWiki's agent contract — already designed).

### Claude Code Role
Your structured response contract (`answer + confidence + action_items + evidence_required + gaps_detected`) maps perfectly to claim adjudication output. The `/auto-validate` skill gates every new policy type against known test claims before going live.

### 7 Levels Map

| Level | Milestone | What it looks like for you |
|---|---|---|
| 1 — Sell 10 | 2 small TPAs on $1K/month pilot | Cold outreach to claims VPs at regional carriers |
| 2 — Growth Flywheel | TPA recommends to their carrier clients | "Your TPA uses it → you should too" referral chain |
| 3 — Business OS | Policy ingestion pipeline: upload → live in 4 hrs | SOC 2 Type II as the unlock for enterprise carriers |
| 4 — Double Pay | $50K MRR from 8 TPAs/carriers | Full-time hire for compliance + customer success |
| 5 — Advisory Board | 1 ex-Allstate claims director, 1 insurtech investor, 1 insurance attorney | State regulatory compliance guidance |
| 6 — Acquisition | Acquire a policy management SaaS losing to larger competitors | Their policy data model + your AI = moat |
| 7 — Exit / Legacy | The intelligence layer for P&C claims processing | Acquisition target for Guidewire, Duck Creek, Majesco |

**Revenue ceiling:** $30M–100M ARR (P&C claims is a $300B+ industry)

### Sales & Marketing

**Ideal Customer Profile (ICP)**
- Title: VP of Claims, Claims Operations Director, Chief Claims Officer
- Company: Regional P&C insurer (50–500 adjusters), TPA (Third Party Administrator), or MGU (Managing General Underwriter)
- Pain signal: Senior adjusters are being used as a phone-a-friend service by junior staff — a $120/hr human acting as a search engine

**Cold lead generation from zero**
1. **LinkedIn Sales Navigator** — Filter: Title = "VP Claims" OR "Claims Director" OR "Chief Claims Officer", Industry = "Insurance", Company size = 200–2,000. Message: *"I built an AI agent that answers policy coverage questions with clause citations in under 10 seconds — built specifically for adjusters. Could save your team 30–60 min per complex claim. Worth a 15-min look?"*
2. **NAMIC / AICPCU insurance conferences** — The National Association of Mutual Insurance Companies and similar groups hold annual conferences. Attend. Claims operations VPs congregate here.
3. **Apollo.io cold email sequence** — 4-email drip to Claims VPs: Email 1 = problem (cost of manual lookups), Email 2 = concept demo (video loom), Email 3 = ROI calculator (claims handled × 45 min saved × adjuster hourly rate), Email 4 = last call.
4. **Insurance trade press** — Pitch an article to *Claims Journal* or *Insurance Business America* on AI-assisted claims adjudication. Editors are hungry for practical AI content. Article = inbound leads at zero cost.

**Core message (one line)**
> *"Your policy documents know the answer. Your adjusters are just spending 45 minutes finding it — we fix that."*

**Pilot → Paid conversion path**
- Offer a 60-day pilot on one line of business (e.g. commercial auto)
- Upload their actual policy forms + endorsements
- Track: average lookup time before vs. after; escalations to senior adjuster before vs. after
- One prevented E&O claim pays for 5 years of subscription — use this in the ROI conversation

**Content / inbound engine**
- LinkedIn: Post weekly on claims efficiency — cost of manual policy lookup, E&O exposure from inconsistent answers
- ROI calculator landing page: *"How much does your team spend manually answering coverage questions?"* (input: # adjusters, avg claim complexity) → captures email
- Partner with insurance CE (continuing education) providers — your tool as a reference resource for adjuster training

**Why it's sticky**
Policy forms are uploaded and indexed. Switching means re-indexing everything. Compliance teams hate change. SOC 2 certification (once achieved) becomes a re-procurement barrier.

---

## Business 4 — Legal Knowledge Fabric for SMB Law Firms
*50,000 small law firms with zero knowledge management*

### The Gap
Small law firms (2–20 attorneys) have no institutional knowledge system. Associates research the same precedents repeatedly. Partners carry all client context in their heads. When a partner leaves, the firm loses years of case strategy. No affordable AI product addresses this — Westlaw and Lexis are research tools, not firm knowledge systems.

### The Product
LLMWiki for law firms. Upload case files, contracts, memos, court orders → agents answer: "Have we handled a similar non-compete case?" or "What was our argument in the Smith matter?" Add a matter onboarding agent that auto-generates a client intake wiki page from the initial consultation notes.

### Claude Code Role
`/fusion` builds the "precedent finder + strategy synthesiser" agent pair in one session. Your existing Bedrock KB pipeline handles legal PDFs via the Textract converter you already have (`lambda/converter/`).

### 7 Levels Map

| Level | Milestone | What it looks like for you |
|---|---|---|
| 1 — Sell 10 | 3 boutique firms at $300/month | State bar association demo day; personal referral from one attorney |
| 2 — Growth Flywheel | Bar association sponsorship → inbound | Practice area specialisation (e.g. "for employment law firms") |
| 3 — Business OS | Matter ingestion in <30 min; IOLTA billing untouched | Clio/MyCase integration as growth unlock |
| 4 — Double Pay | $15K MRR from 20 firms | Affordable enough to stay bootstrapped |
| 5 — Advisory Board | 1 legal tech investor, 1 BigLaw knowledge management director, 1 malpractice attorney | Risk/liability framing for sales |
| 6 — Acquisition | Acquire a legal document automation SaaS (HotDocs competitor) | Bundle: knowledge + document generation |
| 7 — Exit / Legacy | The knowledge OS for SMB law firms | Acquisition target for Clio, MyCase, Thomson Reuters |

**Revenue ceiling:** $5M–20M ARR (50K firms × $300/month is a $180M TAM)

### Sales & Marketing

**Ideal Customer Profile (ICP)**
- Title: Managing Partner, Office Manager, Senior Associate
- Company: 2–15 attorney firm; practice areas with high document volume — employment, real estate, immigration, family law
- Pain signal: Associates spend 2–4 hrs/week re-researching questions the firm has already answered in a prior matter

**Cold lead generation from zero**
1. **State bar association directories** — Every state bar publishes a member directory. Scrape it (legally — it's public). Filter by firm size (solo to 15 attorneys). Email sequence via Mailchimp or Apollo: *"Do you have a system for capturing what your firm already knows — or does it leave with every attorney who walks out?"*
2. **Clio + MyCase user communities** — Both practice management tools have active Facebook groups and forums. Post genuinely: *"We built a tool that turns your case files into a searchable knowledge base. Happy to show it to a few firms for free."* Expect DMs.
3. **YouTube demo videos** — Record a 3-minute screen recording: "Watch how a law firm finds their own prior case strategy in 15 seconds." Target long-tail keyword: "law firm knowledge management software." Ranks fast in a low-competition niche.
4. **Local bar association CLE events** — Sponsor a CLE lunch ($300–800). Attorneys have to attend CLEs — you get a captive audience. Demo after the educational segment.
5. **ProductHunt / Indie Hackers launch** — Legal tech buyers are active there. A scrappy "we built AI for small law firms" launch gets organic attention.

**Core message (one line)**
> *"Every answer your firm has ever given lives in your case files. We make it searchable in plain English — before the partner leaves."*

**Pilot → Paid conversion path**
- Free 30-day pilot: upload files from 3 recent matters
- Success metric: *"Find a prior argument you know exists in your files"* — demo the before/after in the first session
- $300/month is under the billing rate of a single hour — price anchoring is easy

**Content / inbound engine**
- LinkedIn: Target attorney-to-attorney content — *"The $50,000 question your law firm already answered once"* style posts
- Legal tech newsletter sponsorships: *Above the Law*, *Lawyerist*, *Law Technology Today* — all have small-firm audiences
- Referral program: $100 credit per referred firm (attorneys refer to each other constantly within bar networks)

**Why it's sticky**
The firm's institutional knowledge accumulates inside the product. Leaving means losing it. The more matters uploaded, the more valuable it becomes — a compounding knowledge asset.

---

## Business 5 — Franchise Operations Intelligence
*5,000+ franchise brands, all with the same broken operations problem*

### The Gap
Every franchise brand has an operations manual — a document that is (a) 300+ pages, (b) updated once a year, (c) impossible for franchisees to search, and (d) answered via a support hotline that costs the franchisor $50–200 per call. Corporate teams manually answer the same questions from franchisees thousands of times per year. No franchise brand below $500M revenue has an AI operations agent.

### The Product
An agentic operations hub for franchise networks. Franchise corporate uploads their operations manuals, training materials, supplier contracts, compliance requirements → franchisees ask questions → agents answer with citations, escalate gaps to the support team. Add a compliance monitoring agent that detects when a franchisee's reported metrics suggest a policy violation.

### Claude Code Role
This is a clean multi-tenant deployment of LLMWiki: one Terraform workspace per brand, shared Bedrock endpoint, brand-specific HOCON agent registries. `/fusion` generates the franchise-specific FAQ agent from their operations manual in one session.

### 7 Levels Map

| Level | Milestone | What it looks like for you |
|---|---|---|
| 1 — Sell 10 | 2 franchise brands (100–500 units each) at $2K/month | International Franchise Association conference |
| 2 — Growth Flywheel | Brand A's VP of Ops refers Brand B at same conference | "The franchise AI platform" positioning |
| 3 — Business OS | New brand onboarded in <1 week; multi-tenant by design | Per-unit pricing model scales with brand growth |
| 4 — Double Pay | $40K MRR from 6 brands | Franchise royalty = recurring; very sticky |
| 5 — Advisory Board | 1 ex-McDonald's ops director, 1 FranConnect exec, 1 franchise attorney | Compliance and audit trail use cases |
| 6 — Acquisition | Acquire a franchise intranet/portal company | Merge their communication tools with your AI knowledge layer |
| 7 — Exit / Legacy | The operations intelligence platform for franchise networks | Acquisition target for FranConnect, Naranga, ServiceMaster |

**Revenue ceiling:** $10M–40M ARR (a $1B TAM at 5,000 brands)

### Sales & Marketing

**Ideal Customer Profile (ICP)**
- Title: VP of Franchise Operations, Director of Franchisee Support, Chief Operating Officer
- Company: Franchise brand with 50–500 units; fast food, fitness, home services, retail — any brand where franchisee support calls eat the ops team's time
- Pain signal: Their franchisee support line handles 200+ calls/month answering questions that are in the operations manual

**Cold lead generation from zero**
1. **IFA (International Franchise Association) directory** — IFA publishes a searchable member directory of 1,300+ franchise brands with contact info. It's your cold outreach list. Filter by unit count (50–500 units) and sector. Email VPs of Operations directly: *"Your franchisees are calling your support line for answers that live in your ops manual. We turn that manual into an AI agent that answers them instantly — and cuts your support volume by 40%."*
2. **Franchise trade press** — *Franchise Times*, *Entrepreneur Franchise 500*, *Franchise Business Review* all accept contributed articles. Pitch: *"How AI is cutting franchisee support calls in half."* One article = inbound from 50+ brands.
3. **LinkedIn targeted ads** — $500/month budget targeting "Franchise Operations" job titles. Drive to a 60-second Loom demo video. Cost per lead in B2B franchise is low because almost nobody is advertising here.
4. **FranConnect user community** — FranConnect (franchise ops software) has user groups. Get known in their ecosystem as the AI layer that sits on top.
5. **Cold call franchisee support lines** — Call the 1-800 number of a franchise brand as a "test." Count the rings. Hear the hold music. Then email the VP of Ops: *"I called your support line today. Here's what I noticed."* Personal, specific, impossible to ignore.

**Core message (one line)**
> *"Your franchisees call your ops team 200 times a month for answers that are already in your manual — we make those answers instant and self-serve."*

**Pilot → Paid conversion path**
- Offer a free pilot on one geographic region or franchise category (e.g. food franchisees only)
- Measure: support call volume before vs. after; franchisee satisfaction score
- ROI calculator: *"200 support calls/month × 20 min each × $30/hr ops cost = $2,000/month. We cost $2,000/month."* — break-even on day one
- Scale pricing per unit (50 units = $2K/month, 500 units = $8K/month)

**Content / inbound engine**
- Podcast outreach: *Franchise Euphoria*, *Franchise Secrets* — podcast hosts are always looking for operational AI guests
- Webinar: *"From ops manual to AI agent in 48 hours"* — co-host with a franchise consultant
- Case study after first win: *"How [Brand X] cut franchisee support calls by 38% in 60 days"* — share in IFA communities

**Why it's sticky**
The ops manual is evergreen. Every update you push into the system improves the agent. Franchisors are risk-averse — once approved by corporate compliance, they don't switch vendors. Multi-year contracts are standard in this space.

---

## Business 6 — Clinical Trial Protocol Intelligence
*FDA submissions are manual — and getting one wrong costs $10M+*

### The Gap
Clinical trial teams (biotech, CROs, pharma) produce hundreds of documents per study: protocols, amendments, investigator brochures, informed consent forms, regulatory correspondence. Every new team member, every FDA query, every protocol deviation investigation requires manually searching this document mountain. Getting it wrong means a warning letter or clinical hold. No SMB biotech or small CRO has an AI agent for this — they have shared drives and experienced staff who leave.

### The Product
An agentic regulatory intelligence system for clinical trials. Upload all study documents → agents answer "What does the protocol say about dose escalation criteria?" or "Has this adverse event type been reported before in this study?" with citations. Add a "deviation detection agent" that flags when a reported event contradicts the approved protocol.

### Claude Code Role
Your existing Bedrock KB + Textract pipeline handles clinical PDFs. The `evidence_required` field in your agent response contract maps perfectly to FDA citation requirements. `/auto-validate` gates every new document type against known protocol questions before deploying to a live study.

### 7 Levels Map

| Level | Milestone | What it looks like for you |
|---|---|---|
| 1 — Sell 10 | 3 small CROs or Series A biotechs at $3K/month | DIA conference; LinkedIn outreach to clinical ops directors |
| 2 — Growth Flywheel | CRO recommends to their sponsor clients | "Sponsor requires their CRO to use it" pull-through |
| 3 — Business OS | Study setup in <2 hrs; 21 CFR Part 11 audit trail | FDA compliance framing replaces sales objection |
| 4 — Double Pay | $60K MRR from 8 studies/companies | High ACV: one protocol deviation prevented = ROI proven |
| 5 — Advisory Board | 1 ex-FDA reviewer, 1 Big Pharma clinical ops VP, 1 health IT attorney | Regulatory positioning and risk management |
| 6 — Acquisition | Acquire a eTMF (electronic Trial Master File) SaaS | Merge document management + AI intelligence |
| 7 — Exit / Legacy | The AI intelligence layer for clinical trial operations | Acquisition target for Veeva, Medidata, Oracle Health Sciences |

**Revenue ceiling:** $20M–60M ARR (the clinical trial management market is $2B+)

### Sales & Marketing

**Ideal Customer Profile (ICP)**
- Title: VP of Clinical Operations, Head of Regulatory Affairs, Clinical Project Manager
- Company: CRO (Contract Research Organisation) with 10–200 staff, or Series A–C biotech running 1–5 active studies
- Pain signal: They have had a protocol deviation, an FDA query, or a near-miss because a team member didn't find the right protocol section in time

**Cold lead generation from zero**
1. **ClinicalTrials.gov as your lead database** — Every active clinical trial in the US is listed publicly with the sponsor name, principal investigator, and study phase. Filter by Phase II/III (they have the most document complexity and the most to lose). Find the sponsor company. Find their Clinical Ops VP on LinkedIn. This is a free, real-time, intent-signal lead list updated daily.
2. **LinkedIn outreach to clinical ops titles** — Message: *"Protocol deviations cost sponsors $50K–$500K to remediate with the FDA. We built an AI agent that answers protocol questions with exact citations in seconds — so team members stop guessing. Would you see a 15-min demo on a live study?"*
3. **DIA (Drug Information Association) and ACRP (Association of Clinical Research Professionals) conferences** — DIA Annual Meeting is the single best room for clinical ops decision makers. One conference = 50 qualified conversations. Sponsor a coffee station ($2K–5K) at a small DIA chapter meeting to start.
4. **CRO partnership channel** — Contact mid-size CROs (ICON, PRA, Syneos mid-tier) and position as a tool they can offer their sponsor clients. One CRO = dozens of studies. This is your fastest Level 2 flywheel.
5. **Regulatory consultant network** — Independent regulatory consultants advise biotechs on trial design. If they recommend your tool to their clients, that's warm inbound. Reach them via LinkedIn; offer a revenue share or referral fee.

**Core message (one line)**
> *"Protocol deviations happen when team members can't find the right answer fast enough — we give them cited protocol answers in seconds, not hours."*

**Pilot → Paid conversion path**
- Free pilot on one active study (30–60 days)
- Upload protocol + amendments + investigator brochure
- Define a success event upfront: *"How long does it take your team to answer a protocol question today?"*
- ROI frame: one protocol deviation costs $50K+ to remediate. One prevented deviation pays for 5 years of subscription.
- Convert at $3K–6K/month; multi-study discounts drive expansion revenue

**Content / inbound engine**
- Webinar: *"How AI is preventing protocol deviations in Phase II trials"* — co-host with a regulatory consultant
- LinkedIn: Post weekly on real FDA warning letters (public record) — what the deviation was, how an AI query layer could have caught it
- Regulatory newsletter sponsorship: *The FDA Law Blog*, *RAPS Regulatory Focus* — niche but read by every decision maker
- YouTube: *"Watch this clinical ops team answer an FDA query in 90 seconds"* — screen recording demo

**Why it's sticky**
21 CFR Part 11 compliance requirements mean validated systems are very hard to switch. Once your tool is in the audit trail of a live study, it stays until the study closes — and then follows the team to their next study.

---

## Business 7 — Municipal Permit & Compliance Intelligence
*Every city government is running on paper and phone calls*

### The Gap
Local governments and municipalities receive thousands of permit applications, zoning variance requests, and code compliance inquiries per year. Staff manually look up municipal codes, zoning ordinances, and prior decisions to answer each one. Citizens wait weeks for answers that should take minutes. No municipality below 500K population has an AI agent for this — they have static websites and overworked clerks. This market is completely untouched because it is perceived as unsexy and procurement-heavy. That is exactly why it is wide open.

### The Product
An agentic civic intelligence system. A municipality uploads their municipal code, zoning maps, permit procedures, historical decisions → citizens and staff ask: "Can I build a detached garage on a 6,000 sqft R-1 lot?" → agent answers with code section, setback requirements, and permit fee — instantly. Add a permit triage agent that pre-screens applications for completeness before they reach a human reviewer.

### Claude Code Role
`/fusion` builds the "zoning code expert + permit procedure guide" agent pair from municipal documents in one session. Your Terraform IaC deploys a white-label instance per municipality. The civic data is public domain — no data licensing cost.

### 7 Levels Map

| Level | Milestone | What it looks like for you |
|---|---|---|
| 1 — Sell 10 | 3 mid-size cities (50K–200K population) at $1.5K/month | ICMA (city manager association) conference; GovTech channels |
| 2 — Growth Flywheel | One city's success becomes a case study cited at state league of cities | State municipal league conference as distribution |
| 3 — Business OS | New city live in <1 week; staff training in 2 hrs | Annual contract aligned to municipal budget cycles |
| 4 — Double Pay | $20K MRR from 8 cities | Low churn: government contracts renew quietly |
| 5 — Advisory Board | 1 ex-city manager, 1 GovTech investor, 1 municipal attorney | Navigate procurement rules + FOIA/public records compliance |
| 6 — Acquisition | Acquire a permit tracking SaaS (many legacy players) | Bolt AI onto their existing permit workflow product |
| 7 — Exit / Legacy | The AI layer for civic operations nationwide | Acquisition target for Tyler Technologies, Granicus, Salesforce Public Sector |

**Revenue ceiling:** $10M–30M ARR (19,000+ municipalities in the US × $1.5K/month = $340M TAM)

### Sales & Marketing

**Ideal Customer Profile (ICP)**
- Title: City Manager, Director of Community Development, Building & Planning Director, Permit Office Manager
- Company: Municipality of 30,000–300,000 population — large enough to have a real permit volume, small enough to have no IT budget for custom software
- Pain signal: Citizens wait days for a simple zoning question; permit staff spend half their day on the phone answering the same 20 questions

**Cold lead generation from zero**
1. **Municipal directories as your list** — The National League of Cities (NLC) and ICMA publish directories of member cities with city manager contacts. Every US state also has a League of Municipalities with a searchable directory. This is a public, free, structured lead list of 19,000 potential buyers. Filter to cities with population 30K–300K. Email the City Manager or Planning Director.
2. **GovTech media and channels** — *Government Technology* magazine, *GovTech* website, *StateScoop* — all have directories and events. A contributed article (*"How AI is cutting permit phone calls by 60% in mid-size cities"*) gets read by thousands of city managers.
3. **ICMA Annual Conference** — The single best room for city managers in the US. A booth costs $3K–5K. Alternatively, attend as a delegate ($800) and do 20 scheduled coffee meetings pre-booked on LinkedIn.
4. **State municipal league annual conferences** — Every state has one. Florida League of Cities, Texas Municipal League, etc. These are smaller, cheaper to exhibit at, and the decision makers are all in one room. Start with 2–3 state leagues.
5. **Cold email to City Managers** — City Manager emails follow a predictable format (firstname.lastname@cityname.gov or similar). Apollo.io has many. 3-line email: *"Your permit office answers the same 20 zoning questions by phone every day. We built an AI agent that answers them instantly from your municipal code — free pilot for 60 days. Worth 15 minutes?"*
6. **Pilot city as a reference** — One successful city = every neighbouring city becomes a warm lead. Mayors and city managers talk to each other constantly at regional councils of government meetings.

**Core message (one line)**
> *"Citizens wait days for zoning answers your municipal code already contains — we make those answers instant, cited, and available 24/7."*

**Pilot → Paid conversion path**
- Offer a free 60-day pilot (government procurement cycles are slow — a free pilot bypasses the RFP process)
- Municipal code is public domain — you can pre-load it before the first meeting and demo it live with their actual code
- Success metric: *"How many permit inquiry calls does your office receive per week?"* — measure before and after
- Annual contract aligned to fiscal year budget cycle (municipalities budget in June–August for the following year)
- Frame as a one-time "digital services" line item, not "software" — easier to approve without IT committee review

**Content / inbound engine**
- Case study after first city win: *"City of [X] cut permit inquiry calls by 55% in 60 days"* — submit to Government Technology, StateScoop, and the relevant state municipal league newsletter
- Webinar with ICMA or NLC: *"From phone calls to AI: how cities are modernising permit services without an IT budget"*
- LinkedIn: Post on permit office efficiency, citizen satisfaction scores, planning department burnout — topics city managers care about
- Google Ads: Target "municipal permit software" and "city permit management system" — low competition, high intent

**Why it's sticky**
Government contracts renew quietly on multi-year cycles. The municipal code is always changing — every zoning amendment, every new ordinance is a reason to keep the subscription active. No city manager wants to explain to their council why they dropped a working system.

---

## Comparative Snapshot

| # | Business | Time to Level 1 | Revenue Ceiling | Your Stack Reuse | Automation Gap |
|---|---|---|---|---|---|
| 1 | Healthcare IT Implementation | 2–4 weeks | $5M–15M ARR | 95% — it IS LLMWiki | High |
| 2 | Construction Project Intelligence | 4–6 weeks | $20M–80M ARR | 80% | Very High |
| 3 | Insurance Adjuster Knowledge Agent | 6–8 weeks | $30M–100M ARR | 75% | High |
| 4 | Legal Knowledge Fabric (SMB) | 3–5 weeks | $5M–20M ARR | 80% | Very High |
| 5 | Franchise Operations Intelligence | 4–6 weeks | $10M–40M ARR | 85% | Very High |
| 6 | Clinical Trial Protocol Intelligence | 8–12 weeks | $20M–60M ARR | 70% | Extreme |
| 7 | Municipal Permit Intelligence | 6–10 weeks | $10M–30M ARR | 80% | Extreme |

---

## Recommended Starting Order

**If you want lowest risk, fastest Level 1:** Start with **Business 1** — you already have the product, domain knowledge, and a Cognizant network to get 3 pilot customers. Your LLMWiki IS the product.

**If you want the largest exit:** **Business 2 (Construction)** or **Business 3 (Insurance)** — massive TAMs, no dominant AI player yet, and your stack maps directly.

**If you want the most defensible moat:** **Business 6 (Clinical Trials)** — the compliance requirement creates a switching cost that is almost impossible to break once you're embedded in a running study.

**The sequence that makes sense:**
1. Productise Business 1 while still at Cognizant (3–6 months, side project)
2. Use revenue from Business 1 to self-fund a second vertical (Business 2 or 5)
3. By Level 3–4 in Business 1, the multi-tenant Terraform architecture you build there is the deployment platform for all other businesses

---

## Universal Sales & Marketing Playbook (Starting From Zero Leads)

This applies to all 7 businesses. You have no brand, no list, no warm network in the target market. Here is the repeatable system.

---

### The Cold Lead Engine (Week 1 — Day 1)

**Tools needed:** LinkedIn Sales Navigator ($80/mo), Apollo.io ($50/mo), Loom (free), a plain-text email account

#### Step 1 — Build your ICP list
- LinkedIn Sales Navigator: filter by Title + Industry + Company Size per the ICP above
- Apollo.io: enrich with verified business emails
- Target: 200–500 contacts per business per vertical
- Cost: ~$130/month total

#### Step 2 — The 3-line cold email (what actually gets replies)
```
Subject: [Specific pain point] at [Company Name]

Hi [First name],

[One sentence naming the exact pain — be specific, not generic.]
[One sentence on what you built and the outcome it delivers.]
[One sentence CTA — a 15-min call or a free pilot, not "let me know if interested."]

— Srini
```

Example for Business 2 (Construction):
```
Subject: RFI lookups at [GC Name]

Hi Mike,

GC project managers spend 2–3 hrs/week searching specs and RFI logs for 
answers that should take 10 seconds.
I built an AI agent that answers project document questions with citations — 
free pilot on your next active project.
15 minutes to see it live?

— Srini
```

**Send 15–20 emails/day. Expect 3–5% reply rate. That is 1–2 conversations per week from day one.**

---

#### Step 3 — The 10-minute Loom demo (your 24/7 sales rep)
Record a 10-minute screen recording that shows:
1. The pain (30 seconds — show the old way: searching a PDF, emailing around)
2. The product (7 minutes — live query against real documents, show citations)
3. The offer (90 seconds — free pilot, specific CTA)

Include this Loom link in every cold email, LinkedIn message, and social post.
**A good Loom demo converts faster than any sales deck.**

---

#### Step 4 — LinkedIn outreach (parallel to email)
- 20 connection requests/day with a one-line personalised note (no pitch in the request)
- After acceptance: send the Loom link with one sentence of context
- Post 3× per week: one educational post (the pain), one case study / result, one opinion on the industry

**The rule:** Never pitch in the first message. Build curiosity. The Loom does the selling.

---

#### Step 5 — The free pilot (your Level 1 closer)
The single most effective thing you can do to get from 0 → first paying customer:

> **"Free 30-day pilot. Upload your documents. If it saves your team time, you pay. If not, you keep the questions we answered for free."**

This removes every objection at Level 1. You don't need a brand, a case study, or a sales team. You need one person willing to try it — and a product that delivers in the first session.

---

### The Content Engine (Week 2 onwards — builds inbound over time)

| Channel | Cadence | Content type | Expected outcome |
|---|---|---|---|
| LinkedIn posts | 3×/week | Pain story, case study snippet, industry observation | Inbound connection requests; DM replies |
| Loom demo video | Once (update quarterly) | 10-min product walkthrough | Conversion tool for all outbound |
| YouTube | 1×/month | 3-min screen recording demo | Long-tail SEO; organic discovery |
| Industry newsletter | 1 contributed article/quarter | Educational (no pitch) | 50–200 warm inbound leads per article |
| Conference | 1–2/year | Talk or booth at the niche conference for that vertical | 20–50 qualified conversations in 2 days |
| Cold email drip | Daily | 4-email sequence (problem → demo → ROI → last call) | Consistent pipeline at low cost |

---

### The Referral Engine (Level 2 — activate after first 3 paying customers)

Every customer you have is connected to 10 more potential customers in their industry.

**How to activate it:**
1. After 60 days, ask for a 15-minute case study call (record it with permission)
2. Post the case study on LinkedIn — tag the customer if they allow it
3. Ask one direct question: *"Who else in your network has this same problem?"*
4. Offer: $200 credit or one free month for every referred customer who signs up

One strong referral from a satisfied customer is worth 100 cold emails. The referral engine is how you get from Level 1 (10 customers) to Level 2 (predictable growth flywheel) without hiring a sales team.

---

### Sales Metrics to Track From Day 1

| Metric | Target | Why |
|---|---|---|
| Cold outreach per day | 20–30 (email + LinkedIn) | Pipeline is a numbers game at Level 1 |
| Reply rate | ≥3% | Below this = fix the message, not the volume |
| Demo → pilot conversion | ≥40% | If lower, the demo is unclear or ICP is wrong |
| Pilot → paid conversion | ≥60% | If lower, the product isn't delivering in the pilot |
| Time to first revenue | <60 days | The only metric that matters at Level 1 |

---

## How Claude Code Compounds Across All 7

The reason these businesses are achievable solo or with a tiny team is the fusion harness:

```
Level 1 (Sell 10):     /auto-validate ships working prototypes in hours → demo in days, not months
Level 2 (Flywheel):    /fusion generates domain-specific agent content faster than any competitor can hire
Level 3 (Business OS): /unit-test keeps the codebase green as the product grows
Level 4 (Pay):         Low headcount = high margin; Codex writes the boilerplate, you architect
Level 5 (Advisory):    Technical credibility from a working product beats a deck every time
Level 6 (Acquisition): Your stack absorbs an acquired company's documents in 48 hrs
Level 7 (Wealth):      The moat is not the code — it is the compounding domain knowledge inside each wiki
```

The businesses above are not ideas. They are the same business — **an agentic knowledge fabric for document-heavy industries** — applied seven times to seven markets where no one has gone yet.
