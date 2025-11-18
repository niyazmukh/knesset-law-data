Checkpoint — 2025-11-13

Overview

- Switched scraping to a visible Chrome DevTools (Puppeteer) flow that mirrors the site UX: listing → open each lawitemid → collect and paginate PDFs → return → next listing page. Selenium remains as fallback.
- Broadened PDF matching to any .pdf (query/hash supported). Downloader continues strong verification (HTTP/type/%PDF-/min-bytes) before success.
- Default runs are visible (headless off) due to headless rendering issues observed on the site.

Codebase Map

- pipeline.py: Orchestrator. Prefers DevTools scraper; falls back to Selenium. Stages: scrape → download → ocr → postproc.
- devtools_scrape.js: Puppeteer scraper implementing the nested sequence with ASP.NET __doPostBack next, page-signature change detection, and cookie banner dismissal.
- scraper.py: Selenium alternative. Adds scoped “Next” click within the files grid and a nested traversal helper matching the DevTools flow.
- downloader.py, state.py: Atomic downloads, validations, and persistent SQLite state (pipeline_state.db).
- ocr_pipeline.py, postproc.py: Text-first extraction, OCR fallback (Tesseract/Poppler), then conservative Hebrew post-processing.
- config.py: Key settings
  - CHROME_BINARY: C:\\users\\niyaz\\chrome-cft-142.0.7444.162\\chrome-win64\\chrome.exe
  - BROWSER_HEADLESS default: 0 (visible)
  - PDF_HREF_REGEX: \\.pdf(?:$|[?#])
  - MAX_LISTING_PAGES / MAX_LAW_PAGES: 0 = no limit

Pipeline State (current)

- Full run launched in a separate cmd (visible Chrome) using DevTools scraper. Outputs:
  - scraped_urls_*.txt, pdf_links_*.txt in repo root
  - downloaded_pdfs/ (verified PDFs), pipeline_state.db (download state)
- Recent bounded probe (1 listing page, up to 2 inner pages per law) produced 30 law URLs and 742 PDF URLs; full crawl is expected to exceed 4k PDFs.

How to Run

- Full run: python pipeline.py all (visible browser). Optional bounds via MAX_LISTING_PAGES / MAX_LAW_PAGES.
- If Selenium is required and shows “data:” or SessionNotCreated, prefer the DevTools path (default) or ensure visible UI.

MCP

- chrome-devtools-mcp 0.10.1 installed for interactive inspection (optional):
  chrome-devtools-mcp --executablePath "C:\\users\\niyaz\\chrome-cft-142.0.7444.162\\chrome-win64\\chrome.exe" --isolated --viewport 1600x1000
