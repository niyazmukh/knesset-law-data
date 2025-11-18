import logging
import os
import re
import hashlib
from datetime import datetime
from typing import Iterable, List, Set, Tuple

import config
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    WebDriverException,
    NoSuchElementException,
    StaleElementReferenceException,
)

"""
Note: We rely on Selenium Manager (built into Selenium 4.6+) to locate and
download a matching ChromeDriver automatically. This avoids version mismatch
issues sometimes seen with webdriver-manager on Windows.
"""


log = logging.getLogger(__name__)


def build_driver() -> webdriver.Chrome:
    def make_options(mode: str) -> Options:
        o = Options()
        o.add_argument(f"user-agent={config.USER_AGENT}")
        # Headless modes
        if config.HEADLESS:
            if mode == "new":
                o.add_argument("--headless=new")
            elif mode == "old":
                o.add_argument("--headless")
            # Common headless stability flags
            o.add_argument("--disable-gpu")
            o.add_argument("--window-size=1280,720")
            o.add_argument("--disable-software-rasterizer")
            o.add_argument("--remote-debugging-port=0")
        o.add_argument("--no-sandbox")
        o.add_argument("--disable-dev-shm-usage")
        o.add_argument("--disable-blink-features=AutomationControlled")
        o.add_experimental_option("excludeSwitches", ["enable-automation"])
        o.add_experimental_option("useAutomationExtension", False)
        o.add_argument("--disable-notifications")
        o.add_argument("--lang=he-IL")
        o.add_argument("--remote-allow-origins=*")
        # Use a dedicated user data dir to avoid profile locks
        try:
            prof = os.path.join(config.ROOT, "chrome_profile")
            os.makedirs(prof, exist_ok=True)
            o.add_argument(f"--user-data-dir={prof}")
            o.add_argument("--no-first-run")
            o.add_argument("--no-default-browser-check")
            o.add_argument("--start-maximized")
        except Exception:
            pass
        if config.CHROME_BINARY:
            o.binary_location = config.CHROME_BINARY
        return o

    # Try visible first; then old/new headless as fallbacks if visible fails
    modes = []
    if config.HEADLESS:
        modes.append("new" if config.HEADLESS_MODE == "new" else "old")
        modes.append("old" if modes[0] == "new" else "new")
        modes.append("none")
    else:
        modes.extend(["none", "old", "new"])  # prefer non-headless, then fallbacks

    last_err = None
    for mode in modes:
        try:
            opts = make_options(mode)
            # First attempt: Selenium Manager auto driver
            try:
                driver = webdriver.Chrome(options=opts)
            except Exception:
                # Fallback: webdriver-manager
                try:
                    from selenium.webdriver.chrome.service import Service
                    from webdriver_manager.chrome import ChromeDriverManager
                    service = Service(ChromeDriverManager().install())
                    driver = webdriver.Chrome(service=service, options=opts)
                except Exception as inner:
                    raise inner
            try:
                driver.execute_cdp_cmd("Network.setUserAgentOverride", {"userAgent": config.USER_AGENT})
                driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            except Exception:
                pass
            driver.set_page_load_timeout(config.PAGELOAD_TIMEOUT)
            log.info(f"Chrome started (mode={mode}, headless={config.HEADLESS}, binary={(config.CHROME_BINARY or 'auto')})")
            return driver
        except Exception as e:
            last_err = e
            log.warning(f"Chrome start failed in mode={mode}: {e}")
            continue
    # If all modes failed, raise the last error
    raise last_err if last_err else RuntimeError("Failed to start Chrome")


def _wait_ready(driver):
    WebDriverWait(driver, config.WAIT_TIMEOUT).until(
        lambda d: d.execute_script("return document.readyState") in ("interactive", "complete")
    )


def open_url(driver, url: str):
    try:
        driver.get(url)
        _wait_ready(driver)
    except WebDriverException as e:
        log.error(f"Error opening URL {url}: {e}")


def handle_popups(driver):
    # Accept cookie dialogs / simple banners
    possible_selectors = [
        "button#onetrust-accept-btn-handler",
        "button[aria-label*='accept' i]",
        "button[aria-label*='close' i]",
    ]
    for sel in possible_selectors:
        try:
            elems = driver.find_elements(By.CSS_SELECTOR, sel)
            for el in elems:
                if el.is_displayed():
                    el.click()
        except Exception:
            pass
    # Hebrew text buttons via XPath
    try:
        xp = "//button[contains(., 'מאשר') or contains(., 'אשר') or contains(., 'קבל') or contains(., 'סגור')]"
        for el in driver.find_elements(By.XPATH, xp):
            try:
                if el.is_displayed():
                    el.click()
            except Exception:
                pass
    except Exception:
        pass
    # Dismiss JS alerts if any
    try:
        WebDriverWait(driver, 2).until(EC.alert_is_present())
        alert = driver.switch_to.alert
        alert.accept()
    except Exception:
        pass


def _collect_links(driver, predicate) -> Set[str]:
    hrefs: Set[str] = set()
    try:
        links = driver.find_elements(By.TAG_NAME, "a")
        for a in links:
            try:
                href = a.get_attribute("href")
            except StaleElementReferenceException:
                continue
            if href and predicate(href):
                hrefs.add(href)
    except Exception as e:
        log.error(f"Collect links error: {e}")
    return hrefs


def _page_signature(driver) -> str:
    """A lightweight fingerprint of the current page to detect real navigation."""
    try:
        cur = driver.current_url or ""
    except Exception:
        cur = ""
    hrefs: List[str] = []
    try:
        anchors = driver.find_elements(By.TAG_NAME, "a")
        for a in anchors:
            try:
                h = a.get_attribute("href")
                if h:
                    hrefs.append(h)
            except StaleElementReferenceException:
                continue
    except Exception:
        pass
    hrefs.sort()
    m = hashlib.sha256()
    m.update(cur.encode("utf-8", errors="ignore"))
    for h in hrefs[:500]:  # cap for performance
        m.update(h.encode("utf-8", errors="ignore"))
    return m.hexdigest()


def _click_next_in_scope(driver, scope, prev_signature: str) -> Tuple[bool, str]:
    try:
        # Prefer explicit Next link by id/class within the scope
        nxt = None
        for selector in [
            "a[id*='aNextPage']:not(.disabled):not([disabled])",
            "a[id*='lnkbtnNext']:not(.disabled):not([disabled])",
        ]:
            try:
                nxt = WebDriverWait(scope, 5).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                )
                break
            except TimeoutException:
                continue
        if nxt is None:
            raise TimeoutException()
        outer = nxt.get_attribute("outerHTML") or ""
        if "disabled" in outer:
            return False, prev_signature
        nxt.click()
        try:
            WebDriverWait(driver, config.WAIT_TIMEOUT).until(lambda d: _page_signature(d) != prev_signature)
        except TimeoutException:
            return False, prev_signature
        _wait_ready(driver)
        return True, _page_signature(driver)
    except Exception:
        # Fallback: any __doPostBack anchor in scope
        try:
            pb = scope.find_element(By.XPATH, ".//a[contains(@href,'__doPostBack')]")
            pb.click()
            try:
                WebDriverWait(driver, config.WAIT_TIMEOUT).until(lambda d: _page_signature(d) != prev_signature)
            except TimeoutException:
                return False, prev_signature
            _wait_ready(driver)
            return True, _page_signature(driver)
        except Exception:
            return False, prev_signature


def _aspnet_next(driver, prev_signature: str) -> Tuple[bool, str]:
    # Prefer explicit Next link by id/class
    candidates = [
        (By.CSS_SELECTOR, "a[id*='aNextPage']:not(.disabled):not([disabled])"),
        (By.CSS_SELECTOR, "a[id*='lnkbtnNext']:not(.disabled):not([disabled])"),
        (By.XPATH, "//a[contains(@id,'lnkbtnNext') and not(contains(@class,'disabled'))]")
    ]
    for by, q in candidates:
        try:
            nxt = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((by, q)))
            outer = nxt.get_attribute("outerHTML") or ""
            if "disabled" in outer:
                return False, prev_signature
            nxt.click()
            # Wait for signature change to confirm real navigation
            try:
                WebDriverWait(driver, config.WAIT_TIMEOUT).until(lambda d: _page_signature(d) != prev_signature)
            except TimeoutException:
                return False, prev_signature
            _wait_ready(driver)
            return True, _page_signature(driver)
        except TimeoutException:
            pass
        except Exception:
            pass

    # Fallback: __doPostBack extraction (global)
    try:
        nxt = driver.find_element(By.XPATH, "//a[contains(@href,'__doPostBack')]")
        href = nxt.get_attribute("href") or ""
        m = re.search(r"__doPostBack\('([^']*)','([^']*)'\)", href)
        if m:
            event_target, event_argument = m.group(1), m.group(2)
            driver.execute_script(
                "document.getElementById('__EVENTTARGET').value = arguments[0];", event_target
            )
            driver.execute_script(
                "document.getElementById('__EVENTARGUMENT').value = arguments[0];",
                event_argument,
            )
            driver.execute_script("document.forms[0].submit();")
            # Wait for signature change
            try:
                WebDriverWait(driver, config.WAIT_TIMEOUT).until(lambda d: _page_signature(d) != prev_signature)
            except TimeoutException:
                return False, prev_signature
            _wait_ready(driver)
            return True, _page_signature(driver)
    except NoSuchElementException:
        return False, prev_signature
    except Exception:
        return False, prev_signature

    return False, prev_signature


def collect_lawitem_urls(driver, start_url: str) -> List[str]:
    seen_signatures: Set[str] = set()
    collected: Set[str] = set()
    open_url(driver, start_url)
    handle_popups(driver)

    pages = 0
    while True:
        cur_sig = _page_signature(driver)
        if cur_sig in seen_signatures:
            log.info("Listing signature repeated; stopping pagination.")
            break
        seen_signatures.add(cur_sig)

        page_links = _collect_links(driver, lambda href: "lawitemid=" in href)
        collected |= page_links
        log.info(f"Listing page collected {len(page_links)} lawitem links; total {len(collected)}")

        pages += 1
        if config.MAX_LISTING_PAGES and pages >= config.MAX_LISTING_PAGES:
            log.info(f"Reached MAX_LISTING_PAGES={config.MAX_LISTING_PAGES}; stopping.")
            break

        current_sig = _page_signature(driver)
        moved, new_sig = _aspnet_next(driver, current_sig)
        if not moved or new_sig == current_sig:
            break

    return sorted(collected)


def collect_pdf_links_from_law_page(driver) -> Set[str]:
    return _collect_links(
        driver, lambda href: bool(re.search(config.PDF_HREF_REGEX, href, re.IGNORECASE))
    )


def collect_pdfs_for_laws(driver, law_urls: Iterable[str]) -> List[str]:
    pdfs: Set[str] = set()
    for url in law_urls:
        log.info(f"Processing law page: {url}")
        open_url(driver, url)
        handle_popups(driver)

        seen_signatures: Set[str] = set()
        page_count = 0
        while True:
            cur_sig = _page_signature(driver)
            if cur_sig in seen_signatures:
                log.info("Law page signature repeated; stopping pagination.")
                break
            seen_signatures.add(cur_sig)

            cur_links = collect_pdf_links_from_law_page(driver)
            new_links = cur_links - pdfs
            if new_links:
                pdfs |= new_links
                log.info(f"Law page found {len(new_links)} new PDFs; cumulative total {len(pdfs)}")
            else:
                log.info("Law page iteration yielded no new PDFs.")

            page_count += 1
            if config.MAX_LAW_PAGES and page_count >= config.MAX_LAW_PAGES:
                log.info(f"Reached MAX_LAW_PAGES={config.MAX_LAW_PAGES}; stopping law pagination for this item.")
                break

            # Try to scope pagination to the container that holds PDFs
            moved = False
            new_sig = cur_sig
            try:
                # Pick a PDF link and use its closest reasonable container as scope
                scope = None
                pdf_el = None
                try:
                    pdf_el = driver.find_element(By.XPATH, "//a[contains(translate(@href,'PDF','pdf'),'.pdf')]")
                except Exception:
                    pdf_el = None
                if pdf_el is not None:
                    try:
                        scope = pdf_el.find_element(By.XPATH, "ancestor::*[contains(@id,'rg') or contains(@class,'RadGrid') or contains(@class,'k-grid') or contains(@class,'grid')][1]")
                    except Exception:
                        scope = None
                if scope is not None:
                    moved, new_sig = _click_next_in_scope(driver, scope, cur_sig)
            except Exception:
                pass
            if not moved:
                moved, new_sig = _aspnet_next(driver, cur_sig)
            if not moved:
                log.info("Next page navigation unavailable; stopping law pagination.")
                break
            if not new_links and new_sig in seen_signatures:
                log.info("Next page produced no new PDFs; stopping law pagination.")
                break

    return sorted(pdfs)

def run_scrape():
    """End-to-end: listing -> per-law PDFs with in-page pagination; write files."""
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    url_out = os.path.join(os.getcwd(), f"scraped_urls_{ts}.txt")
    pdf_out = os.path.join(os.getcwd(), f"pdf_links_{ts}.txt")

    driver = build_driver()
    try:
        law_urls = collect_lawitem_urls(driver, config.START_URL)
        log.info(f"Collected {len(law_urls)} unique law URLs from listings.")
        pdf_links = collect_pdfs_for_laws(driver, law_urls)
        with open(url_out, "w", encoding="utf-8") as f:
            for u in sorted(set(law_urls)):
                f.write(u + "\n")
        with open(pdf_out, "w", encoding="utf-8") as f:
            for u in sorted(set(pdf_links)):
                f.write(u + "\n")

        log.info(f"Saved law URLs to {url_out}")
        log.info(f"Saved PDF links to {pdf_out}")
        return url_out, pdf_out
    finally:
        driver.quit()
