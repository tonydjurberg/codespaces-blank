# Nya företag – Sweden

This project is intentionally built around official/reusable company data rather than systematic scraping of Allabolag.

## Goal

Produce a daily CSV of newly registered Swedish companies, with a target of 100 new records per run.

Primary output:

`exports/nya_foretag_YYYY-MM-DD.csv`

## Why not scrape Allabolag?

The current Allabolag "Nystartade bolag" page states that regular, systematic or continuous collection, storage, indexing, distribution or compilation of its data is not permitted without written permission from UC Affärsinformation.

The collector therefore does not bypass or automate that restriction.

## Supported input

The first version accepts an official Bolagsverket/SCB export as CSV or Excel and:

- detects common Swedish column names
- normalizes organization numbers
- parses registration dates
- filters newly registered companies
- removes duplicates
- sorts newest first
- writes the first 100 records (configurable)
- keeps a local history so the same company is not delivered twice

The next step can connect the same pipeline to an authorized Bolagsverket API once API credentials are available.

## Windows

Run:

```
run_nya_foretag.bat
```

Or:

```
python nya_foretag.py --input data/bolagsverket.csv --days 30 --limit 100
```

Output is written to `exports/`.
