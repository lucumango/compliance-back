"""Extract raw per-page text from a PDF.

Uses PyMuPDF's native text layer when present; falls back to Tesseract OCR
(Spanish) for pages that are scanned images with no text layer, such as
ley_27693.pdf and ley_30424.pdf.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import cv2
import fitz  # PyMuPDF
import numpy as np
import pytesseract
from PIL import Image

OCR_DPI = 300
MIN_NATIVE_TEXT_CHARS = 20  # below this, treat the page as scanned

# Article headers in the El Peruano scans are underlined. Those rules merge
# with the glyphs' descenders and wreck recognition, so "Artículo 3º.-" comes
# out as "lo 39.-", which loses the article boundary entirely. Detecting long
# horizontal runs and inpainting them away restores the headers. 300 DPI
# recovers more headers than 400 here; higher resolution makes the underline
# thin enough that the morphology pass leaves fragments behind.
_LINE_KERNEL_LEN = OCR_DPI // 6  # ~4mm: long enough to be a rule, not a glyph


@dataclass
class PageText:
    page_number: int  # 1-indexed
    text: str
    source: str  # "native" or "ocr"


def _remove_horizontal_rules(gray: np.ndarray) -> np.ndarray:
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 25, 15
    )
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (_LINE_KERNEL_LEN, 1))
    rules = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.dilate(rules, np.ones((3, 3), np.uint8), iterations=1)
    return cv2.inpaint(gray, mask, 3, cv2.INPAINT_TELEA)


def _ocr_page(page: fitz.Page) -> str:
    zoom = OCR_DPI / 72
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    gray = np.array(Image.open(io.BytesIO(pix.tobytes("png"))).convert("L"))
    cleaned = _remove_horizontal_rules(gray)
    # psm 3 (default) keeps the two-column gazette layout in reading order;
    # psm 6 recovers slightly more glyphs but interleaves the columns.
    return pytesseract.image_to_string(
        Image.fromarray(cleaned), lang="spa", config="--psm 3"
    )


def extract_pages(pdf_path: str) -> list[PageText]:
    doc = fitz.open(pdf_path)
    pages: list[PageText] = []
    for i, page in enumerate(doc):
        native = page.get_text()
        if len(native.strip()) >= MIN_NATIVE_TEXT_CHARS:
            pages.append(PageText(page_number=i + 1, text=native, source="native"))
        else:
            ocr_text = _ocr_page(page)
            pages.append(PageText(page_number=i + 1, text=ocr_text, source="ocr"))
    doc.close()
    return pages


def extract_full_text(pdf_path: str) -> str:
    """Concatenate page texts with form-feed separators (used for regex parsing)."""
    pages = extract_pages(pdf_path)
    return "\f".join(p.text for p in pages)


if __name__ == "__main__":
    import sys

    for path in sys.argv[1:]:
        pages = extract_pages(path)
        n_ocr = sum(1 for p in pages if p.source == "ocr")
        print(f"{path}: {len(pages)} pages, {n_ocr} via OCR")
