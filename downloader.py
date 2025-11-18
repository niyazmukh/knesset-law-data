import hashlib
import logging
import os
import re
import shutil
import time
from datetime import datetime
from typing import Iterable, List, Tuple

import requests

import config
import state


log = logging.getLogger(__name__)


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _is_valid_pdf(path: str) -> bool:
    try:
        size = os.path.getsize(path)
        if size < config.PDF_MIN_BYTES:
            return False
        with open(path, "rb") as f:
            header = f.read(5)
        return header == b"%PDF-"
    except Exception:
        return False


def _sleep_backoff(attempt: int):
    delay = min(config.RETRY_MAX_SLEEP, (config.RETRY_BACKOFF_BASE ** attempt))
    time.sleep(delay)


def _safe_filename_from_url(url: str) -> str:
    base = os.path.basename(url.split("?", 1)[0])
    base = re.sub(r"[^A-Za-z0-9_.-]", "_", base)
    return base or ("file_" + hashlib.md5(url.encode()).hexdigest() + ".pdf")


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": config.USER_AGENT})
    return s


def download_verified(url: str, out_dir: str) -> Tuple[bool, str]:
    os.makedirs(out_dir, exist_ok=True)
    filename = _safe_filename_from_url(url)
    final_path = os.path.join(out_dir, filename)
    part_path = final_path + ".part"

    if state.is_success(url) and os.path.exists(final_path):
        log.info(f"Already verified: {final_path}")
        return True, final_path

    sess = _session()
    for attempt in range(1, config.MAX_RETRIES + 1):
        state.mark_attempt(url)
        try:
            with sess.get(url, stream=True, timeout=config.REQUEST_TIMEOUT) as r:
                status = r.status_code
                ctype = r.headers.get("Content-Type", "").split(";")[0].strip().lower()
                if status >= 400:
                    state.mark_failure(url, f"HTTP {status}", http_status=status)
                    _sleep_backoff(attempt)
                    continue
                # Validate content-type early
                if ctype and ctype not in config.ALLOW_CONTENT_TYPES:
                    # Still allow if it's missing but don't trust text/html
                    if ctype.startswith("text/"):
                        state.mark_failure(url, f"Unexpected content-type {ctype}", http_status=status)
                        _sleep_backoff(attempt)
                        continue

                with open(part_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1024 * 64):
                        if chunk:
                            f.write(chunk)

            if not _is_valid_pdf(part_path):
                try:
                    os.remove(part_path)
                except OSError:
                    pass
                state.mark_failure(url, "Downloaded file is not a valid PDF")
                _sleep_backoff(attempt)
                continue

            # Move into place and finalize
            shutil.move(part_path, final_path)
            sha = _sha256_file(final_path)
            size = os.path.getsize(final_path)
            state.mark_success(url, final_path, size, sha, ctype or "", status)
            log.info(f"Verified download: {final_path} ({size} bytes)")

            # Back-compat: append to simple log
            try:
                with open(os.path.join(os.getcwd(), "downloaded_pdfs.log"), "a", encoding="utf-8") as lf:
                    lf.write(final_path + "\n")
            except Exception:
                pass

            return True, final_path
        except requests.RequestException as e:
            state.mark_failure(url, f"Request error: {e}")
        except Exception as e:
            state.mark_failure(url, f"Unhandled error: {e}")

        _sleep_backoff(attempt)

    return False, final_path


def download_all(pdf_links: Iterable[str]) -> List[str]:
    state.init_db()
    out_paths: List[str] = []
    for i, url in enumerate(pdf_links, 1):
        ok, path = download_verified(url, config.DOWNLOAD_DIR)
        if ok:
            out_paths.append(path)
        else:
            log.error(f"Failed to download after retries: {url}")
    return out_paths

