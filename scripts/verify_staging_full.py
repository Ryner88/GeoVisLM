#!/usr/bin/env python3
"""Headless Cloudflare Access login test for GeoVis LM staging.

Usage:
  # Install dependencies first:
  pip install playwright requests
  playwright install chromium

  # Then run (preferred, pass credentials via env vars):
  CF_USER=you@example.com CF_PASS="your-password" python3 scripts/verify_staging_full.py

Notes:
- This script performs an automated headless browser login using Playwright.
- It does NOT store credentials. Provide them via environment variables.
"""
import os
import sys
import time
from urllib.parse import urlparse

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
except Exception as e:
    print("Playwright not installed. Install with: pip install playwright && playwright install chromium")
    sys.exit(2)

DOMAIN = os.environ.get("VERIFY_DOMAIN", "https://geovis.nextgenbytes.me")
CF_USER = os.environ.get("CF_USER") or os.environ.get("CF_USERNAME")
CF_PASS = os.environ.get("CF_PASS") or os.environ.get("CF_PASSWORD")

def find_and_fill(page, selectors, value):
    for sel in selectors:
        try:
            el = page.query_selector(sel)
        except Exception:
            el = None
        if el:
            try:
                el.fill(value)
                return True
            except Exception:
                try:
                    el.type(value)
                    return True
                except Exception:
                    pass
    return False

def click_selector(page, selectors):
    for sel in selectors:
        try:
            el = page.query_selector(sel)
        except Exception:
            el = None
        if el:
            try:
                el.click()
                return True
            except Exception:
                pass
    return False

def main():
    if not CF_USER or not CF_PASS:
        print("Missing Cloudflare Access credentials. Set CF_USER and CF_PASS environment variables.")
        sys.exit(2)

    print("Starting headless browser for:", DOMAIN)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()  # no storage
        page = context.new_page()
        try:
            page.goto(DOMAIN, wait_until="networkidle", timeout=30000)
        except PlaywrightTimeout:
            print("Initial navigation timed out")

        title = page.title() or ""
        print("Page title:", title)

        # Heuristics for Cloudflare Access login form
        email_selectors = [
            'input[type=email]', 'input[name=email]', 'input[name=username]', "input[type=text]"
        ]
        password_selectors = [
            'input[type=password]', 'input[name=password]', 'input[id=password]'
        ]
        submit_selectors = [
            'button[type=submit]', 'input[type=submit]', 'button:has-text("Log in")', 'button:has-text("Sign in")'
        ]

        found_email = page.query_selector('input[type=email]') or page.query_selector('input[name=email]')
        found_password = page.query_selector('input[type=password]')

        if found_email or found_password or 'Access' in title or 'Login' in title:
            print('Detected login form — attempting automated login')
            ok = find_and_fill(page, email_selectors, CF_USER)
            if not ok:
                print('Could not find email/username field to fill')
            time.sleep(0.5)
            ok2 = find_and_fill(page, password_selectors, CF_PASS)
            if not ok2:
                print('Could not find password field to fill')
            time.sleep(0.5)
            clicked = click_selector(page, submit_selectors)
            if not clicked:
                # Try pressing Enter on password field
                try:
                    pwd = page.query_selector(password_selectors[0])
                    if pwd:
                        pwd.press('Enter')
                        clicked = True
                except Exception:
                    clicked = False
            if not clicked:
                print('Could not submit the login form automatically')

            # Wait for navigation to dashboard or readyz
            try:
                page.wait_for_load_state('networkidle', timeout=30000)
            except PlaywrightTimeout:
                print('Post-login navigation timed out — continuing to check state')

            # Heuristic: check for dashboard indicator in title or page
            title = page.title() or ''
            content = ''
            try:
                content = page.content()[:2000]
            except Exception:
                pass

            if 'GeoVis' in title or 'GeoVis' in content or '/readyz' in page.url:
                print('Login appears successful, dashboard reachable')
                print('Final URL:', page.url)
                browser.close()
                sys.exit(0)
            else:
                print('Could not confirm dashboard post-login. Title:', title)
                print('Current URL:', page.url)
                browser.close()
                sys.exit(3)
        else:
            print('No interactive Access login detected on initial page — site may be public or uses non-standard flow')
            print('Page title:', title)
            browser.close()
            sys.exit(4)

if __name__ == '__main__':
    main()
