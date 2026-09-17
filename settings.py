"""
settings.py — all configuration for Upwork Monitor.
Edit this file to add/remove search URLs, adjust filters, etc.
"""

# ── Telegram ──────────────────────────────────────────────────────────────────
# Loaded from .env — do not hardcode here.
# Required env vars: TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL

# ── Search URLs ───────────────────────────────────────────────────────────────
# Each URL gets its own systemd timer.
# Run `sudo bash setup_timers.sh` after adding/removing URLs.

import os
import urllib.parse
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

DEFAULT_SEARCH_URLS = [
    # Flutter Mobile (iOS & Android)
    "https://www.upwork.com/nx/search/jobs/?q=Flutter&sort=recency",
    # iOS / Swift / SwiftUI
    "https://www.upwork.com/nx/search/jobs/?q=iOS%20Swift&sort=recency",
    # React / Next.js / Frontend
    "https://www.upwork.com/nx/search/jobs/?q=React%20Next.js&sort=recency",
    # Node.js / NestJS / TypeScript Backend
    "https://www.upwork.com/nx/search/jobs/?q=Node.js%20NestJS%20TypeScript&sort=recency",
    # Laravel / PHP Backend
    "https://www.upwork.com/nx/search/jobs/?q=Laravel&sort=recency",
    # Full Stack Web & Mobile (TypeScript, MySQL, Node, React)
    "https://www.upwork.com/nx/search/jobs/?q=Fullstack%20TypeScript%20Node%20MySQL&sort=recency",
]

# Configurable via .env:
# SEARCH_KEYWORDS="Flutter, iOS Swift, React, Node.js" (comma-separated)
# OR full custom URLs via SEARCH_URLS="https://...,https://..."
env_keywords = os.environ.get("SEARCH_KEYWORDS", "").strip()
env_urls = os.environ.get("SEARCH_URLS", "").strip()

if env_keywords:
    SEARCH_URLS = [
        f"https://www.upwork.com/nx/search/jobs/?q={urllib.parse.quote(kw.strip())}&sort=recency"
        for kw in env_keywords.split(",")
        if kw.strip()
    ]
elif env_urls:
    SEARCH_URLS = [url.strip() for url in env_urls.split(",") if url.strip()]
else:
    SEARCH_URLS = DEFAULT_SEARCH_URLS

# ── Filters ───────────────────────────────────────────────────────────────────

# Skip jobs from these countries (lowercase name or 3-letter ISO code)
SKIP_COUNTRIES = {"india", "ind", "bangladesh", "bgd", "pakistan", "pak"}

# Skip fixed-price jobs below this budget (USD) - customizable via .env MIN_FIXED_BUDGET
MIN_FIXED_BUDGET = int(os.environ.get("MIN_FIXED_BUDGET", "50"))

# Maximum job age in minutes — customizable via .env MAX_JOB_AGE_MINUTES (default 60 = under 1 hour)
MAX_JOB_AGE_MINUTES = int(os.environ.get("MAX_JOB_AGE_MINUTES", "60"))

# ── Country settings ──────────────────────────────────────────────────────────
# Country flags dictionary removed to ensure clean emoji-free text output
COUNTRY_FLAGS = {}
