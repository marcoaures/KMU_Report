"""Recognise the CMS / site builder from the homepage we already downloaded.

No extra request is made. Only what the page says about itself is used:
the generator meta tag, typical asset paths and a few response headers.
"""
from __future__ import annotations

import re
from typing import Dict, Mapping, Optional

from bs4 import BeautifulSoup

# generator meta content (lower-case substring) -> CMS name
_GENERATORS = [
    ("wordpress", "WordPress"), ("woocommerce", "WordPress"), ("elementor", "WordPress"),
    ("wpbakery", "WordPress"), ("divi", "WordPress"), ("site kit by google", "WordPress"),
    ("joomla", "Joomla"), ("typo3", "TYPO3"), ("drupal", "Drupal"),
    ("wix.com", "Wix"), ("jimdo", "Jimdo"), ("webflow", "Webflow"),
    ("squarespace", "Squarespace"), ("shopify", "Shopify"), ("contao", "Contao"),
    ("weblication", "Weblication"), ("webnode", "Webnode"), ("prestashop", "PrestaShop"),
    ("magento", "Magento"), ("shopware", "Shopware"), ("odoo", "Odoo"),
    ("hubspot", "HubSpot CMS"), ("ghost", "Ghost"), ("craft cms", "Craft CMS"),
    ("concrete", "Concrete CMS"), ("neos", "Neos"), ("silverstripe", "Silverstripe"),
    ("kirby", "Kirby"), ("statamic", "Statamic"), ("october", "October CMS"),
    ("duda", "Duda"), ("godaddy", "GoDaddy Website Builder"), ("framer", "Framer"),
    ("hugo", "Hugo"), ("jekyll", "Jekyll"), ("gatsby", "Gatsby"), ("astro", "Astro"),
    ("weebly", "Weebly"), ("ionos", "IONOS MyWebsite"), ("processwire", "ProcessWire"),
    ("modx", "MODX"), ("plone", "Plone"), ("umbraco", "Umbraco"), ("sitecore", "Sitecore"),
]

# substring of the raw HTML (lower-case) -> CMS name; first hit wins
_MARKUP = [
    ("/wp-content/", "WordPress"), ("/wp-includes/", "WordPress"),
    ("static.wixstatic.com", "Wix"), ("static.parastorage.com", "Wix"),
    ("cdn.shopify.com", "Shopify"),
    ("static1.squarespace.com", "Squarespace"), ("squarespace-cdn.com", "Squarespace"),
    ("data-wf-site", "Webflow"), ("website-files.com", "Webflow"),
    ("jimstatic.com", "Jimdo"),
    ("/typo3conf/", "TYPO3"), ("/typo3temp/", "TYPO3"),
    ("/media/jui/", "Joomla"), ("/media/system/js/", "Joomla"), ("/components/com_", "Joomla"),
    ("/sites/default/files", "Drupal"), ("drupal-settings-json", "Drupal"),
    ("/bundles/contao", "Contao"), ("/assets/contao/", "Contao"),
    ("framerusercontent.com", "Framer"),
    ("website-editor.net", "IONOS MyWebsite"),
    ("multiscreensite.com", "Duda"),
    ("editmysite.com", "Weebly"),
    ("webnode.page", "Webnode"), ("d1di2lzuh97fh2.cloudfront.net", "Webnode"),
    ("img1.wsimg.com", "GoDaddy Website Builder"),
    ("/static/version", "Magento"),
    ("/modules/ps_", "PrestaShop"),
    ("/bundles/storefront/", "Shopware"),
    ("/web/assets/", "Odoo"),
]

# response header (lower-case name) -> CMS name
_HEADERS = {
    "x-wix-request-id": "Wix",
    "x-shopid": "Shopify", "x-shopify-stage": "Shopify",
    "x-drupal-cache": "Drupal", "x-drupal-dynamic-cache": "Drupal",
    "x-jimdo-instance": "Jimdo",
    "x-typo3-parsetime": "TYPO3",
    "x-ghost-cache-status": "Ghost",
}

_VERSION_RE = re.compile(r"(\d+(?:\.\d+){0,3})")


def detect_cms(
    soup: BeautifulSoup, html: str, headers: Optional[Mapping[str, str]] = None
) -> Dict[str, Optional[str]]:
    """Returns cms_name ("" if nothing was recognised), cms_version and the
    kind of evidence ("generator", "markup", "header")."""
    best = None
    for meta in soup.find_all("meta", attrs={"name": re.compile(r"^generator$", re.I)}):
        content = (meta.get("content") or "").strip()
        low = content.lower()
        for needle, name in _GENERATORS:
            if needle not in low:
                continue
            version = None
            # "WordPress 6.4.2" carries the CMS version; "Elementor 3.1" does not
            if low.startswith(name.lower().split()[0]):
                m = _VERSION_RE.search(content[len(name.split()[0]):])
                version = m.group(1) if m else None
            if best is None or (version and not best["cms_version"]):
                best = {"cms_name": name, "cms_version": version, "cms_evidence": "generator"}
            break
    if best:
        return best

    hdrs = {k.lower(): v for k, v in (headers or {}).items()}
    for key, name in _HEADERS.items():
        if key in hdrs:
            return {"cms_name": name, "cms_version": None, "cms_evidence": "header"}
    powered = (hdrs.get("x-powered-by", "") + " " + hdrs.get("x-generator", "") + " "
               + hdrs.get("server", "")).lower()
    for needle, name in (("wp engine", "WordPress"), ("drupal", "Drupal"), ("typo3", "TYPO3"),
                         ("squarespace", "Squarespace"), ("shopware", "Shopware"),
                         ("pepyaka", "Wix"), ("webflow", "Webflow")):
        if needle in powered:
            return {"cms_name": name, "cms_version": None, "cms_evidence": "header"}

    low_html = (html or "").lower()
    for needle, name in _MARKUP:
        if name and needle in low_html:
            return {"cms_name": name, "cms_version": None, "cms_evidence": "markup"}

    return {"cms_name": "", "cms_version": None, "cms_evidence": ""}
