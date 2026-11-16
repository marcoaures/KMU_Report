# KMU Webcheck

A hobby project: a command-line script that visits a list of websites and
notes down what it sees – is the site reachable, is HTTPS set up properly, is
there an imprint, a privacy policy, a cookie banner, alt texts, a sitemap, and
so on. One CSV row per domain. It was built with Swiss small-business websites
in mind (German, French, Italian and English keywords, Swiss phone numbers and
postal codes).

It is not a security scanner and not an audit. Many checks are heuristics that
look at the homepage only. See [What it can't do](#what-it-cant-do) before
drawing conclusions from the numbers.

Parts of the code were written and refactored with the help of AI tools.

## What it looks at

- **Reachability & transport**: HTTP status, redirect target, HTTPS redirect,
  HSTS, TLS handshake and certificate problems, CDN/WAF hints.
- **DNS**: DNSSEC (heuristic), MX, SPF, DMARC.
- **Structure**: robots.txt, sitemaps (count, pages, last modified), blog/news,
  careers, imprint, privacy policy and terms pages.
- **Homepage**: language tags and hreflang, structured data, social profiles,
  contact details, responsive-design signals, word count, placeholder pages.
- **Accessibility basics**: alt attributes, heading order, ARIA usage,
  clickable `<div>`s.
- **Tracking & consent**: analytics tools, tag managers, consent tools, cookie
  banner buttons – as far as they are visible in the delivered HTML.
- **Tech & trust**: CMS (from the page itself, optionally WhatCMS), security
  headers, `security.txt`, `llms.txt`, PageSpeed scores (optional).

## Quick start

Python 3.10 or newer.

```bash
pip install -r requirements.txt
python tools/update_plz.py        # optional: postal code list for address detection
mkdir -p _input _output
python main.py
```

Put your list at `_input/input.csv`. It needs a `website` column (`url` or
`domain` work too); everything else is ignored:

```csv
name;address;industry;website
Beispiel AG;Bern;Töpferei;https://beispiel.ch
```

Results land in `_output/output.csv`. Run it again and it continues where it
stopped: finished domains are skipped, failed ones are tried again. Set
`RESUME = False` in `config/config.py` to start over.

Optional API keys, as environment variables:

- `PAGESPEED_API_KEY` – Google PageSpeed Insights
- `WHATCMS_API_KEY` – WhatCMS (only asked when the page itself gives no hint,
  see `WHATCMS_MODE`)

## Being a polite visitor

The script identifies itself (`KMU-Webcheck/<version>` plus a link), obeys
robots.txt including `Crawl-delay`, and tries hard not to look or behave like
a vulnerability scanner:

- at most 30 requests per domain, usually far fewer
- 1.5 s between requests to the same server IP – shared across workers, so
  many small sites on one shared host are not hit all at once
- a handful of guessed URLs at most, and none on sites that answer every URL
- a 403 on the homepage or a 429 anywhere ends the scan of that domain
- if many domains in a row block or time out, everything pauses

Before a larger run, please:

1. Set `INFO_URL` to a page that says who you are, what this is and how to opt
   out, and set `CONTACT` (or the `KMU_CONTACT` environment variable).
2. Put domains that asked to be left alone into `_input/opt_out.txt`.
3. Try 50 domains first and look at `requests.log` and the `scan_status` column.

All knobs are in `config/config.py`, with comments.

## Reading the output

- **Empty means "not measured"**, `False` means "looked and did not find it".
- `scan_status`: `ok`, `partial` (stopped early, see `scan_note`),
  `unreachable`, `http_error`, `blocked`, `disallowed_by_robots`,
  `skipped_platform` (the link points to Facebook, a Wix subdomain, …), `error`.
- `*_source` columns say where something was found (`sitemap`,
  `homepage_link`, `fallback_url`), `address_source` how sure the address is.
- `third_parties_without_consent` lists what Lighthouse saw loading without
  anyone clicking a cookie banner (needs the PageSpeed key).

The full column list is `FIELDNAMES` at the top of `main.py`.

## What it can't do

- **Only the delivered HTML is read.** Cookie banners and trackers that a
  script adds in the browser are invisible, unless the consent tool's own
  script tag gives them away or PageSpeed reports them.
- **Mostly the homepage.** Accessibility, language and contact checks say
  nothing about the rest of the site.
- **Heuristics miss and misfire.** Section detection works on keywords;
  "responsive" means a viewport tag plus width-dependent CSS; DNSSEC is judged
  by DS/DNSKEY records, not by validating signatures. Check a sample by hand
  before you trust a percentage.
- **Blocked is not random.** Sites behind a strict firewall drop out, and they
  are probably not the worst-secured ones.
- SPF/DMARC are looked up on the website's domain. Many small businesses send
  mail from somewhere else; `mail_mx_present` helps to tell these apart.

## Project layout

```
main.py                     orchestration, input/output, column list
config/config.py            settings
config/dictionary_config.py keyword lists and patterns
http_tools/client.py        the polite HTTP client (budget, throttling, robots)
http_tools/                 reachability, TLS, security headers, CDN hints
dns_tools/                  MX, SPF, DMARC, DNSSEC
analysis/                   homepage, language, sections, sitemaps, address, CMS
integrations/               PageSpeed and WhatCMS
tools/update_plz.py         downloads the postal code list
tests/                      pytest suite, runs against a local fake server
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

No test touches the internet.

## Credits & license

MIT, see `LICENSE`. If you build on it, a mention of
"KMU Webcheck by Marco Aures – https://marcoaures.ch" is appreciated.

The optional postal code list comes from swisstopo's *Amtliches
Ortschaftenverzeichnis* (open use, source must be named).

Bugs, ideas and cat pictures: see https://marcoaures.ch for contact details.
(Not on GitHub that often.)
