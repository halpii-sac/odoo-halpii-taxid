# Copyright 2026 HALPII S.A.C.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    halpii_taxid_api_key = fields.Char(
        string="HALPII Tax ID API key",
        config_parameter="halpii_taxid.api_key",
        help="Key from https://taxid.halpii.com (no cost to create). Without a key the API "
        "only allows a few lookups a day per network.",
    )
    halpii_taxid_validate_on_save = fields.Boolean(
        string="Validate on save",
        config_parameter="halpii_taxid.validate_on_save",
        help="Validate the tax ID automatically when a company or individual contact is "
        "created, or when its tax ID or country changes. Each validation is one API lookup.",
    )
    halpii_taxid_block_on_fail = fields.Boolean(
        string="Block when the verdict is fail",
        config_parameter="halpii_taxid.block_on_fail",
        help="Refuse to save a contact whose tax ID gets the verdict 'fail' (invalid, not "
        "active or blacklisted). Off by default: the contact is saved and only flagged. "
        "If the service cannot be reached, the contact is always saved.",
    )
