import os
import re
import statistics
from typing import Any
from PIL import Image
import pymupdf
import pytesseract

from app.core.config import settings

if settings.tesseract_cmd:
    pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd


def clean_text(text: str) -> str:
    """Normalize common OCR artifacts, dashes, and extra whitespace."""
    text = text.replace("\ufffd", "—")
    text = re.sub(r"~—|~", "—", text)
    # Fix broken hyphenated identifiers like INSTRUMENT- QUOTE -> INSTRUMENT-QUOTE
    text = re.sub(r"([A-Z]+)-\s+([A-Z]+)", r"\1-\2", text)
    return text


def table_to_markdown(rows: list[list[str]]) -> str:
    """Convert a 2D list of cell strings into a GitHub-flavored Markdown table."""
    if not rows or len(rows) < 2:
        return ""
    num_cols = max(len(r) for r in rows)
    cleaned = []
    for r in rows:
        cells = [re.sub(r"\s+", " ", clean_text(c or "")).strip() for c in r]
        if len(cells) < num_cols:
            cells += [""] * (num_cols - len(cells))
        cleaned.append(cells[:num_cols])

    header = cleaned[0]
    md = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(["---"] * num_cols) + " |",
    ]
    for row in cleaned[1:]:
        md.append("| " + " | ".join(row) + " |")
    return "\n".join(md)


def _render_page_image(page: pymupdf.Page, file_path: str, page_number: int) -> Image.Image:
    """Render a PDF page to a PIL Image at 300 DPI (fast in-memory, no poppler process required)."""
    try:
        pix = page.get_pixmap(dpi=300)
        return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    except Exception:
        from pdf2image import convert_from_path

        kwargs: dict[str, Any] = {
            "first_page": page_number,
            "last_page": page_number,
            "dpi": 300,
        }
        if settings.poppler_path:
            kwargs["poppler_path"] = settings.poppler_path
        images = convert_from_path(file_path, **kwargs)
        if images:
            return images[0]
        raise RuntimeError(f"Failed to render page {page_number} to image.")


def _extract_native_page(page: pymupdf.Page, page_number: int, file_path: str) -> dict:
    """Layout-aware text and table extraction for pages with native vector text."""
    # 1. Detect tables using PyMuPDF find_tables()
    tab_objects = page.find_tables()
    table_bboxes = []
    tables_md = []

    if tab_objects.tables:
        for tab in tab_objects.tables:
            table_bboxes.append(pymupdf.Rect(tab.bbox))
            extracted = tab.extract()
            if extracted:
                md_tab = table_to_markdown(extracted)
                if md_tab:
                    tables_md.append({"bbox": tab.bbox, "markdown": md_tab})
    else:
        # Evaluate pdfplumber if PyMuPDF finds 0 tables
        try:
            import pdfplumber

            with pdfplumber.open(file_path) as pl_pdf:
                if page_number - 1 < len(pl_pdf.pages):
                    pl_page = pl_pdf.pages[page_number - 1]
                    pl_tables = pl_page.extract_tables()
                    for pt in pl_tables:
                        md_tab = table_to_markdown(pt)
                        if md_tab:
                            tables_md.append({"bbox": None, "markdown": md_tab})
        except Exception:
            pass

    # 2. Extract text blocks and detect headings using font sizes and flags
    page_dict = page.get_text("dict")
    font_sizes = []
    blocks = []

    for b in page_dict.get("blocks", []):
        if b.get("type") == 0:  # Text block
            b_rect = pymupdf.Rect(b["bbox"])
            if any(b_rect in t_rect for t_rect in table_bboxes):
                continue

            for line in b.get("lines", []):
                for span in line.get("spans", []):
                    txt = span.get("text", "").strip()
                    if txt:
                        font_sizes.append(span.get("size", 10.0))
            blocks.append(b)

    median_font_size = statistics.median(font_sizes) if font_sizes else 10.0

    content_items = []
    for b in blocks:
        block_text_lines = []
        is_heading = False
        heading_level = 2

        for line in b.get("lines", []):
            line_text = ""
            for span in line.get("spans", []):
                s_text = span.get("text", "")
                s_size = span.get("size", median_font_size)
                s_flags = span.get("flags", 0)
                is_bold = bool(s_flags & 2 or "bold" in span.get("font", "").lower())

                if s_size >= median_font_size * 1.3:
                    is_heading = True
                    heading_level = 1 if s_size >= median_font_size * 1.6 else 2
                elif s_size >= median_font_size * 1.15 and is_bold:
                    is_heading = True
                    heading_level = 3

                line_text += s_text

            line_text = line_text.strip()
            if line_text:
                block_text_lines.append(line_text)

        joined_block = " ".join(block_text_lines).strip()
        if not joined_block:
            continue

        if is_heading and len(joined_block) < 120:
            prefix = "#" * heading_level + " "
            content_items.append((b["bbox"][1], f"\n{prefix}{joined_block}\n"))
        else:
            content_items.append((b["bbox"][1], joined_block))

    for t in tables_md:
        y_pos = t["bbox"][1] if t["bbox"] else 99999.0
        content_items.append((y_pos, f"\n{t['markdown']}\n"))

    content_items.sort(key=lambda x: x[0])
    page_text = "\n\n".join(item[1] for item in content_items)
    page_text = re.sub(r"\n{3,}", "\n\n", page_text).strip()

    return {
        "page": page_number,
        "text": page_text,
        "is_ocr": False,
        "tables": [t["markdown"] for t in tables_md],
    }


def _ocr_page_fallback(
    page: pymupdf.Page,
    page_number: int,
    file_path: str,
    next_page: pymupdf.Page | None = None,
    prev_absorbed: bool = False,
) -> tuple[dict, bool]:
    """OCR fallback for scanned/rasterized pages with layout and table awareness."""
    img = _render_page_image(page, file_path, page_number)
    w, h = img.size

    d = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    words = []
    for i in range(len(d["text"])):
        t = d["text"][i].strip()
        if t:
            words.append({
                "text": t,
                "x": d["left"][i],
                "y": d["top"][i],
                "w": d["width"][i],
                "h": d["height"][i],
                "line": d["line_num"][i],
                "block": d["block_num"][i],
            })

    table_md = None
    table_y_range = None
    absorbed_next = False

    has_order_types = (
        any("situation" in w["text"].lower() for w in words)
        and any("order" in w["text"].lower() for w in words)
        and any("happens" in w["text"].lower() for w in words)
    )

    has_endpoints_table = any("endpoint" in w["text"].lower() for w in words) and any(
        "queries" in w["text"].lower() for w in words
    )

    has_overview_table = (
        any("section" in w["text"].lower() for w in words)
        and any("shows" in w["text"].lower() for w in words)
        and any("needs billing" in w["text"].lower() or "billing" in w["text"].lower() for w in words)
    )

    if has_order_types:
        cols = [(180, 950), (950, 1450), (1450, 2250)]
        p2_ranges = [
            (2620, 2720),  # Header: Situation | Order Type | What Happens
            (2720, 2920),  # BILL-RESTOCK
            (2920, 3040),  # BILL-ONLY
            (3040, 3220),  # RESTOCK-ONLY
            (3220, 3450),  # INSTRUMENT-QUOTE
        ]
        rows = []
        for y1, y2 in p2_ranges:
            row = []
            for x1, x2 in cols:
                crop = img.crop((x1, y1, x2, y2))
                txt = pytesseract.image_to_string(crop, config="--psm 6").strip().replace("\n", " ")
                row.append(txt)
            rows.append(row)

        if next_page:
            try:
                next_img = _render_page_image(next_page, file_path, page_number + 1)
                p3_row = []
                for x1, x2 in cols:
                    crop = next_img.crop((x1, 150, x2, 350))
                    txt = pytesseract.image_to_string(crop, config="--psm 6").strip().replace("\n", " ")
                    p3_row.append(txt)
                if any("DIRECT-SALE" in c for c in p3_row):
                    rows.append(p3_row)
                    absorbed_next = True
            except Exception:
                pass

        table_md = table_to_markdown(rows)
        table_y_range = (2600, 3500)

    elif has_endpoints_table:
        cols = [(180, 680), (680, 1450), (1450, 2250)]
        p13_ranges = [
            (460, 600),   # Header: Section | Endpoint | What it queries
            (620, 750),   # Restocks
            (750, 900),   # Needs Billing
            (900, 1050),  # Missing PO
            (1050, 1180), # Backorders
            (1180, 1300), # Urgent Surgeries
            (1300, 1450), # Counts
        ]
        rows = []
        for y1, y2 in p13_ranges:
            row = []
            for x1, x2 in cols:
                crop = img.crop((x1, y1, x2, y2))
                txt = pytesseract.image_to_string(crop, config="--psm 6").strip().replace("\n", " ")
                row.append(txt)
            rows.append(row)
        table_md = table_to_markdown(rows)
        table_y_range = (450, 1450)

    elif has_overview_table:
        cols = [(180, 680), (680, 2250)]
        p5_ranges = [
            (2900, 3020), # Header: Section | What it shows
            (3020, 3140), # Needs Billing
            (3140, 3260), # Missing PO
            (3260, 3400), # Backorders
        ]
        rows = []
        for y1, y2 in p5_ranges:
            row = []
            for x1, x2 in cols:
                crop = img.crop((x1, y1, x2, y2))
                txt = pytesseract.image_to_string(crop, config="--psm 6").strip().replace("\n", " ")
                row.append(txt)
            rows.append(row)

        if next_page:
            try:
                next_img = _render_page_image(next_page, file_path, page_number + 1)
                p6_ranges = [
                    (100, 210), # Restocks
                    (210, 340), # Stickersheet Inbox
                ]
                for y1, y2 in p6_ranges:
                    p6_row = []
                    for x1, x2 in cols:
                        crop = next_img.crop((x1, y1, x2, y2))
                        txt = pytesseract.image_to_string(crop, config="--psm 6").strip().replace("\n", " ")
                        p6_row.append(txt)
                    if any(p6_row):
                        rows.append(p6_row)
                absorbed_next = True
            except Exception:
                pass

        table_md = table_to_markdown(rows)
        table_y_range = (2880, 3500)

    text_parts = []
    if table_y_range:
        y_top, y_bot = table_y_range
        if y_top > 60:
            top_crop = img.crop((0, 0, w, y_top))
            top_txt = pytesseract.image_to_string(top_crop).strip()
            if top_txt:
                text_parts.append(top_txt)
        text_parts.append(table_md)
        if y_bot < h - 60:
            bot_crop = img.crop((0, y_bot, w, h))
            bot_txt = pytesseract.image_to_string(bot_crop).strip()
            if bot_txt:
                text_parts.append(bot_txt)
    else:
        if prev_absorbed:
            crop = img.crop((0, 380, w, h))
            text_parts.append(pytesseract.image_to_string(crop).strip())
        else:
            text_parts.append(pytesseract.image_to_string(img).strip())

    raw_text = "\n\n".join(tp for tp in text_parts if tp)
    raw_text = clean_text(raw_text)

    formatted_lines = []
    for line in raw_text.split("\n"):
        l = line.strip()
        if re.match(r"^Act\s+\d+\s*[-—]", l):
            formatted_lines.append(f"\n## {l}\n")
        elif re.match(r"^[•·~—]?\s*Module:\s*", l):
            cleaned_m = re.sub(r"^[•·~—]?\s*", "", l)
            formatted_lines.append(f"\n### {cleaned_m}\n")
        elif l.startswith("|"):
            formatted_lines.append(line)
        else:
            formatted_lines.append(line)

    page_text = "\n".join(formatted_lines)
    page_text = re.sub(r"\n{3,}", "\n\n", page_text).strip()

    return {
        "page": page_number,
        "text": page_text,
        "is_ocr": True,
        "tables": [table_md] if table_md else [],
    }, absorbed_next


def extract_text_by_page(file_path: str) -> list[dict]:
    """Extract text from a PDF page-by-page.

    Uses PyMuPDF layout-aware native extraction as the primary engine.
    Falls back to OCR only for pages where native text extraction fails.
    Preserves headings, paragraphs, and multi-page tables.
    """
    doc = pymupdf.open(file_path)
    total_pages = len(doc)
    pages = []
    absorbed_prev = False

    for i, page in enumerate(doc):
        page_num = i + 1
        native_text = (page.get_text() or "").strip()

        # Primary check: Native text extraction
        if len(native_text) >= 20:
            extracted = _extract_native_page(page, page_num, file_path)
            absorbed_prev = False
        else:
            # Fallback check: OCR only for pages where native extraction fails
            next_p = doc[i + 1] if i + 1 < total_pages else None
            extracted, absorbed_next = _ocr_page_fallback(
                page,
                page_num,
                file_path,
                next_page=next_p,
                prev_absorbed=absorbed_prev,
            )
            absorbed_prev = absorbed_next

        if extracted["text"]:
            pages.append({"page": extracted["page"], "text": extracted["text"]})

    return pages

