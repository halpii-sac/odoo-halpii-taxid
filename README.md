# Tax ID Validation (120+ countries) – HALPII · Odoo module

Odoo 17 and 18 (Community) module `halpii_taxid`: validates the tax ID of
contacts with the [HALPII Tax ID API](https://taxid.halpii.com) and stores the verdict
(pass / review / fail), the reasons, the verification level and the date of the registry data.
It covers 120+ countries and territories; the current list is at <https://taxid.halpii.com/countries>
and the module reads it from the API, so new countries work without an update.

- Module: [`halpii_taxid/`](halpii_taxid/) (see its `README.rst`, which also carries the changelog)
- License: LGPL-3
- Branches: `17.0` and `18.0` (one per Odoo version, as the Odoo Apps Store requires)

## Local test

```sh
docker compose up -d db
docker compose run --rm odoo odoo -d test -i contacts,halpii_taxid \
  --test-tags /halpii_taxid --stop-after-init --without-demo=all
docker compose down -v
```

`ODOO_VERSION=18` runs the same on Odoo 18. The tests mock the API: no key or network needed.
