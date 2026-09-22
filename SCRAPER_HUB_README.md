# Scraper Hub

Central entry point for multiple scraper projects in the same GitHub repository.

## Modules
- Eniro: `eniro_scraper/`
- MäklarScraper: `maklarscraper/`
- Google Maps: `google_maps_maklarscraper.py`
- Nya företag: `nya_foretag/`

The hub does not merge scraper logic. Each project remains isolated so one change does not break another.

For private-person sources such as Eniro, only publicly displayed information should be handled and no personnummer should be collected. Do not bypass anti-bot or access controls.
