from __future__ import annotations

import base64
from pathlib import Path

from playwright.sync_api import sync_playwright

OUTPUT = Path("generated/blogger/browser-state.json")


def main() -> int:
    print("Opening installed Google Chrome. Sign in with the Google account that owns the target Blogger blog.")
    print("If Chrome is already open, close all Chrome windows before continuing.")
    with sync_playwright() as playwright:
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
        page.goto("https://www.blogger.com/", wait_until="domcontentloaded", timeout=60000)
        input("Complete Google/Blogger login in Chrome, then press Enter here...")
        page.goto("https://www.blogger.com/blog/posts", wait_until="domcontentloaded", timeout=60000)
        input("Confirm that the Blogger dashboard is visible, then press Enter here...")

        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        context.storage_state(path=str(OUTPUT))
        browser.close()

    encoded = base64.b64encode(OUTPUT.read_bytes()).decode("ascii")
    print("\nCreated:", OUTPUT)
    print("\nGitHub Actions secret value for BLOGGER_UI_STORAGE_STATE_B64:")
    print(encoded)
    print("\nDo not commit or paste the decoded storage state into the repository.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
