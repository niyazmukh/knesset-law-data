import logging
import os
import re
from typing import List, Set, Tuple

from scraper import build_driver, open_url, handle_popups


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


PDF_REGEX_WIDE = re.compile(r"\.pdf(\?|#|$)", re.IGNORECASE)
PDF_REGEX_LSR = re.compile(r"_lsr_\d{1,10}\.pdf$", re.IGNORECASE)


def unique_sample(values: Set[str], k: int = 15) -> List[str]:
    out = []
    for v in sorted(values):
        out.append(v)
        if len(out) >= k:
            break
    return out


def inspect_law_pages(law_urls: List[str], limit: int = 10) -> None:
    driver = build_driver()
    try:
        total_all = 0
        total_lsr = 0
        all_hosts: Set[str] = set()
        non_lsr_samples: Set[str] = set()
        lsr_samples: Set[str] = set()

        for url in law_urls[:limit]:
            logging.info(f"Inspecting law page: {url}")
            open_url(driver, url)
            handle_popups(driver)

            links = driver.find_elements('css selector', 'a[href$=".pdf" i], a[href*=".pdf?" i], a[href*=".pdf#" i]')
            hrefs: Set[str] = set()
            for a in links:
                try:
                    h = a.get_attribute('href')
                except Exception:
                    continue
                if not h:
                    continue
                if PDF_REGEX_WIDE.search(h):
                    hrefs.add(h)

            all_count = len(hrefs)
            lsr = {h for h in hrefs if PDF_REGEX_LSR.search(h)}
            non_lsr = hrefs - lsr

            total_all += all_count
            total_lsr += len(lsr)
            for h in hrefs:
                try:
                    host = h.split('/')[2]
                    all_hosts.add(host)
                except Exception:
                    pass
            non_lsr_samples |= set(list(non_lsr)[:5])
            lsr_samples |= set(list(lsr)[:5])

            logging.info(
                f"Found PDFs on page: all={all_count}, lsr={len(lsr)}, non_lsr={len(non_lsr)}"
            )

        logging.info("Summary across inspected pages:")
        logging.info(f"Total PDFs (wide match): {total_all}")
        logging.info(f"Total PDFs (_lsr_ filtered): {total_lsr}")
        logging.info(f"Distinct hosts: {sorted(all_hosts)}")
        logging.info("Sample _lsr_ matches:")
        for u in unique_sample(lsr_samples):
            logging.info(u)
        logging.info("Sample non-_lsr_ matches:")
        for u in unique_sample(non_lsr_samples):
            logging.info(u)
    finally:
        driver.quit()


def load_law_urls_from_latest() -> List[str]:
    # Prefer a previously scraped URLs file if present
    candidates = [f for f in os.listdir(os.getcwd()) if f.startswith('scraped_urls_') and f.endswith('.txt')]
    if not candidates:
        return []
    latest = max(candidates, key=lambda p: os.path.getctime(os.path.join(os.getcwd(), p)))
    urls: List[str] = []
    with open(latest, 'r', encoding='utf-8') as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                urls.append(ln)
    return urls


if __name__ == '__main__':
    urls = load_law_urls_from_latest()
    if not urls:
        logging.error('No scraped_urls_*.txt found. Run python pipeline.py scrape first.')
    else:
        inspect_law_pages(urls, limit=12)

