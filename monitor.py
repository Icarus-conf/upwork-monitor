"""
Upwork Job Monitor
==================
Monitors multiple Upwork search URLs for new job postings and sends
Telegram notifications with full job + client details.

Architecture:
- 8 systemd timers run this script with index 0-7 (one per search URL)
- Each run opens the search URL in a headless browser (nodriver/Chrome)
- Parses job tiles, fetches client info from each job page
- Sends new jobs to a Telegram channel
- Global deduplication via state/seen_global.json

Configuration:
- Copy .env.example to .env and fill in your values
- Run setup_timers.sh (as root) to install systemd timers
"""

from __future__ import annotations

import asyncio
import fcntl
import json
import os
import re
import sys
from pathlib import Path

import httpx
import nodriver as uc
from dotenv import load_dotenv
from settings import SEARCH_URLS, SKIP_COUNTRIES, MIN_FIXED_BUDGET, COUNTRY_FLAGS, MAX_JOB_AGE_MINUTES

# ── Config ────────────────────────────────────────────────────────────────────

load_dotenv(Path(__file__).parent / ".env")

TELEGRAM_BOT_TOKEN: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL:   str = os.environ.get("TELEGRAM_CHANNEL", "")

BASE_URL  = "https://www.upwork.com"
STATE_DIR = Path(__file__).parent / "state"
LOCK_FILE = Path(__file__).parent / "monitor.lock"


# ── State (global deduplication) ──────────────────────────────────────────────

GLOBAL_STATE_FILE = STATE_DIR / "seen_global.json"


def load_state() -> set[str]:
    """
    Load seen job UIDs from global state file.
    Also migrates legacy per-index files (seen_0.json … seen_N.json) on first run.
    """
    STATE_DIR.mkdir(exist_ok=True)

    merged: set[str] = set()

    # Migrate old per-index files
    for old_f in STATE_DIR.glob("seen_[0-9]*.json"):
        try:
            merged |= set(json.loads(old_f.read_text()))
        except Exception:
            pass

    if GLOBAL_STATE_FILE.exists():
        try:
            merged |= set(json.loads(GLOBAL_STATE_FILE.read_text()))
        except Exception:
            pass

    if merged:
        _write_state(merged)
        for old_f in STATE_DIR.glob("seen_[0-9]*.json"):
            try:
                old_f.unlink()
            except Exception:
                pass

    return merged


def _write_state(seen: set[str]) -> None:
    STATE_DIR.mkdir(exist_ok=True)
    tmp = GLOBAL_STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(sorted(seen), indent=2))
    tmp.rename(GLOBAL_STATE_FILE)


def save_state(seen: set[str]) -> None:
    _write_state(seen)


# ── HTML parsing ──────────────────────────────────────────────────────────────

def strip_tags(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html).strip()


def parse_tiles(html: str) -> list[dict]:
    """Extract job data from Upwork search results HTML."""
    jobs = []
    tiles = re.findall(
        r'(<article[^>]*data-test="JobTile"[^>]*>.*?</article>)',
        html, re.DOTALL,
    )
    print(f"  Tiles found: {len(tiles)}", flush=True)

    for tile in tiles:
        job: dict = {}

        # UID
        m = re.search(r'data-ev-job-uid="(\d+)"', tile)
        job["uid"] = m.group(1) if m else ""

        # URL (clean, no query params, clean highlight tags from slug)
        m = re.search(r'href="(/jobs/[^"]+)"[^>]*data-ev-label="link"', tile)
        if not m:
            m = re.search(r'data-ev-label="link"[^>]*href="(/jobs/[^"]+)"', tile)
        if m:
            clean_path = m.group(1).split("?")[0]
            clean_path = re.sub(r"span-class-highlight-[^-_]+-span-?", "", clean_path)
            job["url"] = BASE_URL + clean_path
        else:
            job["url"] = f"{BASE_URL}/jobs/~0{job['uid']}" if job.get("uid") else ""

        # Title
        m = re.search(r'data-test="job-tile-title-link[^"]*"[^>]*>(.*?)</a>', tile, re.DOTALL)
        job["title"] = strip_tags(m.group(1)) if m else ""

        # Posted date
        m = re.search(r'data-test="job-pubilshed-date"[^>]*>(.*?)</small>', tile, re.DOTALL)
        if not m:
            m = re.search(r'data-test="job-pubilshed-date"[^>]*>(.*?)</div>', tile, re.DOTALL)
        job["posted"] = strip_tags(m.group(1)) if m else ""

        # Job type / rate
        m = re.search(r'data-test="job-type-label"[^>]*><strong>([^<]+)</strong>', tile)
        rate_val = m.group(1).strip() if m else ""
        m_hr = re.search(r'\$([\d,\.]+)\s*-\s*\$([\d,\.]+)', tile)
        if m_hr:
            rate_val = f"${m_hr.group(1)} - ${m_hr.group(2)}/hr"
        job["rate"] = rate_val

        # Fixed price budget
        m = re.search(r'data-test="is-fixed-price"[^>]*>.*?\$([\d,\.]+)', tile, re.DOTALL)
        job["fixed_budget"] = f"${m.group(1)}" if m else ""

        # Experience level
        m = re.search(r'data-test="experience-level"[^>]*><strong>([^<]+)</strong>', tile)
        job["level"] = m.group(1).strip() if m else ""

        # Description snippet
        m = re.search(r'data-test="[^"]*JobDescription[^"]*".*?<p[^>]*>(.*?)</p>', tile, re.DOTALL)
        job["description"] = strip_tags(m.group(1))[:300] if m else ""

        # Required skills
        job["skills"] = [
            strip_tags(s)
            for s in re.findall(r'data-test="token"[^>]*>(.*?)</button>', tile, re.DOTALL)
        ]

        # Client info (basic — enriched later from job page)
        job["payment_verified"] = bool(re.search(r"Payment method verified", tile))
        m = re.search(r'data-test="total-spent"[^>]*><strong>([^<]+)</strong>', tile)
        if not m:
            m = re.search(r"(\$[\d,\.]+[KMk+]*)\s*(?:spent|total)", tile)
        job["spent"] = m.group(1).strip() if m else ""

        m = re.search(r'data-test="client-rating"[^>]*aria-label="([\d\.]+)', tile)
        if not m:
            m = re.search(
                r'data-test="client-rating"[^>]*>.*?<span[^>]*>([\d\.]+)</span>',
                tile, re.DOTALL,
            )
        job["rating"] = m.group(1).strip() if m else ""

        m = re.search(
            r'data-test="client-location"[^>]*>.*?<strong[^>]*>([^<]+)</strong>',
            tile, re.DOTALL,
        )
        if not m:
            m = re.search(r"location[^>]*>.*?<span[^>]*>([^<]+)</span>", tile, re.DOTALL)
        job["country"] = m.group(1).strip() if m else ""

        m = re.search(r"Proposals:\s*<strong>([^<]+)</strong>", tile)
        if not m:
            m = re.search(r'data-test="proposals"[^>]*>.*?(\d[^<]*)</span>', tile, re.DOTALL)
        job["proposals"] = m.group(1).strip() if m else ""

        if job.get("uid") and job.get("title"):
            jobs.append(job)

    return jobs


# ── Client info (job page) ────────────────────────────────────────────────────

_CLIENT_JS = """
(function() {
    if (!document.body) return null;
    var qa = function(s) { return document.querySelector('[data-qa="' + s + '"]'); };
    var it = function(el) { return el ? el.innerText.trim() : ''; };
    var body = document.body.innerText;

    var locRaw = it(qa('client-location'));
    var country = locRaw ? locRaw.split('\\n')[0].trim() : '';

    var proposals = '', interviewing = '', invites_sent = '', unanswered = '', last_viewed = '';
    var actIdx = body.indexOf('Activity on this job');
    if (actIdx !== -1) {
        var actTxt = body.substring(actIdx, actIdx + 600);
        var rx = function(label) {
            var m = actTxt.match(new RegExp(label + '[:\\\\s]*\\\\n([^\\\\n]+)'));
            return m ? m[1].trim() : '';
        };
        proposals    = rx('Proposals');
        interviewing = rx('Interviewing');
        invites_sent = rx('Invites sent');
        unanswered   = rx('Unanswered invites');
        last_viewed  = rx('Last viewed by client');
    }

    return {
        spent:            it(qa('client-spend')),
        country:          country,
        hires:            it(qa('client-hires')),
        rating:           it(qa('client-job-posting-stats')),
        payment_verified: body.indexOf('Payment method verified') !== -1,
        proposals:        proposals,
        interviewing:     interviewing,
        invites_sent:     invites_sent,
        unanswered:       unanswered,
        last_viewed:      last_viewed,
    };
})()
"""


async def _fetch_client_info_inner(job_url: str, browser) -> dict:
    """Open job page in a new tab and extract client + activity data."""
    try:
        tab = await browser.get(job_url, new_tab=True)

        # Wait for client data to appear
        for _ in range(20):
            await asyncio.sleep(1)
            has_client = await tab.evaluate(
                "!!document.querySelector('[data-qa=\"client-spend\"]') || "
                "!!document.querySelector('[data-qa=\"client-location\"]')"
            )
            if has_client:
                break
            body_len = await tab.evaluate(
                "document.body ? document.body.innerText.length : 0"
            )
            if isinstance(body_len, int) and body_len > 8000:
                break

        data = await tab.evaluate(_CLIENT_JS)
        await tab.close()

        if isinstance(data, list):
            data = {
                pair[0]: pair[1].get("value", "") if isinstance(pair[1], dict) else pair[1]
                for pair in data
            }

        info = {}
        if isinstance(data, dict):
            info = {k: v for k, v in data.items() if v not in (None, "", False)}

        print(f"  client_info: {info}", flush=True)
        return info

    except Exception as e:
        print(f"  client_info error: {type(e).__name__}: {e}", flush=True)
        return {}


async def fetch_client_info(browser, job_url: str) -> dict:
    """Fetch client info with a hard timeout."""
    try:
        return await asyncio.wait_for(
            _fetch_client_info_inner(job_url, browser), timeout=45
        )
    except asyncio.TimeoutError:
        print(f"  client_info timeout: {job_url}", flush=True)
        return {}
    except Exception as e:
        print(f"  client_info error: {e}", flush=True)
        return {}


# ── Filtering ─────────────────────────────────────────────────────────────────

def parse_age_minutes(posted_str: str) -> int | None:
    """Parse relative posted string (e.g. 'Posted 15 minutes ago') into minutes."""
    if not posted_str:
        return None
    s = posted_str.lower().strip()
    if "just now" in s or "second" in s:
        return 0
    m_min = re.search(r"(\d+)\s*min", s)
    if m_min:
        return int(m_min.group(1))
    m_hr = re.search(r"(\d+)\s*hour", s)
    if m_hr:
        return int(m_hr.group(1)) * 60
    m_day = re.search(r"(\d+)\s*day", s)
    if m_day:
        return int(m_day.group(1)) * 1440
    if "yesterday" in s:
        return 1440
    return None


def should_skip(job: dict) -> str | None:
    """Return a skip reason string, or None if the job should be sent."""
    # 1. Job age filter (under 1 hour)
    posted_str = (job.get("posted") or "").strip()
    age_min = parse_age_minutes(posted_str)
    if age_min is not None and age_min > MAX_JOB_AGE_MINUTES:
        return f"age={posted_str} (> {MAX_JOB_AGE_MINUTES}m)"

    # 2. Country filter
    country = (job.get("country") or "").strip().lower()
    if country in SKIP_COUNTRIES:
        return f"country={job.get('country')}"

    # 3. Minimum fixed budget
    budget_str = job.get("fixed_budget", "")
    if budget_str:
        amount = float(re.sub(r"[^\d.]", "", budget_str) or "0")
        if 0 < amount < MIN_FIXED_BUDGET:
            return f"fixed_budget={budget_str} < ${MIN_FIXED_BUDGET}"

    return None


# ── Telegram formatting ───────────────────────────────────────────────────────

def escape_md(s: str) -> str:
    """Escape Telegram MarkdownV2 special characters."""
    for ch in r"\_*[]()~`>#+-=|{}.!":
        s = s.replace(ch, "\\" + ch)
    return s


def format_job(job: dict) -> str:
    """Format a job dict into a Telegram MarkdownV2 message (clean text, no emojis)."""
    t       = escape_md(job["title"])
    rate    = escape_md(job.get("rate", ""))
    level   = escape_md(job.get("level", ""))
    posted  = escape_md(job.get("posted", ""))
    desc    = escape_md(job.get("description", ""))
    url     = job["url"]
    skills  = job.get("skills", [])
    country = job.get("country", "")

    lines = [
        f"*{t}*",
        "----------------------------------------",
        "*Contract details*",
    ]
    if posted:
        lines.append(f"Posted: {posted}")
    if rate:
        budget = escape_md(job.get("fixed_budget", ""))
        lines.append(f"Rate: {rate} \\({budget}\\)" if budget else f"Rate: {rate}")
    if level:
        lines.append(f"Level: {level}")
    if skills:
        lines.append(f"Skills: {escape_md(', '.join(skills[:6]))}")
    lines.append(f"[Open Job Link]({url})")
    lines.append("----------------------------------------")

    # Client block
    client_lines = []
    if job.get("payment_verified"):
        client_lines.append("Payment: Verified")
    if job.get("rating"):
        client_lines.append(f"Rating: {escape_md(job['rating'])}")
    if job.get("spent"):
        client_lines.append(f"Total Spent: {escape_md(job['spent'])}")
    if job.get("hires"):
        client_lines.append(f"Hires: {escape_md(job['hires'])}")
    if country:
        client_lines.append(f"Country: {escape_md(country)}")
    if client_lines:
        lines.append("*Client info*")
        lines.extend(client_lines)
        lines.append("----------------------------------------")

    # Activity block
    activity_lines = []
    for label, key in [
        ("Proposals",    "proposals"),
        ("Interviewing", "interviewing"),
        ("Invites sent", "invites_sent"),
        ("Unanswered",   "unanswered"),
        ("Last viewed",  "last_viewed"),
    ]:
        if job.get(key):
            activity_lines.append(f"{label}: {escape_md(job[key])}")
    if activity_lines:
        lines.append("*Activity on this job*")
        lines.extend(activity_lines)
        lines.append("----------------------------------------")

    if desc:
        suffix = escape_md("...") if len(job["description"]) >= 300 else ""
        lines.append(desc + suffix)

    return "\n".join(lines)


# ── Telegram sender ───────────────────────────────────────────────────────────

async def send_telegram(text: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHANNEL:
        print("  [Notice] Telegram credentials not configured in .env. Alert preview:")
        print(text)
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    async with httpx.AsyncClient() as client:
        r = await client.post(
            url,
            json={
                "chat_id": TELEGRAM_CHANNEL,
                "text": text,
                "parse_mode": "MarkdownV2",
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
        print(f"  TG: {r.status_code}", flush=True)
        if r.status_code != 200:
            print(f"  TG error: {r.text}", flush=True)


# ── Main ──────────────────────────────────────────────────────────────────────

async def main(url_idx: int) -> None:
    seen = load_state()
    print(f"Known seen jobs in state: {len(seen)}", flush=True)

    browser = await uc.start(
        headless=False,
        browser_args=[
            "--window-position=-3000,-3000",
            "--window-size=1200,800",
            "--no-first-run",
            "--no-default-browser-check",
        ],
    )
    all_jobs: list[dict] = []

    try:
        for search_url in SEARCH_URLS:
            print(f"Opening search: {search_url}", flush=True)
            page = await browser.get(search_url)

            # Wait for Cloudflare challenge to pass
            for _ in range(25):
                await asyncio.sleep(1)
                title = await page.evaluate("document.title")
                if title and "moment" not in title.lower():
                    break

            # Wait for job tiles to hydrate into DOM
            for _ in range(10):
                has_tiles = await page.evaluate(
                    "!!document.querySelector('[data-test=\"JobTile\"]')"
                )
                if has_tiles:
                    break
                await asyncio.sleep(1)

            await asyncio.sleep(2)
            html = await page.get_content()
            print(f"  HTML loaded: {len(html)} chars", flush=True)
            all_jobs.extend(parse_tiles(html))
            await asyncio.sleep(2)

        # Deduplicate within this run (same job in multiple searches)
        seen_this_run: set[str] = set()
        unique_jobs = []
        for job in all_jobs:
            if job["uid"] not in seen_this_run:
                seen_this_run.add(job["uid"])
                unique_jobs.append(job)

        # Only jobs we haven't seen before
        new_jobs = [j for j in unique_jobs if j["uid"] not in seen]
        print(f"Jobs parsed: {len(unique_jobs)}, new: {len(new_jobs)}", flush=True)

        for job in new_jobs:
            # Fast filter check (age & budget) before opening individual job tab
            pre_skip = should_skip(job)
            if pre_skip:
                print(f"  SKIP ({pre_skip}): {job['title'][:50]}", flush=True)
                seen.add(job["uid"])
                continue

            if job.get("url"):
                print(f"  Fetching client info: {job['title'][:50]}", flush=True)
                client_info = await fetch_client_info(browser, job["url"])
                job.update(client_info)

            skip_reason = should_skip(job)
            if skip_reason:
                print(f"  SKIP ({skip_reason}): {job['title'][:50]}", flush=True)
                seen.add(job["uid"])
                continue

            print(f"  Sending: {job['title'][:60]}", flush=True)
            await send_telegram(format_job(job))
            await asyncio.sleep(0.5)
            seen.add(job["uid"])

    finally:
        browser.stop()
        save_state(seen)

    print(f"Done. Total seen UIDs: {len(seen)}", flush=True)


if __name__ == "__main__":
    lock_fd = open(LOCK_FILE, "w")
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("Another instance is running — exiting.", flush=True)
        sys.exit(0)

    try:
        if len(sys.argv) > 1:
            idx = int(sys.argv[1])
            SEARCH_URLS[:] = [SEARCH_URLS[idx]]
        else:
            idx = 0
        uc.loop().run_until_complete(main(idx))
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        lock_fd.close()
