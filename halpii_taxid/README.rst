=====================================================
Tax ID Validation (120+ countries) – HALPII
=====================================================

Validate the tax ID of customers and suppliers from the contact form, in 120+
countries and territories, with the HALPII Tax ID API
(https://taxid.halpii.com). The current list is at
https://taxid.halpii.com/countries.

Every check stores on the contact:

* **Verdict**: ``pass``, ``review`` or ``fail``, with the **reasons** in plain words.
* **Verification level**: how deep the check went (see below).
* **Data as of**: the date of the registry data the verdict is based on.
* **Official name** and **registry status**, when the source publishes them.

What each verification level checks
====================================

The level is stored on every check, because it depends on the country **and**
on the ID type.

``official_registry``
    The number was looked up in the official tax or business registry, or in
    the copy the registry publishes. Today: Peru (SUNAT RUC), Colombia (RUES),
    Costa Rica (Hacienda, beta), Dominican Republic (DGII), Chile (SII list of
    legal entities), Canada (federal corporations only), Norway, Switzerland,
    Taiwan, Singapore, Israel, and the EU member states. For EU VAT numbers
    the source is VIES of the European Commission: it confirms that the number
    is registered for intra-EU transactions (and gives the name where the
    member state shares it), not the trade-register status. Some ID types of
    these countries are still format only (for example the Spanish NIF or the
    Irish VAT number). Only this level can return ``pass``.

``format_and_lists``
    Mexico: structure and check digit of the RFC plus the SAT public lists
    (69 and 69-B). Mexico has no public RFC registry, so the verdict is never
    ``pass``.

``format``
    Most of the other countries and territories (United Kingdom, Brazil,
    Argentina, India, Japan, United States EIN and more): structure and check
    digit only, offline. It shows that the number is well formed, **not** that
    the business exists or is active. The verdict is ``review`` (well formed)
    or ``fail`` (malformed), never ``pass``; when the country has an official
    lookup, its link is stored so you can confirm it yourself.

Countries, ID types and the level of each one:
https://taxid.halpii.com/countries (machine-readable:
https://taxid.halpii.com/v1/countries). The module reads this list from the
API once a day, so a country added there works in Odoo without updating the
module; an embedded copy is used only while the API cannot be reached.

Configuration
=============

Settings > Tax ID Validation:

* **API key**: create a no-cost key at https://taxid.halpii.com; it includes
  100 lookups a month. Without a key the API allows only a few lookups a day
  per network. For higher volumes the API has a monthly plan: US$39 a month
  with 1,000 lookups included and US$0.03 per extra lookup
  (https://taxid.halpii.com/pricing). The plan is billed by the API, not by
  this module.
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
  or the lookup limit is reached (429); a source that is down (503) only
  skips that contact, which keeps its previous result.

Labels, buttons and messages are in English and Spanish. The reasons and the
registry status are written by the API and arrive in English.

The country comes from the contact's country, or from a country prefix in
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

Changelog
=========

1.1.1 (2026-11-20)
    * The no-cost key of the HALPII Tax ID API is now counted by month: 100
      lookups a month (before, 100 a day). The settings, the description and
      the limit message (now "Monthly lookup limit reached") say so, and the
      message names the monthly plan: US$39 a month with 1,000 lookups
      included. No change in behaviour or data.

1.1.0 (2026-11-20)
    * The list of supported countries is read from the API
      (``GET /v1/countries``) and kept for a day, instead of a fixed list of
      58: the 120+ countries and territories covered today, and those added
      later, validate without a module update. An embedded copy (121
      countries, 2026-11-20) is the backup when the API cannot be reached.
    * A country prefix in the tax ID is only read as a country when a digit
      follows it or the country uses VAT numbers.
    * Texts and messages no longer carry a country count; the daily-limit
      message and the settings show the current terms (no-cost key with 100
      lookups a day, monthly plan on the pricing page).

1.0.0 (2026-11-16)
    * First release.

Credits
=======

Author: HALPII S.A.C. (Lima, Peru) – contacto@halpii.com

License: LGPL-3
