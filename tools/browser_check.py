"""M7's browser check: drive the running dashboard in a real (headless) browser, the way a person would, and save a
screenshot of each page to runs\\browser-check\\.

Start the dashboard first (uv run pair-refiner), then: uv run python tools/browser_check.py
It starts a real run of the first 5 MIZAN sentences with a $0.50 spending limit (a few cents)."""

import sys
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

URL = "http://127.0.0.1:8765"
OUT = Path(__file__).parents[1] / "runs" / "browser-check"
RUN = f"dashboard-check-{datetime.now():%Y%m%d-%H%M}"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        page = p.chromium.launch().new_page(viewport={"width": 1280, "height": 900})

        def shot(name: str) -> None:
            page.screenshot(path=OUT / f"{name}.png", full_page=True)
            print(f"  {name}.png")

        page.goto(f"{URL}/runs")
        expect(page.get_by_role("heading", name="Runs")).to_be_visible()
        expect(page.locator("header")).to_contain_text("OpenRouter balance: $")
        shot("1-runs")

        page.get_by_role("link", name="New run").click()
        page.select_option("select[name=dataset]", "mizan-sample-2000")
        page.wait_for_load_state()
        page.fill("input[name=name]", RUN)
        page.fill("input[name=sentence_limit]", "5")
        page.fill("input[name=spending_limit]", "0.50")
        page.get_by_role("button", name="Estimate").click()
        expect(page.get_by_text("Estimate: $")).to_be_visible()
        shot("2-new-run-estimate")

        page.get_by_role("button", name="Start").click()
        page.wait_for_url(f"**/runs/{RUN}")
        shot("3-run-started")
        deadline = time.monotonic() + 600
        while True:  # the run page refreshes itself every 3 seconds while the run works
            try:
                text = page.inner_text("main")
            except Exception:  # caught mid-refresh: look again
                text = ""
            if "finished" in text or "stopped" in text:
                break
            if time.monotonic() > deadline:
                sys.exit("the run didn't finish in 10 minutes")
            page.wait_for_timeout(1000)
        page.wait_for_load_state()
        expect(page.get_by_text("5 of 5 sentences")).to_be_visible()
        shot("4-run-finished")

        page.locator("table a").first.click()
        expect(page.get_by_text("Cost of this sentence")).to_be_visible()
        shot("5-sentence")

        page.get_by_role("link", name="Models").click()
        expect(page.get_by_role("heading", name="Models")).to_be_visible()
        shot("6-models")

        page.goto(f"{URL}/runs")
        expect(page.get_by_role("link", name=RUN)).to_be_visible()
        shot("7-runs-after")
    print(f"browser check passed; screenshots in {OUT}")


if __name__ == "__main__":
    main()
