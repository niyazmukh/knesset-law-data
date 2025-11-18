import logging
import os
from typing import List

import config

logging.getLogger("pytesseract").setLevel(logging.WARNING)
log = logging.getLogger(__name__)


def _configure_tools():
    try:
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = config.TESSERACT_CMD
    except Exception as e:
        log.error(f"Tesseract config error: {e}")


def _text_extract_first(pdf_path: str) -> str:
    # Try pypdf first, fallback silently to empty on errors
    try:
        from pypdf import PdfReader

        reader = PdfReader(pdf_path)
        parts = []
        for page in reader.pages:
            txt = page.extract_text() or ""
            if txt:
                parts.append(txt)
        return "\n".join(parts)
    except Exception:
        return ""


def _convert_to_images(pdf_path: str, out_folder: str) -> List[str]:
    from pdf2image import convert_from_path

    base = os.path.splitext(os.path.basename(pdf_path))[0]
    dest = os.path.join(out_folder, base)
    os.makedirs(dest, exist_ok=True)
    images = convert_from_path(pdf_path, dpi=config.OCR_DPI, poppler_path=config.POPPLER_BIN)
    out_files: List[str] = []
    for i, img in enumerate(images, start=1):
        out_file = os.path.join(dest, f"{base}_page_{i}.png")
        img.save(out_file, "PNG")
        out_files.append(out_file)
    return out_files


def _preprocess_image(path: str):
    from PIL import Image, ImageFilter

    im = Image.open(path)
    im = im.convert("L")
    im = im.point(lambda x: 0 if x < 128 else 255, "1")
    im = im.filter(ImageFilter.MedianFilter())
    return im


def _ocr_image(path: str) -> str:
    import pytesseract

    im = _preprocess_image(path)
    return pytesseract.image_to_string(im, lang=config.TESSERACT_LANG)


def ocr_pdf(pdf_path: str, out_text_path: str):
    # Text-first
    txt = _text_extract_first(pdf_path)
    if len(txt.strip()) >= config.TEXT_FIRST_MIN_CHARS:
        with open(out_text_path, "w", encoding="utf-8") as f:
            f.write(txt)
        log.info(f"Direct text extracted for {pdf_path}")
        return

    # Fallback to OCR
    img_files = _convert_to_images(pdf_path, config.IMAGE_DIR)
    buf = []
    for img in img_files:
        buf.append(_ocr_image(img))
    with open(out_text_path, "w", encoding="utf-8") as f:
        f.write("\n".join(buf))
    log.info(f"OCR completed for {pdf_path}")


def run_ocr_on_dir(pdf_dir: str):
    _configure_tools()
    os.makedirs(config.OCR_TEXT_DIR, exist_ok=True)
    files = [f for f in os.listdir(pdf_dir) if f.lower().endswith(".pdf")]
    for name in files:
        p = os.path.join(pdf_dir, name)
        out = os.path.join(config.OCR_TEXT_DIR, os.path.splitext(name)[0] + ".txt")
        if os.path.exists(out):
            continue
        try:
            ocr_pdf(p, out)
        except Exception as e:
            log.error(f"OCR failed for {p}: {e}")

