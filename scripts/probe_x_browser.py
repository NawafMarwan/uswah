#!/usr/bin/env python3
"""Probe: can a headless browser on a GitHub runner read view counts from X without logging in?"""
import re
import sys

from playwright.sync_api import sync_playwright

USER = sys.argv[1] if len(sys.argv) > 1 else "OSWAHH1"
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1280, "height": 1600}, locale="en-US",
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")
    page = ctx.new_page()
    page.goto(f"https://x.com/{USER}", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(9000)
    text = page.inner_text("body")
    print("title:", page.title())
    print("login wall:", bool(re.search(r"Log in|Sign in|Sign up", text)), "| tweets (articles):", page.locator("article").count())
    print("body text (first 900 chars):")
    print(re.sub(r"\s+", " ", text)[:900])
    views = page.locator("a[href*='/analytics']")
    print("analytics links:", views.count(), [views.nth(i).inner_text() for i in range(min(views.count(), 8))])
    b.close()
