import argparse
import glob
import logging
import os
from datetime import datetime

import config
import subprocess
import sys
import shlex
from datetime import datetime
from downloader import download_all
from ocr_pipeline import run_ocr_on_dir
import postproc


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )


def latest(pattern: str) -> str:
    files = glob.glob(pattern)
    if not files:
        raise FileNotFoundError(f"No files for pattern: {pattern}")
    return max(files, key=os.path.getctime)


def run_scrape_devtools():
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    workdir = config.ROOT
    url_out = os.path.join(workdir, f"scraped_urls_{ts}.txt")
    pdf_out = os.path.join(workdir, f"pdf_links_{ts}.txt")
    node = "node"
    script = os.path.join(workdir, "devtools_scrape.js")
    args = [
        node,
        script,
        "--chromeExe", config.CHROME_BINARY,
        "--startUrl", config.START_URL,
        "--urlOut", url_out,
        "--pdfOut", pdf_out,
        "--maxListing", str(config.MAX_LISTING_PAGES),
        "--maxLaw", str(config.MAX_LAW_PAGES),
    ]
    env = os.environ.copy()
    env.setdefault("PUPPETEER_EXECUTABLE_PATH", config.CHROME_BINARY)
    logging.info("Launching DevTools scraper (Puppeteer)")
    proc = subprocess.run(args, cwd=workdir, env=env, text=True, capture_output=True)
    if proc.returncode != 0:
        logging.error(proc.stdout)
        logging.error(proc.stderr)
        raise RuntimeError("DevTools scraper failed")
    logging.info(proc.stdout.strip())
    return url_out, pdf_out


def main():
    setup_logging()
    parser = argparse.ArgumentParser(description="Knesset data pipeline")
    parser.add_argument("stage", nargs="?", default="all", choices=["all", "scrape", "download", "ocr", "postproc"], help="Stage to run")
    args = parser.parse_args()

    config.ensure_dirs()

    if args.stage in ("all", "scrape"):
        try:
            url_file, pdf_file = run_scrape_devtools()
        except Exception:
            # Fallback to Selenium-based scraper if DevTools fails
            from scraper import run_scrape as run_scrape_selenium
            logging.warning("DevTools scraper failed; falling back to Selenium.")
            url_file, pdf_file = run_scrape_selenium()
    else:
        # Best effort to pick latest inputs
        url_file = latest("scraped_urls_*.txt") if os.path.exists(os.getcwd()) else None
        pdf_file = latest("pdf_links_*.txt")

    if args.stage in ("all", "download"):
        with open(pdf_file, "r", encoding="utf-8") as f:
            links = [ln.strip() for ln in f if ln.strip()]
        download_all(links)

    if args.stage in ("all", "ocr"):
        run_ocr_on_dir(config.DOWNLOAD_DIR)

    if args.stage in ("all", "postproc"):
        postproc.postprocess_files(config.OCR_TEXT_DIR, config.POSTPROC_TEXT_DIR)


if __name__ == "__main__":
    main()
