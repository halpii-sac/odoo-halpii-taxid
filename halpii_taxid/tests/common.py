# Copyright 2026 HALPII S.A.C.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).
import json

# Shaped like real answers of taxid.halpii.com (2026-11).
PE_PASS = {
    "country": "PE",
    "id_type": "RUC",
    "verification_level": "official_registry",
    "ruc": "20615614841",
    "format_valid": True,
    "check_digit_valid": True,
    "taxpayer_type": "legal_entity",
    "found": True,
    "legal_name": "HALPII S.A.C.",
    "status": {"code": "ACTIVO", "label": "Active", "active": True},
    "domicile_condition": {"code": "HABIDO", "label": "Located", "located": True},
    "assessment": {"verdict": "pass", "reasons": ["Active taxpayer.", "Domicile located (HABIDO)."]},
    "source": {"name": "SUNAT Padrón Reducido", "url": "https://www.sunat.gob.pe", "data_as_of": "2026-11-14"},
}
PE_MALFORMED = {
    "country": "PE",
    "id_type": "RUC",
    "verification_level": "format",
    "format_valid": False,
    "check_digit_valid": False,
    "taxpayer_type": "unknown",
    "found": None,
    "assessment": {"verdict": "fail", "reasons": ["Not 11 digits."]},
    "source": {"name": "SUNAT Padrón Reducido", "data_as_of": "2026-11-14"},
    "error": "Malformed RUC.",
}
DE_FORMAT = {
    "country": "DE",
    "id_type": "VAT",
    "verification_level": "format",
    "format_valid": True,
    "check_digit_valid": True,
    "registry_checked": False,
    "assessment": {
        "verdict": "review",
        "reasons": [
            "Well-formed USt-IdNr. with a valid check digit (ISO 7064 mod 11,10).",
            "Format check only: it does not show that the business exists, is registered or is active.",
        ],
    },
    "official_lookup_url": "https://ec.europa.eu/taxation_customs/vies/",
}

# Shaped like GET /v1/countries, cut down to a few rows. "ZZ" stands for a country the
# API adds after this module was released.
COUNTRIES = {
    "verification_levels": {"official_registry": "...", "format_and_lists": "...", "format": "..."},
    "countries": [
        {
            "country": "PE",
            "name": "Peru",
            "verification_level": "official_registry",
            "id_types": [
                {
                    "id_type": "RUC",
                    "verification_level": "official_registry",
                    "endpoint": "https://taxid.halpii.com/v1/pe/ruc/{ruc}",
                }
            ],
        },
        {
            "country": "MX",
            "name": "Mexico",
            "verification_level": "format_and_lists",
            "id_types": [
                {
                    "id_type": "RFC",
                    "verification_level": "format_and_lists",
                    "endpoint": "https://taxid.halpii.com/v1/mx/rfc/{rfc}",
                }
            ],
        },
        {
            "country": "GR",
            "name": "Greece",
            "verification_level": "official_registry",
            "aliases": ["EL"],
            "id_types": [
                {
                    "id_type": "VAT",
                    "verification_level": "official_registry",
                    "endpoint": "https://taxid.halpii.com/v1/gr/vat/{id}",
                }
            ],
        },
        {
            "country": "ES",
            "name": "Spain",
            "verification_level": "official_registry",
            "id_types": [
                {"id_type": "NIF", "verification_level": "format", "endpoint": "https://taxid.halpii.com/v1/es/nif/{id}"},
                {
                    "id_type": "VAT",
                    "verification_level": "official_registry",
                    "endpoint": "https://taxid.halpii.com/v1/es/vat/{id}",
                },
            ],
        },
        {
            "country": "UG",
            "name": "Uganda",
            "verification_level": "format",
            "id_types": [
                {"id_type": "TIN", "verification_level": "format", "endpoint": "https://taxid.halpii.com/v1/ug/tin/{id}"}
            ],
        },
        {
            "country": "ZZ",
            "name": "Sample country",
            "verification_level": "format",
            "id_types": [
                {"id_type": "TIN", "verification_level": "format", "endpoint": "https://taxid.halpii.com/v1/zz/tin/{id}"}
            ],
        },
        {"country": "not a code", "id_types": []},
    ],
}


class FakeResponse:
    def __init__(self, status_code, body, headers=None):
        self.status_code = status_code
        self._body = body
        self.headers = headers or {}
        self.text = "" if isinstance(body, Exception) else json.dumps(body)

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body
