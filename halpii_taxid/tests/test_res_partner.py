# Copyright 2026 HALPII S.A.C.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).
from unittest.mock import patch

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged

from ..models import taxid_client
from .common import DE_FORMAT, PE_MALFORMED, PE_PASS, FakeResponse


@tagged("post_install", "-at_install")
class TestResPartnerTaxId(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.param = cls.env["ir.config_parameter"].sudo()
        cls.param.set_param("halpii_taxid.api_key", "test-key")
        cls.pe = cls.env.ref("base.pe")
        cls.de = cls.env.ref("base.de")

    def _mock(self, *responses):
        """Patch requests.get with a list of answers; returns the mock."""
        answers = list(responses)
        return patch.object(taxid_client.requests, "get", side_effect=lambda *a, **k: answers.pop(0))

    def _partner(self, **vals):
        vals.setdefault("name", "Acme")
        vals.setdefault("is_company", True)
        return self.env["res.partner"].create(vals)

    def test_validate_button_stores_result_without_renaming(self):
        partner = self._partner(country_id=self.pe.id, vat="20615614841")
        self.assertFalse(partner.halpii_taxid_verdict, "validate on save is off by default")
        with self._mock(FakeResponse(200, PE_PASS)) as get:
            action = partner.action_halpii_validate_taxid()
        args, kwargs = get.call_args
        self.assertEqual(args[0], "https://taxid.halpii.com/v1/pe/ruc/20615614841")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer test-key")
        self.assertEqual(action["params"]["type"], "success")
        self.assertEqual(partner.halpii_taxid_verdict, "pass")
        self.assertEqual(partner.halpii_taxid_level, "official_registry")
        self.assertEqual(str(partner.halpii_taxid_data_as_of), "2026-11-14")
        self.assertEqual(partner.halpii_taxid_legal_name, "HALPII S.A.C.")
        self.assertEqual(partner.halpii_taxid_status, "Active")
        self.assertIn("HABIDO", partner.halpii_taxid_reasons)
        # The contact name is never overwritten without the "Use official name" button.
        self.assertEqual(partner.name, "Acme")
        self.assertTrue(partner.halpii_taxid_name_differs)
        partner.action_halpii_use_official_name()
        self.assertEqual(partner.name, "HALPII S.A.C.")
        self.assertFalse(partner.halpii_taxid_name_differs)

    def test_generic_endpoint_for_other_countries(self):
        partner = self._partner(country_id=self.de.id, vat="DE123456788")
        with self._mock(FakeResponse(200, DE_FORMAT)) as get:
            partner.action_halpii_validate_taxid()
        args, kwargs = get.call_args
        self.assertEqual(args[0], "https://taxid.halpii.com/v1/validate")
        self.assertEqual(kwargs["params"], {"country": "DE", "id": "DE123456788"})
        self.assertEqual(partner.halpii_taxid_verdict, "review")
        self.assertEqual(partner.halpii_taxid_level, "format")
        self.assertFalse(partner.halpii_taxid_data_as_of)
        self.assertEqual(partner.halpii_taxid_lookup_url, "https://ec.europa.eu/taxation_customs/vies/")

    def test_errors_are_clear_and_keep_previous_result(self):
        partner = self._partner(country_id=self.pe.id, vat="20615614841")
        with self._mock(FakeResponse(200, PE_PASS)):
            partner.action_halpii_validate_taxid()
        for status, words in ((401, "API key"), (429, "limit"), (503, "Try again later")):
            with self._mock(FakeResponse(status, {"error": "boom"})):
                with self.assertRaises(UserError) as ctx:
                    partner.action_halpii_validate_taxid()
            self.assertIn(words, str(ctx.exception))
            self.assertEqual(partner.halpii_taxid_verdict, "pass")

    def test_validate_on_save_warns_by_default(self):
        self.param.set_param("halpii_taxid.validate_on_save", "True")
        with self._mock(FakeResponse(400, PE_MALFORMED)):
            partner = self._partner(country_id=self.pe.id, vat="2061561")
        self.assertEqual(partner.halpii_taxid_verdict, "fail")

    def test_block_on_fail(self):
        self.param.set_param("halpii_taxid.validate_on_save", "True")
        self.param.set_param("halpii_taxid.block_on_fail", "True")
        with self._mock(FakeResponse(400, PE_MALFORMED)):
            with self.assertRaises(ValidationError):
                self._partner(country_id=self.pe.id, vat="2061561")
        # An unreachable service never blocks the save.
        with self._mock(FakeResponse(503, {"error": "SUNAT down"})):
            partner = self._partner(country_id=self.pe.id, vat="20615614841")
        self.assertFalse(partner.halpii_taxid_verdict)
        self.assertIn("SUNAT down", partner.halpii_taxid_error)

    def test_changing_vat_drops_stale_result(self):
        partner = self._partner(country_id=self.pe.id, vat="20615614841")
        with self._mock(FakeResponse(200, PE_PASS)):
            partner.action_halpii_validate_taxid()
        partner.name = "Renamed"
        self.assertEqual(partner.halpii_taxid_verdict, "pass")
        partner.vat = "20615614842"
        self.assertFalse(partner.halpii_taxid_verdict)
        self.assertFalse(partner.halpii_taxid_legal_name)

    def test_validate_on_save_revalidates_changed_vat(self):
        self.param.set_param("halpii_taxid.validate_on_save", "True")
        with self._mock(FakeResponse(200, PE_PASS)):
            partner = self._partner(country_id=self.pe.id, vat="20615614841")
        with self._mock(FakeResponse(400, PE_MALFORMED)) as get:
            partner.write({"vat": "2061561"})
        self.assertEqual(get.call_count, 1)
        self.assertEqual(partner.halpii_taxid_verdict, "fail")
        # Child contacts receive the company's tax ID but are not validated on their own.
        with self._mock() as get:
            self.env["res.partner"].create({"name": "Child", "parent_id": partner.id})
        self.assertEqual(get.call_count, 0)

    def test_bulk_stops_on_quota(self):
        partners = self.env["res.partner"]
        for i in range(3):
            partners |= self._partner(name="P%s" % i, country_id=self.pe.id, vat="20615614841")
        partners |= self._partner(name="No VAT")
        with self._mock(
            FakeResponse(200, PE_PASS),
            FakeResponse(429, {"error": "Daily limit of 100 lookups reached."}),
        ) as get:
            action = partners.action_halpii_validate_selected()
        self.assertEqual(get.call_count, 2)
        message = action["params"]["message"]
        self.assertIn("1 validated", message)
        self.assertIn("Stopped early", message)
        self.assertIn("1 skipped", message)
        self.assertEqual(action["params"]["type"], "danger")
        self.assertEqual(partners.mapped("halpii_taxid_verdict").count("pass"), 1)

    def test_bulk_continues_after_unavailable_source(self):
        a = self._partner(name="A", country_id=self.pe.id, vat="20615614841")
        b = self._partner(name="B", country_id=self.de.id, vat="DE123456788")
        with self._mock(FakeResponse(503, {"error": "down"}), FakeResponse(200, DE_FORMAT)):
            action = (a | b).action_halpii_validate_selected()
        self.assertIn("1 could not be checked", action["params"]["message"])
        self.assertTrue(a.halpii_taxid_error)
        self.assertEqual(b.halpii_taxid_verdict, "review")
