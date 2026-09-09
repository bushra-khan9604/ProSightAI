from __future__ import annotations

import hashlib
import shutil
import zipfile
from pathlib import Path
from lxml import etree as ET


SOURCE = Path(r"C:\Users\Bushra Zareen\Downloads\1735881528566-633f5eef-04e7-4ca6-902d-737ea647ee52__community_file.docx")
ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "documents" / "ProSight_AI_Day_1_Idea_Submission.docx"
EXPECTED_SHA256 = "5947c057e78789e7df2fa67f2da7381972e5d52482a1d08475ec70b6ef2553e2"

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML = "http://www.w3.org/XML/1998/namespace"
NS = {"w": W}


RESPONSES = {
    2: "ProSight AI",
    3: "Governed Multi-Agent Construction Project Intelligence",
    6: (
        "ProSight AI is a manager-style assistant for completed, active, and future construction projects. "
        "It brings structured project records and approved documents into one conversational workspace so users can "
        "find reliable information without searching across spreadsheets, reports, and contact lists."
    ),
    7: (
        "The project addresses slow information retrieval, disconnected data, unclear document provenance, and the risk "
        "of exposing sensitive project information through ungoverned AI tools."
    ),
    8: "",
    11: (
        "Primary users are executives, project managers, planning engineers, project engineers, and administrators in "
        "construction organizations."
    ),
    12: (
        "They need quick visibility into portfolio health, schedule delay, progress, manpower, equipment, milestones, "
        "contacts, invoices, and evidence from the latest approved reports."
    ),
    13: "",
    16: (
        "1. Portfolio command center for completed, active, and future projects.\n"
        "2. Natural-language assistant for project health, schedules, resources, contacts, and commercial signals.\n"
        "3. Project-scoped PDF retrieval with page-level source citations.\n"
        "4. Role-based access, contact masking, and privacy-safe request logging.\n"
        "5. PDF and Excel upload workflows with validation and Admin approval before use."
    ),
    17: "",
    18: "",
    21: (
        "A React and FastAPI application connects to a governed gpt-5.6-luna multi-agent workflow. Project-filtered Chroma "
        "RAG uses text-embedding-3-small, while SQLite and narrow authorized tools manage structured prototype data."
    ),
    22: "",
    23: "",
    26: (
        "Risks include outdated data, hallucination, cross-project leakage, restricted information, and API availability. "
        "Validation, Admin approval, project filters, role-based access, citations, audit logs, and offline tests reduce them."
    ),
    27: "",
    28: "",
    31: (
        "Submit this completed template as a PDF, supported by a short live demo or recording of the dashboard, role-aware "
        "assistant, cited answers, and upload approval workflow."
    ),
    32: "",
    33: "",
    36: (
        "A working prototype that answers construction project questions faster, identifies delivery and resource risks, "
        "and shows its evidence while remaining project-scoped, role-aware, and human-controlled."
    ),
    37: "",
    38: "",
    41: (
        "The prototype uses fictional sample data. Production evolution would add company SSO, PostgreSQL, object storage, "
        "durable jobs, source connectors, and formal accuracy and security evaluation."
    ),
    42: "",
    43: "",
}


def set_paragraph_text(paragraph: ET.Element, text: str) -> None:
    paragraph_properties = paragraph.find(f"{{{W}}}pPr")
    for child in list(paragraph):
        if child is not paragraph_properties:
            paragraph.remove(child)
    if not text:
        if paragraph_properties is None:
            paragraph_properties = ET.Element(f"{{{W}}}pPr")
            paragraph.insert(0, paragraph_properties)
        spacing = paragraph_properties.find(f"{{{W}}}spacing")
        if spacing is None:
            spacing = ET.SubElement(paragraph_properties, f"{{{W}}}spacing")
        spacing.set(f"{{{W}}}before", "0")
        spacing.set(f"{{{W}}}after", "0")
        spacing.set(f"{{{W}}}line", "1")
        spacing.set(f"{{{W}}}lineRule", "exact")
        return

    run = ET.SubElement(paragraph, f"{{{W}}}r")
    lines = text.split("\n")
    for index, line in enumerate(lines):
        if index:
            ET.SubElement(run, f"{{{W}}}br")
        node = ET.SubElement(run, f"{{{W}}}t")
        if line.startswith(" ") or line.endswith(" "):
            node.set(f"{{{XML}}}space", "preserve")
        node.text = line


def build() -> None:
    if hashlib.sha256(SOURCE.read_bytes()).hexdigest() != EXPECTED_SHA256:
        raise RuntimeError("The source template has changed; refresh the template contract before editing.")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE, OUTPUT)

    with zipfile.ZipFile(SOURCE, "r") as source_zip:
        entries = [(info, source_zip.read(info.filename)) for info in source_zip.infolist()]

    document_bytes = dict((info.filename, data) for info, data in entries)["word/document.xml"]
    root = ET.fromstring(document_bytes)
    body = root.find("w:body", NS)
    paragraphs = body.findall("w:p", NS)
    if len(paragraphs) != 44:
        raise RuntimeError(f"Unexpected paragraph count: {len(paragraphs)}")
    for index, value in RESPONSES.items():
        set_paragraph_text(paragraphs[index], value)
    updated_document = ET.tostring(root, encoding="UTF-8", xml_declaration=True, standalone=True)

    with zipfile.ZipFile(OUTPUT, "w") as target_zip:
        for info, data in entries:
            target_zip.writestr(info, updated_document if info.filename == "word/document.xml" else data)

    with zipfile.ZipFile(SOURCE) as a, zipfile.ZipFile(OUTPUT) as b:
        preserve_parts = set(a.namelist()) - {"word/document.xml"}
        changed = [name for name in preserve_parts if a.read(name) != b.read(name)]
        if changed:
            raise RuntimeError(f"Preserve-only package parts changed: {changed}")

    print(OUTPUT.name)


if __name__ == "__main__":
    build()
