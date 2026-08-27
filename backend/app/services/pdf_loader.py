import pytesseract
from pdf2image import convert_from_path
from pypdf import PdfReader

from app.core.config import settings

if settings.tesseract_cmd:
    pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd


def _ocr_page(file_path: str, page_number: int) -> str:
    kwargs = {"first_page": page_number, "last_page": page_number, "dpi": 300}
    if settings.poppler_path:
        kwargs["poppler_path"] = settings.poppler_path

    images = convert_from_path(file_path, **kwargs)
    if not images:
        return ""
    return pytesseract.image_to_string(images[0]).strip()


def extract_text_by_page(file_path: str) -> list[dict]:
    reader = PdfReader(file_path)
    pages = []
    for i, page in enumerate(reader.pages):
        text = (page.extract_text() or "").strip()
        if not text:
            text = _ocr_page(file_path, i + 1)
        if text:
            pages.append({"page": i + 1, "text": text})
    return pages
