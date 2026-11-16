# Copyright 2026 HALPII S.A.C.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).
{
    "name": "Tax ID Validation (58 countries) – HALPII",
    "summary": "Validate customer and supplier tax IDs (RUC, RFC, NIT, VAT, RUT…) "
    "in 58 countries: verdict with reasons, verification level and data date.",
    "version": "17.0.1.0.0",
    "category": "Accounting/Localizations",
    "author": "HALPII",
    "website": "https://taxid.halpii.com",
    "support": "contacto@halpii.com",
    "license": "LGPL-3",
    "depends": ["base_setup"],
    "external_dependencies": {"python": ["requests"]},
    "data": [
        "data/server_actions.xml",
        "views/res_config_settings_views.xml",
        "views/res_partner_views.xml",
    ],
    "images": ["static/description/banner.png"],
    "installable": True,
    "application": False,
}
