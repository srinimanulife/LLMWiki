"""
Generates linkedin_w2_carousel.pdf — 8-slide LinkedIn carousel
for LLMWiki Week 2: The AWS Architecture post.

LinkedIn carousel requirements:
- Upload as a Document post (PDF)
- Square slides: 1080x1080px = 1080/72 = 15 inches at 72dpi
- Dark background, white text, electric blue + green accents
"""

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os

# ── Dimensions ──────────────────────────────────────────────────────────────
SIZE = 1080  # pixels at 72dpi
PT   = SIZE  # 1080pt = 1080px at 72dpi (reportlab uses points = 1/72 inch)
PAGE_SIZE = (PT, PT)

# ── Brand colours ────────────────────────────────────────────────────────────
BG          = HexColor("#0a0a14")   # near-black background
BLUE        = HexColor("#3b82f6")   # electric blue
GREEN       = HexColor("#22c55e")   # green
AMBER       = HexColor("#f59e0b")   # amber / warning
RED         = HexColor("#ef4444")   # red / alert
WHITE       = HexColor("#ffffff")
LIGHT_GREY  = HexColor("#94a3b8")
DARK_NAVY   = HexColor("#0f172a")   # bottom strip

OUTPUT = os.path.join(os.path.dirname(__file__), "linkedin_w2_carousel.pdf")


def new_canvas(filename):
    c = canvas.Canvas(filename, pagesize=PAGE_SIZE)
    c.setTitle("LLMWiki AWS Architecture — LinkedIn Carousel")
    return c


def bg(c):
    """Fill full slide with background colour."""
    c.setFillColor(BG)
    c.rect(0, 0, PT, PT, fill=1, stroke=0)


def bottom_strip(c, text):
    """Dark navy footer strip with white text."""
    strip_h = 72
    c.setFillColor(DARK_NAVY)
    c.rect(0, 0, PT, strip_h, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Oblique", 22)
    c.drawCentredString(PT / 2, 24, text)


def slide_number(c, n):
    """Small slide counter top-right."""
    c.setFillColor(LIGHT_GREY)
    c.setFont("Helvetica", 22)
    c.drawRightString(PT - 32, PT - 40, f"{n} / 8")


def title_tag(c, text, colour=BLUE, y=None):
    """Small coloured label above a heading."""
    if y is None:
        y = PT - 130
    c.setFillColor(colour)
    c.setFont("Helvetica-Bold", 26)
    c.drawCentredString(PT / 2, y, text.upper())


def heading(c, text, y, size=56, colour=WHITE):
    c.setFillColor(colour)
    c.setFont("Helvetica-Bold", size)
    c.drawCentredString(PT / 2, y, text)


def sub(c, text, y, size=30, colour=LIGHT_GREY):
    c.setFillColor(colour)
    c.setFont("Helvetica", size)
    c.drawCentredString(PT / 2, y, text)


def bullet_lines(c, lines, start_y, line_height=52, size=30,
                 colour=WHITE, indent=120, dot_colour=BLUE):
    y = start_y
    for line in lines:
        # bullet dot
        c.setFillColor(dot_colour)
        c.circle(indent - 20, y + 8, 6, fill=1, stroke=0)
        # text
        c.setFillColor(colour)
        c.setFont("Helvetica", size)
        c.drawString(indent, y, line)
        y -= line_height
    return y


def arrow_head(c, tip_x, tip_y, colour):
    """Draw a right-pointing arrowhead with tip at (tip_x, tip_y)."""
    from reportlab.graphics.shapes import Path
    from reportlab.graphics import renderPDF
    from reportlab.graphics.shapes import Drawing, Polygon
    p = c.beginPath()
    p.moveTo(tip_x, tip_y)
    p.lineTo(tip_x - 12, tip_y + 7)
    p.lineTo(tip_x - 12, tip_y - 7)
    p.close()
    c.setFillColor(colour)
    c.drawPath(p, fill=1, stroke=0)


def flow_row(c, items, y, box_w=180, box_h=64, gap=18,
             fill=BLUE, text_colour=WHITE, arrow_colour=BLUE):
    """Render a horizontal pipeline row of boxes with arrows."""
    total = len(items) * box_w + (len(items) - 1) * (gap + 24)
    x = (PT - total) / 2
    for i, item in enumerate(items):
        # box
        c.setFillColor(fill)
        c.roundRect(x, y - box_h / 2, box_w, box_h, 8, fill=1, stroke=0)
        c.setFillColor(text_colour)
        c.setFont("Helvetica-Bold", 22)
        c.drawCentredString(x + box_w / 2, y - 8, item)
        # arrow (not after last)
        if i < len(items) - 1:
            ax_start = x + box_w + 2
            ax_end = x + box_w + gap + 22
            c.setStrokeColor(arrow_colour)
            c.setLineWidth(3)
            c.line(ax_start, y, ax_end - 12, y)
            arrow_head(c, ax_end, y, arrow_colour)
        x += box_w + gap + 24


def badge_row(c, badges, y, box_w=170, box_h=52):
    """Render 5 coloured pillar badges."""
    colours = [BLUE, GREEN, RED, AMBER, HexColor("#a855f7")]
    total = len(badges) * box_w + (len(badges) - 1) * 16
    x = (PT - total) / 2
    for i, (emoji, label) in enumerate(badges):
        col = colours[i % len(colours)]
        c.setFillColor(col)
        c.roundRect(x, y - box_h / 2, box_w, box_h, 8, fill=1, stroke=0)
        c.setFillColor(WHITE)
        c.setFont("Helvetica-Bold", 20)
        c.drawCentredString(x + box_w / 2, y - 6, f"{emoji} {label}")
        x += box_w + 16


def divider(c, y, colour=BLUE, width=600):
    c.setStrokeColor(colour)
    c.setLineWidth(2)
    c.line((PT - width) / 2, y, (PT + width) / 2, y)


# ════════════════════════════════════════════════════════════════════════════
# SLIDES
# ════════════════════════════════════════════════════════════════════════════

def slide_1(c):
    """Hook + title card."""
    bg(c)
    slide_number(c, 1)

    # Brand badge top-left
    c.setFillColor(BLUE)
    c.roundRect(40, PT - 80, 160, 44, 8, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 22)
    c.drawCentredString(120, PT - 63, "LLMWiki")

    # Big hook text
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 52)
    c.drawCentredString(PT / 2, PT - 230, "We saved $400/month")
    c.setFont("Helvetica-Bold", 52)
    c.drawCentredString(PT / 2, PT - 295, "on day one by NOT")
    c.setFillColor(AMBER)
    c.setFont("Helvetica-Bold", 52)
    c.drawCentredString(PT / 2, PT - 360, "using the obvious choice.")

    divider(c, PT - 420, colour=BLUE, width=700)

    c.setFillColor(LIGHT_GREY)
    c.setFont("Helvetica", 32)
    c.drawCentredString(PT / 2, PT - 475, "The full LLMWiki architecture on AWS")
    c.setFont("Helvetica", 28)
    c.drawCentredString(PT / 2, PT - 520, "and every decision behind it.")

    # Pipeline preview
    flow_row(c, ["S3", "Textract", "Bedrock", "S3 Vectors", "Lambda"],
             y=PT - 640, box_w=155, box_h=56, gap=10)

    # Five pillar dots
    badge_row(c,
              [("🔵", "Distributed"), ("🟢", "Fault-tolerant"),
               ("🔴", "Secured"), ("🟡", "Scalable"), ("🟣", "Validated")],
              y=PT - 760, box_w=170)

    bottom_strip(c, "Swipe → full architecture breakdown, every decision explained")
    c.showPage()


def slide_2(c):
    """The Problem — before state."""
    bg(c)
    slide_number(c, 2)

    title_tag(c, "The Problem", colour=RED, y=PT - 110)
    heading(c, "This is how most enterprises", PT - 185, size=44)
    heading(c, "manage critical knowledge today.", PT - 240, size=44)

    divider(c, PT - 280)

    pain_items = [
        ("📁", "Critical docs buried in shared drives nobody searches"),
        ("🧠", "Tribal memory — one person holds the answer"),
        ("📧", "Email thread to find the expert — 2 days wait"),
        ("🚪", "Answer walks out the door when they resign"),
    ]
    y = PT - 360
    for emoji, text in pain_items:
        c.setFillColor(RED)
        c.roundRect(80, y - 36, PT - 160, 60, 8, fill=1, stroke=0)
        c.setFillColor(WHITE)
        c.setFont("Helvetica-Bold", 28)
        c.drawString(120, y - 12, f"{emoji}  {text}")
        y -= 85

    bottom_strip(c, "Sound familiar? Swipe to see the fix →")
    c.showPage()


def slide_3(c):
    """The Ingestion Pipeline."""
    bg(c)
    slide_number(c, 3)

    title_tag(c, "The Ingestion Pipeline", colour=BLUE, y=PT - 110)
    heading(c, "Any format. Any size.", PT - 190, size=50)
    heading(c, "3 minutes to queryable.", PT - 250, size=50, colour=GREEN)

    divider(c, PT - 295)

    # Pipeline boxes — two rows
    flow_row(c, ["PDF / Office", "Scanned Docs", "Runbooks"],
             y=PT - 390, box_w=200, box_h=60, gap=10, fill=HexColor("#1e3a5f"))

    # Arrow down
    c.setStrokeColor(BLUE)
    c.setLineWidth(3)
    c.line(PT / 2, PT - 430, PT / 2, PT - 468)
    # downward arrowhead via path
    c.setFillColor(BLUE)
    p = c.beginPath()
    p.moveTo(PT / 2, PT - 478)
    p.lineTo(PT / 2 - 10, PT - 462)
    p.lineTo(PT / 2 + 10, PT - 462)
    p.close()
    c.drawPath(p, fill=1, stroke=0)

    c.setFillColor(LIGHT_GREY)
    c.setFont("Helvetica-Oblique", 24)
    c.drawCentredString(PT / 2, PT - 465, "Amazon S3  ←  EventBridge trigger on upload")

    flow_row(c, ["AWS Textract", "Amazon Bedrock", "S3 Vectors"],
             y=PT - 570, box_w=220, box_h=64, gap=14, fill=BLUE)

    # Annotations
    annotations = [
        (140, PT - 650, "PDF → Markdown"),
        (PT / 2, PT - 650, "Chunk + Embed"),
        (PT - 140, PT - 650, "Vector Store\n~$0/mo base"),
    ]
    for x, y, txt in annotations:
        c.setFillColor(LIGHT_GREY)
        c.setFont("Helvetica-Oblique", 22)
        c.drawCentredString(x, y, txt)

    # Not polling label
    c.setFillColor(GREEN)
    c.roundRect((PT - 420) / 2, PT - 730, 420, 48, 8, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 24)
    c.drawCentredString(PT / 2, PT - 710, "✓  Pure event-driven. Zero idle cost.")

    bottom_strip(c, "No polling. No scheduled jobs. Fires on every upload.")
    c.showPage()


def slide_4(c):
    """The Query Pipeline."""
    bg(c)
    slide_number(c, 4)

    title_tag(c, "The Query Pipeline", colour=GREEN, y=PT - 110)
    heading(c, "Question in. Cited answer out.", PT - 195, size=46)

    divider(c, PT - 235)

    flow_row(c,
             ["User Question", "Lambda", "Bedrock KB", "Claude", "Cited Answer"],
             y=PT - 360, box_w=162, box_h=60, gap=8, fill=BLUE)

    # Confidence meter
    c.setFillColor(LIGHT_GREY)
    c.setFont("Helvetica-Bold", 28)
    c.drawCentredString(PT / 2, PT - 460, "Confidence Score attached to every answer:")

    conf_items = [
        (GREEN, "HIGH", "2+ direct-match sources"),
        (AMBER, "MEDIUM", "Partial match sources"),
        (RED, "LOW", "Gap Detection triggered"),
    ]
    x = 120
    for col, label, desc in conf_items:
        c.setFillColor(col)
        c.roundRect(x, PT - 590, 260, 100, 10, fill=1, stroke=0)
        c.setFillColor(WHITE)
        c.setFont("Helvetica-Bold", 34)
        c.drawCentredString(x + 130, PT - 540, label)
        c.setFont("Helvetica", 20)
        c.drawCentredString(x + 130, PT - 575, desc)
        x += 280

    c.setFillColor(LIGHT_GREY)
    c.setFont("Helvetica", 26)
    c.drawCentredString(PT / 2, PT - 650, "Every answer includes the source wiki pages that were used.")

    c.setFillColor(GREEN)
    c.setFont("Helvetica-Bold", 26)
    c.drawCentredString(PT / 2, PT - 700, "No hallucination without citation. Gaps are flagged, not fabricated.")

    bottom_strip(c, "RAG retrieval + Claude synthesis in one Lambda invocation")
    c.showPage()


def slide_5(c):
    """The Data Layer — DynamoDB tables."""
    bg(c)
    slide_number(c, 5)

    title_tag(c, "The Data Layer", colour=AMBER, y=PT - 110)
    heading(c, "Every query logged.", PT - 190, size=50)
    heading(c, "Every source tracked.", PT - 250, size=50, colour=AMBER)

    divider(c, PT - 295)

    tables = [
        ("llmwiki-index", "Page registry — every wiki document,\nits slug, type, tags, confidence baseline"),
        ("llmwiki-log", "Full audit trail — every query, every\nagent invocation, every confidence score"),
        ("llmwiki-source-registry", "Document provenance — uploader, timestamp,\ntrust level, KB sync status"),
    ]
    y = PT - 390
    for name, desc in tables:
        c.setFillColor(HexColor("#1e3a5f"))
        c.roundRect(80, y - 70, PT - 160, 88, 10, fill=1, stroke=0)
        c.setFillColor(BLUE)
        c.setFont("Helvetica-Bold", 28)
        c.drawString(120, y - 25, name)
        c.setFillColor(LIGHT_GREY)
        c.setFont("Helvetica", 22)
        c.drawString(120, y - 55, desc.replace("\n", "  ·  "))
        y -= 115

    c.setFillColor(GREEN)
    c.setFont("Helvetica-Bold", 26)
    c.drawCentredString(PT / 2, PT - 750, "Compliance-ready audit trail out of the box.")

    bottom_strip(c, "DynamoDB — serverless, scales to zero, pay per request")
    c.showPage()


def slide_6(c):
    """The Cost Decision — S3 Vectors vs OpenSearch."""
    bg(c)
    slide_number(c, 6)

    title_tag(c, "The Cost Decision", colour=AMBER, y=PT - 110)
    heading(c, "Same capability.", PT - 185, size=52)
    heading(c, "1/∞ the floor cost.", PT - 250, size=52, colour=GREEN)

    divider(c, PT - 295)

    # Two comparison boxes
    # Left — OpenSearch (bad)
    c.setFillColor(HexColor("#3b1010"))
    c.roundRect(60, PT - 680, 420, 340, 12, fill=1, stroke=0)
    c.setFillColor(RED)
    c.setFont("Helvetica-Bold", 36)
    c.drawCentredString(270, PT - 370, "OpenSearch")
    lines_os = [
        ("$700+/month", WHITE, 34),
        ("minimum — whether", LIGHT_GREY, 24),
        ("you use it or not", LIGHT_GREY, 24),
        ("", WHITE, 10),
        ("Always-on capacity", LIGHT_GREY, 22),
        ("OCU billing", LIGHT_GREY, 22),
        ("Complex IAM setup", LIGHT_GREY, 22),
    ]
    y = PT - 420
    for txt, col, sz in lines_os:
        if txt:
            c.setFillColor(col)
            c.setFont("Helvetica-Bold" if sz >= 28 else "Helvetica", sz)
            c.drawCentredString(270, y, txt)
        y -= sz + 8

    # Right — S3 Vectors (good)
    c.setFillColor(HexColor("#0f2d1a"))
    c.roundRect(600, PT - 680, 420, 340, 12, fill=1, stroke=0)
    c.setFillColor(GREEN)
    c.setFont("Helvetica-Bold", 36)
    c.drawCentredString(810, PT - 370, "✅  S3 Vectors")
    lines_sv = [
        ("~$0/month base", WHITE, 34),
        ("pay per query", LIGHT_GREY, 24),
        ("zero idle cost", LIGHT_GREY, 24),
        ("", WHITE, 10),
        ("Serverless native", LIGHT_GREY, 22),
        ("S3 IAM — already set up", LIGHT_GREY, 22),
        ("Same vector search", LIGHT_GREY, 22),
    ]
    y = PT - 420
    for txt, col, sz in lines_sv:
        if txt:
            c.setFillColor(col)
            c.setFont("Helvetica-Bold" if sz >= 28 else "Helvetica", sz)
            c.drawCentredString(810, y, txt)
        y -= sz + 8

    # VS label
    c.setFillColor(AMBER)
    c.circle(PT / 2, PT - 510, 36, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 28)
    c.drawCentredString(PT / 2, PT - 520, "VS")

    bottom_strip(c, "We chose S3 Vectors on day one. Still the right call.")
    c.showPage()


def slide_7(c):
    """The Five Pillars."""
    bg(c)
    slide_number(c, 7)

    title_tag(c, "The Five Pillars", colour=BLUE, y=PT - 110)
    heading(c, "Production, not a demo.", PT - 185, size=50)

    divider(c, PT - 225)

    pillars = [
        ("🔵", "DISTRIBUTED", BLUE,
         "Event-driven ingestion + retrieval",
         "Independent components — no bottleneck"),
        ("🟢", "FAULT-TOLERANT", GREEN,
         "Idempotent Lambdas · DLQs · DynamoDB state",
         "Automatic retry — no manual intervention"),
        ("🔴", "SECURED", RED,
         "KMS encryption at rest + in transit",
         "IAM least-privilege per Lambda · VPC isolation"),
        ("🟡", "SCALABLE", AMBER,
         "Serverless-first — scales to zero",
         "Scales to millions of documents · no rearchitecting"),
        ("🟣", "VALIDATED", HexColor("#a855f7"),
         "22 unit tests generated by Codex",
         "First-pass: 22 passed · 0 failed · CI-ready"),
    ]

    y = PT - 300
    for emoji, label, col, line1, line2 in pillars:
        c.setFillColor(HexColor("#111827"))
        c.roundRect(60, y - 52, PT - 120, 68, 8, fill=1, stroke=0)
        # colour bar left edge
        c.setFillColor(col)
        c.roundRect(60, y - 52, 12, 68, 4, fill=1, stroke=0)
        # emoji + label
        c.setFillColor(col)
        c.setFont("Helvetica-Bold", 26)
        c.drawString(100, y - 18, f"{emoji}  {label}")
        # description
        c.setFillColor(LIGHT_GREY)
        c.setFont("Helvetica", 21)
        c.drawString(380, y - 15, line1)
        c.setFont("Helvetica", 19)
        c.drawString(380, y - 38, line2)
        y -= 88

    bottom_strip(c, "LLMWiki runs in production — not as a proof-of-concept")
    c.showPage()


def slide_8(c):
    """What's Next — teaser + DM CTA."""
    bg(c)
    slide_number(c, 8)

    # Gradient-style top accent bar
    c.setFillColor(BLUE)
    c.rect(0, PT - 12, PT, 12, fill=1, stroke=0)

    title_tag(c, "What's Next", colour=GREEN, y=PT - 130)

    heading(c, "This architecture just got a brain.", PT - 220, size=46)

    divider(c, PT - 265, colour=GREEN)

    c.setFillColor(WHITE)
    c.setFont("Helvetica", 32)
    c.drawCentredString(PT / 2, PT - 335,
                        "Next week: Neuro-SAN & the AAOSA Protocol")
    c.setFillColor(LIGHT_GREY)
    c.setFont("Helvetica", 26)
    lines = [
        "5 specialist agents collaborating on one customer question.",
        "No agent ever sees the sensitive data.",
        "Orchestrated in HOCON — no Python business logic required.",
    ]
    y = PT - 405
    for line in lines:
        c.drawCentredString(PT / 2, y, line)
        y -= 44

    divider(c, PT - 555, colour=BLUE)

    # CTA box
    c.setFillColor(BLUE)
    c.roundRect(120, PT - 730, PT - 240, 130, 12, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 32)
    c.drawCentredString(PT / 2, PT - 665, "Want to see this on your own documents?")
    c.setFont("Helvetica", 26)
    c.drawCentredString(PT / 2, PT - 705, "30 minutes · Live demo · DM me on LinkedIn")

    bottom_strip(c, "Follow for the full series · LLMWiki by Srinivasan Sethuraman")
    c.showPage()


# ════════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════════

def main():
    c = new_canvas(OUTPUT)
    slide_1(c)
    slide_2(c)
    slide_3(c)
    slide_4(c)
    slide_5(c)
    slide_6(c)
    slide_7(c)
    slide_8(c)
    c.save()
    size_kb = os.path.getsize(OUTPUT) // 1024
    print(f"✅  Saved: {OUTPUT}")
    print(f"   Pages: 8  |  Size: {size_kb} KB")
    print(f"   Upload this PDF as a Document post on LinkedIn (not as a photo).")


if __name__ == "__main__":
    main()
