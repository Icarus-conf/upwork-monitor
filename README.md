# Upwork Job Monitor

> Automated real-time Upwork job monitoring engine with Cloudflare Turnstile bypass, sub-1-hour freshness filtering, client intelligence enrichment, and instant Telegram push alerts.

![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Cloudflare](https://img.shields.io/badge/Cloudflare-Turnstile%20Bypass-orange.svg)
![Telegram](https://img.shields.io/badge/Telegram-Push%20Alerts-2CA5E0.svg)

---

## Why Upwork Job Monitor?

In August 2024, Upwork officially deprecated and blocked all public RSS feeds, putting all job searches behind Cloudflare Enterprise Bot Management. Standard HTTP scrapers (curl, requests, httpx) are immediately met with `HTTP 403 Forbidden` (`Cf-Mitigated: challenge`).

**Upwork Job Monitor** solves this by orchestrating an undetected automated browser engine ([nodriver](https://github.com/ultrafunkamsterdam/nodriver)) that bypasses Cloudflare Turnstile in under 4 seconds, extracts live job cards from Upwork's client-side Nuxt/Vue DOM, enriches client spending history, and delivers structured alerts straight to your personal Telegram or group channel.

---

## Features

- **Cloudflare Turnstile Bypass**: Seamlessly clears Cloudflare bot detection using nodriver Chrome automation.
- **100% Invisible Background Execution**: Chrome launches at off-screen coordinates (`--window-position=-3000,-3000`). Cloudflare sees a full GPU-accelerated browser, but zero windows ever appear or steal focus on your desktop.
- **Sub-1-Hour Freshness Filtering**: Pre-filters listings by age (`MAX_JOB_AGE_MINUTES=60`) directly from search tiles. Stale jobs (> 1 hour) are skipped in 0.001s without loading individual pages, securing your first-mover advantage.
- **Minimum Budget Gate**: Automatically skip fixed-price jobs below your specified floor (`MIN_FIXED_BUDGET`).
- **Geographic Filtering**: Skip low-quality spam origins (`SKIP_COUNTRIES`).
- **Deep Client Intelligence**: Fetches client spend, total hires, review rating, proposal volume, active interview count, and payment verification status.
- **Global Deduplication**: Maintains persistent state (`state/seen_global.json`) so you never receive duplicate alerts, even across overlapping search keywords.
- **Single-Command Daemon**: Easy `./start.sh` and `./stop.sh` scripts for continuous background polling on macOS and Linux.

---

## Architecture

```text
[Loop Runner (every 3 min)]
          |
          v
   [nodriver Chrome] ---> Opens Upwork Search URL
          |
          +---> Turnstile Challenge Passed (~3s)
          +---> Vue/Nuxt JobTile DOM Hydration
          |
          v
   [Tile Extraction] ---> Title, URL, Hourly/Fixed Budget, Age, Skills
          |
   [Pre-Fetch Filter] ---> Age > 60 min OR Budget < $50? ---> [SKIP (Instant)]
          |
          v (Fresh jobs only)
   [Job Page Inspection] ---> Fetch Client Country, Spent, Hires, Proposals
          |
   [Country Filter] ---> Country in SKIP_COUNTRIES? ---> [SKIP]
          |
          v
   [Telegram Bot API] ---> Rich MarkdownV2 Alert Delivered to Phone
          |
          v
   [Global State] ---> UID recorded in state/seen_global.json
```

---

## Telegram Alert Preview

Each notification arrives formatted with complete contract and client intelligence:

```text
*Senior Full-Stack Mobile App Developer (Flutter & Firebase)*
----------------------------------------
*Contract details*
Posted: 14 minutes ago
Rate: Fixed price ($2,500.00)
Level: Expert
Skills: Flutter, iOS, Android, Firebase Cloud Functions, TypeScript
[Open Job Link](https://www.upwork.com/jobs/...)
----------------------------------------
*Client info*
Payment: Verified
Rating: 4.95
Total Spent: $45K spent
Hires: 38 hires, 4 active
Country: United States
----------------------------------------
*Activity on this job*
Proposals: Less than 5
Interviewing: 1
Invites sent: 0
Last viewed: 5 minutes ago
----------------------------------------
We are looking for an experienced full-stack mobile developer to build the Phase 1 MVP...
```

---

## Quick Start

### 1. Prerequisites
- **Python 3.10+**
- **Google Chrome** installed on your system.

### 2. Clone the Repository
```bash
git clone https://github.com/your-username/upwork-monitor.git
cd upwork-monitor
```

### 3. Create a Virtual Environment & Install Dependencies
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Edit `.env` with your preferred text editor:
```ini
# Telegram bot token (from @BotFather)
TELEGRAM_BOT_TOKEN=1234567890:ABCDefghIJKlmNoPQRstuVWXyz

# Your Telegram user ID or channel ID
TELEGRAM_CHANNEL=123456789

# Optional filters (defaults: 60 min age, $50 min budget, 180s cycle)
MAX_JOB_AGE_MINUTES=60
MIN_FIXED_BUDGET=50
CHECK_INTERVAL_SECONDS=180
```

---

## How to Get Your Telegram Bot Token & Chat ID

1. **Get Bot Token**:
   - Open Telegram and search for [@BotFather](https://t.me/BotFather).
   - Send `/newbot`, choose a name and username.
   - Copy the API token provided into `TELEGRAM_BOT_TOKEN`.

2. **Get Your Chat ID**:
   - Open Telegram and search for [@userinfobot](https://t.me/userinfobot).
   - Press **Start** and copy your numeric `Id` into `TELEGRAM_CHANNEL`.
   - **Note**: Open a chat with your newly created bot and send `/start` once so it has permission to message you.

---

## Customizing Search Streams & Filters

### Search Queries (`settings.py`)
Add or modify any Upwork search URL in `settings.py`. You can perform any search on Upwork with your preferred filters and paste the resulting URL:

```python
SEARCH_URLS = [
    # Flutter Mobile (iOS & Android)
    "https://www.upwork.com/nx/search/jobs/?q=Flutter&sort=recency",
    # iOS / Swift / SwiftUI
    "https://www.upwork.com/nx/search/jobs/?q=iOS%20Swift&sort=recency",
    # React / Next.js / Frontend
    "https://www.upwork.com/nx/search/jobs/?q=React%20Next.js&sort=recency",
    # Node.js / NestJS / TypeScript Backend
    "https://www.upwork.com/nx/search/jobs/?q=Node.js%20NestJS%20TypeScript&sort=recency",
    # Full Stack Web & Mobile
    "https://www.upwork.com/nx/search/jobs/?q=Fullstack%20TypeScript%20Node%20MySQL&sort=recency",
]
```

### Country & Spam Filters (`settings.py`)
```python
# Skip jobs from specific country names or ISO-3 codes
SKIP_COUNTRIES = {"india", "ind", "bangladesh", "bgd", "pakistan", "pak"}
```

---

## Running the Monitor

### 1. Run as a Background Daemon (Recommended)
Starts the monitor running continuously in the background every 3 minutes:
```bash
./start.sh
```

To stop / kill the background daemon:
```bash
./stop.sh
```

To stream live logs in real time:
```bash
tail -f monitor.log
```

### 2. Run a One-Off Scan
To test a single scan immediately in your current shell:
```bash
./venv/bin/python3 monitor.py
```
Or scan only a specific search index (e.g. index 0):
```bash
./venv/bin/python3 monitor.py 0
```

---

## Project Structure

```text
upwork-monitor/
├── monitor.py          # Core engine: Chrome automation, Turnstile bypass & parser
├── settings.py         # Search queries, country filters
├── loop_monitor.py     # Background loop runner
├── start.sh            # One-command daemon launcher
├── stop.sh             # One-command daemon terminator
├── requirements.txt    # Python dependencies (nodriver, httpx, python-dotenv)
├── .env.example        # Environment variable template
├── .env                # Your private credentials (git-ignored)
└── state/
    └── seen_global.json  # Global deduplication ledger (git-ignored)
```

---

## Security & Privacy

- **Zero Hardcoded Secrets**: All tokens, chat IDs, and private parameters reside strictly in `.env`.
- **Pre-configured `.gitignore`**: Automatically excludes `.env`, `state/`, `*.log`, `*.pid`, `venv/`, and temporary runtime files.
- **Safety First**: Verify with `git status` before pushing to ensure `.env` remains untracked.

---

## License

MIT License.
