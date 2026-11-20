# Copyright 2026 HALPII S.A.C.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).
from odoo.tests import BaseCase, tagged

from ..models import taxid_client
from .common import COUNTRIES, DE_FORMAT, PE_MALFORMED, FakeResponse


class FakeSession:
    """Answers GET requests from a list and remembers the URLs asked."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.urls = []

    def get(self, url, **kwargs):
        self.urls.append(url)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


@tagged("post_install", "-at_install")
class TestTaxIdClient(BaseCase):
    def setUp(self):
        super().setUp()
        taxid_client.reset_countries_cache()
        self.addCleanup(taxid_client.reset_countries_cache)

    def test_routing(self):
        url, params = taxid_client.build_request(None, "PE", "20615614841")
        self.assertEqual(url, "https://taxid.halpii.com/v1/pe/ruc/20615614841")
        self.assertIsNone(params)
        url, params = taxid_client.build_request(None, "co", "900000000-1")
        self.assertEqual(url, "https://taxid.halpii.com/v1/co/nit/900000000-1")
        url, params = taxid_client.build_request("https://example.test/", "FR", "FR12345678901")
        self.assertEqual(url, "https://example.test/v1/validate")
        self.assertEqual(params, {"country": "FR", "id": "FR12345678901"})

    def test_clean_number(self):
        self.assertEqual(taxid_client.clean_number("PE", "PE 2061 5614841"), "20615614841")
        self.assertEqual(taxid_client.clean_number("CO", "CO900000000-1"), "900000000-1")
        # An RFC that happens to start with MX keeps its letters.
        self.assertEqual(taxid_client.clean_number("MX", "MXA950101AB1"), "MXA950101AB1")
        self.assertEqual(taxid_client.clean_number("MX", "MXABC950101AB1"), "ABC950101AB1")
        # Other countries keep the prefix: /v1/validate understands EU VAT prefixes.
        self.assertEqual(taxid_client.clean_number("DE", "DE123456788"), "DE123456788")

    def test_guess_country(self):
        self.assertEqual(taxid_client.guess_country("FR12345678901"), "FR")
        self.assertEqual(taxid_client.guess_country("EL123456789"), "GR")
        self.assertEqual(taxid_client.guess_country("ESB12345678"), "ES")
        self.assertEqual(taxid_client.guess_country("PE20615614841"), "PE")
        self.assertIsNone(taxid_client.guess_country("20615614841"))
        # Two leading letters are not a country prefix by themselves: a Mexican RFC
        # that starts with "MA" is not a Moroccan ID.
        self.assertIsNone(taxid_client.guess_country("MAGA800101AB1"))
        self.assertIsNone(taxid_client.guess_country("AQ123"))

    def test_countries_list_comes_from_the_api(self):
        listing = taxid_client.parse_countries(COUNTRIES)
        self.assertTrue(listing.live)
        self.assertEqual(listing.codes, {"PE", "MX", "GR", "ES", "UG", "ZZ"})
        self.assertEqual(listing.vat_codes, {"GR", "ES"})
        self.assertEqual(listing.aliases, {"EL": "GR"})
        for bad in ({}, {"countries": []}, {"countries": "x"}, [], None):
            with self.assertRaises(ValueError):
                taxid_client.parse_countries(bad)
        # A country the embedded list does not know is accepted as soon as the API lists it.
        self.assertNotIn("ZZ", taxid_client.FALLBACK_COUNTRIES)
        session = FakeSession(FakeResponse(200, COUNTRIES), FakeResponse(200, DE_FORMAT))
        result = taxid_client.validate("ZZ", "123", session=session)
        self.assertEqual(result["assessment"]["verdict"], "review")
        self.assertEqual(
            session.urls,
            ["https://taxid.halpii.com/v1/countries", "https://taxid.halpii.com/v1/validate"],
        )

    def test_countries_list_is_cached_for_a_day(self):
        session = FakeSession(FakeResponse(200, COUNTRIES), FakeResponse(200, COUNTRIES))
        first = taxid_client.supported_countries(session=session, now=1000)
        again = taxid_client.supported_countries(session=session, now=1000 + taxid_client.COUNTRIES_TTL - 1)
        self.assertIs(first, again)
        self.assertEqual(len(session.urls), 1)
        taxid_client.supported_countries(session=session, now=1000 + taxid_client.COUNTRIES_TTL + 1)
        self.assertEqual(len(session.urls), 2)

    def test_countries_fallback_when_the_api_does_not_answer(self):
        import requests

        for failure in (
            requests.exceptions.ConnectionError("down"),
            FakeResponse(500, {"error": "x"}),
            FakeResponse(200, ValueError("not json")),
            FakeResponse(200, {"unexpected": True}),
        ):
            taxid_client.reset_countries_cache()
            session = FakeSession(failure)
            listing = taxid_client.supported_countries(session=session, now=1000)
            self.assertFalse(listing.live)
            self.assertEqual(listing.codes, taxid_client.FALLBACK_COUNTRIES)
            # No new attempt until the retry delay has passed.
            taxid_client.supported_countries(session=session, now=1000 + taxid_client.COUNTRIES_RETRY - 1)
            self.assertEqual(len(session.urls), 1)
        self.assertEqual(len(taxid_client.FALLBACK_COUNTRIES), 121)
        self.assertLessEqual(taxid_client.FALLBACK_VAT_COUNTRIES, taxid_client.FALLBACK_COUNTRIES)
        self.assertLessEqual(set(taxid_client.DEDICATED), taxid_client.FALLBACK_COUNTRIES)
        # A list that was live keeps its countries when a later refresh fails.
        taxid_client.reset_countries_cache()
        session = FakeSession(FakeResponse(200, COUNTRIES), requests.exceptions.Timeout())
        taxid_client.supported_countries(session=session, now=1000)
        stale = taxid_client.supported_countries(session=session, now=1000 + taxid_client.COUNTRIES_TTL + 1)
        self.assertFalse(stale.live)
        self.assertIn("ZZ", stale.codes)

    def test_backup_list_lets_the_api_decide(self):
        import requests

        # List unreachable: a country missing from the embedded copy is still sent.
        session = FakeSession(requests.exceptions.ConnectionError("down"), FakeResponse(404, {"error": "no"}))
        with self.assertRaises(taxid_client.TaxIdApiError) as ctx:
            taxid_client.validate("AQ", "123", session=session)
        self.assertEqual(ctx.exception.kind, "unsupported")
        self.assertEqual(len(session.urls), 2)
        # Something that is not a country code never leaves the server.
        with self.assertRaises(taxid_client.TaxIdApiError) as ctx:
            taxid_client.validate("A1", "123", session=FakeSession())
        self.assertEqual(ctx.exception.kind, "unsupported")

    def test_parse(self):
        self.assertEqual(taxid_client.parse_response(FakeResponse(400, PE_MALFORMED))["assessment"]["verdict"], "fail")
        cases = {401: "auth", 403: "auth", 429: "quota", 503: "unavailable", 404: "unsupported", 500: "unexpected"}
        for status, kind in cases.items():
            with self.assertRaises(taxid_client.TaxIdApiError) as ctx:
                taxid_client.parse_response(FakeResponse(status, {"error": "x"}))
            self.assertEqual(ctx.exception.kind, kind)
        with self.assertRaises(taxid_client.TaxIdApiError) as ctx:
            taxid_client.parse_response(FakeResponse(502, ValueError("not json")))
        self.assertEqual(ctx.exception.kind, "unexpected")

    def test_unsupported_country_never_calls(self):
        # With a fresh list, only the list itself is requested.
        session = FakeSession(FakeResponse(200, COUNTRIES))
        with self.assertRaises(taxid_client.TaxIdApiError) as ctx:
            taxid_client.validate("AQ", "123", session=session)
        self.assertEqual(ctx.exception.kind, "unsupported")
        with self.assertRaises(taxid_client.TaxIdApiError) as ctx:
            taxid_client.validate(None, "20615614841", session=session)
        self.assertEqual(ctx.exception.kind, "no_country")
        self.assertEqual(session.urls, ["https://taxid.halpii.com/v1/countries"])
