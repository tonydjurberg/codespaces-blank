# Booli Mäklarscraper

Build verification cycle: 2026-09-23.

Real Windows scraper for Booli's Swedish agent directory.

- Opens a real browser with a persistent local profile.
- User logs in manually; credentials are not stored in the program.
- Collects individual /maklare/... profile URLs.
- Opens each individual profile and extracts profile-level data.
- Saves continuously to booli_maklare.csv.
- Resumes using state.json.
- Failed profiles are written to failed_profiles.csv.
- Does not bypass CAPTCHA/security challenges.

The Windows build is produced by GitHub Actions. The EXE uses installed Microsoft Edge when available.
