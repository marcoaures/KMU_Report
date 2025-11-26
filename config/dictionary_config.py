# dictionary_config.py
# Static dictionaries, keyword lists and mappings used by the main KMU Webcheck script.

import re

# ---------------------------------------------------------------------------
# Responsive design CSS heuristics
# ---------------------------------------------------------------------------

EXCLUDE_CSS_SUBSTRINGS = [
    "fonts.googleapis.com",
    "fontawesome",
    "fa-",
    "material-icons",
    "icons.css",
    "icon.css",
    "emoji.css",
    "admin.css",
    "editor.css",
    "wp-admin",
    "gutenberg",
    "login.css",
    "print.css",
]

MAIN_CSS_KEYWORDS = [
    "main",
    "style",
    "styles",
    "theme",
    "layout",
    "site",
    "app",
    "bundle",
    "front",
    "screen",
    "responsive",
]

# ---------------------------------------------------------------------------
# Career-related keywords and fallbacks — Multilingual, CH-relevant
# ---------------------------------------------------------------------------

CAREER_KEYWORDS = [
    # German
    "jobs", "karriere", "karriere-de", "stellen", "stellenangebote",
    "vakanz", "vakanzes", "offene-stellen", "offene stellen",
    "jobangebote", "berufschancen", "berufliche-laufbahn",
    "jobportal", "karrieremöglichkeiten",

    # French
    "carriere", "carrières", "offres-demploi", "offres d'emploi",
    "emplois", "postes-vacants", "postes vacants", "recrutement",
    "jobs-fr", "opportunites", "opportunités", "travail",

    # Italian
    "carriera", "lavoro", "offerte-di-lavoro", "offerte di lavoro",
    "posizioni-aperte", "posizioni aperte", "opportunita",
    "opportunità-di-carriera", "lavora-con-noi",

    # English
    "career", "careers", "jobs-en", "jobs", "vacancies",
    "open-positions", "openings", "job-openings",
    "work-with-us", "join-our-team",

    # Romansh
    "carriera-rm", "lavur", "lavurs", "posts-vacants",
    "occurrenzas-da-lavur", "occurrenzas",
]

CAREER_FALLBACK_PATHS = [
    # German
    "/jobs", "/karriere", "/stellen", "/stellenangebote",
    "/offene-stellen", "/jobportal",

    # French
    "/carriere", "/carrières", "/offres-demploi",
    "/postes-vacants", "/emplois", "/recrutement",

    # Italian
    "/carriera", "/lavoro", "/offerte-di-lavoro",
    "/posizioni-aperte", "/lavora-con-noi",

    # English
    "/career", "/careers", "/vacancies",
    "/open-positions", "/job-openings", "/work-with-us",

    # Romansh
    "/carriera-rm", "/lavur", "/posts-vacants",
]

# ---------------------------------------------------------------------------
# Blog / News keyword lists (CLEANED, high-precision)
# ---------------------------------------------------------------------------

BLOG_SITEMAP_KEYWORDS = [
    # German
    "aktuell", "aktuelles", "blog", "blogartikel", "blogs", "insights",
    "journal", "magazin", "magazine", "medienmitteilungen", "medien-news",
    "neues", "neuigkeiten", "news", "newsroom", "news-und-aktuelles",
    "news-und-stories", "news-aktuelles", "news-stories",
    "press", "presse", "pressemitteilungen", "ratgeber",
    "stories", "storys",

    # French
    "actualites", "les-actualites", "actualite", "actu", "actus",
    "nouvelles", "communiques", "communiques-de-presse",
    "centre-de-presse", "dossier-de-presse",

    # Italian
    "notizie", "novita", "attualita", "storie",
    "comunicati", "comunicati-stampa",
    "approfondimenti",

    # English
    "latest-news", "company-news", "news-and-stories",
    "press-releases", "press-release", "media-centre", "media-center",

    # Romansh
    "novitads", "actualitad", "actualitads",
    "actualitad-local", "actualitads-localas",
    "attualitads", "istorgias", "reportaschas",
    "artitgels",

    # Language-tag variants
    "news-de", "news-fr", "news-it", "news-en",
    "blog-de", "blog-fr", "blog-it", "blog-en",
]


BLOG_LINK_TEXT_KEYWORDS = [
    # German
    "aktuell", "aktuelles", "blog", "blogartikel", "blogs", "insights",
    "journal", "magazin", "magazine", "medienmitteilungen",
    "neues", "neuigkeiten", "news", "newsroom",
    "news und aktuelles", "news und stories",
    "presse", "pressemitteilungen", "ratgeber",
    "stories", "storys",

    # French
    "actualités", "les actualités", "actualité", "actu", "actus",
    "nouvelles", "communiqués", "communiqués de presse",
    "centre de presse", "dossier de presse",

    # Italian
    "notizie", "novità", "attualità", "storie",
    "comunicati", "comunicati stampa",
    "approfondimenti",

    # English
    "latest news", "company news", "news and stories",
    "press releases", "press release", "media centre",
    "media center",

    # Romansh
    "novitads", "actualitad", "actualitads",
    "actualitad local", "actualitads localas",
    "attualitads", "istorgias", "reportaschas",
]


BLOG_HREF_KEYWORDS = [
    # German
    "aktuell", "aktuelles", "blog", "blogartikel", "blogs", "insights",
    "journal", "magazin", "magazine", "medienmitteilungen",
    "medien-news", "neues", "neuigkeiten", "news", "newsroom",
    "news-und-aktuelles", "news-und-stories",
    "presse", "pressemitteilungen", "ratgeber",
    "stories", "storys",

    # French
    "actualites", "les-actualites", "actualite", "actu", "actus",
    "nouvelles", "communiques", "communiques-de-presse",
    "centre-de-presse", "dossier-de-presse",
    
    # Italian
    "notizie", "novita", "attualita", "storie",
    "comunicati", "comunicati-stampa",
    "approfondimenti",

    # English
    "latest-news", "company-news", "news-and-stories",
    "press-releases", "press-release", "media-centre",
    "media-center",

    # Romansh
    "novitads", "actualitad", "actualitads",
    "actualitad-local", "actualitads-localas",
    "attualitads", "istorgias", "reportaschas",
]


BLOG_FALLBACK_PATHS = [
    # German
    "/aktuell", "/aktuelles", "/blog", "/blogartikel", "/blogs", "/insights",
    "/journal", "/magazin", "/medienmitteilungen", "/medien-news",
    "/neues", "/neuigkeiten", "/news", "/newsroom",
    "/news-und-aktuelles", "/news-und-stories",
    "/presse", "/pressemitteilungen", "/ratgeber",
    "/stories", "/storys",

    # French
    "/actualites", "/les-actualites", "/actualite", "/actu", "/actus",
    "/nouvelles", "/communiques", "/communiques-de-presse",
    "/centre-de-presse", "/dossier-de-presse",

    # Italian
    "/notizie", "/novita", "/attualita", "/storie",
    "/comunicati", "/comunicati-stampa", "/approfondimenti",

    # English
    "/latest-news", "/company-news", "/news-and-stories",
    "/press-releases", "/press-release",
    "/media-centre", "/media-center",

    # Romansh
    "/novitads", "/actualitad", "/actualitads",
    "/actualitad-local", "/actualitads-localas",
    "/attualitads", "/istorgias", "/reportaschas",
]


# ---------------------------------------------------------------------------
# Imprint / Impressum
# ---------------------------------------------------------------------------

IMPRINT_SITEMAP_KEYWORDS = [
    # German (DE / CH)
    "impressum", "rechtliches", "rechtliche-hinweise", "anbieterkennzeichnung",
    "kontakt-impressum", "impressum-und-kontakt", "rechtliches-und-kontakt",
    "rechtliche-informationen", "haftungsausschluss", "disclaimer", "datenschutz-und-impressum",
    "anbieter", "anbieterinformationen",

    # French (FR / CH)
    "mentions-legales", "mentionslégales", "mentions-legale", "mention-legale",
    "mentions", "information-legale", "informations-legales", "editeur", "editeur-du-site",
    "responsabilite", "responsabilite-editoriale", "conditions-legales",

    # Italian (IT / CH)
    "note-legali", "nota-legale", "informazioni-legali", "informativa-legale",
    "editore", "responsabilita", "responsabilita-legale", "dati-societari",

    # English
    "imprint", "legal", "legal-notice", "legal-information", "legal-notices",
    "company-information", "company-details", "site-notice",

    # Romansh (RM)
    "impressum-rm", "indicaziuns-legalas", "infurmaziuns-legalas", "avis-legal",
]

IMPRINT_LINK_TEXT_KEYWORDS = [
    # German
    "impressum", "rechtliches", "rechtliche hinweise", "anbieterkennzeichnung",
    "kontakt impressum", "rechtliche informationen", "haftungsausschluss",
    "disclaimer", "datenschutz und impressum",

    # French
    "mentions légales", "mention légale", "informations légales",
    "éditeur", "éditeur du site", "responsabilité", "conditions légales",

    # Italian
    "note legali", "informazioni legali", "informativa legale",
    "editore", "responsabilità legale", "dati societari",

    # English
    "imprint", "legal notice", "legal information", "site notice",
    "company information", "company details",

    # Romansh
    "indicaziuns legalas", "infurmaziuns legalas", "avis legal", "impressum rm",
]

IMPRINT_HREF_KEYWORDS = [
    # German
    "impressum", "rechtliches", "rechtliche-hinweise", "anbieterkennzeichnung",
    "kontakt-impressum", "rechtliche-informationen", "haftungsausschluss",
    "disclaimer", "datenschutz-und-impressum",

    # French
    "mentions-legales", "mention-legale", "informations-legales",
    "editeur", "editeur-du-site", "responsabilite", "conditions-legales",

    # Italian
    "note-legali", "informazioni-legali", "informativa-legale",
    "editore", "responsabilita-legale", "dati-societari",

    # English
    "imprint", "legal", "legal-notice", "legal-information",
    "company-information", "site-notice",

    # Romansh
    "indicaziuns-legalas", "infurmaziuns-legalas", "avis-legal", "impressum-rm",
]
IMPRINT_FALLBACK_PATHS = [
    # German
    "/impressum", "/rechtliches", "/rechtliche-hinweise", "/anbieterkennzeichnung",
    "/kontakt-impressum", "/rechtliche-informationen", "/haftungsausschluss",
    "/disclaimer", "/datenschutz-und-impressum",

    # French
    "/mentions-legales", "/mention-legale", "/informations-legales",
    "/editeur", "/editeur-du-site", "/responsabilite", "/conditions-legales",

    # Italian
    "/note-legali", "/informazioni-legali", "/informativa-legale",
    "/editore", "/responsabilita-legale", "/dati-societari",

    # English
    "/imprint", "/legal", "/legal-notice", "/legal-information",
    "/company-information", "/site-notice",

    # Romansh
    "/indicaziuns-legalas", "/infurmaziuns-legalas", "/avis-legal", "/impressum-rm",
]

# ---------------------------------------------------------------------------
# Privacy Policy / Datenschutz
# ---------------------------------------------------------------------------

PRIVACY_SITEMAP_KEYWORDS = [
    # German
    "datenschutz", "datenschutzerklaerung", "datenschutzerklärung",
    "datenschutzbestimmungen", "datenschutzinformationen",
    "datenschutz-und-sicherheit", "datenschutzrichtlinie",
    "hinweise-zum-datenschutz", "privacy-de", "privacy-ch",

    # French
    "protection-des-donnees", "protection-donnees",
    "politique-de-confidentialite", "politique-confidentialite",
    "confidentialite", "donnees-personnelles",
    "traitement-des-donnees", "privacy-fr",

    # Italian
    "protezione-dei-dati", "protezione-dati",
    "informativa-sulla-privacy", "informativa-privacy",
    "privacy-it", "trattamento-dati",

    # English
    "privacy", "privacy-policy", "data-privacy", "data-protection",
    "privacy-notice", "privacy-statement", "cookie-and-privacy",
    "gdpr-privacy", "legal-privacy",

    # Romansh
    "proteccion-da-datas", "protecziun-da-datas",
    "politica-da-privadetgna", "privacy-rm",
]

PRIVACY_LINK_TEXT_KEYWORDS = [
    # German
    "datenschutz", "datenschutzerklärung", "datenschutzerklaerung",
    "datenschutzbestimmungen", "datenschutzinformationen",
    "hinweise zum datenschutz", "datenschutz und sicherheit",
    "datenschutzrichtlinie",

    # French
    "protection des données", "politique de confidentialité",
    "confidentialité", "données personnelles",
    "informations sur la confidentialité",

    # Italian
    "protezione dei dati", "informativa sulla privacy",
    "informativa privacy", "protezione dati", "trattamento dati",

    # English
    "privacy", "privacy policy", "data privacy", "data protection",
    "privacy notice", "privacy statement", "cookie and privacy",

    # Romansh
    "protecziun da datas", "politica da privadetgna",
    "infurmaziuns davart datas", "privacy rm",
]

PRIVACY_HREF_KEYWORDS = [
    # German
    "datenschutz", "datenschutzerklaerung", "datenschutzerklärung",
    "datenschutzbestimmungen", "datenschutzinformationen",
    "datenschutz-und-sicherheit", "datenschutzrichtlinie",
    "hinweise-zum-datenschutz",

    # French
    "protection-des-donnees", "politique-de-confidentialite",
    "confidentialite", "donnees-personnelles",

    # Italian
    "protezione-dei-dati", "informativa-sulla-privacy",
    "informativa-privacy", "trattamento-dati",

    # English
    "privacy", "privacy-policy", "data-privacy", "data-protection",
    "privacy-notice", "privacy-statement",

    # Romansh
    "protecziun-da-datas", "politica-da-privadetgna",
    "proteccion-da-datas",
]

PRIVACY_FALLBACK_PATHS = [
    # German
    "/datenschutz", "/datenschutzerklaerung", "/datenschutzerklärung",
    "/datenschutzbestimmungen", "/datenschutzinformationen",
    "/datenschutz-und-sicherheit", "/datenschutzrichtlinie",
    "/hinweise-zum-datenschutz",

    # French
    "/protection-des-donnees", "/politique-de-confidentialite",
    "/confidentialite", "/donnees-personnelles",

    # Italian
    "/protezione-dei-dati", "/informativa-sulla-privacy",
    "/informativa-privacy", "/trattamento-dati",

    # English
    "/privacy", "/privacy-policy", "/privacy-notice",
    "/privacy-statement", "/data-privacy", "/data-protection",

    # Romansh
    "/protecziun-da-datas", "/politica-da-privadetgna",
    "/proteccion-da-datas",
]

# ---------------------------------------------------------------------------
# Terms & Conditions / AGB — Multilingual, CH-relevant, expanded lists
# ---------------------------------------------------------------------------

TERMS_SITEMAP_KEYWORDS = [
    # German
    "agb", "a-g-b", "allgemeine-geschäftsbedingungen",
    "allgemeine geschaeftsbedingungen", "allgemeine geschäftsbedingungen",
    "geschaeftsbedingungen", "geschäftsbedingungen", "nutzungsbedingungen",
    "nutzungsbedingung", "rechtliche-bedingungen", "geschaeftsordnung",
    "vertragliche-bedingungen", "bedingungen",

    # French
    "conditions-generales", "conditions générales",
    "conditions-generales-de-vente", "conditions-generales-de-service",
    "conditions-de-vente", "conditions-dutilisation",
    "conditions-utilisation", "conditions-generales-dutilisation",
    "cgv", "cgu", "termes-et-conditions",

    # Italian
    "termini-e-condizioni", "termini di utilizzo",
    "condizioni-generali", "condizioni-generali-di-vendita",
    "condizioni-duso", "condizioni-di-servizio",
    "termini", "termini-utilizzo",

    # English
    "terms", "terms-and-conditions", "terms-of-service",
    "general-terms", "general-conditions",
    "terms-of-use", "user-terms", "service-terms",
    "tos", "agreement",

    # Romansh
    "cundiziuns-generalas", "cundiziuns-da-utilisaziun",
    "cundiziuns", "terms-rm",
]


TERMS_LINK_TEXT_KEYWORDS = [
    # German
    "agb", "allgemeine geschäftsbedingungen",
    "allgemeine geschaeftsbedingungen", "geschäftsbedingungen",
    "nutzungsbedingungen", "rechtliche bedingungen",
    "vertragliche bedingungen",

    # French
    "conditions générales", "conditions générales de vente",
    "conditions d'utilisation", "conditions générales d'utilisation",
    "cgv", "cgu", "termes et conditions",

    # Italian
    "termini e condizioni", "condizioni generali",
    "termini di utilizzo", "condizioni di servizio",
    "condizioni d'uso",

    # English
    "terms", "terms and conditions", "terms of use",
    "terms of service", "general terms", "general conditions",
    "service terms",

    # Romansh
    "cundiziuns generalas", "cundiziuns d'utilisaziun",
    "cundiziuns", "terms rm",
]


TERMS_HREF_KEYWORDS = [
    # German
    "agb", "allgemeine-geschäftsbedingungen",
    "allgemeine-geschaeftsbedingungen", "geschaeftsbedingungen",
    "nutzungsbedingungen", "rechtliche-bedingungen",
    "vertragliche-bedingungen",

    # French
    "conditions-generales", "conditions-generales-de-vente",
    "conditions-generales-dutilisation", "conditions-dutilisation",
    "cgv", "cgu", "termes-et-conditions",

    # Italian
    "termini-e-condizioni", "condizioni-generali",
    "termini-di-utilizzo", "condizioni-di-servizio",
    "condizioni-duso",

    # English
    "terms", "terms-and-conditions", "terms-of-service",
    "terms-of-use", "general-terms", "general-conditions",
    "service-terms", "tos",

    # Romansh
    "cundiziuns-generalas", "cundiziuns-da-utilisaziun",
    "cundiziuns", "terms-rm",
]


TERMS_FALLBACK_PATHS = [
    # German
    "/agb", "/allgemeine-geschäftsbedingungen",
    "/allgemeine-geschaeftsbedingungen", "/geschaeftsbedingungen",
    "/nutzungsbedingungen",

    # French
    "/conditions-generales", "/conditions-generales-de-vente",
    "/conditions-dutilisation", "/conditions-generales-dutilisation",
    "/cgv", "/cgu",

    # Italian
    "/termini-e-condizioni", "/condizioni-generali",
    "/termini-di-utilizzo", "/condizioni-di-servizio",

    # English
    "/terms", "/terms-and-conditions", "/terms-of-service",
    "/terms-of-use", "/general-terms",

    # Romansh
    "/cundiziuns-generalas", "/cundiziuns-da-utilisaziun",
]

# ---------------------------------------------------------------------------
# Language / localization dictionaries
# ---------------------------------------------------------------------------

LANG_NAME_TO_CODE = {
    "de": "de",
    "deutsch": "de",
    "german": "de",
    "fr": "fr",
    "français": "fr",
    "french": "fr",
    "it": "it",
    "italiano": "it",
    "italian": "it",
    "en": "en",
    "english": "en",
    "rm": "rm",
    "rumantsch": "rm",
    "rätoromanisch": "rm",
}

COUNTRY_FLAG_TO_LANG = {
    "de": "de",
    "at": "de",
    "ch": None,
    "fr": "fr",
    "it": "it",
    "gb": "en",
    "uk": "en",
    "us": "en",
    "en": "en",
}


# ---------------------------------------------------------------------------
# Social media link detection
# ---------------------------------------------------------------------------

SOCIAL_DOMAINS = {
    "linkedin.com": "LinkedIn",
    "facebook.com": "Facebook",
    "instagram.com": "Instagram",
    "x.com": "X",
    "twitter.com": "Twitter",
    "youtube.com": "YouTube",
    "tiktok.com": "TikTok",
}


# ---------------------------------------------------------------------------
# Analytics tools pattern detection
# ---------------------------------------------------------------------------

TAG_MANAGER_PATTERNS = {
    # Google Tag Manager
    "googletagmanager.com/gtm.js": "GTM",
    "googletagmanager.com/ns.html": "GTM",

    # Tealium iQ Tag Manager
    "tags.tiqcdn.com": "Tealium",
    "utag.js": "Tealium",

    # Adobe Launch / Adobe DTM
    "assets.adobedtm.com": "Adobe Launch",
    "adobedtm.com": "Adobe DTM",

    # Segment
    "cdn.segment.com/analytics.js": "Segment",
    "cdn.segment.com": "Segment",

    # Piwik PRO Tag Manager
    "piwik.pro": "Piwik PRO Tag Manager",
    "ppms.php": "Piwik PRO Tag Manager",

    # Matomo Tag Manager
    "matomo.js": "Matomo Tag Manager",
    "matomoTagManager": "Matomo Tag Manager",
}

# ---------------------------------------------------------------------------
# Cookie / Consent tools pattern detection – CH-focused, conservative on FPs
# ---------------------------------------------------------------------------

# External cookie / CMP script & stylesheet URLs
# substring in src/href → Vendor label
COOKIE_PATTERNS = {
    # Existing
    "cookiebot.com": "Cookiebot",
    "consent.cookiebot.com": "Cookiebot",
    "onetrust.com": "OneTrust",
    "cookielaw.org": "OneTrust",
    "usercentrics.eu": "Usercentrics",
    "usercentrics.com": "Usercentrics",
    "privacy-mgmt.com": "SourcePoint",
    "trustpid.com": "TrustPid",

    # Common EU / CH CMPs
    "consentmanager.net": "consentmanager",
    "cookiefirst.com": "CookieFirst",
    "cookieinformation.com": "CookieInformation",
    "cookie-script.com": "CookieScript",
    "cookiehub.eu": "CookieHub",
    "cookiepro.com": "CookiePro",
    "cookieyes.com": "CookieYes",
    "didomi.io": "Didomi",
    "trustarc.com": "TrustArc",
    "truste.com": "TrustArc",
    "iubenda.com": "Iubenda",
    "osano.com": "Osano",
    "termly.io": "Termly",

    # IAB TCF / frameworks
    "consensu.org": "IAB TCF",
    "quantcast.mgr.consensu.org": "Quantcast Choice",
    "quantcast.com": "Quantcast Choice",
    "fundingchoicesmessages.google.com": "Google Funding Choices",
}

# CMP / cookie tooling detection (inline JS heuristics)
COOKIE_INLINE_PATTERNS = {
    "cookiebot": "Cookiebot",
    "onetrust": "OneTrust",
    "usercentrics": "Usercentrics",
    "consentmanager": "consentmanager",
    "didomi": "Didomi",
    "cookieyes": "CookieYes",
    "iubenda": "Iubenda",
    "trustarc": "TrustArc",
    "cookieinformation": "CookieInformation",
    "cookiehub": "CookieHub",
    "cookiepro": "CookiePro",
    "fundingchoices": "Google Funding Choices",
    "borlabs": "Borlabs",
    "tarteaucitron": "Tarteaucitron",
}

# Stage 1: strong, cookie-/privacy-specific container tokens (id/class)
# → These must stay fairly strict to avoid FPs; text is still confirmed by COOKIE_INFO_PHRASES.
COOKIE_BANNER_CONTAINER_TOKENS = [
    # Generic cookie / privacy
    "cookie",
    "cookies",
    "consent",
    "gdpr",
    "privacy",
    "cmp",

    # DE / CH-DE
    "datenschutz",
    "dsgvo",   # EU
    "dsg",     # CH
    "ndsg",     # CH
    "revdsg",     # CH
    "einwilligung",
    "zustimmung",
    "privatsphäre",

    # FR / CH-FR
    "confidentialite",
    "confidentialité",
    "vie-privee",
    "vie_privée",
    "vieprivee",
    "donnees-personnelles",
    "donnees_personnelles",
    "données-personnelles",
    "données_personnelles",

    # IT / CH-IT
    "protezione-dati",
    "protezione_dati",
    "protezionedati",
    "dati-personali",
    "dati_personali",
    "datipersonali",
]

# Stage 2: fallback generic modal/container tokens
# → Used only if Stage 1 found nothing AND text matches COOKIE_INFO_PHRASES.
COOKIE_BANNER_FALLBACK_TOKENS = [
    "overlay",
    "modal",
    "popup",
    "pop-up",
    "dialog",
    "banner",
]

# Text phrases that indicate cookie info (all lowercased, substring match).
# This is where we aggressively extend DE/FR/IT, but still always with “cookie(s)”.
COOKIE_INFO_PHRASES = [
    # EN
    "this website uses cookies",
    "this site uses cookies",
    "we use cookies",
    "we use cookies to",
    "by using this website you agree to our use of cookies",
    "by continuing to use this site you accept the use of cookies",
    "cookie policy",
    "cookie notice",
    "cookie settings",
    "cookie preferences",

    # DE / CH-DE
    "diese website verwendet cookies",
    "diese webseite verwendet cookies",
    "diese seite verwendet cookies",
    "wir verwenden cookies",
    "wir nutzen cookies",
    "wir setzen cookies",
    "auf dieser website werden cookies verwendet",
    "durch die nutzung dieser website stimmen sie der verwendung von cookies zu",
    "mit der weiteren nutzung der website stimmen sie der verwendung von cookies zu",
    "hinweis zu cookies",
    "hinweis über cookies",
    "cookie-richtlinie",
    "cookierichtlinie",
    "cookie-hinweis",
    "cookiehinweis",
    "cookie-einstellungen",
    "cookie einstellungen",

    # FR / CH-FR
    "ce site utilise des cookies",
    "ce site web utilise des cookies",
    "nous utilisons des cookies",
    "nous recourons à des cookies",
    "en utilisant ce site, vous acceptez les cookies",
    "en poursuivant votre navigation sur ce site, vous acceptez l'utilisation de cookies",
    "en continuant à naviguer sur ce site, vous acceptez l'utilisation de cookies",
    "politique de cookies",
    "politique relative aux cookies",
    "paramètres des cookies",
    "préférences cookies",

    # IT / CH-IT
    "questo sito utilizza cookie",
    "questo sito web utilizza cookie",
    "utilizziamo i cookie",
    "usiamo i cookie",
    "continuando la navigazione acconsenti all'uso dei cookie",
    "continuando a utilizzare questo sito acconsenti all'uso dei cookie",
    "proseguendo nella navigazione autorizzi l'uso dei cookie",
    "informativa sui cookie",
    "informativa cookie",
    "impostazioni cookie",
    "preferenze cookie",
]

# Strong indicators of real consent / granular control (all lowercased).
# Checked only inside already-confirmed cookie containers.
COOKIE_STRONG_CONSENT_PHRASES = [
    # EN
    "only essential cookies",
    "only necessary cookies",
    "necessary cookies only",
    "only technical cookies",
    "functional cookies only",
    "allow only required cookies",
    "use only required cookies",
    "disable non-essential cookies",
    "opt out of non-essential cookies",

    # DE / CH-DE
    "nur notwendige cookies",
    "nur essenzielle cookies",
    "nur funktionale cookies",
    "nur technisch notwendige cookies",
    "nur technisch notwendige",
    "nur erforderliche cookies",
    "optionale cookies deaktivieren",
    "nicht notwendige cookies deaktivieren",
    "nicht notwendige cookies ablehnen",
    "marketing-cookies deaktivieren",
    "analyse-cookies deaktivieren",
    "nur unbedingt erforderliche cookies verwenden",

    # FR / CH-FR
    "cookies essentiels uniquement",
    "seulement les cookies nécessaires",
    "seulement les cookies essentiels",
    "uniquement les cookies nécessaires",
    "uniquement les cookies essentiels",
    "cookies fonctionnels uniquement",
    "désactiver les cookies non essentiels",
    "désactiver les cookies non nécessaires",
    "refuser les cookies non essentiels",
    "refuser les cookies non nécessaires",

    # IT / CH-IT
    "solo i cookie necessari",
    "solo cookie necessari",
    "solo i cookie essenziali",
    "solo cookie essenziali",
    "solo cookie tecnici",
    "consenti solo i cookie necessari",
    "consenti solo i cookie tecnici",
    "disattiva i cookie non essenziali",
    "disattiva i cookie non necessari",
    "rifiuta i cookie non essenziali",
]

# Button label patterns (all lowercased, substring match).
# Used only on buttons/links inside a confirmed cookie banner container.
COOKIE_ACCEPT_BUTTON_LABELS = [
    # EN
    "accept all",
    "accept cookies",
    "accept",
    "allow all",
    "allow cookies",
    "agree",
    "i agree",
    "accept all cookies",
    "agree and accept",
    "agree and continue",
    "agree to all",

    # DE / CH-DE
    "alle akzeptieren",
    "cookies akzeptieren",
    "cookies zulassen",
    "akzeptieren",
    "alle zulassen",
    "zustimmen",
    "ich stimme zu",
    "einverstanden",
    "na klar",
    "na klar!",
    "ja, gerne",
    "ja gerne",

    # FR / CH-FR
    "tout accepter",
    "accepter tout",
    "accepter les cookies",
    "accepter",
    "autoriser tous les cookies",
    "j'accepte",

    # IT / CH-IT
    "accetta tutti i cookie",
    "accetta tutti",
    "accetta i cookie",
    "accetta",
    "consenti tutti i cookie",
    "consenti tutti",
    "consenti",
]

COOKIE_REJECT_BUTTON_LABELS = [
    # EN
    "reject all",
    "reject",
    "decline all",
    "decline",
    "deny",
    "continue without accepting",
    "continue without cookies",
    "use only necessary cookies",
    "only use necessary cookies",
    "no thanks",
    "no, thanks",
    "reject non-essential cookies",
    "decline non-essential cookies",
    "reject optional cookies",
   
    # DE / CH-DE
    "alle ablehnen",
    "ablehnen",
    "nicht akzeptieren",
    "ohne cookies fortfahren",
    "ohne zustimmung fortfahren",
    "nur notwendige cookies",
    "nur essenzielle cookies",
    "nur funktionale cookies",
    "nur technisch notwendige cookies",
    "nein danke",
    "nein, danke",

    # FR / CH-FR
    "tout refuser",
    "refuser tout",
    "refuser",
    "continuer sans accepter",
    "utiliser uniquement les cookies nécessaires",

    # IT / CH-IT
    "rifiuta tutti",
    "rifiuta",
    "continua senza accettare",
    "usa solo i cookie necessari",
    "utilizza solo i cookie necessari",
]

COOKIE_SETTINGS_BUTTON_LABELS = [
    # EN
    "cookie settings",
    "manage cookies",
    "manage cookie settings",
    "cookie preferences",
    "preferences",
    "settings",
    "customize",
    "customise",
    "more options",
    "show details",
    "manage my choices",
    "manage your choices",
    "save preferences",
    "save my choices",

    # DE / CH-DE
    "cookie-einstellungen",
    "cookie einstellungen",
    "cookies verwalten",
    "cookie-konfiguration",
    "weitere einstellungen",
    "individuelle einstellungen",
    "details anzeigen",
    "präferenzen",
    "einstellungen",

    # FR / CH-FR
    "paramètres des cookies",
    "paramètres cookies",
    "gérer les cookies",
    "gestion des cookies",
    "préférences cookies",
    "préférences",
    "personnaliser les cookies",
    "personnaliser",
    "en savoir plus",
    "afficher les détails",
    "paramètres",
    "enregistrer les préférences",
    "enregistrer mes choix",
    "gérer mes choix",

    # IT / CH-IT
    "impostazioni cookie",
    "gestisci i cookie",
    "gestisci preferenze",
    "preferenze cookie",
    "personalizza i cookie",
    "personalizza",
    "maggiori informazioni",
    "visualizza dettagli",
    "impostazioni",
    "salva le preferenze",
    "salva i miei preferenze",
    "gestisci le scelte",
]

# Generic “OK” / confirmation labels when no explicit choice is offered.
# Still only used inside containers that already matched COOKIE_INFO_PHRASES.
COOKIE_GENERIC_OK_LABELS = [
    # EN
    "ok",
    "okay",
    "got it",
    "got it!",
    "understood",
    "close",

    # DE / CH-DE
    "ok, verstanden",
    "ok",
    "okay",
    "verstanden",
    "schliessen",
    "schließen",
    "weiter",
   
    # FR / CH-FR
    "d'accord",
    "c'est bon",
    "ok",
    "fermer",
    "continuer",

    # IT / CH-IT
    "va bene",
    "ok",
    "ho capito",
    "chiudi",
    "continua",
]

# ---------------------------------------------------------------------------
# Contact detection patterns
# ---------------------------------------------------------------------------

EMAIL_REGEX = re.compile(
    r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
    re.IGNORECASE,
)

EMAIL_IGNORED_LOCALPARTS = [
    "no-reply",
    "noreply",
    "do-not-reply",
    "donotreply",
    "bounce",
]

# Swiss phone formats (international +41 xx xxx xx xx, national 0xx xxx xx xx)
SWISS_PHONE_PATTERNS = [
    re.compile(r"\+41\s?[1-9]\d\s?\d{3}\s?\d{2}\s?\d{2}"),
    re.compile(r"0[1-9]\d\s?\d{3}\s?\d{2}\s?\d{2}"),
]

# ZIP + city (very simple heuristic)
ZIP_CITY_REGEX = re.compile(
    r"\b(\d{4})\s+([A-ZÄÖÜ][A-Za-zÄÖÜäöüéèàâêîôûçß\- ]{2,})"
)

CONTACT_LINK_TEXTS = [
    # DE
    "kontakt", "kontaktformular",
    # EN
    "contact", "contact us",
    # FR
    "contactez-nous", "nous contacter", "contact",
    # IT
    "contatto", "contatti",
    # Romansh (super simple)
    "cuntact",
]
CONTACT_LINK_TEXTS_L = [t.lower() for t in CONTACT_LINK_TEXTS]

# ---------------------------------------------------------------------------
# Decorative image detection & image categorization
# ---------------------------------------------------------------------------

ICON_DECORATIVE_TOKENS = [
    "icon", "ico-", "-ico", "sprite", "arrow", "caret", "chevron",
    "hamburger", "burger", "menu-", "-menu", "close", "xmark",
    "prev", "next", "scroll", "slider", "bullet", "dot",
    "rating-star", "star-", "-star", "flag-", "-flag", "lang-",
]

SOCIAL_TOKENS = [
    "facebook", "instagram", "linkedin", "xing", "twitter", "x.com",
    "whatsapp", "tiktok", "youtube", "vimeo", "pinterest",
]

PAYMENT_TOKENS = [
    "visa", "mastercard", "mc_", "amex", "maestro", "paypal",
    "twint", "applepay", "googlepay", "postfinance",
]

# ---------------------------------------------------------------------------
# Interactive Elements
# ---------------------------------------------------------------------------

INTERACTIVE_ROLES = {
    "button", "link", "menuitem", "tab", "checkbox",
    "switch", "radio", "option",
}

INTERACTIVE_CLASS_TOKENS = [
    "btn",
    "button",
    "cta",
]
