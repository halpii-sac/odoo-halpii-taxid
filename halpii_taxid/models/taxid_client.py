# Copyright 2026 HALPII S.A.C.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).
"""Small HTTP client for the HALPII Tax ID API (https://taxid.halpii.com).

It only knows how to route a (country, number) pair to the right endpoint and
turn the HTTP answer into either a result dict or a ``TaxIdApiError`` with a
message the user can act on. It does not touch the database.
"""
import re

import requests

DEFAULT_BASE_URL = "https://taxid.halpii.com"
TIMEOUT = 20  # the API gives up on a slow registry after ~8 s

# Countries with their own lookup endpoint (the generic /v1/validate refuses them).
DEDICATED = {
    "PE": "/v1/pe/ruc/%s",
    "MX": "/v1/mx/rfc/%s",
    "CO": "/v1/co/nit/%s",
    "CR": "/v1/cr/cedula/%s",
}

# The 58 countries GET /v1/countries listed on 2026-11-15.
SUPPORTED_COUNTRIES = frozenset(
    "AR AT AU BE BG BO BR CA CH CL CO CR CY CZ DE DK DO EC EE ES FI FR GB GR "
    "GT HR HU IE IL IN IS IT JP KR LT LU LV MT MX NL NO NZ PA PE PL PT PY RO "
    "SE SG SI SK TR TW US UY VE ZA".split()
)


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


def guess_country(vat):
    """Country from an EU-style prefix (``FR12345678901``), or None."""
    prefix = (vat or "").strip()[:2].upper()
    if prefix == "EL":  # Greek VAT numbers use EL
        return "GR"
    return prefix if prefix in SUPPORTED_COUNTRIES else None


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
    cc = (country or "").upper() or guess_country(vat)
    if not cc:
        raise TaxIdApiError("no_country")
    if cc not in SUPPORTED_COUNTRIES:
        raise TaxIdApiError("unsupported", cc)
    number = clean_number(cc, vat)
    if not number:
        raise TaxIdApiError("no_number")
    url, params = build_request(base_url, cc, number)
    headers = {"Accept": "application/json", "User-Agent": "HALPII-TaxID-Odoo/1.0"}
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
