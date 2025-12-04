"""Configuration for KMU Webcheck CLI.

Environment variables are preferred for secrets such as API keys.
"""

import os

VERSION = "2.1"  # Next public release identifier

PAGESPEED_API_KEY = os.getenv("PAGESPEED_API_KEY", None)
WHATCMS_API_KEY = os.getenv("WHATCMS_API_KEY", None)

# API behavior switches
DEBUG_API = False
SKIPPING_APIS = False          # skip external calls entirely
WHATCMS_PRIVATE = False        # set to True for paid/private WhatCMS mode

# ---------------------------------------------------------------------------
# Global settings
# ---------------------------------------------------------------------------

# File paths (relative to where the script is executed)
INPUT_CSV = "_input/input.csv"
OUTPUT_CSV = "_output/output.csv"

# Input windowing for batch runs
DOMAIN_OFFSET = max(0, int(os.getenv("DOMAIN_OFFSET", 0)))

_domains_per_run_env = os.getenv("DOMAINS_PER_RUN", None)
if _domains_per_run_env:
    _domains_per_run = int(_domains_per_run_env)
    DOMAINS_PER_RUN = _domains_per_run if _domains_per_run > 0 else None
else:
    DOMAINS_PER_RUN = None

# Number of concurrent worker threads
WORKER_COUNT = 4

# Limits for the responsive check
MAX_CSS_FILES_FOR_RESPONSIVE_CHECK = 2
MAX_CSS_BYTES_FOR_RESPONSIVE_CHECK = 300_000  # bytes

# Progress output controls
SHOW_PROGRESS = True
SHOW_VERBOSE_PROGRESS = False
# Flush partial output after this many processed rows
CHECKPOINT_INTERVAL = 20

# HTTP defaults
REQUEST_TIMEOUT = 10
USER_AGENT = f"KMU-Webcheck/{VERSION} (+https://marcoaures.ch; hoi@marcoaures.ch)"
HEADERS = {
    "User-Agent": USER_AGENT,
}
