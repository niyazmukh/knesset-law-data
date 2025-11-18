# Knesset Data Pipeline

Scrape every public law item from the Knesset site, download each PDF with verification, OCR anything that lacks embedded text, and post-process the output into clean, tokenized Hebrew text that can be indexed downstream.

## Why this pipeline exists

- 🔁 **Idempotent at every stage** – reruns never clobber verified results.
- 🧭 **End-to-end traceability** – every PDF, OCR artifact, and text file is linked back to the source URL via timestamped manifests and a SQLite state store.
- 🧱 **Hardened scraping** – Selenium and a Puppeteer/DevTools collector share pagination logic, popup dismissal, and loop-safety signatures to survive ASP.NET postbacks.
- 🛡️ **Verified downloads** – `%PDF-` magic bytes, MIME filtering, size checks, and SHA-256 hashes prevent silent corruption.
- 🧠 **Text-first OCR** – direct PDF text extraction is preferred; Tesseract/Poppler is used only when needed, keeping throughput high and quality predictable.

## Architecture at a glance

| Stage | Script | What it does |
| --- | --- | --- |
| Scrape listings & law pages | `scraper.py` (Selenium) / `devtools_scrape.js` (Puppeteer) | Walks listing pagination, dedupes every `lawitemid=...` URL, then harvests all PDF links within each law page with in-page pagination safeguards. |
| Download PDFs | `downloader.py` + `state.py` | Streams each PDF to `*.part`, validates, hashes, records metadata in `pipeline_state.db`, and only then promotes to `downloaded_pdfs/`. |
| OCR / text extraction | `ocr_pipeline.py` | Uses `pypdf` first; falls back to Poppler → PNG conversion + Tesseract OCR, caching all intermediate page images under `ocr_images/`. |
| Post-process text | `postproc.py` | Tokenizes via `hebrew_tokenizer` and converts conservative Hebrew year tokens (5000–7000) to Gregorian equivalents; writes final text to `postproc_texts/`. |
| Orchestration | `pipeline.py` | Ensures directories exist, runs the requested stage(s), and auto-selects the latest scrape manifests when skipping straight to download/OCR/postproc. |

```text
listing pages ─► law pages ─► pdf_links_*.txt ─► downloader ─► downloaded_pdfs/
                                             │                            │
                                             └────────── state.db ◄──────┘

downloaded_pdfs/ ─► text-first extract ─┐
                                       ├─► OCR fallback ─► ocr_images/ → ocr_texts/
                                       └───────────────────────────────────────────
ocr_texts/ ─► postproc.py ─► postproc_texts/
```

## Quick start

1. **Python requirements**
   ```powershell
   pip install -r requirements.txt
   ```
2. **System dependencies**
   - Chrome or [Chrome for Testing](https://developer.chrome.com/docs/chromedriver/chrome-for-testing). Set `CHROME_BINARY` if the auto-located binary is not suitable.
   - [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) with the Hebrew language pack.
   - [Poppler](https://github.com/oschwartz10612/poppler-windows/releases) binaries for `pdf2image`.
3. **Optional Node scraper**
   ```powershell
   npm install
   ```
   `devtools_scrape.js` uses `puppeteer-core` and your Chrome binary for faster exploratory runs or selector validation.
4. **Environment overrides** (PowerShell examples):
   ```powershell
   $env:CHROME_BINARY = "C:\\Users\\you\\chrome-cft-122\\chrome-win64\\chrome.exe"
   $env:BROWSER_HEADLESS = "0"   # show UI for first-run cookie dialogs
   $env:MAX_LISTING_PAGES = "2"   # optional throttle during development
   ```
5. **Run the pipeline**
   ```powershell
   python pipeline.py all
   ```
   or stage-by-stage:
   ```powershell
   python pipeline.py scrape
   python pipeline.py download
   python pipeline.py ocr
   python pipeline.py postproc
   ```

## Data & state layout

| Path / pattern | Purpose |
| --- | --- |
| `scraped_urls_YYYY-MM-DD_HH-MM-SS.txt` | Timestamped list of every `lawitemid` page discovered during scraping. |
| `pdf_links_YYYY-MM-DD_HH-MM-SS.txt` | Timestamped list of per-law PDF URLs (input to the downloader). |
| `downloaded_pdfs/` | Canonical PDFs that passed validation; filenames are sanitized from the source URL. |
| `downloaded_pdfs.log` | Human-readable append-only log of successful downloads (legacy, optional). |
| `pipeline_state.db` | SQLite DB storing attempts, HTTP status, content-type, SHA-256, and final status per URL. |
| `ocr_images/<pdf_basename>/` | Cached PNGs produced while OCRing a PDF; retained for auditing. |
| `ocr_texts/<pdf_basename>.txt` | Raw extracted text (direct or OCR). |
| `postproc_texts/<pdf_basename>.txt` | Tokenized, lightly normalized text suitable for downstream ingestion. |

## Configuration reference

All tunables live in `config.py` and can be overridden via environment variables.

### Scraper / browser
- `CHROME_BINARY`: explicit Chrome path; falls back to Selenium Manager auto-detection.
- `BROWSER_HEADLESS`: set to `0` for visible UI, `1` for headless (default).
- `HEADLESS_MODE`: `new` or `old` to toggle Chrome’s headless flavor.
- `PAGELOAD_TIMEOUT`, `WAIT_TIMEOUT`: Selenium waits (seconds).
- `MAX_LISTING_PAGES`, `MAX_LAW_PAGES`: safety limits for pagination loops.
- `USER_AGENT`: customize if corporate networks inspect UA strings.

### Downloader
- `MAX_RETRIES`, `RETRY_BACKOFF_BASE`, `RETRY_MAX_SLEEP`: exponential retry policy.
- `REQUEST_TIMEOUT`: streaming timeout per request (seconds).
- `PDF_MIN_BYTES`: reject suspiciously small files.
- `ALLOW_CONTENT_TYPES`: whitelist of acceptable MIME types (default: PDF + OCTET-STREAM).

### Paths
- `DOWNLOAD_DIR`, `IMAGE_DIR`, `OCR_TEXT_DIR`, `POSTPROC_TEXT_DIR`, `STATE_DB`: override to relocate artifacts (e.g., to a larger volume).

### OCR
- `TESSERACT_CMD`: path to `tesseract.exe`.
- `POPPLER_BIN`: path containing `pdftoppm.exe` and friends.
- `TESSERACT_LANG`: defaults to `heb` but supports comma-separated languages.
- `OCR_DPI`: DPI passed into `pdf2image` when rasterizing pages.
- `TEXT_FIRST_MIN_CHARS`: threshold that decides whether direct extraction is “good enough” to skip OCR.

## Operational playbook

1. **Scrape**
   - Prefer `python pipeline.py scrape` so Selenium handles cookie banners and complicated pagination.
   - If Selenium is blocked, run `node devtools_scrape.js --chromeExe <chrome> --startUrl <url> --urlOut urls.txt --pdfOut pdfs.txt` to regenerate manifests, then set `pdf_file` manually or copy to the repository root.
2. **Download**
   - `pipeline.py download` automatically picks the newest `pdf_links_*.txt` and resumes where the SQLite state left off.
   - The downloader skips URLs already marked `success`; use `DELETE FROM downloads WHERE url=...` in `pipeline_state.db` to force a retry.
3. **OCR**
   - `pipeline.py ocr` touches only PDFs lacking a matching `.txt` in `ocr_texts/`.
   - Poppler + Tesseract paths may need escaping if they contain spaces; prefer short paths such as `C:\tools\tesseract\tesseract.exe`.
4. **Post-process**
   - `pipeline.py postproc` rewrites outputs deterministically, so reruns are safe and keep downstream diffs small.
5. **Monitoring**
   - Watch `downloaded_pdfs.log` and `pipeline_state.db` for repeated failures; URLs with many failed attempts usually indicate temporary Knesset outages or CAPTCHA walls.

## Troubleshooting tips

- **Chrome fails to launch**: set `BROWSER_HEADLESS=0`, verify `CHROME_BINARY`, and ensure no stale `chrome_profile/` lock files remain.
- **Pagination loops**: raise `MAX_LISTING_PAGES` only for production runs; for debugging, cap it at 1–2 so you can inspect `scraped_urls_*.txt` quickly.
- **OCR throughput**: Poppler rasterization is CPU-bound. Run OCR separately (`python pipeline.py ocr`) on a beefy machine and copy the resulting `ocr_texts/` back if necessary.
- **Poppler/Tesseract localization**: Hebrew text benefits from setting your Windows locale to UTF-8 or running `chcp 65001` before invoking the pipeline so console logs render correctly.

## Development checklist

- Keep `requirements.txt` + `package.json` in sync with the actual runtime tools you install locally.
- Use a Python 3.11 virtual environment so the `pypdf` and `pdf2image` dependencies remain isolated from the system interpreter.
- Logs and datasets live outside of version control (see `.gitignore`); treat the repo as the source of truth for code, configs, and manifests only.
- When contributing changes, run at least one small `pipeline.py scrape` + `download` cycle with `MAX_LISTING_PAGES=1` to ensure selectors and validation logic still work.

Happy scraping! ✨
