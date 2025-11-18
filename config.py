import os


# General
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)
HEADLESS = True if os.environ.get("BROWSER_HEADLESS", "0") == "0" else False
HEADLESS_MODE = os.environ.get("HEADLESS_MODE", "new")  # new|old
PAGELOAD_TIMEOUT = int(os.environ.get("PAGELOAD_TIMEOUT", "30"))
WAIT_TIMEOUT = int(os.environ.get("WAIT_TIMEOUT", "15"))
CHROME_BINARY = os.environ.get(
    "CHROME_BINARY",
    r"C:\\users\\niyaz\\chrome-cft-142.0.7444.162\\chrome-win64\\chrome.exe",
)

# Start URL(s)
START_URL = (
    "https://main.knesset.gov.il/Activity/Legislation/Laws/Pages/"
    "LawLaws.aspx?t=LawLaws&st=LawLawsValidity"
)

# Paths
ROOT = os.path.abspath(os.path.dirname(__file__))
DOWNLOAD_DIR = os.environ.get(
    "DOWNLOAD_DIR", os.path.join(ROOT, "downloaded_pdfs")
)
IMAGE_DIR = os.environ.get("IMAGE_DIR", os.path.join(ROOT, "ocr_images"))
OCR_TEXT_DIR = os.environ.get("OCR_TEXT_DIR", os.path.join(ROOT, "ocr_texts"))
POSTPROC_TEXT_DIR = os.environ.get(
    "POSTPROC_TEXT_DIR", os.path.join(ROOT, "postproc_texts")
)
STATE_DB = os.environ.get("STATE_DB", os.path.join(ROOT, "pipeline_state.db"))

# Link patterns
# Match any .pdf link, including those with query or hash components
# Example matches: foo.pdf, foo.pdf?ver=1, foo.pdf#anchor
PDF_HREF_REGEX = r"\.pdf(?:$|[?#])"  # case-insensitive

# Downloader
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", "5"))
RETRY_BACKOFF_BASE = float(os.environ.get("RETRY_BACKOFF_BASE", "1.5"))
RETRY_MAX_SLEEP = float(os.environ.get("RETRY_MAX_SLEEP", "30"))
REQUEST_TIMEOUT = int(os.environ.get("REQUEST_TIMEOUT", "60"))
PDF_MIN_BYTES = int(os.environ.get("PDF_MIN_BYTES", "2048"))  # reject tiny files
ALLOW_CONTENT_TYPES = {"application/pdf", "application/octet-stream"}

# OCR
TESSERACT_CMD = os.environ.get(
    "TESSERACT_CMD",
    r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe",
)
POPPLER_BIN = os.environ.get(
    "POPPLER_BIN",
    r"C:\\Games\\poppler-24.08.0\\Library\\bin",
)
TESSERACT_LANG = os.environ.get("TESSERACT_LANG", "heb")
OCR_DPI = int(os.environ.get("OCR_DPI", "300"))
TEXT_FIRST_MIN_CHARS = int(os.environ.get("TEXT_FIRST_MIN_CHARS", "200"))

# Testing / limits
MAX_LISTING_PAGES = int(os.environ.get("MAX_LISTING_PAGES", "0"))  # 0 = no limit
MAX_LAW_PAGES = int(os.environ.get("MAX_LAW_PAGES", "0"))  # 0 = no limit


def ensure_dirs():
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    os.makedirs(IMAGE_DIR, exist_ok=True)
    os.makedirs(OCR_TEXT_DIR, exist_ok=True)
    os.makedirs(POSTPROC_TEXT_DIR, exist_ok=True)
