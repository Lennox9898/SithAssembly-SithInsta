"""Build the English reference PDFs after installing requirements-docs.txt."""

from __future__ import annotations

import argparse
import html
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import (
    LongTable,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
EDITION = "2026-09-06"

INK = colors.HexColor("#111113")
PAPER = colors.HexColor("#F4F0E7")
MUTED = colors.HexColor("#68645E")
RED = colors.HexColor("#D93C3C")
GRID = colors.HexColor("#D5D0C7")
PANEL = colors.HexColor("#E9E4DA")


@dataclass(frozen=True)
class PdfSpec:
    output: Path
    title: str
    subtitle: str
    source_paths: tuple[Path, ...]
    status: str
    page_size: tuple[float, float]


def _register_fonts() -> tuple[str, str, str]:
    candidates = [
        Path("C:/Windows/Fonts/aptos.ttf"),
        Path("C:/Windows/Fonts/calibri.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
    ]
    bold_candidates = [
        Path("C:/Windows/Fonts/aptos-bold.ttf"),
        Path("C:/Windows/Fonts/calibrib.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf"),
    ]
    mono_candidates = [
        Path("C:/Windows/Fonts/consola.ttf"),
        Path("C:/Windows/Fonts/cour.ttf"),
    ]

    regular = next((path for path in candidates if path.exists()), None)
    bold = next((path for path in bold_candidates if path.exists()), None)
    mono = next((path for path in mono_candidates if path.exists()), None)
    if regular and bold and mono:
        pdfmetrics.registerFont(TTFont("SithSans", str(regular)))
        pdfmetrics.registerFont(TTFont("SithSansBold", str(bold)))
        pdfmetrics.registerFont(TTFont("SithMono", str(mono)))
        return "SithSans", "SithSansBold", "SithMono"
    return "Helvetica", "Helvetica-Bold", "Courier"


BODY_FONT, BOLD_FONT, MONO_FONT = _register_fonts()


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "Body": ParagraphStyle(
            "Body",
            parent=base["BodyText"],
            fontName=BODY_FONT,
            fontSize=9.2,
            leading=13.2,
            textColor=INK,
            spaceAfter=7,
        ),
        "Lead": ParagraphStyle(
            "Lead",
            parent=base["BodyText"],
            fontName=BODY_FONT,
            fontSize=12,
            leading=17,
            textColor=INK,
            spaceAfter=12,
        ),
        "H1": ParagraphStyle(
            "H1",
            parent=base["Heading1"],
            fontName=BOLD_FONT,
            fontSize=21,
            leading=25,
            textColor=INK,
            spaceBefore=8,
            spaceAfter=12,
            keepWithNext=True,
        ),
        "H2": ParagraphStyle(
            "H2",
            parent=base["Heading2"],
            fontName=BOLD_FONT,
            fontSize=14,
            leading=18,
            textColor=RED,
            spaceBefore=11,
            spaceAfter=7,
            keepWithNext=True,
        ),
        "H3": ParagraphStyle(
            "H3",
            parent=base["Heading3"],
            fontName=BOLD_FONT,
            fontSize=10.5,
            leading=14,
            textColor=INK,
            spaceBefore=8,
            spaceAfter=5,
            keepWithNext=True,
        ),
        "Bullet": ParagraphStyle(
            "Bullet",
            parent=base["BodyText"],
            fontName=BODY_FONT,
            fontSize=8.9,
            leading=12.5,
            leftIndent=13,
            firstLineIndent=-8,
            textColor=INK,
            spaceAfter=4,
        ),
        "Quote": ParagraphStyle(
            "Quote",
            parent=base["BodyText"],
            fontName=BODY_FONT,
            fontSize=9.2,
            leading=13,
            leftIndent=12,
            borderColor=RED,
            borderWidth=0,
            borderPadding=(5, 8, 5, 10),
            backColor=PANEL,
            textColor=INK,
            spaceAfter=9,
        ),
        "Code": ParagraphStyle(
            "Code",
            parent=base["Code"],
            fontName=MONO_FONT,
            fontSize=7.8,
            leading=10.5,
            leftIndent=8,
            rightIndent=8,
            borderPadding=7,
            backColor=INK,
            textColor=PAPER,
            spaceBefore=4,
            spaceAfter=9,
        ),
        "Table": ParagraphStyle(
            "Table",
            parent=base["BodyText"],
            fontName=BODY_FONT,
            fontSize=7.1,
            leading=9.2,
            textColor=INK,
        ),
        "TableHead": ParagraphStyle(
            "TableHead",
            parent=base["BodyText"],
            fontName=BOLD_FONT,
            fontSize=7.2,
            leading=9.3,
            textColor=PAPER,
        ),
    }


STYLES = _styles()


def _inline_markdown(value: str) -> str:
    escaped = html.escape(value.strip())
    escaped = re.sub(r"\[([^]]+)]\((https?://[^)]+)\)", r'<a href="\2" color="#A72525">\1</a>', escaped)
    escaped = re.sub(r"`([^`]+)`", rf'<font name="{MONO_FONT}">\1</font>', escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", escaped)
    return escaped


def _column_widths(count: int, width: float) -> list[float]:
    ratios = {
        2: (0.28, 0.72),
        3: (0.20, 0.20, 0.60),
        4: (0.17, 0.18, 0.28, 0.37),
        5: (0.16, 0.09, 0.13, 0.29, 0.33),
    }.get(count)
    if ratios is None:
        return [width / count] * count
    return [width * ratio for ratio in ratios]


def _table(rows: list[list[str]], width: float) -> LongTable:
    column_count = max(len(row) for row in rows)
    normalized = [row + [""] * (column_count - len(row)) for row in rows]
    data = []
    for row_index, row in enumerate(normalized):
        style = STYLES["TableHead"] if row_index == 0 else STYLES["Table"]
        data.append([Paragraph(_inline_markdown(cell), style) for cell in row])

    result = LongTable(
        data,
        colWidths=_column_widths(column_count, width),
        repeatRows=1,
        hAlign="LEFT",
        splitByRow=1,
    )
    result.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), INK),
                ("BACKGROUND", (0, 1), (-1, -1), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.45, GRID),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return result


def _parse_markdown(text: str, width: float) -> list[object]:
    lines = text.replace("\r\n", "\n").split("\n")
    story: list[object] = []
    paragraph: list[str] = []
    code: list[str] = []
    in_code = False

    def flush_paragraph() -> None:
        if paragraph:
            story.append(Paragraph(_inline_markdown(" ".join(paragraph)), STYLES["Body"]))
            paragraph.clear()

    index = 0
    while index < len(lines):
        line = lines[index].rstrip()
        stripped = line.strip()

        if stripped.startswith("```"):
            flush_paragraph()
            if in_code:
                story.append(Preformatted("\n".join(code), STYLES["Code"], maxLineLength=110))
                code.clear()
            in_code = not in_code
            index += 1
            continue
        if in_code:
            code.append(line)
            index += 1
            continue
        if stripped.startswith("|") and stripped.endswith("|"):
            flush_paragraph()
            table_lines: list[str] = []
            while index < len(lines):
                candidate = lines[index].strip()
                if not (candidate.startswith("|") and candidate.endswith("|")):
                    break
                table_lines.append(candidate)
                index += 1
            rows = [[cell.strip() for cell in item.strip("|").split("|")] for item in table_lines]
            rows = [row for row in rows if not all(re.fullmatch(r":?-{3,}:?", cell) for cell in row)]
            if rows:
                story.extend([_table(rows, width), Spacer(1, 8)])
            continue
        if not stripped:
            flush_paragraph()
            index += 1
            continue
        if stripped.startswith("### "):
            flush_paragraph()
            story.append(Paragraph(_inline_markdown(stripped[4:]), STYLES["H3"]))
        elif stripped.startswith("## "):
            flush_paragraph()
            story.append(Paragraph(_inline_markdown(stripped[3:]), STYLES["H2"]))
        elif stripped.startswith("# "):
            flush_paragraph()
            story.append(Paragraph(_inline_markdown(stripped[2:]), STYLES["H1"]))
        elif stripped.startswith("> "):
            flush_paragraph()
            story.append(Paragraph(_inline_markdown(stripped[2:]), STYLES["Quote"]))
        elif stripped.startswith("- "):
            flush_paragraph()
            story.append(Paragraph(_inline_markdown(stripped[2:]), STYLES["Bullet"], bulletText="-"))
        elif re.match(r"^\d+\.\s", stripped):
            flush_paragraph()
            marker, content = stripped.split(" ", 1)
            story.append(Paragraph(_inline_markdown(content), STYLES["Bullet"], bulletText=marker))
        else:
            paragraph.append(stripped)
        index += 1

    flush_paragraph()
    if code:
        story.append(Preformatted("\n".join(code), STYLES["Code"], maxLineLength=110))
    return story


def _cover(spec: PdfSpec, width: float) -> list[object]:
    label = Paragraph(
        "SITHASSEMBLY // CONTROLLED REFERENCE",
        ParagraphStyle(
            "CoverLabel",
            fontName=BOLD_FONT,
            fontSize=9,
            leading=11,
            textColor=RED,
            spaceAfter=8,
            tracking=1.8,
        ),
    )
    title = Paragraph(
        html.escape(spec.title),
        ParagraphStyle(
            "CoverTitle",
            fontName=BOLD_FONT,
            fontSize=28,
            leading=32,
            textColor=PAPER,
            spaceAfter=10,
        ),
    )
    subtitle = Paragraph(
        html.escape(spec.subtitle),
        ParagraphStyle(
            "CoverSubtitle",
            fontName=BODY_FONT,
            fontSize=12,
            leading=17,
            textColor=colors.HexColor("#C8C2B8"),
        ),
    )
    panel = Table([[[label, title, subtitle]]], colWidths=[width])
    panel.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), INK),
                ("BOX", (0, 0), (-1, -1), 1.2, RED),
                ("LEFTPADDING", (0, 0), (-1, -1), 22),
                ("RIGHTPADDING", (0, 0), (-1, -1), 22),
                ("TOPPADDING", (0, 0), (-1, -1), 28),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 30),
            ]
        )
    )

    sources = "<br/>".join(html.escape(path.relative_to(ROOT).as_posix()) for path in spec.source_paths)
    meta = Table(
        [
            ["EDITION", EDITION],
            ["STATUS", spec.status],
            ["SOURCE", Paragraph(sources, STYLES["Table"])],
            ["CONTROL", "Repository-tracked English source"],
        ],
        colWidths=[32 * mm, width - 32 * mm],
    )
    meta.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), BOLD_FONT),
                ("FONTNAME", (1, 0), (1, 1), BODY_FONT),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("TEXTCOLOR", (0, 0), (0, -1), RED),
                ("TEXTCOLOR", (1, 0), (-1, -1), INK),
                ("LINEBELOW", (0, 0), (-1, -1), 0.5, GRID),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return [Spacer(1, 17 * mm), panel, Spacer(1, 15 * mm), meta, PageBreak()]


def _page_frame(canvas, document) -> None:
    canvas.saveState()
    page_width, page_height = document.pagesize
    canvas.setStrokeColor(RED)
    canvas.setLineWidth(1.2)
    canvas.line(document.leftMargin, page_height - 14 * mm, page_width - document.rightMargin, page_height - 14 * mm)
    canvas.setFont(BOLD_FONT, 7.2)
    canvas.setFillColor(MUTED)
    canvas.drawString(document.leftMargin, page_height - 10.5 * mm, "SITHASSEMBLY // SITHINSTA")
    canvas.setFont(MONO_FONT, 7)
    canvas.drawRightString(page_width - document.rightMargin, 9 * mm, f"PAGE {document.page}")
    canvas.setFont(BODY_FONT, 6.8)
    canvas.drawString(document.leftMargin, 9 * mm, "EVIDENCE-BOUND // HUMAN-REVIEWED")
    canvas.restoreState()


def build(spec: PdfSpec) -> None:
    document = SimpleDocTemplate(
        str(spec.output),
        pagesize=spec.page_size,
        leftMargin=17 * mm,
        rightMargin=17 * mm,
        topMargin=21 * mm,
        bottomMargin=16 * mm,
        title=spec.title,
        author="Lennox9898 / SithAssembly",
        subject=spec.subtitle,
        creator="SithAssembly reference builder",
    )
    story = _cover(spec, document.width)
    for source_index, source_path in enumerate(spec.source_paths):
        story.extend(_parse_markdown(source_path.read_text(encoding="utf-8"), document.width))
        if source_index < len(spec.source_paths) - 1:
            story.append(PageBreak())
    document.build(story, onFirstPage=_page_frame, onLaterPages=_page_frame)


def specs() -> Iterable[PdfSpec]:
    yield PdfSpec(
        output=DOCS / "Network-Intelligence-Command-Reference.pdf",
        title="Network Intelligence Command Reference",
        subtitle="The enabled, allowlisted local command surface for SithInsta casework.",
        source_paths=(DOCS / "COMMANDS.md",),
        status="Current local executor reference",
        page_size=A4,
    )
    yield PdfSpec(
        output=DOCS / "External-Stack-Evaluation-Dossier-2026-09-04.pdf",
        title="External Stack Evaluation Dossier",
        subtitle="Current-state assessment, scorecard, and bounded proof-of-concept sequence.",
        source_paths=(
            DOCS / "architecture" / "external-stack-evaluation.md",
            DOCS / "architecture" / "external-stack-scorecard.md",
            DOCS / "architecture" / "poc-plan.md",
        ),
        status="Architecture review snapshot dated 2026-09-04",
        page_size=landscape(A4),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the versioned English SithInsta reference PDFs.")
    parser.add_argument("--check", action="store_true", help="validate sources and dependencies without writing PDFs")
    options = parser.parse_args()

    selected = tuple(specs())
    for spec in selected:
        missing = [path for path in spec.source_paths if not path.is_file()]
        if missing:
            raise FileNotFoundError(f"missing PDF source files: {missing}")
    if options.check:
        print(f"validated {len(selected)} PDF specifications")
        return 0

    for spec in selected:
        build(spec)
        print(spec.output.relative_to(ROOT).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
