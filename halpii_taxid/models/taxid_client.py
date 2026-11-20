# Copyright 2026 HALPII S.A.C.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).
"""Small HTTP client for the HALPII Tax ID API (https://taxid.halpii.com).

It only knows how to route a (country, number) pair to the right endpoint and
turn the HTTP answer into either a result dict or a ``TaxIdApiError`` with a
message the user can act on. It does not touch the database.

The list of supported countries is not fixed in this file: it is read from
``GET /v1/countries`` and kept in memory for a day (per Odoo worker). The
embedded list below is only used while the API cannot be reached.
"""
import collections
import re
import threading
import time

import requests

DEFAULT_BASE_URL = "https://taxid.halpii.com"
TIMEOUT = 20  # the API gives up on a slow registry after ~8 s
USER_AGENT = "HALPII-TaxID-Odoo/1.1"

COUNTRIES_TIMEOUT = 10  # the list is a small cached document
COUNTRIES_TTL = 24 * 3600  # refresh the list once a day
COUNTRIES_RETRY = 3600  # after a failed refresh, wait before asking again

# Countries with their own lookup endpoint (the generic /v1/validate refuses them).
DEDICATED = {
    "PE": "/v1/pe/ruc/%s",
    "MX": "/v1/mx/rfc/%s",
    "CO": "/v1/co/nit/%s",
    "CR": "/v1/cr/cedula/%s",
}

# Backup copy of GET /v1/countries as of 2026-11-20 (121 countries and
# territories). Only used while the live list cannot be fetched; in that case a
# country missing here is still sent to the API, which has the last word.
FALLBACK_COUNTRIES = frozenset(
    "AD AE AI AL AM AR AT AU AW AZ BB BD BE BG BN BO BR BY BZ CA CH CK CL CN "
    "CO CR CW CY CZ DE DK DM DO DZ EC EE EG ES FI FO FR GB GD GE GH GL GN GR "
    "GT HK HN HR HU ID IE IL IM IN IS IT JE JM JP KE KR KW KZ LC LI LT LU LV "
    "MA MC MD ME MH MK MT MU MV MX MY MZ NG NL NO NR NZ OM PA PE PH PK PL PT "
    "PY QA RO RS RU SA SC SE SG SI SK SM SN SV TH TN TR TW UA UG US UY VE VN "
    "ZA".split()
)
# Countries with a "VAT" ID type: their numbers are commonly written with the
# country prefix followed by letters or digits (``ESB12345678``).
FALLBACK_VAT_COUNTRIES = frozenset(
    "AT BE BG CY CZ DE DK EE ES FI FR GB GR HR HU IE IT LT LU LV MC MT NL OM "
    "PL PT RO SE SI SK ZA".split()
)
FALLBACK_ALIASES = {"EL": "GR", "UK": "GB"}  # prefixes used in VAT numbers

# ``live`` is True when the list came from the API within the last day.
CountryList = collections.namedtuple("CountryList", "codes vat_codes aliases live")
FALLBACK_LIST = CountryList(FALLBACK_COUNTRIES, FALLBACK_VAT_COUNTRIES, FALLBACK_ALIASES, False)

_countries_cache = {}  # base URL -> (expires_at, CountryList)
_countries_lock = threading.Lock()


def parse_countries(body):
    """CountryList from the JSON of GET /v1/countries. Raises ValueError when
    the document does not look like the list."""
    rows = body.get("countries") if isinstance(body, dict) else None
    if not isinstance(rows, list):
        raise ValueError("no countries list")
    codes, vat_codes, aliases = set(), set(), {}
    for row in rows:
        code = row.get("country") if isinstance(row, dict) else None
        if not isinstance(code, str) or not re.fullmatch(r"[A-Za-z]{2}", code):
            continue
        code = code.upper()
        codes.add(code)
        id_types = row.get("id_types")
        for id_type in id_types if isinstance(id_types, list) else []:
            if isinstance(id_type, dict) and str(id_type.get("id_type") or "").upper() == "VAT":
                vat_codes.add(code)
        row_aliases = row.get("aliases")
        for alias in row_aliases if isinstance(row_aliases, list) else []:
            if isinstance(alias, str) and re.fullmatch(r"[A-Za-z]{2}", alias):
                aliases[alias.upper()] = code
    if not codes:
        raise ValueError("empty countries list")
    return CountryList(frozenset(codes), frozenset(vat_codes), aliases, True)


def fetch_countries(base_url=None, session=None):
    """Ask the API for the list. Raises on any problem."""
    base = (base_url or DEFAULT_BASE_URL).rstrip("/")
    resp = (session or requests).get(
        base + "/v1/countries",
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        timeout=COUNTRIES_TIMEOUT,
    )
    if resp.status_code != 200:
        raise ValueError("HTTP %s" % resp.status_code)
    return parse_countries(resp.json())


def supported_countries(base_url=None, session=None, now=None):
    """The current CountryList: from memory, else from the API, else the last
    known list (or the embedded one) marked as not live. Never raises."""
    base = (base_url or DEFAULT_BASE_URL).rstrip("/")
    now = time.time() if now is None else now
    with _countries_lock:
        cached = _countries_cache.get(base)
        if cached and cached[0] > now:
            return cached[1]
    try:
        listing = fetch_countries(base, session)
        expires = now + COUNTRIES_TTL
    except Exception:  # pylint: disable=broad-except
        # Network, timeout, bad JSON, or requests blocked (as in Odoo's test mode):
        # looking up the list must never be the reason a validation fails.
        previous = cached[1] if cached else FALLBACK_LIST
        listing = previous._replace(live=False)
        expires = now + COUNTRIES_RETRY
    with _countries_lock:
        _countries_cache[base] = (expires, listing)
    return listing


def reset_countries_cache():
    with _countries_lock:
        _countries_cache.clear()


class TaxIdApiError(Exception):
    """An answer that is not a validation result.

    ``kind`` is one of: no_country, unsupported, no_number, auth, quota,
    unavailable, timeout, network, bad_request, unexpected. ``detail`` is the
    API's own (English) message or the country code. The Odoo model turns the
    kind into a translated message.
    """

    def __init__(self, kind, detail="", status=None, retry_after=None):
        super().__init__("%s: %s" % (kind, detail))
        self.kind = kind
        self.detail = detail or ""
        self.status = status
        self.retry_after = retry_after

    @property
    def stop_batch(self):
        """A bulk run stops: more requests would fail the same way."""
        return self.kind in ("auth", "quota", "network")


def clean_number(country, vat):
    """Drop spaces and, for the four dedicated endpoints, a leading country
    prefix that some databases store (``PE20615614841``)."""
    number = re.sub(r"\s+", "", vat or "")
    cc = (country or "").upper()
    if cc in DEDICATED and number[:2].upper() == cc:
        rest = number[2:].lstrip("-")
        if cc == "MX":
            # A real RFC may start with "MX": strip only when the rest is still 12-13 chars.
            if len(number) >= 14 and len(rest) in (12, 13):
                number = rest
        elif rest[:1].isdigit():
            number = rest
    return number


def guess_country(vat, listing=None):
    """Country from a prefix in the number (``FR12345678901``), or None.

    A prefix counts when it is a supported country and either a digit follows
    (``PE20615614841``) or the country has VAT numbers, which may continue with
    a letter (``ESB12345678``). This keeps IDs that merely start with two
    letters, such as a Mexican RFC, from being read as another country.
    """
    listing = listing or FALLBACK_LIST
    number = re.sub(r"\s+", "", vat or "").upper()
    prefix = number[:2]
    if not re.fullmatch(r"[A-Z]{2}", prefix):
        return None
    code = listing.aliases.get(prefix, prefix)  # Greek VAT numbers use EL
    if code not in listing.codes:
        return None
    if code in listing.vat_codes or number[2:3].isdigit():
        return code
    return None


def build_request(base_url, country, number):
    """(url, params) for a lookup."""
    base = (base_url or DEFAULT_BASE_URL).rstrip("/")
    cc = country.upper()
    if cc in DEDICATED:
        return base + DEDICATED[cc] % requests.utils.quote(number, safe=""), None
    return base + "/v1/validate", {"country": cc, "id": number}


def validate(country, vat, api_key=None, base_url=None, session=None):
    """Validate ``vat`` for ``country`` (ISO 3166 alpha-2). Returns the JSON result.

    Raises TaxIdApiError for anything that is not a result.
    """
    listing = supported_countries(base_url, session)
    cc = (country or "").strip().upper() or guess_country(vat, listing)
    if not cc:
        raise TaxIdApiError("no_country")
    # With a fresh list an unsupported country is refused here, without spending a
    # lookup. With the backup list the API decides (it answers 404 for those).
    if cc not in listing.codes and (listing.live or not re.fullmatch(r"[A-Z]{2}", cc)):
        raise TaxIdApiError("unsupported", cc)
    number = clean_number(cc, vat)
    if not number:
        raise TaxIdApiError("no_number")
    url, params = build_request(base_url, cc, number)
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    if api_key:
        headers["Authorization"] = "Bearer %s" % api_key.strip()
    try:
        resp = (session or requests).get(url, params=params, headers=headers, timeout=TIMEOUT)
    except requests.exceptions.Timeout:
        raise TaxIdApiError("timeout")
    except requests.exceptions.RequestException:
        raise TaxIdApiError("network")
    return parse_response(resp)


def parse_response(resp):
    status = resp.status_code
    try:
        body = resp.json()
    except ValueError:
        body = {}
    if not isinstance(body, dict):
        body = {}
    api_msg = body.get("error") or ""
    if status == 200 and "assessment" in body:
        return body
    # A malformed number comes back as 400 with a full "fail" assessment: that is a result.
    if status == 400 and isinstance(body.get("assessment"), dict):
        return body
    if status in (401, 403):
        raise TaxIdApiError("auth", api_msg, status)
    if status == 429:
        raise TaxIdApiError("quota", api_msg, status, resp.headers.get("x-ratelimit-reset"))
    if status == 503:
        raise TaxIdApiError("unavailable", api_msg, status, resp.headers.get("retry-after"))
    if status == 404:
        raise TaxIdApiError("unsupported", api_msg, status)
    if status == 400:
        raise TaxIdApiError("bad_request", api_msg, status)
    raise TaxIdApiError("unexpected", "HTTP %s" % status, status)
