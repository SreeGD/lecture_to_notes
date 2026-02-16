"""
PDF Generation Tool: Convert Markdown to styled PDF.

Renders enriched lecture notes as publication-ready PDF with Unicode
font support (DejaVu for IAST diacritics), Vaishnava colour scheme,
tables, code blocks, blockquotes, and a parameterised title page.
Pure function + BaseTool wrapper pattern.
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Optional

try:
    from crewai.tools import BaseTool
except ImportError:
    from pydantic import BaseModel as BaseTool  # type: ignore[assignment]

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Check for fpdf2
try:
    from fpdf import FPDF
    HAS_FPDF = True
except ImportError:
    HAS_FPDF = False
    FPDF = None  # type: ignore[assignment,misc]

# ---------------------------------------------------------------------------
# Colour palette (Vaishnava theme)
# ---------------------------------------------------------------------------

DARK_RED = (139, 0, 0)
GOLD = (180, 150, 50)
DARK_BROWN = (74, 14, 14)
MED_BROWN = (92, 51, 23)
BLACK = (26, 26, 26)
GREY = (100, 100, 100)
WHITE = (255, 255, 255)
CREAM = (250, 248, 242)
LIGHT_GOLD = (255, 248, 220)
TABLE_HEADER_BG = (139, 0, 0)
TABLE_ALT_BG = (250, 248, 242)


# ---------------------------------------------------------------------------
# Font discovery
# ---------------------------------------------------------------------------

def _find_fonts_dir() -> Optional[Path]:
    """Locate the DejaVu fonts directory.

    Search order:
    1. Package resources: src/lecture_agents/resources/fonts/
    2. Fallback: output/fonts/ (legacy location)
    """
    # Package resources (relative to this file)
    pkg_fonts = Path(__file__).resolve().parent.parent / "resources" / "fonts"
    if pkg_fonts.is_dir() and (pkg_fonts / "DejaVuSans.ttf").exists():
        return pkg_fonts

    # Legacy fallback
    legacy = Path("output") / "fonts"
    if legacy.is_dir() and (legacy / "DejaVuSans.ttf").exists():
        return legacy

    return None


# ---------------------------------------------------------------------------
# Custom PDF class
# ---------------------------------------------------------------------------

if HAS_FPDF:
    class EnrichedNotesPDF(FPDF):
        """Custom PDF with headers, footers, and styled markdown rendering."""

        def __init__(
            self,
            title: str = "Lecture Notes",
            orientation: str = "P",
            page_format: str = "A4",
            margin_mm: int = 18,
        ):
            super().__init__(orientation=orientation, unit="mm", format=page_format)
            self.set_auto_page_break(auto=True, margin=20)
            self.set_margins(margin_mm, margin_mm, margin_mm)
            self._book_title = title

            # Register Unicode fonts for IAST diacriticals
            fonts_dir = _find_fonts_dir()
            if fonts_dir:
                self.add_font("DejaVu", "", str(fonts_dir / "DejaVuSans.ttf"))
                self.add_font("DejaVu", "B", str(fonts_dir / "DejaVuSans-Bold.ttf"))
                self.add_font("DejaVu", "I", str(fonts_dir / "DejaVuSans-Oblique.ttf"))
                self.add_font("DejaVu", "BI", str(fonts_dir / "DejaVuSans-BoldOblique.ttf"))
                self.add_font("DejaVuMono", "", str(fonts_dir / "DejaVuSansMono.ttf"))
                self.default_font = "DejaVu"
                self.mono_font = "DejaVuMono"
            else:
                logger.warning("DejaVu fonts not found; using Helvetica (IAST may not render)")
                self.default_font = "Helvetica"
                self.mono_font = "Courier"

        def header(self):
            if self.page_no() > 1:
                self.set_font(self.default_font, "I", 7)
                self.set_text_color(*GREY)
                header_text = self._book_title
                if len(header_text) > 80:
                    header_text = header_text[:77] + "..."
                self.cell(0, 6, header_text, align="C")
                self.ln(2)
                self.set_draw_color(*GOLD)
                self.set_line_width(0.3)
                self.line(18, self.get_y(), self.w - 18, self.get_y())
                self.ln(4)

        def footer(self):
            self.set_y(-15)
            self.set_font(self.default_font, "I", 8)
            self.set_text_color(*GREY)
            self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")


# ---------------------------------------------------------------------------
# Markdown parser
# ---------------------------------------------------------------------------

def parse_markdown(md_text: str) -> list[dict]:
    """Parse markdown into a list of block elements for rendering."""
    blocks: list[dict] = []
    lines = md_text.split("\n")
    i = 0

    while i < len(lines):
        prev_i = i  # Safety: track position to detect stalls
        line = lines[i]

        # Separator lines
        if re.match(r"^={3,}$", line.strip()) or re.match(r"^-{3,}$", line.strip()):
            blocks.append({"type": "hr"})
            i += 1
            continue

        # Headings
        m = re.match(r"^(#{1,4})\s+(.*)", line)
        if m:
            level = len(m.group(1))
            blocks.append({"type": f"h{level}", "text": m.group(2).strip()})
            i += 1
            continue

        # Fenced code blocks
        if line.strip().startswith("```"):
            code_lines: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            if i < len(lines):
                i += 1  # skip closing ```
            blocks.append({"type": "code", "text": "\n".join(code_lines)})
            continue

        # Tables
        if "|" in line and i + 1 < len(lines) and re.match(r"^\s*\|[-|: ]+\|\s*$", lines[i + 1]):
            table_lines: list[str] = []
            while i < len(lines) and "|" in lines[i]:
                table_lines.append(lines[i])
                i += 1
            headers = [c.strip() for c in table_lines[0].split("|") if c.strip()]
            rows = []
            for tl in table_lines[2:]:
                cells = [c.strip() for c in tl.split("|") if c.strip()]
                if cells:
                    rows.append(cells)
            blocks.append({"type": "table", "headers": headers, "rows": rows})
            continue

        # Blockquotes — only consume lines starting with ">"
        if line.strip().startswith(">"):
            quote_lines: list[str] = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote_lines.append(re.sub(r"^>\s?", "", lines[i]))
                i += 1
            blocks.append({"type": "quote", "text": " ".join(l.strip() for l in quote_lines)})
            continue

        # Indented blocks (4 spaces) — preformatted
        if line.startswith("    ") and line.strip():
            pre_lines: list[str] = []
            while i < len(lines) and (lines[i].startswith("    ") or not lines[i].strip()):
                if not lines[i].strip() and i + 1 < len(lines) and not lines[i + 1].startswith("    "):
                    break
                if not lines[i].strip() and i + 1 >= len(lines):
                    break
                pre_lines.append(lines[i][4:] if lines[i].startswith("    ") else lines[i])
                i += 1
            if not pre_lines:
                i += 1  # Ensure progress if no lines consumed
            blocks.append({"type": "code", "text": "\n".join(pre_lines)})
            continue

        # List items
        m_ul = re.match(r"^(\s*)[-*]\s+(.*)", line)
        m_ol = re.match(r"^(\s*)\d+\.\s+(.*)", line)
        if m_ul or m_ol:
            list_items: list[dict] = []
            while i < len(lines):
                um = re.match(r"^(\s*)[-*]\s+(.*)", lines[i])
                om = re.match(r"^(\s*)\d+\.\s+(.*)", lines[i])
                if um:
                    indent = len(um.group(1)) // 2
                    list_items.append({"indent": indent, "text": um.group(2), "ordered": False})
                    i += 1
                elif om:
                    indent = len(om.group(1)) // 2
                    list_items.append({"indent": indent, "text": om.group(2), "ordered": True})
                    i += 1
                elif lines[i].strip() == "":
                    i += 1
                    break
                else:
                    break
            blocks.append({"type": "list", "items": list_items})
            continue

        # Empty line
        if not line.strip():
            i += 1
            continue

        # Regular paragraph (include lines with "|" that aren't table starts)
        para_lines: list[str] = []
        while (
            i < len(lines)
            and lines[i].strip()
            and not lines[i].startswith("#")
            and not lines[i].startswith("```")
            and not lines[i].startswith(">")
            and not lines[i].startswith("    ")
            and not re.match(r"^[-*]\s+", lines[i])
            and not re.match(r"^\d+\.\s+", lines[i])
            and not re.match(r"^={3,}$", lines[i].strip())
            and not re.match(r"^-{3,}$", lines[i].strip())
        ):
            # Check if this line starts a table (has | AND next line is separator)
            if "|" in lines[i] and i + 1 < len(lines) and re.match(
                r"^\s*\|[-|: ]+\|\s*$", lines[i + 1]
            ):
                break
            para_lines.append(lines[i])
            i += 1
        if para_lines:
            blocks.append({"type": "para", "text": " ".join(para_lines)})

        # Safety valve: if no branch advanced i, force progress
        if i == prev_i:
            logger.debug("parse_markdown: skipping unmatched line %d: %r", i, lines[i][:80])
            i += 1

    return blocks


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def strip_md_formatting(text: str) -> str:
    """Remove markdown bold/italic markers for plain text rendering."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"_(.+?)_", r"\1", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)
    return text


def _render_rich_text(pdf, text: str, font_size: float = 10):
    """Render text with **bold** and *italic* via fpdf2 write_html."""
    html = text
    html = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html)
    html = re.sub(r"\*(.+?)\*", r"<i>\1</i>", html)
    html = re.sub(r"`(.+?)`", r"<b>\1</b>", html)
    html = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2">\1</a>', html)
    html = html.replace("- [x]", "☑").replace("- [ ]", "☐")

    pdf.set_font(pdf.default_font, "", font_size)
    pdf.write_html(f'<font size="{font_size}">{html}</font>')
    pdf.ln(2)


# ---------------------------------------------------------------------------
# Table helpers (word-wrapping cells)
# ---------------------------------------------------------------------------

def _compute_col_widths(
    headers: list[str], rows: list[list[str]], n_cols: int, available: float,
) -> list[float]:
    """Compute proportional column widths based on content length."""
    # Measure max content length per column
    max_lens = [len(strip_md_formatting(h)) for h in headers]
    for row in rows:
        for j in range(min(n_cols, len(row))):
            cl = len(strip_md_formatting(row[j]))
            if j < len(max_lens):
                max_lens[j] = max(max_lens[j], cl)
            else:
                max_lens.append(cl)

    # Pad to n_cols
    while len(max_lens) < n_cols:
        max_lens.append(10)

    # For 2-column key-value tables, use fixed 30/70 split
    if n_cols == 2:
        first_max = max_lens[0]
        if first_max < 25:
            widths = [available * 0.30, available * 0.70]
            return widths

    total = sum(max_lens) or 1
    widths = [max(available * (ml / total), 20) for ml in max_lens]

    # Normalize to fit available width
    w_total = sum(widths)
    if w_total > 0:
        widths = [w * available / w_total for w in widths]
    return widths


def _measure_cell_height(pdf, text: str, col_width: float, line_h: float) -> float:
    """Estimate the height a multi_cell would need for the given text."""
    font_size = pdf.font_size
    # Approximate chars per line (font_size in pt, col_width in mm)
    char_w = font_size * 0.22  # rough mm per char at this font size
    chars_per_line = max(1, int((col_width - 2) / char_w))
    n_lines = 1
    for paragraph in text.split("\n"):
        n_lines += max(1, -(-len(paragraph) // chars_per_line))  # ceil division
    return max(line_h, n_lines * line_h)


def _render_table_row(
    pdf,
    cells: list[str],
    col_widths: list[float],
    n_cols: int,
    line_h: float,
    fill: bool = False,
    is_header: bool = False,
) -> None:
    """Render one table row with word-wrapping cells."""
    x_start = pdf.get_x()
    y_start = pdf.get_y()

    # Prepare cell texts and measure heights
    cell_texts = []
    row_height = line_h
    for j in range(n_cols):
        text = strip_md_formatting(cells[j]) if j < len(cells) else ""
        cell_texts.append(text)
        h = _measure_cell_height(pdf, text, col_widths[j], line_h)
        row_height = max(row_height, h)

    # Cap row height to avoid oversized rows
    row_height = min(row_height, 50)

    # Check page break
    if y_start + row_height > pdf.h - 20:
        pdf.add_page()
        y_start = pdf.get_y()

    # Draw cell backgrounds and borders, then render text
    for j in range(n_cols):
        x = x_start + sum(col_widths[:j])
        # Draw filled rect as cell background + border
        pdf.rect(x, y_start, col_widths[j], row_height, style="DF" if fill else "D")
        # Render text inside the cell with 1mm padding
        pdf.set_xy(x + 1, y_start + 0.5)
        pdf.multi_cell(col_widths[j] - 2, line_h, cell_texts[j])

    # Move cursor below the row
    pdf.set_xy(x_start, y_start + row_height)


# ---------------------------------------------------------------------------
# PDF renderer
# ---------------------------------------------------------------------------

def _render_blocks(blocks: list[dict], pdf) -> None:
    """Render parsed markdown blocks into the PDF."""
    for block in blocks:
        btype = block["type"]

        if btype == "hr":
            pdf.ln(3)
            y = pdf.get_y()
            pdf.set_draw_color(*GOLD)
            pdf.set_line_width(0.4)
            pdf.line(18, y, pdf.w - 18, y)
            pdf.ln(5)
            continue

        if btype == "h1":
            pdf.ln(4)
            pdf.set_font(pdf.default_font, "B", 17)
            pdf.set_text_color(*DARK_RED)
            text = strip_md_formatting(block["text"])
            pdf.multi_cell(0, 8, text)
            y = pdf.get_y()
            pdf.set_draw_color(*DARK_RED)
            pdf.set_line_width(0.6)
            pdf.line(18, y, pdf.w - 18, y)
            pdf.ln(4)
            continue

        if btype == "h2":
            pdf.ln(3)
            pdf.set_font(pdf.default_font, "B", 13)
            pdf.set_text_color(*DARK_BROWN)
            text = strip_md_formatting(block["text"])
            pdf.multi_cell(0, 7, text)
            y = pdf.get_y()
            pdf.set_draw_color(*GOLD)
            pdf.set_line_width(0.3)
            pdf.line(18, y, pdf.w - 18, y)
            pdf.ln(3)
            continue

        if btype == "h3":
            pdf.ln(2)
            pdf.set_font(pdf.default_font, "B", 11)
            pdf.set_text_color(*MED_BROWN)
            text = strip_md_formatting(block["text"])
            pdf.multi_cell(0, 6, text)
            pdf.ln(2)
            continue

        if btype == "h4":
            pdf.ln(1)
            pdf.set_font(pdf.default_font, "BI", 10)
            pdf.set_text_color(*MED_BROWN)
            text = strip_md_formatting(block["text"])
            pdf.multi_cell(0, 6, text)
            pdf.ln(1)
            continue

        if btype == "quote":
            pdf.ln(2)
            x0 = pdf.get_x()
            pdf.set_font(pdf.default_font, "I", 9.5)
            pdf.set_text_color(50, 50, 50)
            text = strip_md_formatting(block["text"])
            pdf.set_x(x0 + 8)
            w = pdf.w - 18 - x0 - 8
            pdf.multi_cell(w, 5, text)
            y1 = pdf.get_y()
            # We don't know y0 exactly after multi_cell, draw left border
            pdf.set_draw_color(*GOLD)
            pdf.set_line_width(0.8)
            # approximate start based on line count
            est_lines = max(1, len(text) // 80 + 1)
            y0_est = y1 - est_lines * 5
            pdf.line(x0 + 4, y0_est, x0 + 4, y1)
            pdf.ln(2)
            continue

        if btype == "code":
            pdf.ln(2)
            x0 = pdf.get_x()
            pdf.set_font(pdf.mono_font, "", 7.5)
            pdf.set_text_color(30, 30, 30)

            text = block["text"]
            lines_count = text.count("\n") + 1
            est_height = lines_count * 3.8 + 6

            if pdf.get_y() + est_height > pdf.h - 20:
                pdf.add_page()

            start_y = pdf.get_y()
            pdf.set_x(x0 + 4)
            for code_line in text.split("\n"):
                if pdf.get_y() > pdf.h - 22:
                    pdf.add_page()
                pdf.set_x(x0 + 4)
                pdf.cell(0, 3.8, code_line, new_x="LMARGIN", new_y="NEXT")
            end_y = pdf.get_y()

            pdf.set_draw_color(200, 200, 200)
            pdf.set_line_width(0.2)
            pdf.line(x0, start_y - 1, pdf.w - 18, start_y - 1)
            pdf.line(x0, end_y + 1, pdf.w - 18, end_y + 1)
            pdf.ln(3)
            continue

        if btype == "table":
            pdf.ln(2)
            headers = block["headers"]
            rows = block["rows"]
            n_cols = len(headers)

            available = pdf.w - 36
            col_widths = _compute_col_widths(headers, rows, n_cols, available)

            line_h = 4.0  # line height within cells
            font_size = 8

            # Header row
            pdf.set_font(pdf.default_font, "B", font_size)
            pdf.set_fill_color(*TABLE_HEADER_BG)
            pdf.set_text_color(*WHITE)
            _render_table_row(
                pdf, headers, col_widths, n_cols, line_h, fill=True, is_header=True,
            )

            # Data rows
            for ri, row in enumerate(rows):
                if pdf.get_y() > pdf.h - 25:
                    pdf.add_page()
                pdf.set_font(pdf.default_font, "", font_size)
                if ri % 2 == 0:
                    pdf.set_fill_color(*TABLE_ALT_BG)
                else:
                    pdf.set_fill_color(*WHITE)
                pdf.set_text_color(*BLACK)
                _render_table_row(
                    pdf, row, col_widths, n_cols, line_h, fill=True, is_header=False,
                )

            pdf.ln(2)
            continue

        if btype == "list":
            pdf.set_text_color(*BLACK)
            for item in block["items"]:
                indent = item["indent"]
                text = strip_md_formatting(item["text"])
                bullet = "•" if not item["ordered"] else "–"
                pdf.set_font(pdf.default_font, "", 9.5)
                x_offset = 22 + indent * 6
                pdf.set_x(x_offset)
                pdf.cell(5, 5, bullet)
                pdf.set_x(x_offset + 5)
                pdf.multi_cell(pdf.w - 18 - x_offset - 5, 5, text)
            pdf.ln(1)
            continue

        if btype == "para":
            pdf.set_font(pdf.default_font, "", 10)
            pdf.set_text_color(*BLACK)
            text = strip_md_formatting(block["text"])
            pdf.multi_cell(0, 5, text)
            pdf.ln(2)
            continue


# ---------------------------------------------------------------------------
# Title page renderer
# ---------------------------------------------------------------------------

def _render_title_page(
    pdf,
    title: str,
    speaker: Optional[str] = None,
    subtitle: Optional[str] = None,
) -> None:
    """Render a styled Vaishnava title page."""
    pdf.add_page()
    pdf.ln(30)

    # Gold decorative line
    pdf.set_draw_color(*GOLD)
    pdf.set_line_width(1.0)
    pdf.line(40, pdf.get_y(), pdf.w - 40, pdf.get_y())
    pdf.ln(8)

    # Invocation
    pdf.set_font(pdf.default_font, "I", 11)
    pdf.set_text_color(*GOLD)
    pdf.cell(0, 7, "All glories to Śrī Guru and Gaurāṅga!", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 7, "All glories to Śrīla Prabhupāda!", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)

    # Title
    pdf.set_font(pdf.default_font, "B", 24)
    pdf.set_text_color(*DARK_RED)
    pdf.multi_cell(0, 12, title, align="C")
    pdf.ln(4)

    # Subtitle
    if subtitle:
        pdf.set_font(pdf.default_font, "I", 13)
        pdf.set_text_color(*DARK_BROWN)
        pdf.cell(0, 8, subtitle, align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

    pdf.ln(6)

    # Gold decorative line
    pdf.set_draw_color(*GOLD)
    pdf.set_line_width(0.5)
    pdf.line(50, pdf.get_y(), pdf.w - 50, pdf.get_y())
    pdf.ln(8)

    # Speaker info
    if speaker:
        pdf.set_font(pdf.default_font, "", 11)
        pdf.set_text_color(*BLACK)
        pdf.cell(0, 7, f"Speaker: {speaker}", align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(6)

    # Bottom decorative line
    pdf.set_draw_color(*GOLD)
    pdf.set_line_width(1.0)
    pdf.line(40, pdf.get_y(), pdf.w - 40, pdf.get_y())
    pdf.ln(10)

    # Footer note
    pdf.set_font(pdf.default_font, "I", 9)
    pdf.set_text_color(*GREY)
    pdf.cell(
        0, 6, "All scripture references verified against vedabase.io",
        align="C", new_x="LMARGIN", new_y="NEXT",
    )
    pdf.cell(
        0, 6, "Generated by the Lecture-to-Notes Pipeline",
        align="C", new_x="LMARGIN", new_y="NEXT",
    )


# ---------------------------------------------------------------------------
# Core pure function
# ---------------------------------------------------------------------------

def generate_pdf(
    markdown_text: str,
    output_path: str,
    title: str = "Lecture Notes",
    speaker: Optional[str] = None,
    subtitle: Optional[str] = None,
    include_cover: bool = True,
    page_format: str = "A4",
    margin_mm: int = 18,
) -> dict:
    """
    Generate a styled PDF from markdown text.

    Args:
        markdown_text: Complete markdown content to render.
        output_path: Destination path for the PDF file.
        title: Book title (used in header and cover page).
        speaker: Speaker name (optional, shown on cover page).
        subtitle: Subtitle (optional, shown on cover page).
        include_cover: Whether to generate a title page.
        page_format: Page format (default A4).
        margin_mm: Page margins in mm.

    Returns:
        dict with keys: pdf_path, total_pages, file_size_kb, has_cover_page,
        warnings, error.
    """
    if not HAS_FPDF:
        return {
            "pdf_path": None,
            "total_pages": 0,
            "file_size_kb": 0.0,
            "has_cover_page": False,
            "warnings": [],
            "error": "fpdf2 not installed. pip install fpdf2",
        }

    warnings: list[str] = []
    start = time.time()

    try:
        # Parse markdown
        blocks = parse_markdown(markdown_text)
        if not blocks:
            return {
                "pdf_path": None,
                "total_pages": 0,
                "file_size_kb": 0.0,
                "has_cover_page": False,
                "warnings": [],
                "error": "No content blocks parsed from markdown",
            }

        # Create PDF
        pdf = EnrichedNotesPDF(
            title=title,
            page_format=page_format,
            margin_mm=margin_mm,
        )
        pdf.alias_nb_pages()

        # Font check
        if pdf.default_font != "DejaVu":
            warnings.append("DejaVu fonts not found; IAST diacritics may not render correctly")

        # Title page
        if include_cover:
            _render_title_page(pdf, title=title, speaker=speaker, subtitle=subtitle)

        # Content
        pdf.add_page()
        _render_blocks(blocks, pdf)

        # Write PDF
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        pdf.output(str(out))

        elapsed = time.time() - start
        size_kb = out.stat().st_size / 1024

        logger.info(
            "PDF generated: %s (%.0f KB, %d pages, %.1fs)",
            out, size_kb, pdf.page_no(), elapsed,
        )

        return {
            "pdf_path": str(out.resolve()),
            "total_pages": pdf.page_no(),
            "file_size_kb": round(size_kb, 1),
            "has_cover_page": include_cover,
            "warnings": warnings,
            "error": None,
        }

    except Exception as e:
        logger.error("PDF generation failed: %s", e)
        return {
            "pdf_path": None,
            "total_pages": 0,
            "file_size_kb": 0.0,
            "has_cover_page": False,
            "warnings": warnings,
            "error": str(e),
        }


# ---------------------------------------------------------------------------
# CrewAI BaseTool wrapper
# ---------------------------------------------------------------------------


class PDFGenerateInput(BaseModel):
    markdown_text: str = Field(..., description="Markdown content to render as PDF")
    output_path: str = Field(..., description="Destination path for the PDF file")
    title: str = Field(default="Lecture Notes", description="Book title")
    speaker: Optional[str] = Field(None, description="Speaker name")


class PDFGenerateTool(BaseTool):
    name: str = "generate_pdf"
    description: str = (
        "Generate a styled PDF from markdown text with Vaishnava colour scheme, "
        "Unicode IAST diacritical support, tables, code blocks, and a title page."
    )
    args_schema: type[BaseModel] = PDFGenerateInput

    def _run(
        self,
        markdown_text: str,
        output_path: str,
        title: str = "Lecture Notes",
        speaker: Optional[str] = None,
    ) -> str:
        result = generate_pdf(
            markdown_text=markdown_text,
            output_path=output_path,
            title=title,
            speaker=speaker,
        )
        return json.dumps(result)
