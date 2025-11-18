import logging
import re
from urllib.parse import urlparse

import config
from scraper import build_driver, open_url, handle_popups, collect_pdf_links_from_law_page


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def main():
    driver = build_driver()
    try:
        # Validate listing page selectors
        open_url(driver, config.START_URL)
        handle_popups(driver)
        law_links = [a.get_attribute('href') for a in driver.find_elements('css selector', 'a[href*="lawitemid="]') if a.get_attribute('href')]
        logging.info(f"Listing page lawitem links found: {len(law_links)}")

        # Visit up to 3 law pages and validate PDF detection
        for href in law_links[:3]:
            open_url(driver, href)
            handle_popups(driver)
            pdfs = collect_pdf_links_from_law_page(driver)
            logging.info(f"{href} -> PDF links found: {len(pdfs)}")
    finally:
        driver.quit()


if __name__ == '__main__':
    main()

