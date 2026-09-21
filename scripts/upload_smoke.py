"""Playwright smoke test for the Streamlit multi-file upload workflow."""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8507")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="heeh-upload-smoke-") as temp_dir:
        root = Path(temp_dir)
        first = root / "first.png"
        second = root / "second.png"
        Image.new("L", (8, 8), 1).save(first)
        Image.new("L", (8, 8), 2).save(second)

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            try:
                page.goto(args.url)
                page.wait_for_load_state("networkidle")
                page.get_by_text("Direct Upload", exact=True).click()
                page.wait_for_timeout(1000)
                uploader = page.locator('input[type="file"]').first
                uploader.set_input_files([str(first), str(second)])
                page.get_by_text("2 file(s) selected", exact=False).wait_for()

                page.get_by_role("button", name="Clear uploaded files").click()
                page.get_by_text("System Ready. Waiting for data input", exact=False).wait_for()
            finally:
                browser.close()


if __name__ == "__main__":
    main()
