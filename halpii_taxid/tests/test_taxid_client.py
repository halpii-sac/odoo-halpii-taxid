# Copyright 2026 HALPII S.A.C.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).
from odoo.tests import BaseCase, tagged

from ..models import taxid_client
from .common import PE_MALFORMED, FakeResponse


@tagged("post_install", "-at_install")
class TestTaxIdClient(BaseCase):
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
        self.assertIsNone(taxid_client.guess_country("20615614841"))

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
        with self.assertRaises(taxid_client.TaxIdApiError) as ctx:
            taxid_client.validate("AQ", "123", session=object())
        self.assertEqual(ctx.exception.kind, "unsupported")
        with self.assertRaises(taxid_client.TaxIdApiError) as ctx:
            taxid_client.validate(None, "20615614841", session=object())
        self.assertEqual(ctx.exception.kind, "no_country")
