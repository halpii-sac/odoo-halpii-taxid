# Copyright 2026 HALPII S.A.C.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import str2bool

from . import taxid_client

_logger = logging.getLogger(__name__)

# Upper bound for one "Validate selected" run (each contact is one API lookup).
BATCH_LIMIT = 200

RESULT_FIELDS = [
    "halpii_taxid_verdict",
    "halpii_taxid_level",
    "halpii_taxid_data_as_of",
    "halpii_taxid_legal_name",
    "halpii_taxid_status",
    "halpii_taxid_reasons",
    "halpii_taxid_source",
    "halpii_taxid_lookup_url",
    "halpii_taxid_checked_on",
    "halpii_taxid_checked_key",
    "halpii_taxid_error",
]


class ResPartner(models.Model):
    _inherit = "res.partner"

    halpii_taxid_verdict = fields.Selection(
        [("pass", "Pass"), ("review", "Review"), ("fail", "Fail")],
        string="Tax ID verdict",
        readonly=True,
        copy=False,
        index=True,
        help="Pass: found in the official registry and active (only possible with an "
        "official registry check). Review: needs a human look (format check only, unusual "
        "status, or not found in a source that may be incomplete). Fail: invalid number, "
        "not active, or on an official blacklist.",
    )
    halpii_taxid_level = fields.Selection(
        [
            ("official_registry", "Official registry"),
            ("format_and_lists", "Format + official lists"),
            ("format", "Format only"),
        ],
        string="Verification level",
        readonly=True,
        copy=False,
        help="Official registry: looked up in the tax or business registry (or its published "
        "copy). Format + official lists: structure, check digit and official blacklists, "
        "because no public registry exists (Mexico). Format only: structure and check digit, "
        "offline; it does not show that the business exists.",
    )
    halpii_taxid_data_as_of = fields.Date(
        string="Data as of", readonly=True, copy=False,
        help="Date of the registry data the verdict is based on, as stated by the source.",
    )
    halpii_taxid_legal_name = fields.Char(string="Official name", readonly=True, copy=False)
    halpii_taxid_status = fields.Char(string="Registry status", readonly=True, copy=False)
    halpii_taxid_reasons = fields.Text(string="Reasons", readonly=True, copy=False)
    halpii_taxid_source = fields.Char(string="Source", readonly=True, copy=False)
    halpii_taxid_lookup_url = fields.Char(string="Official lookup", readonly=True, copy=False)
    halpii_taxid_checked_on = fields.Datetime(string="Checked on", readonly=True, copy=False)
    halpii_taxid_checked_key = fields.Char(readonly=True, copy=False)
    halpii_taxid_error = fields.Char(string="Last validation problem", readonly=True, copy=False)
    halpii_taxid_name_differs = fields.Boolean(compute="_compute_halpii_taxid_name_differs")

    @api.depends("name", "halpii_taxid_legal_name")
    def _compute_halpii_taxid_name_differs(self):
        for partner in self:
            official = " ".join((partner.halpii_taxid_legal_name or "").split()).casefold()
            current = " ".join((partner.name or "").split()).casefold()
            partner.halpii_taxid_name_differs = bool(official) and official != current

    # ------------------------------------------------------------------
    # Settings and helpers
    # ------------------------------------------------------------------
    @api.model
    def _halpii_taxid_settings(self):
        param = self.env["ir.config_parameter"].sudo()
        return {
            "api_key": param.get_param("halpii_taxid.api_key") or False,
            "base_url": param.get_param("halpii_taxid.base_url") or taxid_client.DEFAULT_BASE_URL,
            "validate_on_save": str2bool(param.get_param("halpii_taxid.validate_on_save") or "0"),
            "block_on_fail": str2bool(param.get_param("halpii_taxid.block_on_fail") or "0"),
        }

    def _halpii_taxid_key(self):
        self.ensure_one()
        return "%s:%s" % (self.country_id.code or "", (self.vat or "").replace(" ", "").upper())

    def _halpii_taxid_is_main(self):
        """Only the commercial entity carries the tax ID (child contacts get a copy)."""
        self.ensure_one()
        return self.commercial_partner_id == self

    def _halpii_taxid_error_message(self, err):
        kind, detail = err.kind, err.detail
        if kind == "no_country":
            return _("Set the contact's country (or a country prefix in the tax ID) to validate it.")
        if kind == "no_number":
            return _("The contact has no tax ID to validate.")
        if kind == "unsupported":
            return _(
                "This country or ID type is not supported yet (%s). The supported countries "
                "and territories are listed at https://taxid.halpii.com/countries.",
                detail,
            )
        if kind == "auth":
            return _(
                "The HALPII Tax ID API key was rejected (%s). Check it in Settings > Tax ID "
                "Validation; a key can be created at no cost at https://taxid.halpii.com.",
                detail or "401",
            )
        if kind == "quota":
            return _(
                "Monthly lookup limit reached (%s). A no-cost key includes 100 lookups a month; "
                "for more, the monthly plan costs US$39 a month with 1,000 lookups included: "
                "https://taxid.halpii.com/pricing.",
                detail or "429",
            )
        if kind == "unavailable":
            return _(
                "The official source for this country is not answering right now. Try again "
                "later; this lookup was not charged. Detail: %s",
                detail or "503",
            )
        if kind == "timeout":
            return _("The validation service took too long to answer. Try again in a few minutes.")
        if kind == "network":
            return _("Could not reach taxid.halpii.com. Check this server's internet connection.")
        if kind == "bad_request":
            return _("The tax ID could not be read: %s", detail)
        return _("Unexpected answer from the validation service (%s).", detail)

    @api.model
    def _halpii_taxid_result_vals(self, result):
        assessment = result.get("assessment") or {}
        verdict = assessment.get("verdict")
        level = result.get("verification_level")
        source = result.get("source") if isinstance(result.get("source"), dict) else {}
        status = result.get("status")
        if isinstance(status, dict):
            status = status.get("label") or status.get("code")
        legal_name = result.get("legal_name")
        # The API writes "withheld (...)" instead of a person's name in some cases: not a name.
        if not isinstance(legal_name, str) or legal_name.lower().startswith("withheld"):
            legal_name = False
        as_of = source.get("data_as_of")
        reasons = assessment.get("reasons") or []
        return {
            "halpii_taxid_verdict": verdict if verdict in ("pass", "review", "fail") else False,
            "halpii_taxid_level": level
            if level in ("official_registry", "format_and_lists", "format")
            else False,
            "halpii_taxid_data_as_of": as_of[:10] if isinstance(as_of, str) and len(as_of) >= 10 else False,
            "halpii_taxid_legal_name": legal_name,
            "halpii_taxid_status": status if isinstance(status, str) else False,
            "halpii_taxid_reasons": "\n".join(str(r) for r in reasons) or False,
            "halpii_taxid_source": source.get("name") or False,
            "halpii_taxid_lookup_url": result.get("official_lookup_url") or False,
            "halpii_taxid_checked_on": fields.Datetime.now(),
            "halpii_taxid_error": False,
        }

    def _halpii_taxid_store(self, vals):
        self.with_context(halpii_taxid_internal=True).write(vals)

    def _halpii_taxid_call(self, settings=None):
        """One lookup for one contact. Stores the result; raises TaxIdApiError otherwise."""
        self.ensure_one()
        settings = settings or self._halpii_taxid_settings()
        result = taxid_client.validate(
            self.country_id.code,
            self.vat,
            api_key=settings["api_key"],
            base_url=settings["base_url"],
        )
        vals = self._halpii_taxid_result_vals(result)
        vals["halpii_taxid_checked_key"] = self._halpii_taxid_key()
        self._halpii_taxid_store(vals)
        return vals

    def _halpii_taxid_clear(self):
        self._halpii_taxid_store({f: False for f in RESULT_FIELDS})

    # ------------------------------------------------------------------
    # Automatic validation on create / write
    # ------------------------------------------------------------------
    def _halpii_taxid_auto_validate(self):
        settings = self._halpii_taxid_settings()
        failed = []
        for partner in self:
            if not partner.vat or not partner._halpii_taxid_is_main():
                continue
            try:
                vals = partner._halpii_taxid_call(settings)
            except taxid_client.TaxIdApiError as err:
                # Never block a save because the service is unreachable or out of quota.
                _logger.info("HALPII Tax ID: partner %s not validated (%s)", partner.id, err.kind)
                partner._halpii_taxid_store(
                    {f: False for f in RESULT_FIELDS if f != "halpii_taxid_error"}
                    | {"halpii_taxid_error": partner._halpii_taxid_error_message(err)}
                )
                continue
            if vals["halpii_taxid_verdict"] == "fail":
                failed.append((partner, vals))
        if failed and settings["block_on_fail"]:
            partner, vals = failed[0]
            raise ValidationError(
                _(
                    "The tax ID %(vat)s of %(name)s did not pass validation:\n%(reasons)s\n\n"
                    "Correct it, or ask an administrator to turn off 'Block when the verdict "
                    "is fail' in Settings.",
                    vat=partner.vat,
                    name=partner.display_name,
                    reasons=vals["halpii_taxid_reasons"] or "",
                )
            )

    @api.model_create_multi
    def create(self, vals_list):
        partners = super().create(vals_list)
        if not self.env.context.get("halpii_taxid_internal"):
            to_check = partners.filtered("vat")
            if to_check and self._halpii_taxid_settings()["validate_on_save"]:
                to_check._halpii_taxid_auto_validate()
        return partners

    def write(self, vals):
        res = super().write(vals)
        if self.env.context.get("halpii_taxid_internal") or not ({"vat", "country_id"} & set(vals)):
            return res
        # A stored result belongs to one country + number: drop it when either changes.
        stale = self.filtered(
            lambda p: (p.halpii_taxid_checked_key or p.halpii_taxid_error)
            and p.halpii_taxid_checked_key != p._halpii_taxid_key()
        )
        if self._halpii_taxid_settings()["validate_on_save"]:
            changed = self.filtered(
                lambda p: p.vat and p.halpii_taxid_checked_key != p._halpii_taxid_key()
            )
            (stale - changed)._halpii_taxid_clear()
            changed._halpii_taxid_auto_validate()
        else:
            stale._halpii_taxid_clear()
        return res

    # ------------------------------------------------------------------
    # Buttons and actions
    # ------------------------------------------------------------------
    def action_halpii_validate_taxid(self):
        self.ensure_one()
        partner = self.commercial_partner_id
        try:
            vals = partner._halpii_taxid_call()
        except taxid_client.TaxIdApiError as err:
            raise UserError(partner._halpii_taxid_error_message(err)) from None
        labels = dict(self._fields["halpii_taxid_verdict"]._description_selection(self.env))
        kind = {"pass": "success", "review": "warning", "fail": "danger"}.get(
            vals["halpii_taxid_verdict"], "info"
        )
        return self._halpii_taxid_notify(
            _("Tax ID: %s", labels.get(vals["halpii_taxid_verdict"], "-")),
            vals["halpii_taxid_reasons"] or "",
            kind,
        )

    def action_halpii_use_official_name(self):
        """Replace the contact's name with the official one. The button asks for confirmation."""
        for partner in self:
            if partner.halpii_taxid_legal_name:
                partner.name = partner.halpii_taxid_legal_name
        return True

    def action_halpii_validate_selected(self):
        """Bulk validation from the list view ("Validate selected tax IDs")."""
        partners = self.filtered(lambda p: p.vat and p._halpii_taxid_is_main())
        skipped = len(self) - len(partners)
        extra = max(0, len(partners) - BATCH_LIMIT)
        partners = partners[:BATCH_LIMIT]
        settings = self._halpii_taxid_settings()
        counts = {"pass": 0, "review": 0, "fail": 0}
        problems = 0
        stop_message = False
        for partner in partners:
            try:
                vals = partner._halpii_taxid_call(settings)
            except taxid_client.TaxIdApiError as err:
                message = partner._halpii_taxid_error_message(err)
                if err.stop_batch:
                    stop_message = message
                    break
                problems += 1
                partner._halpii_taxid_store({"halpii_taxid_error": message})
                continue
            if vals["halpii_taxid_verdict"] in counts:
                counts[vals["halpii_taxid_verdict"]] += 1
        done = sum(counts.values())
        lines = [
            _(
                "%(done)s validated: %(ok)s pass, %(review)s review, %(fail)s fail.",
                done=done,
                ok=counts["pass"],
                review=counts["review"],
                fail=counts["fail"],
            )
        ]
        if problems:
            lines.append(
                _("%s could not be checked now (see 'Last validation problem' on each contact).", problems)
            )
        if skipped:
            lines.append(_("%s skipped: no tax ID, or a child contact of a company.", skipped))
        if extra:
            lines.append(_("%s not processed: at most %s contacts per run.", extra, BATCH_LIMIT))
        if stop_message:
            lines.append(_("Stopped early: %s", stop_message))
        kind = "danger" if stop_message else ("warning" if problems or counts["fail"] else "success")
        return self._halpii_taxid_notify(_("Tax ID validation"), "\n".join(lines), kind, sticky=True)

    def _halpii_taxid_notify(self, title, message, kind, sticky=False):
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": title,
                "message": message,
                "type": kind,
                "sticky": sticky,
                "next": {"type": "ir.actions.client", "tag": "soft_reload"},
            },
        }
