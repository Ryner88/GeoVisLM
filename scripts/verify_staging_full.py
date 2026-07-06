#!/usr/bin/env python3
"""Headless Cloudflare Access login test for GeoVis LM staging.

Usage:
  # Install dependencies first:
  pip install playwright requests
  playwright install chromium

  # Then run (preferred, pass credentials via env vars):
  CF_USER=you@example.com CF_PASS="your-password" python3 scripts/verify_staging_full.py [--domain host]

Notes:
- This script performs an automated headless browser login using Playwright.
- It does NOT store credentials. Provide them via environment variables.
"""
import argparse
import os
import sys
import time

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
except Exception:
    print("Playwright not installed. Install with: pip install playwright && playwright install chromium")
    sys.exit(2)

PLAYWRIGHT_WAIT_TIMEOUT_MS = 10_000


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--domain",
        default=None,
        help="Hostname or URL to verify (defaults to VERIFY_DOMAIN, DOMAIN, or https://geovis.nextgenbytes.me)",
    )
    return parser.parse_args()


def get_domain(cli_domain):
    return cli_domain or os.environ.get("VERIFY_DOMAIN") or os.environ.get("DOMAIN") or "https://geovis.nextgenbytes.me"


def find_and_fill(page, selectors, value):
    for sel in selectors:
        try:
            page.wait_for_selector(sel, timeout=PLAYWRIGHT_WAIT_TIMEOUT_MS)
        except PlaywrightTimeout:
            continue
        except Exception:
            continue

        try:
            locator = page.locator(sel).first
            locator.fill(value)
            return True
        except Exception:
            try:
                locator = page.locator(sel).first
                locator.type(value)
                return True
            except Exception:
                continue
    return False


def click_selector(page, selectors):
    for sel in selectors:
        try:
            page.wait_for_selector(sel, timeout=PLAYWRIGHT_WAIT_TIMEOUT_MS)
        except PlaywrightTimeout:
            continue
        except Exception:
            continue

        try:
            locator = page.locator(sel).first
            locator.click()
            return True
        except Exception:
            continue
    return False


def main():
    args = parse_args()
    domain = get_domain(args.domain)
    cf_user = os.environ.get("CF_USER") or os.environ.get("CF_USERNAME")
    cf_pass = os.environ.get("CF_PASS") or os.environ.get("CF_PASSWORD")

    if not cf_user or not cf_pass:
        print("Missing Cloudflare Access credentials. Set CF_USER and CF_PASS environment variables.")
        sys.exit(2)

    print("Starting headless browser for:", domain)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()  # no storage
        page = context.new_page()
        try:
            page.goto(domain, wait_until="networkidle", timeout=30000)
        except PlaywrightTimeout:
            print("Initial navigation timed out")

        title = page.title() or ""
        print("Page title:", title)

        # Heuristics for Cloudflare Access login form
        email_selectors = [
            "input[type=email]",
            "input[name=email]",
            "input[name=username]",
            "input[type=text]",
        ]
        password_selectors = [
            "input[type=password]",
            "input[name=password]",
            "input[id=password]",
        ]
        submit_selectors = [
            "button[type=submit]",
            "input[type=submit]",
            'button:has-text("Log in")',
            'button:has-text("Sign in")',
        ]

        found_email = page.locator("input[type=email]").count() > 0 or page.locator("input[name=email]").count() > 0
        found_password = page.locator("input[type=password]").count() > 0

        if found_email or found_password or "Access" in title or "Login" in title:
            print("Detected login form — attempting automated login")
            ok = find_and_fill(page, email_selectors, cf_user)
            if not ok:
                print("Could not find email/username field to fill")
            time.sleep(0.5)
            ok2 = find_and_fill(page, password_selectors, cf_pass)
            if not ok2:
                print("Could not find password field to fill")
            time.sleep(0.5)
            clicked = click_selector(page, submit_selectors)
            if not clicked:
                try:
                    pwd = page.locator(password_selectors[0]).first
                    if pwd.count() > 0:
                        pwd.press("Enter")
                        clicked = True
                except Exception:
                    clicked = False
            if not clicked:
                print("Could not submit the login form automatically")

            try:
                page.wait_for_load_state("networkidle", timeout=30000)
            except PlaywrightTimeout:
                print("Post-login navigation timed out — continuing to check state")

            title = page.title() or ""
            content = ""
            try:
                content = page.content()[:2000]
            except Exception:
                pass

            if "GeoVis" in title or "GeoVis" in content or "/readyz" in page.url:
                print("Login appears successful, dashboard reachable")
                print("Final URL:", page.url)
                browser.close()
                sys.exit(0)
            else:
                print("Could not confirm dashboard post-login. Title:", title)
                print("Current URL:", page.url)
                browser.close()
                sys.exit(3)
        else:
            print("No interactive Access login detected on initial page — site may be public or uses non-standard flow")
            print("Page title:", title)
            browser.close()
            sys.exit(4)


if __name__ == "__main__":
    main()
