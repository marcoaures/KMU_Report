"""Is there a Swiss postal address on the page?

Evidence, strongest first:
    jsonld        schema.org PostalAddress in structured data
    microdata     itemprop="postalCode"
    address_tag   an <address> element containing a postal code
    plz_match     "8000 Zürich" in the text, checked against the official list
    plz_heuristic no list installed: postal code next to a street or "CH-"

Without these checks every "© 2025 Muster AG" would look like an address.
"""
from __future__ import annotations

import csv
import json
import os
import re
import unicodedata
from typing import Dict, Optional, Set, Tuple

from bs4 import BeautifulSoup

from config import config as cfg
from config.dictionary_config import STREET_REGEX, YEAR_CONTEXT_WORDS, ZIP_CITY_REGEX

_plz_cache: Optional[Dict[str, Set[str]]] = None


def _norm(text: str) -> str:
    """Lower-case, strip accents and punctuation: 'Zürich' -> 'zurich'."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def load_plz(path: Optional[str] = None) -> Dict[str, Set[str]]:
    """PLZ -> set of normalised place names; empty if no list is installed.

    Reads our own "PLZ;Ort" file as well as the swisstopo CSV as downloaded
    (columns are found by their header names).
    """
    global _plz_cache
    if path is None and _plz_cache is not None:
        return _plz_cache
    table: Dict[str, Set[str]] = {}
    file_path = path or cfg.PLZ_FILE
    if os.path.exists(file_path):
        with open(file_path, newline="", encoding="utf-8-sig") as f:
            sample = f.readline()
            f.seek(0)
            delimiter = ";" if sample.count(";") >= sample.count(",") else ","
            reader = csv.reader(f, delimiter=delimiter)
            header = [h.strip().lower() for h in next(reader, [])]
            plz_col = next((i for i, h in enumerate(header) if h in ("plz", "plz4", "postleitzahl")), 0)
            name_col = next((i for i, h in enumerate(header)
                             if h in ("ort", "ortschaftsname", "ortschaft", "name")), 1)
            for row in reader:
                if len(row) <= max(plz_col, name_col):
                    continue
                plz = row[plz_col].strip()
                if not re.fullmatch(r"\d{4}", plz):
                    continue
                for part in re.split(r"[/(]", row[name_col]):
                    name = _norm(part)
                    # "Buchs SG" is written "Buchs" on most websites
                    short = re.sub(r"\s(?:[a-z]{2}|\d+)$", "", name)
                    for variant in {name, short}:
                        if len(variant) >= 2:
                            table.setdefault(plz, set()).add(variant)
    if path is None:
        _plz_cache = table
    return table


def _jsonld_has_address(node) -> bool:
    if isinstance(node, dict):
        types = node.get("@type")
        types = types if isinstance(types, list) else [types]
        if "PostalAddress" in types and (node.get("postalCode") or node.get("streetAddress")):
            return True
        return any(_jsonld_has_address(v) for v in node.values())
    if isinstance(node, list):
        return any(_jsonld_has_address(v) for v in node)
    return False


def text_has_address(text: str, plz_table: Optional[Dict[str, Set[str]]] = None) -> Optional[str]:
    """Return "plz_match"/"plz_heuristic" if the text contains an address."""
    table = load_plz() if plz_table is None else plz_table
    for m in ZIP_CITY_REGEX.finditer(text or ""):
        plz, tail = m.group(1), m.group(2)
        if table:
            tail_n = _norm(tail)
            names = table.get(plz, ())
            if any(tail_n == n or tail_n.startswith(n + " ") for n in names):
                return "plz_match"
            continue
        # No list: be strict. Swiss postal codes run from 1000 to 9658.
        if not 1000 <= int(plz) <= 9658:
            continue
        before = text[max(0, m.start() - 80): m.start()]
        if any(before.lower().rstrip(" :,-–").endswith(w) for w in YEAR_CONTEXT_WORDS):
            continue
        if m.group(0).upper().startswith("CH") or STREET_REGEX.search(before):
            return "plz_heuristic"
    return None


def detect_address(soup: BeautifulSoup, text: Optional[str] = None) -> Tuple[bool, str]:
    """(address_present, address_source)"""
    for script in soup.find_all("script", attrs={"type": re.compile(r"ld\+json", re.I)}):
        try:
            data = json.loads(script.string or script.get_text() or "")
        except (ValueError, TypeError):
            continue
        if _jsonld_has_address(data):
            return True, "jsonld"

    if soup.find(attrs={"itemprop": re.compile(r"^postalCode$", re.I)}):
        return True, "microdata"

    for tag in soup.find_all("address"):
        if re.search(r"(?<!\d)[1-9]\d{3}(?!\d)", tag.get_text(" ", strip=True)):
            return True, "address_tag"

    if text is None:
        text = soup.get_text(" ", strip=True)
    source = text_has_address(text)
    return (True, source) if source else (False, "")
