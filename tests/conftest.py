import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import config as cfg  # noqa: E402

# Tests talk to a local fake server only: no waiting, no API calls.
cfg.REQUEST_DELAY_SECONDS = 0
cfg.SKIPPING_APIS = True
cfg.REQUEST_LOG_FILE = ""
cfg.PLZ_FILE = os.path.join(ROOT, "tests", "data", "plz_sample.csv")
