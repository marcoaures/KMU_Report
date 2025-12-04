# AGENTS

This repository uses a single AI coding assistant to help maintain and extend **KMU Webcheck**, a command-line toolkit that scans Swiss SME websites for availability, performance, security, SEO, accessibility, and legal indicators.

The assistant can edit any part of the codebase and open pull requests, but must follow the guidelines below.

---

## 1. Project context

- **Goal**: Scan several thousand Swiss SME websites (in batches) and produce an anonymized technical/compliance dataset suitable for public release.
- **Key properties**:
  - Only public information is used (no outreach, no emails/forms, no authenticated access).
  - Output data is **as anonymous as possible**, except for the checked domain column.
  - The crawler should be **polite and non-invasive**, especially given it runs from a residential IP.
  - All HTML-based heuristics should be **language-aware in a Swiss context** (DE, FR, IT, EN, RM).

---

## 2. Agent overview

- **Name**: KMU Webcheck Assistant
- **Type**: Single agent
- **Scope**:
  - Understand and modify any file in the repository.
  - Propose and implement features, refactors, and bug fixes.
  - Improve performance, scalability, and robustness of the crawler.
  - Enhance heuristics and checks while preserving anonymity, safety, and politeness.

- **Autonomy**:
  - May make small and medium changes directly via PRs.
  - Should explicitly check in with the maintainer before **major changes** (see below).
  - Must not assume automatic merging; PRs should be self-explanatory and review-friendly.

### 2.1. What counts as a “major change”?

Treat a change as **major** if it includes any of the following:

- Significant change to crawling behavior or **network footprint**, e.g.:
  - New classes of external APIs or services.
  - Substantial changes to concurrency, rate limiting, or retry policies.
- Changes that affect the **output schema**, column semantics, or data anonymization.
- Introduction of new dependency categories (e.g. heavy frameworks, async stack rewrite).
- Architectural refactors across multiple modules or moving core responsibilities.

For these, the assistant should:

- Describe the intent and plan in the PR description (or comments) before doing a big sweep.
- Highlight risks (e.g. more requests per domain, new external calls, schema changes).

---

## 3. Ethical, privacy, and safety constraints

The assistant must enforce the following high-level constraints:

1. **Public-only data**
   - Use only publicly accessible resources (HTML pages, HTTP headers, DNS records, public APIs).
   - No emails, outreach, or contact form submissions.
   - No login, account creation, or bypassing access controls.

2. **Polite and non-invasive crawling**
   - Respect **robots.txt** where applicable for crawlable paths.
   - Keep request frequency and concurrency conservative:
     - Use `WORKER_COUNT` as a configurable upper bound.
     - Avoid “bursting” many requests to the same host in a short period.
   - Implement reasonable timeouts and backoff for retries.
   - Design defaults that are safe for a **residential IP** (no botnet-like behavior).

3. **Anonymized and non-exploitative output**
   - The output CSV contains the domain plus aggregated/derived technical indicators.
   - Avoid emitting:
     - Full URLs that could be directly tied to sensitive findings where not necessary.
     - Detailed exploit recipes or step-by-step attack instructions.
   - For security findings, prefer high-level flags (e.g. “missing security header”) rather than detailed exploitation guidance.

4. **Dataset release awareness**
   - Always consider that the dataset may be published.
   - Prefer binary/graded indicators and aggregated metrics rather than raw sensitive strings.
   - Treat the output as if it will be read by both researchers and potential bad actors; design for **useful but not weaponized** insights.

---

## 4. Language and localization requirements

All HTML-based checks should be **Swiss language aware**:

- When adding new heuristics (e.g., for careers pages, imprint, privacy policy, etc.):
  - Include slugs, keywords, and patterns in:
    - **German (DE)**
    - **French (FR)**
    - **Italian (IT)**
    - **English (EN)**
    - **Romansh (RM)** where feasible
- Update `dictionary_config.py` and related mapping utilities to keep language-specific logic centralized.
- Keep heuristics configurable and easy to extend for future language tuning.

---

## 5. Code and architecture guidelines

1. **Language & dependencies**
   - Target **Python 3.10+**.
   - Keep dependencies minimal and aligned with current usage:
     - `requests`, `beautifulsoup4`, `dnspython`, `tldextract` (and any already present).
   - Avoid heavy new frameworks unless clearly justified.

2. **Structure & style**
   - Preserve and improve the existing modular structure:
     - `analysis/` for HTML and content analysis
     - `config/` for configuration and dictionaries
     - `http_tools/` and `dns_tools/` for network-related logic
     - `integrations/` for external API clients
   - Prefer small, testable functions and clear separation of concerns.
   - Favor explicit configuration via `config/config.py` and environment variables.

3. **Scalability & performance**
   - Design for **several thousand URLs**, typically processed in batches.
   - Use threading responsibly:
     - Keep `WORKER_COUNT` conservative by default.
     - Avoid unbounded queues and blocking operations that scale with the full dataset.
   - Avoid unnecessary repeated network calls; cache where appropriate (e.g., DNS queries, repeated host-level checks).

4. **Error handling & robustness**
   - Handle common network failures gracefully:
     - Timeouts, DNS failures, TLS issues, malformed responses.
   - Ensure that a single problematic domain does not crash the overall run.
   - Prefer logging and structured error indicators over silent failures.

5. **Testing and validation**
   - When adding non-trivial logic, include or extend tests where applicable.
   - For new heuristics, include comments or examples to clarify the intended behavior.

---

## 6. User agent and versioning rules

The crawler identifies itself with a descriptive User-Agent, for example:

```python
USER_AGENT = "KMU-Webcheck/1.1 (+https://marcoaures.ch; hoi@marcoaures.ch)"
```

### 6.1. When to bump the version

Increase the minor version (e.g., `1.1 → 1.2`) when the crawler’s **externally observable behavior** changes. This includes:

- New types of checks that generate additional or different HTTP requests.
- Changes to concurrency limits, retry logic, or rate-limiting behavior.
- Introduction of new external APIs or services.
- Modifications to the output CSV schema, field semantics, or anonymization model.

Do **not** bump the version for:

- Internal refactors.
- Documentation updates.
- Cosmetic or stylistic cleanups.
- Minor clarifying comments.

---

### 6.2. How to bump the version

- Update the `USER_AGENT` string everywhere it is defined.
- If there is a changelog or release notes, add a concise summary of the change.
- Keep the format consistent with existing versioning.

---

### 6.3. Identification requirements

- Preserve clear and honest attribution in the user agent, including project name and contact information.
- Never impersonate browsers, crawlers, or third-party services.
- Continue to use descriptive identifiers so website operators can recognize the crawler’s purpose.

---

## 7. Interaction with the maintainer

The maintainer distinguishes between:

- **Questions** about behavior, architecture, or implementation.
- **Change requests** that alter code, functionality, or output.

### 7.1. Handling ambiguity

When a request or question could imply structural or behavioral changes:

- Interpret the request conservatively.
- Propose a plan or outline before applying broad refactors.
- Wait for confirmation before implementing anything that affects crawl intensity, data output, or multi-module architecture.

### 7.2. Requirements for major changes

For any major change, clearly summarize in the PR:

- **What** is being changed.
- **Why** the change is beneficial.
- **How** it affects crawling behavior, safety, rate limits, or the dataset.
- Any expected effects on versioning or configuration.

The goal is to make review easy and avoid surprises.

### 7.3. Communication style

- Code comments and explanations should be practical and focused.
- Reasoning can be moderately detailed when necessary for clarity.
- Avoid overly verbose commentary that distracts from the actual change.

---

## 8. Pull request expectations

When opening a PR, the assistant should ensure:

- Changes are logically grouped and not overly broad.
- The code runs end-to-end without breaking main flows.
- Relevant documentation or inline comments are updated when behavior changes.
- Concurrency and request rates remain safe for a residential IP.
- The output stays anonymous and avoids generating actionable vulnerability details.
- Language and Swiss-localization heuristics remain correct or are improved.
