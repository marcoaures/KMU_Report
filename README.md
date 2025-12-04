# KMU Webcheck

A command-line toolkit that scans websites for availability, performance, security, SEO, accessibility, and legal indicators. It ingests a CSV of domains and produces a consolidated report that highlights technical gaps and compliance risks for small and medium-sized businesses (with a focus on Switzerland).

**Version 2.1:** Public release version

**Disclaimer:** This project includes refactoring and documentation improvements made with the help of AI tools.

## Features
- **Availability & DNS**: Reachability checks, HTTPS enforcement, HSTS header detection, CDN/WAF hints, DNSSEC/SPF/DMARC lookups, and TLS handshake details.
- **Sitemaps & sections**: robots.txt discovery, sitemap probing, URL and lastmod counting, and detection of blog/news, careers, imprint, privacy policy, and terms pages using sitemap hints, homepage links, and fallback paths.
- **Homepage analysis**: Structured data JSON-LD discovery, social profile extraction, responsive-design heuristics, analytics and tag manager detection, cookie banner UI heuristics, and contact info signals (email/phone/address).
- **Language & localization**: HTML/meta language tags, visible-text language detection, hreflang parsing, and language switcher/URL hints.
- **Performance & responsiveness**: PageSpeed scores (via API) and responsive-design signals based on CSS usage and viewport hints.
- **Accessibility**: Alt-text coverage, logo and body image tagging, heading structure, ARIA usage, and heuristics for clickable non-link elements.
- **Trust signals**: Security headers, cookie/consent choice likelihood, and discovery of `.well-known/security.txt` and `llms.txt`.

## Attribution & License

If you use or adapt this project, please attribute it as follows:

```
KMU Webcheck by Marco Aures  
Source: https://marcoaures.ch
Licensed under CC BY-NC 4.0 – https://creativecommons.org/licenses/by-nc/4.0/
```

## Project structure
```
main.py                    # Entry point: orchestrates all checks and writes the output CSV
analysis/
  html_analysis.py         # Homepage parsing for analytics, cookies, accessibility, language, responsiveness
  language_localization.py # Language detection helpers and hreflang parsing
  sections.py              # Blog/news, careers, imprint, privacy, and terms detection
  sitemap_utils.py         # robots.txt and sitemap discovery/parsing utilities
config/
  config.py                # Paths, worker count, and global settings loaded via environment variables
  dictionary_config.py     # Keyword lists and patterns for section and consent detection
http_tools/
  http_utils.py            # HTTP helpers, reachability, HTTPS enforcement, and HSTS checks
  security_http.py         # Security header and .well-known file checks
  tls_utils.py             # TLS handshake and certificate parsing
  cdn_utils.py             # CDN/WAF heuristics using DNS and HTTP signals
integrations/api_clients.py # PageSpeed Insights and WhatCMS API helpers
dns_tools/dns_security.py   # SPF, DMARC, and DNSSEC checks
```

## Setup
- Python 3.10+ is recommended.
- Install the required Python packages:
  ```bash
  pip install requests beautifulsoup4 dnspython tldextract
  ```
- Create `_input/` and `_output/` directories if they do not exist.
- Optional API keys (set as environment variables or export them before running):
  - `PAGESPEED_API_KEY` for Google PageSpeed Insights
  - `WHATCMS_API_KEY` for CMS detection

## Running a scan
1. Place your input CSV under `_input/` or update `INPUT_CSV` in `config/config.py`.
2. Ensure the CSV is semicolon-delimited and contains a `website` header, for example:
   ```csv
   name;address;industry;website
   Beispiel AG;Bern;Töpferei;https://beispiel.ch
   ```
3. Update `OUTPUT_CSV` in `config/config.py` to control where the results are written (default `_output/output.csv`).
4. (Optional) Adjust `WORKER_COUNT`, progress logging flags, API toggles (`DEBUG_API`, `SKIPPING_APIS`, `WHATCMS_PRIVATE`), the checkpointing frequency (`CHECKPOINT_INTERVAL`), or batch controls (`DOMAIN_OFFSET`, `DOMAINS_PER_RUN`) in `config/config.py` if needed.
5. Run the scanner:
   ```bash
   python main.py
   ```

Batch controls:
- `DOMAIN_OFFSET` lets you skip a fixed number of initial CSV rows (useful to resume interrupted runs).
- `DOMAINS_PER_RUN` caps how many domains are processed in one execution (leave unset or `<=0` to process all rows).
Both can be set via environment variables or directly in `config/config.py`.

## Output
The generated CSV includes the domain and numerous columns spanning availability, SEO/content sections, language, accessibility, performance, security, compliance, and trust signals. See the `fieldnames` list in `main.py` for the definitive set of columns.

## Notes
- Respect external API rate limits; PageSpeed and WhatCMS calls can be skipped via `SKIPPING_APIS` in `config/config.py` if you only need local checks.
- The tool uses threading for concurrency; keep `WORKER_COUNT` conservative to avoid overloading target sites.

## Contact
Report bugs, share ideas, or send cat pics to [hoi@marcoaures.ch](mailto:hoi@marcoaures.ch)

(Not on GitHub that often.)
