from playwright.sync_api import sync_playwright
import os

def generate_certificate_pdf(url, output_path):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1200, "height": 800})

        page.goto(url, wait_until="networkidle")

        page.pdf(
            path=output_path,
            format="A4",
            landscape=True,
            print_background=True
        )

        browser.close()
