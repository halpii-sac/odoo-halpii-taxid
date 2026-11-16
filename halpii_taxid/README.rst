=====================================================
Tax ID Validation (58 countries) – HALPII
=====================================================

Validate the tax ID of customers and suppliers from the contact form, in 58
countries, with the HALPII Tax ID API (https://taxid.halpii.com).

Every check stores on the contact:

* **Verdict**: ``pass``, ``review`` or ``fail``, with the **reasons** in plain words.
* **Verification level**: how deep the check went (see below).
* **Data as of**: the date of the registry data the verdict is based on.
* **Official name** and **registry status**, when the source publishes them.

What each verification level checks
====================================

``official_registry``
    The number was looked up in the official tax or business registry, or in
    the copy the registry publishes: Peru (SUNAT RUC), Colombia (RUES),
    Costa Rica (Hacienda, beta), Dominican Republic (DGII), Chile (SII list of
    legal entities), Canada (federal corporations only), Norway, Finland,
    France, Ireland and Taiwan. Only this level can return ``pass``.

``format_and_lists``
    Mexico: structure and check digit of the RFC plus the SAT public lists
    (69 and 69-B). Mexico has no public RFC registry, so the verdict is never
    ``pass``.

``format``
    The other countries (EU VAT, United Kingdom, Brazil, Argentina, India,
    Japan, United States EIN and more): structure and check digit only,
    offline. It shows that the number is well formed, **not** that the
    business exists or is active. The verdict is ``review`` (well formed) or
    ``fail`` (malformed), never ``pass``; a link to the official lookup (for
    example VIES) is stored so you can confirm it yourself.

The full list of countries and ID types: https://taxid.halpii.com/v1/countries

Configuration
=============

Settings > Tax ID Validation:

* **API key**: create one at no cost at https://taxid.halpii.com. Without a
  key the API allows only a few lookups a day per network. Usage beyond the
  key's daily allowance is billed by the API (pay as you go), not by this
  module.
* **Validate on save** (off by default): validate automatically when a
  company or individual is created, or when its tax ID or country changes.
* **Block when the verdict is fail** (off by default): refuse to save a
  contact whose tax ID gets ``fail``. When off, the contact is saved and
  flagged in red. If the service cannot be reached the contact is always
  saved.

Usage
=====

* Contact form: **Validate tax ID** next to the Tax ID field. Results are in
  the **Tax ID check** tab.
* The contact's name is never changed automatically. When the registry name
  differs, the **Use official name** button replaces it after a confirmation.
* Contacts list: column **Tax ID verdict**, filters *Tax ID: pass / review /
  fail / not checked* and group by verdict.
* Bulk: select contacts in the list, then *Actions > Validate selected tax
  IDs* (at most 200 per run). The run stops when the key is rejected (401)
  or the daily limit is reached (429); a source that is down (503) only
  skips that contact, which keeps its previous result.

Labels, buttons and messages are in English and Spanish. The reasons and the
registry status are written by the API and arrive in English.

The country comes from the contact's country, or from an EU-style prefix in
the tax ID (``FR12345678901``). Child contacts of a company are not validated
separately: the company carries the tax ID.

Privacy
=======

Only the country code and the tax ID are sent to taxid.halpii.com, with your
API key. No names, addresses or other contact data leave Odoo.

Limits
======

Results come from public sources and can lag behind the registry (see *Data
as of*). Informational only; not legal or tax advice. Confirm critical cases
with the tax authority.

Credits
=======

Author: HALPII S.A.C. (Lima, Peru) – contacto@halpii.com

License: LGPL-3
