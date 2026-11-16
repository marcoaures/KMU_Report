"""Download the official Swiss postal code list and store it as PLZ;Ort.

    python tools/update_plz.py

Source: swisstopo, "Amtliches Ortschaftenverzeichnis" (open use, source must
be named). The file ends up where config.PLZ_FILE points. Without it the
address check falls back to a stricter heuristic.
"""
from __future__ import annotations

import csv
import io
import os
import sys
import zipfile

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config as cfg  # noqa: E402

URL = (
    "https://data.geo.admin.ch/ch.swisstopo-vd.ortschaftenverzeichnis_plz/"
    "ortschaftenverzeichnis_plz/ortschaftenverzeichnis_plz_4326.csv.zip"
)


def main() -> None:
    print("Downloading", URL)
    resp = requests.get(URL, timeout=60)
    resp.raise_for_status()
    archive = zipfile.ZipFile(io.BytesIO(resp.content))
    name = next(n for n in archive.namelist() if n.lower().endswith(".csv"))
    text = archive.read(name).decode("utf-8-sig")
    delimiter = ";" if text.splitlines()[0].count(";") else ","
    rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    header = [h.strip().lower() for h in rows[0]]
    try:
        plz_col = next(i for i, h in enumerate(header) if h in ("plz", "plz4"))
        name_col = next(i for i, h in enumerate(header) if h.startswith("ortschaft"))
    except StopIteration:
        sys.exit(f"Unexpected columns in {name}: {rows[0]}")

    pairs = sorted({(r[plz_col].strip(), r[name_col].strip()) for r in rows[1:]
                    if len(r) > max(plz_col, name_col) and r[plz_col].strip().isdigit()})
    os.makedirs(os.path.dirname(cfg.PLZ_FILE), exist_ok=True)
    with open(cfg.PLZ_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["PLZ", "Ort"])
        writer.writerows(pairs)
    print(f"Wrote {len(pairs)} entries to {cfg.PLZ_FILE}")
    print("Source: swisstopo, Amtliches Ortschaftenverzeichnis")


if __name__ == "__main__":
    main()
