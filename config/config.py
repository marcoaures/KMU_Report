"""Configuration for KMU Webcheck.

Secrets (API keys) come from environment variables. Everything else can be
edited here; a few values can also be overridden via environment variables.
"""

import os

VERSION = "3.0"

PAGESPEED_API_KEY = os.getenv("PAGESPEED_API_KEY", None)
WHATCMS_API_KEY = os.getenv("WHATCMS_API_KEY", None)

# ---------------------------------------------------------------------------
# External APIs
# ---------------------------------------------------------------------------
DEBUG_API = False
SKIPPING_APIS = False          # skip PageSpeed and WhatCMS entirely
WHATCMS_PRIVATE = False        # paid WhatCMS plans: do not store the lookup publicly

# "fallback": ask WhatCMS only if the local HTML fingerprints found no CMS
# "always":   ask WhatCMS for every reachable site
# "off":      never ask WhatCMS
WHATCMS_MODE = "fallback"

# Minimum seconds between two calls to the same API (shared by all workers).
# WhatCMS free plan: 10 s. Paid plans allow much less - check your plan.
WHATCMS_MIN_INTERVAL = 10.0
PAGESPEED_MIN_INTERVAL = 1.0
PAGESPEED_TIMEOUT = 60
API_MAX_ATTEMPTS = 3

# Also read the list of third parties Lighthouse saw while rendering the page
# (no extra request to the target site; needs the PageSpeed key).
PAGESPEED_THIRD_PARTIES = True

# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------
INPUT_CSV = "_input/input.csv"
OUTPUT_CSV = "_output/output.csv"
OUTPUT_DELIMITER = ";"         # ";" opens cleanly in a Swiss Excel
OUTPUT_ENCODING = "utf-8-sig"  # UTF-8 with BOM, also for Excel
LOG_FILE = "run.log"
REQUEST_LOG_FILE = "requests.log"   # one line per HTTP request; "" disables it

# One domain per line; "#" starts a comment. These are never scanned.
OPT_OUT_FILE = "_input/opt_out.txt"

# Optional postal code list (PLZ;Ort) used for address detection.
# Create it with:  python tools/update_plz.py
PLZ_FILE = "config/data/plz_ch.csv"

# ---------------------------------------------------------------------------
# Run control
# ---------------------------------------------------------------------------
# True: keep an existing output file, skip domains that are already in it
#       (rows with scan_status "error" are scanned again) and append new rows.
# False: start from scratch and overwrite the output file.
RESUME = os.getenv("RESUME", "1") not in ("0", "false", "False", "no")

# Skip this many (deduplicated) input domains before doing anything else.
DOMAIN_OFFSET = max(0, int(os.getenv("DOMAIN_OFFSET", 0)))

# Scan at most this many not-yet-scanned domains per run (None = all).
_domains_per_run_env = os.getenv("DOMAINS_PER_RUN", None)
if _domains_per_run_env and int(_domains_per_run_env) > 0:
    DOMAINS_PER_RUN = int(_domains_per_run_env)
else:
    DOMAINS_PER_RUN = None

# Number of domains scanned in parallel. Each domain is scanned sequentially.
WORKER_COUNT = 4

# Scan order is shuffled so that neighbours in the input (often customers of
# the same hoster) are not hit back to back. Output keeps the input order.
SHUFFLE_SCAN_ORDER = True
SHUFFLE_SEED = 42

SHOW_PROGRESS = True
SHOW_VERBOSE_PROGRESS = False

# ---------------------------------------------------------------------------
# Politeness
# ---------------------------------------------------------------------------
# Hard cap of HTTP requests against one domain (everything included).
MAX_REQUESTS_PER_DOMAIN = 30

# Minimum seconds between two requests to the same server IP. This is shared
# by all workers, so many sites on one shared-hosting IP are throttled together.
REQUEST_DELAY_SECONDS = 1.5

# robots.txt "Crawl-delay" is honoured up to this many seconds.
MAX_CRAWL_DELAY_SECONDS = 10.0

# Guessed paths (/impressum, /sitemap.xml, ...) that came back 404/410.
# After this many misses no further paths are guessed for the domain.
MAX_PROBE_MISSES_PER_DOMAIN = 8

# Guessed paths tried per section (imprint, privacy, ...) when neither the
# sitemap nor the homepage links revealed the page. Every section gets its
# first guess before any section gets a second one.
MAX_FALLBACK_PATHS_PER_SECTION = 2

# 403 on the homepage or 429 anywhere stops the scan of that domain at once.
# This many 403s on other URLs do the same.
MAX_FORBIDDEN_PER_DOMAIN = 3

# This many connection errors/timeouts in a row stop the scan of a domain.
MAX_CONSECUTIVE_ERRORS = 3

# Emergency brake: if at least this share of the last BRAKE_WINDOW scanned
# domains was blocked or timed out, all workers pause for BRAKE_PAUSE_SECONDS.
BRAKE_WINDOW = 40
BRAKE_THRESHOLD = 0.5
BRAKE_PAUSE_SECONDS = 600

# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
CONNECT_TIMEOUT = 6
READ_TIMEOUT = 12
REQUEST_TIMEOUT = (CONNECT_TIMEOUT, READ_TIMEOUT)

# Download caps in bytes. Larger responses are cut off, not skipped.
MAX_HTML_BYTES = 2_000_000
MAX_CSS_BYTES_FOR_RESPONSIVE_CHECK = 400_000
MAX_SITEMAP_BYTES = 10_000_000       # also the cap after gunzip
MAX_TEXT_BYTES = 200_000             # robots.txt, security.txt, llms.txt

MAX_CSS_FILES_FOR_RESPONSIVE_CHECK = 2

# Sitemap limits
MAX_SITEMAP_FILES = 8                # sitemap files fetched per domain
MAX_SITEMAP_DEPTH = 3                # nesting of sitemap indexes
MAX_SITEMAP_URLS = 50_000

# Shown to every site you scan. Point INFO_URL at a page that explains what
# this crawler does and how to opt out, and set a contact address people can
# actually reach (here or via the KMU_CONTACT environment variable).
INFO_URL = os.getenv("KMU_INFO_URL", "https://marcoaures.ch")
CONTACT = os.getenv("KMU_CONTACT", "")
USER_AGENT_TOKEN = "KMU-Webcheck"    # the name robots.txt rules can address
USER_AGENT = f"{USER_AGENT_TOKEN}/{VERSION} (+{INFO_URL}" + (f"; {CONTACT})" if CONTACT else ")")
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-CH,de;q=0.9,fr;q=0.8,it;q=0.7,en;q=0.6",
}

# Input rows pointing at these hosts are not scanned (status "skipped_platform"):
# the page belongs to a platform, not to the company.
PLATFORM_DOMAINS = {
    # social / directories
    "facebook.com", "fb.com", "instagram.com", "linkedin.com", "x.com",
    "twitter.com", "youtube.com", "tiktok.com", "xing.com", "pinterest.com",
    "local.ch", "search.ch", "google.com", "goo.gl", "g.page", "business.site",
    "tripadvisor.com", "tripadvisor.ch", "booking.com", "linktr.ee",
    "yelp.com", "yelp.ch", "wikipedia.org",
    # site-builder subdomains (firma.wixsite.com etc.)
    "wixsite.com", "jimdofree.com", "jimdosite.com", "webnode.page",
    "webnode.com", "weebly.com", "wordpress.com", "blogspot.com",
    "squarespace.com", "myshopify.com", "webflow.io", "godaddysites.com",
    "site123.me", "strikingly.com", "github.io", "netlify.app", "vercel.app",
}
