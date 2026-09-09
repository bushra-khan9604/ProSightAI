from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "pdf" / "ProSight_AI_Project_Submission_Report.pdf"

NAVY = colors.HexColor("#071C3A")
BLUE = colors.HexColor("#0C66D4")
CYAN = colors.HexColor("#59C6F2")
MINT = colors.HexColor("#56E0B1")
INK = colors.HexColor("#152338")
MUTED = colors.HexColor("#52647B")
PALE = colors.HexColor("#F3F8FC")
LINE = colors.HexColor("#D8E6F0")
WHITE = colors.white


def P(text, style):
    return Paragraph(text, style)


def section_label(number, title, styles):
    badge = Table(
        [[P(number, styles["badge"])]],
        colWidths=[8 * mm],
        rowHeights=[8 * mm],
        style=TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), BLUE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("BOX", (0, 0), (-1, -1), 0, BLUE),
            ]
        ),
    )
    return Table(
        [[badge, P(title, styles["h2"])]],
        colWidths=[11 * mm, 158 * mm],
        style=TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        ),
    )


def bullet(text, styles, accent=BLUE):
    dot = Table(
        [[""]],
        colWidths=[2.4 * mm],
        rowHeights=[2.4 * mm],
        style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), accent)]),
    )
    return Table(
        [[dot, P(text, styles["body"])]],
        colWidths=[5 * mm, 164 * mm],
        style=TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 1.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        ),
    )


def card(title, body, styles, accent=CYAN, width=82 * mm):
    data = [[P(title, styles["card_title"])], [P(body, styles["card_body"])]]
    return Table(
        data,
        colWidths=[width],
        style=TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PALE),
                ("BOX", (0, 0), (-1, -1), 0.7, LINE),
                ("LINEBEFORE", (0, 0), (0, -1), 3, accent),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, 0), 7),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
                ("TOPPADDING", (0, 1), (-1, 1), 2),
                ("BOTTOMPADDING", (0, 1), (-1, 1), 8),
            ]
        ),
    )


def draw_page(canvas, doc):
    w, h = A4
    canvas.saveState()
    canvas.setFillColor(NAVY)
    canvas.rect(0, h - 10 * mm, w, 10 * mm, fill=1, stroke=0)
    canvas.setFillColor(CYAN)
    canvas.rect(0, h - 10 * mm, 3.5 * mm, 10 * mm, fill=1, stroke=0)
    canvas.setFillColor(MINT)
    canvas.circle(w - 18 * mm, h - 5 * mm, 1.5 * mm, fill=1, stroke=0)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.setFillColor(WHITE)
    canvas.drawString(18 * mm, h - 6.5 * mm, "PROSIGHT AI  /  PROJECT PROPOSAL")
    canvas.setStrokeColor(LINE)
    canvas.line(18 * mm, 14 * mm, w - 18 * mm, 14 * mm)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, 9.5 * mm, "Submission 1  |  Construction Project Intelligence")
    canvas.drawRightString(w - 18 * mm, 9.5 * mm, f"PAGE {doc.page}")
    canvas.restoreState()


def build_styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "Title",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=26,
            leading=29,
            textColor=NAVY,
            alignment=TA_LEFT,
            spaceAfter=5,
        ),
        "subtitle": ParagraphStyle(
            "Subtitle",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=11.5,
            leading=16,
            textColor=MUTED,
            spaceAfter=10,
        ),
        "kicker": ParagraphStyle(
            "Kicker",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            textColor=BLUE,
            spaceAfter=6,
        ),
        "h2": ParagraphStyle(
            "H2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=16,
            textColor=NAVY,
            spaceAfter=0,
        ),
        "badge": ParagraphStyle(
            "Badge",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=9,
            textColor=WHITE,
            alignment=TA_CENTER,
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9.2,
            leading=13.2,
            textColor=INK,
            spaceAfter=5,
        ),
        "body_small": ParagraphStyle(
            "BodySmall",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=8.4,
            leading=11.6,
            textColor=INK,
        ),
        "card_title": ParagraphStyle(
            "CardTitle",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9.2,
            leading=11,
            textColor=NAVY,
        ),
        "card_body": ParagraphStyle(
            "CardBody",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8.2,
            leading=11,
            textColor=MUTED,
        ),
        "flow_num": ParagraphStyle(
            "FlowNum",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=9,
            textColor=WHITE,
            alignment=TA_CENTER,
        ),
        "flow_title": ParagraphStyle(
            "FlowTitle",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.8,
            leading=9.5,
            textColor=NAVY,
            alignment=TA_CENTER,
        ),
        "flow_body": ParagraphStyle(
            "FlowBody",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=7.2,
            leading=9.1,
            textColor=MUTED,
            alignment=TA_CENTER,
        ),
        "callout": ParagraphStyle(
            "Callout",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=14,
            textColor=WHITE,
            alignment=TA_LEFT,
        ),
    }


def flow_step(number, title, body, styles):
    badge = Table(
        [[P(str(number), styles["flow_num"])]],
        colWidths=[7 * mm],
        rowHeights=[7 * mm],
        style=TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), BLUE if number < 4 else CYAN),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ]
        ),
    )
    return Table(
        [[badge], [P(title, styles["flow_title"])], [P(body, styles["flow_body"])]],
        colWidths=[39 * mm],
        style=TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        ),
    )


def build_pdf():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    styles = build_styles()
    doc = BaseDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title="ProSight AI Project Submission Report",
        author="ProSight AI Project Team",
        subject="Submission 1 project proposal",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="main")
    doc.addPageTemplates([PageTemplate(id="proposal", frames=[frame], onPage=draw_page)])

    story = []
    story += [
        P("SUBMISSION 1  /  PROJECT PROPOSAL", styles["kicker"]),
        P("ProSight AI Project Submission Report", styles["title"]),
        P(
            "A governed, multi-agent construction intelligence platform that turns project data and uploaded evidence into fast, role-aware, cited answers.",
            styles["subtitle"],
        ),
    ]

    summary = Table(
        [
            [P("PROJECT DOMAIN", styles["card_title"]), P("PRIMARY USERS", styles["card_title"]), P("PROTOTYPE OUTPUT", styles["card_title"])],
            [P("Construction portfolio management", styles["card_body"]), P("Executives, project managers, planners and admins", styles["card_body"]), P("React command center with an AI project assistant", styles["card_body"])],
        ],
        colWidths=[56 * mm, 56 * mm, 56 * mm],
        style=TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PALE),
                ("BOX", (0, 0), (-1, -1), 0.7, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        ),
    )
    story += [summary, Spacer(1, 8 * mm)]

    story += [section_label("1", "Activity  Define the project concept objectives and approach", styles), Spacer(1, 3 * mm)]
    story += [
        P(
            "<b>Concept.</b> ProSight AI is a manager-style assistant for completed, active and future construction projects. It gives decision-makers one conversational entry point to structured portfolio records and approved project documents. Instead of searching across spreadsheets, reports and directories, a user asks a natural-language question and receives a concise response with its evidence source.",
            styles["body"],
        ),
        P("<b>Objectives</b>", styles["card_title"]),
        bullet("Reduce the time required to find project status, delay, progress, contacts, activities, manpower, equipment, milestones and commercial signals.", styles),
        bullet("Improve trust through project-scoped retrieval, page-level document citations, data freshness and clear not-found responses.", styles, MINT),
        bullet("Protect sensitive information with role-based access, field-level masking, approval gates and privacy-safe audit logs.", styles),
        bullet("Demonstrate how a governed AI team can support decisions without allowing the language model to access or modify databases directly.", styles, MINT),
        Spacer(1, 2 * mm),
        P("<b>Approach.</b> Build a working web prototype around a governed multi-agent workflow. Structured questions use narrow database tools; narrative questions use retrieval-augmented generation over approved PDFs. An orchestrator selects the route, specialist agents return bounded facts or evidence, and a writer agent produces the final cited answer. Excel and PDF uploads enter a validation and Admin-approval workflow before they can affect the system.", styles["body"]),
    ]

    story += [Spacer(1, 3 * mm)]
    two_cards = Table(
        [[
            card("Problem being solved", "Construction information is fragmented across schedules, progress files, reports and contact lists. Manual lookup is slow, and ungoverned AI can mix projects or expose restricted data.", styles),
            card("Proposed value", "A single, traceable interface answers operational questions quickly while preserving project boundaries, approval controls and human accountability.", styles, MINT),
        ]],
        colWidths=[84 * mm, 84 * mm],
        style=TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]),
    )
    story += [two_cards, PageBreak()]

    story += [P("IMPLEMENTATION AND SHOWCASE", styles["kicker"])]
    story += [section_label("2", "No Code Low Code  Decide the idea concept and how it will be showcased", styles), Spacer(1, 3 * mm)]
    story += [
        P(
            "The concept is presented as a low-friction business experience even though the prototype has a coded backend. End users do not configure models or write queries: they select a project context, choose a guided prompt or ask a question in plain language. The command center displays portfolio health, schedule risk, manpower, invoices and approved evidence in a responsive interface.",
            styles["body"],
        ),
        P("<b>Showcase plan</b>", styles["card_title"]),
    ]
    demo_steps = [
        ("1", "Portfolio view", "Open the dashboard and identify delayed or under-performing active projects."),
        ("2", "Natural-language query", "Ask why a selected project is delayed and show its current activities or manpower."),
        ("3", "Evidence and controls", "Expand sources, switch user roles to show contact masking, and upload a PDF or Excel file for review."),
        ("4", "Approval outcome", "Approve the staged item as Admin, then demonstrate that approved evidence becomes available to the assistant."),
    ]
    story += [
        Table(
            [[card(t, b, styles, BLUE if i % 2 == 0 else MINT, 82 * mm) for i, (n, t, b) in enumerate(demo_steps[:2])],
             [card(t, b, styles, BLUE if i % 2 == 0 else MINT, 82 * mm) for i, (n, t, b) in enumerate(demo_steps[2:], start=2)]],
            colWidths=[84 * mm, 84 * mm],
            style=TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]),
        ),
        Spacer(1, 5 * mm),
    ]

    story += [section_label("3", "LLM API ML Path  Choose the model and plan its integration", styles), Spacer(1, 3 * mm)]
    story += [
        P(
            "<b>Model and API choice.</b> The prototype uses OpenAI <b>gpt-5.6-luna</b> for orchestration and answer synthesis through the OpenAI Agents SDK, with <b>text-embedding-3-small</b> for document embeddings. FastAPI exposes typed application endpoints; Chroma stores project-filtered vectors; SQLite stores governed prototype data, workflow state and audit events. A deterministic local mode supports offline testing without model calls.",
            styles["body"],
        ),
    ]

    flow = Table(
        [[
            flow_step(1, "ORCHESTRATOR", "Classifies intent and selects bounded tools.", styles),
            flow_step(2, "DATABASE + RAG", "Retrieves authorized facts and project-scoped evidence.", styles),
            flow_step(3, "WRITER", "Synthesizes only from returned context.", styles),
            flow_step(4, "CITED RESPONSE", "Returns an answer, sources and request trace.", styles),
        ]],
        colWidths=[42 * mm] * 4,
        style=TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PALE),
                ("BOX", (0, 0), (-1, -1), 0.7, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        ),
    )
    story += [flow, Spacer(1, 4 * mm)]
    story += [
        P("<b>Integration safeguards.</b> The model never connects directly to project databases. Authorization is applied before retrieval; every document search is filtered by project code; specialists cannot call one another; the writer is the only agent that produces user-facing prose; and imports remain staged until Admin approval. Production evolution will replace local adapters with SSO, PostgreSQL, object storage and a durable job queue while preserving the same tool contracts.", styles["body_small"]),
        Spacer(1, 4 * mm),
        section_label("4", "Deliverable  Submission 1", styles),
        Spacer(1, 3 * mm),
    ]
    callout = Table(
        [[P("A two-page PDF proposal defining the ProSight AI concept, objectives, showcase approach, model/API selection and integration plan.", styles["callout"]) ]],
        colWidths=[168 * mm],
        style=TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), NAVY),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        ),
    )
    story += [callout, Spacer(1, 2 * mm), P("<b>Collection method:</b> Submit as a PDF.", styles["body_small"])]

    doc.build(story)
    print(OUTPUT.name)


if __name__ == "__main__":
    build_pdf()
