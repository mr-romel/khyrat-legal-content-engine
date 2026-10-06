from __future__ import annotations

import base64
import re
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

OUTPUT = Path("generated/blogger/browser-state.json")
BLOGGER_POSTS_URL = "https://www.blogger.com/blog/posts"
BLOGGER_POSTS_PREFIX = "https://www.blogger.com/blog/posts"


def _page_info(page) -> tuple[str, str]:
    try:
        url = page.url
    except Exception:
        url = "<unavailable>"
    try:
        title = page.title()
    except Exception:
        title = "<unavailable>"
    return url, title


def _is_blogger_posts_url(url: str) -> bool:
    value = str(url or "")
    return value == BLOGGER_POSTS_PREFIX or value.startswith(BLOGGER_POSTS_PREFIX + "/")


def _goto_blogger_posts(page) -> None:
    try:
        page.goto(BLOGGER_POSTS_URL, wait_until="commit", timeout=60000)
    except Exception as exc:
        url, _ = _page_info(page)
        if not _is_blogger_posts_url(url):
            raise
        print(f"Blogger dashboard navigation continued after redirect: {exc!r}")

    try:
        page.wait_for_url(lambda url: _is_blogger_posts_url(url), wait_until="domcontentloaded", timeout=30000)
    except PlaywrightTimeoutError:
        url, _ = _page_info(page)
        if not _is_blogger_posts_url(url):
            raise
        print(f"Blogger dashboard reached without a second URL event; using current URL: {url}")

    try:
        page.wait_for_load_state("domcontentloaded", timeout=15000)
    except PlaywrightTimeoutError:
        pass

    url, _ = _page_info(page)
    if not _is_blogger_posts_url(url):
        raise RuntimeError(f"Blogger dashboard navigation ended at unexpected URL: {url}")


def main() -> int:
    print("Opening installed Google Chrome. Sign in with the Google account that owns the target Blogger blog.")
    print("If Chrome is already open, close all Chrome windows before continuing.")

    playwright = sync_playwright().start()
    browser = None

    try:
        try:
            browser = playwright.chromium.launch(
                channel="chrome",
                headless=False,
                args=["--disable-blink-features=AutomationControlled"],
            )
        except Exception as exc:
            print("\nCould not start installed Chrome.")
            print("Make sure Google Chrome is installed, then run:")
            print("python -m playwright install chrome")
            print(f"\nDetails: {exc}")
            return 1

        context = browser.new_context(locale="ar-EG")
        page = context.new_page()

        try:
            page.goto(
                "https://www.blogger.com/",
                wait_until="domcontentloaded",
                timeout=60000,
            )
            input("Complete Google/Blogger login in Chrome, then press Enter here...")

            _goto_blogger_posts(page)
            input("Confirm that the Blogger dashboard is visible, then press Enter here...")

            OUTPUT.parent.mkdir(parents=True, exist_ok=True)
            context.storage_state(path=str(OUTPUT))

            encoded = base64.b64encode(OUTPUT.read_bytes()).decode("ascii")

            print("\nCreated:", OUTPUT)
            print("\nGitHub Actions secret value for BLOGGER_UI_STORAGE_STATE_B64:")
            print(encoded)
            print("\nDo not commit or paste the decoded storage state into the repository.")

            browser.close()
            browser = None
            return 0

        except Exception as exc:
            url, title = _page_info(page)
            print("\n===== BLOGGER BOOTSTRAP ERROR =====")
            print(f"Exception type: {type(exc).__name__}")
            print(f"Exception: {exc!r}")
            print(f"Current URL: {url}")
            print(f"Page title: {title}")
            print("===================================")
            print("\nChrome is being left open so the failure can be inspected.")
            print("Press Ctrl+C when you are finished inspecting Chrome.")
            while True:
                input()
    finally:
        if browser is None:
            playwright.stop()


if __name__ == "__main__":
    raise SystemExit(main())
