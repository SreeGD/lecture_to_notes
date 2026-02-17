#!/usr/bin/env python3
"""Convert enriched_notes_saranagathi.md to a styled PDF using fpdf2."""

from __future__ import annotations

import re
from pathlib import Path

from fpdf import FPDF

MD_PATH = Path(__file__).parent / "enriched_notes_saranagathi.md"
PDF_PATH = Path(__file__).parent / "enriched_notes_saranagathi.pdf"

# Colours
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


class EnrichedNotesPDF(FPDF):
    """Custom PDF with headers, footers, and styled markdown rendering."""

    def __init__(self):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.set_auto_page_break(auto=True, margin=20)
        self.set_margins(18, 18, 18)
        # Register a Unicode font for IAST diacriticals
        fonts_dir = Path(__file__).parent / "fonts"
        self.add_font("DejaVu", "", str(fonts_dir / "DejaVuSans.ttf"))
        self.add_font("DejaVu", "B", str(fonts_dir / "DejaVuSans-Bold.ttf"))
        self.add_font("DejaVu", "I", str(fonts_dir / "DejaVuSans-Oblique.ttf"))
        self.add_font("DejaVu", "BI", str(fonts_dir / "DejaVuSans-BoldOblique.ttf"))
        self.add_font("DejaVuMono", "", str(fonts_dir / "DejaVuSansMono.ttf"))
        self.default_font = "DejaVu"
        self.mono_font = "DejaVuMono"

    def header(self):
        if self.page_no() > 1:
            self.set_font(self.default_font, "I", 7)
            self.set_text_color(*GREY)
            self.cell(
                0, 6,
                "Understanding the Position of Lord Śiva — SARANAGATHI Enriched Notes",
                align="C",
            )
            self.ln(2)
            # Gold rule
            self.set_draw_color(*GOLD)
            self.set_line_width(0.3)
            self.line(18, self.get_y(), self.w - 18, self.get_y())
            self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font(self.default_font, "I", 8)
        self.set_text_color(*GREY)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")


def parse_markdown(md_text: str) -> list[dict]:
    """Parse markdown into a list of block elements for rendering."""
    blocks: list[dict] = []
    lines = md_text.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]

        # Skip separator lines of === or ---
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

        # Code blocks (fenced)
        if line.strip().startswith("```"):
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1  # skip closing ```
            blocks.append({"type": "code", "text": "\n".join(code_lines)})
            continue

        # Tables
        if "|" in line and i + 1 < len(lines) and re.match(r"^\s*\|[-|: ]+\|\s*$", lines[i + 1]):
            table_lines = []
            while i < len(lines) and "|" in lines[i]:
                table_lines.append(lines[i])
                i += 1
            # Parse table
            headers = [c.strip() for c in table_lines[0].split("|") if c.strip()]
            rows = []
            for tl in table_lines[2:]:  # skip header and separator
                cells = [c.strip() for c in tl.split("|") if c.strip()]
                if cells:
                    rows.append(cells)
            blocks.append({"type": "table", "headers": headers, "rows": rows})
            continue

        # Blockquote
        if line.strip().startswith(">"):
            quote_lines = []
            while i < len(lines) and (lines[i].strip().startswith(">") or (lines[i].strip() and quote_lines)):
                quote_lines.append(re.sub(r"^>\s?", "", lines[i]))
                i += 1
                if i < len(lines) and not lines[i].strip().startswith(">") and not lines[i].strip():
                    break
            blocks.append({"type": "quote", "text": " ".join(l.strip() for l in quote_lines)})
            continue

        # Indented block (4 spaces) — treat as pre-formatted
        if line.startswith("    ") and line.strip():
            pre_lines = []
            while i < len(lines) and (lines[i].startswith("    ") or not lines[i].strip()):
                if not lines[i].strip() and i + 1 < len(lines) and not lines[i + 1].startswith("    "):
                    break
                pre_lines.append(lines[i][4:] if lines[i].startswith("    ") else lines[i])
                i += 1
            blocks.append({"type": "code", "text": "\n".join(pre_lines)})
            continue

        # List items
        m_ul = re.match(r"^(\s*)[-*]\s+(.*)", line)
        m_ol = re.match(r"^(\s*)\d+\.\s+(.*)", line)
        if m_ul or m_ol:
            list_items = []
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

        # Regular paragraph — collect consecutive non-empty lines
        para_lines = []
        while i < len(lines) and lines[i].strip() and not lines[i].startswith("#") and not lines[i].startswith("```") and not lines[i].startswith(">") and not lines[i].startswith("    ") and "|" not in lines[i] and not re.match(r"^[-*]\s+", lines[i]) and not re.match(r"^\d+\.\s+", lines[i]) and not re.match(r"^={3,}$", lines[i].strip()) and not re.match(r"^-{3,}$", lines[i].strip()):
            para_lines.append(lines[i])
            i += 1
        if para_lines:
            blocks.append({"type": "para", "text": " ".join(para_lines)})

    return blocks


def strip_md_formatting(text: str) -> str:
    """Remove markdown bold/italic markers for plain text rendering."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"_(.+?)_", r"\1", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)
    return text


def render_rich_text(pdf: EnrichedNotesPDF, text: str, font_size: float = 10):
    """Render text with **bold** and *italic* support using write_html-like approach."""
    # Simple approach: use multi_cell with markdown parsed inline
    # fpdf2 supports a subset of HTML in write_html, so let's convert
    html = text
    # Bold
    html = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html)
    # Italic
    html = re.sub(r"\*(.+?)\*", r"<i>\1</i>", html)
    # Code
    html = re.sub(r"`(.+?)`", r"<b>\1</b>", html)
    # Links - just show text
    html = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2">\1</a>', html)
    # Checkbox
    html = html.replace("- [x]", "☑").replace("- [ ]", "☐")

    pdf.set_font(pdf.default_font, "", font_size)
    pdf.write_html(f'<font size="{font_size}">{html}</font>')
    pdf.ln(2)


def render_pdf(blocks: list[dict], pdf: EnrichedNotesPDF):
    """Render parsed blocks into the PDF."""

    for block in blocks:
        btype = block["type"]

        if btype == "hr":
            y = pdf.get_y()
            pdf.set_draw_color(*GOLD)
            pdf.set_line_width(0.4)
            pdf.line(18, y, pdf.w - 18, y)
            pdf.ln(4)
            continue

        if btype == "h1":
            pdf.ln(4)
            pdf.set_font(pdf.default_font, "B", 17)
            pdf.set_text_color(*DARK_RED)
            text = strip_md_formatting(block["text"])
            pdf.multi_cell(0, 8, text)
            # Underline
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
            # Draw gold left border and cream background
            x0 = pdf.get_x()
            y0 = pdf.get_y()
            pdf.set_font(pdf.default_font, "I", 9.5)
            pdf.set_text_color(50, 50, 50)
            # Calculate height needed
            text = strip_md_formatting(block["text"])
            # Render with indent
            pdf.set_x(x0 + 8)
            w = pdf.w - 18 - x0 - 8
            pdf.multi_cell(w, 5, text)
            y1 = pdf.get_y()
            # Draw border
            pdf.set_draw_color(*GOLD)
            pdf.set_line_width(0.8)
            pdf.line(x0 + 4, y0, x0 + 4, y1)
            pdf.ln(2)
            continue

        if btype == "code":
            pdf.ln(2)
            # Background box
            x0 = pdf.get_x()
            y0 = pdf.get_y()
            pdf.set_font(pdf.mono_font, "", 7.5)
            pdf.set_text_color(30, 30, 30)

            text = block["text"]
            # Estimate height
            lines_count = text.count("\n") + 1
            est_height = lines_count * 3.8 + 6

            # Check if we need a page break
            if pdf.get_y() + est_height > pdf.h - 20:
                pdf.add_page()
                y0 = pdf.get_y()

            # Draw background
            pdf.set_fill_color(*CREAM)
            pdf.set_draw_color(200, 200, 200)
            # We'll draw after rendering to get actual height

            start_y = pdf.get_y()
            pdf.set_x(x0 + 4)
            for code_line in text.split("\n"):
                if pdf.get_y() > pdf.h - 22:
                    pdf.add_page()
                pdf.set_x(x0 + 4)
                pdf.cell(0, 3.8, code_line, new_x="LMARGIN", new_y="NEXT")
            end_y = pdf.get_y()

            # Draw background rect (behind text — we can't easily do this in fpdf2
            # without overlaying, so just add bottom border)
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

            # Calculate column widths
            available = pdf.w - 36
            col_widths = [available / n_cols] * n_cols

            # Smarter widths: if first col is short label, make it narrower
            if n_cols >= 2:
                max_first = max(len(headers[0]), max((len(r[0]) if r else 0) for r in rows) if rows else 0)
                max_others = max(
                    max(len(h) for h in headers[1:]),
                    max(max((len(c) for c in r[1:n_cols]), default=0) for r in rows) if rows else 0,
                )
                if max_first < max_others * 0.5 and n_cols <= 5:
                    col_widths[0] = available * 0.25
                    remaining = available - col_widths[0]
                    for j in range(1, n_cols):
                        col_widths[j] = remaining / (n_cols - 1)

            # Cap column widths for large tables
            if n_cols > 5:
                col_widths = [available / n_cols] * n_cols

            # Header row
            pdf.set_font(pdf.default_font, "B", 8)
            pdf.set_fill_color(*TABLE_HEADER_BG)
            pdf.set_text_color(*WHITE)
            for j, h in enumerate(headers):
                pdf.cell(col_widths[j], 6, strip_md_formatting(h)[:40], border=1, fill=True)
            pdf.ln()

            # Data rows
            pdf.set_font(pdf.default_font, "", 8)
            for ri, row in enumerate(rows):
                if pdf.get_y() > pdf.h - 22:
                    pdf.add_page()
                if ri % 2 == 0:
                    pdf.set_fill_color(*TABLE_ALT_BG)
                else:
                    pdf.set_fill_color(*WHITE)
                pdf.set_text_color(*BLACK)

                # Calculate max height for this row
                max_lines = 1
                for j in range(min(n_cols, len(row))):
                    cell_text = strip_md_formatting(row[j]) if j < len(row) else ""
                    char_width = col_widths[j] / 2.2  # rough chars per line
                    if char_width > 0:
                        lines_needed = max(1, len(cell_text) / char_width)
                        max_lines = max(max_lines, int(lines_needed) + 1)

                row_height = max(5, min(max_lines * 4.5, 25))

                for j in range(n_cols):
                    cell_text = strip_md_formatting(row[j]) if j < len(row) else ""
                    # Truncate if too long for cell
                    max_chars = int(col_widths[j] / 1.8 * (row_height / 4.5))
                    if len(cell_text) > max_chars:
                        cell_text = cell_text[:max_chars - 3] + "..."
                    pdf.cell(col_widths[j], row_height, cell_text, border=1, fill=True)
                pdf.ln()

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


def main():
    md_text = MD_PATH.read_text(encoding="utf-8")
    blocks = parse_markdown(md_text)

    pdf = EnrichedNotesPDF()
    pdf.alias_nb_pages()

    # Title page
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
    pdf.multi_cell(0, 12, "Understanding the\nPosition of Lord Śiva", align="C")
    pdf.ln(4)

    # Subtitle
    pdf.set_font(pdf.default_font, "I", 13)
    pdf.set_text_color(*DARK_BROWN)
    pdf.cell(0, 8, "Enriched Class Notes", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, "SARANAGATHI Framework v5.0", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)

    # Gold decorative line
    pdf.set_draw_color(*GOLD)
    pdf.set_line_width(0.5)
    pdf.line(50, pdf.get_y(), pdf.w - 50, pdf.get_y())
    pdf.ln(8)

    # Speaker info
    pdf.set_font(pdf.default_font, "", 11)
    pdf.set_text_color(*BLACK)
    pdf.cell(0, 7, "Speaker: His Holiness Jayadvaita Swami", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 7, "Venue: ISKCON Chowpatty, Mumbai", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 7, "Duration: ~68 minutes", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(12)

    # Bottom decorative line
    pdf.set_draw_color(*GOLD)
    pdf.set_line_width(1.0)
    pdf.line(40, pdf.get_y(), pdf.w - 40, pdf.get_y())
    pdf.ln(10)

    pdf.set_font(pdf.default_font, "I", 9)
    pdf.set_text_color(*GREY)
    pdf.cell(0, 6, "All scripture references verified against vedabase.io", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, "Generated by the Lecture-to-Book Pipeline", align="C", new_x="LMARGIN", new_y="NEXT")

    # Content pages
    pdf.add_page()

    # Skip the opening invocation lines from the markdown since we have a title page
    # Find where the real content starts (after the first invocation block)
    start_idx = 0
    for i, b in enumerate(blocks):
        if b["type"] == "h1" and "ENRICHED CLASS NOTES" in b.get("text", ""):
            start_idx = i
            break

    render_pdf(blocks[start_idx:], pdf)

    pdf.output(str(PDF_PATH))
    size_kb = PDF_PATH.stat().st_size / 1024
    print(f"PDF generated: {PDF_PATH}")
    print(f"Size: {size_kb:.0f} KB")
    print(f"Pages: {pdf.page_no()}")


if __name__ == "__main__":
    main()
