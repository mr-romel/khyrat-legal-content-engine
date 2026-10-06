from __future__ import annotations

import base64
from pathlib import Path

from playwright.sync_api import sync_playwright

OUTPUT = Path("generated/blogger/browser-state.json")


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

            page.goto(
                "https://www.blogger.com/blog/posts",
                wait_until="domcontentloaded",
                timeout=60000,
            )
            input("Confirm that the Blogger dashboard is visible, then press Enter here...")

            OUTPUT.parent.mkdir(parents=True, exist_ok=True)
            context.storage_state(path=str(OUTPUT))

            encoded = base64.b64encode(OUTPUT.read_bytes()).decode("ascii")

            print("\nCreated:", OUTPUT)
            print("\nGitHub Actions secret value for BLOGGER_UI_STORAGE_STATE_B64:")
            print(encoded)
            print("\nDo not commit or paste the decoded storage state into the repository.")

            # Close Chrome only after the storage state has been written successfully.
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
            # Keep the process alive so Playwright does not tear down the browser
            # immediately after an exception. No browser.close() is attempted here.
            while True:
                input()
    finally:
        # On the normal success path browser is already closed. On launch failure
        # there is no browser. On an exception, this block deliberately does not
        # close Chrome.
        if browser is None:
            playwright.stop()


if __name__ == "__main__":
    raise SystemExit(main())
