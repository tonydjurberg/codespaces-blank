from __future__ import annotations

import argparse
import csv
import hashlib
import re
from datetime import date, datetime, timedelta
from pathlib import Path

try:
    import pandas as pd
except ImportError:
    raise SystemExit("Install dependencies first: pip install -r requirements.txt")

ROOT = Path(__file__).resolve().parent
HISTORY = ROOT / "data" / "seen_orgnr.txt"
EXPORTS = ROOT / "exports"

ORG_ALIASES = [
    "orgnr", "orgnr.", "organisationsnummer", "organisationsnr",
    "organizationnumber", "organization_number"
]
NAME_ALIASES = ["namn", "företagsnamn", "companyname", "company_name", "name"]
DATE_ALIASES = [
    "registreringsdatum", "registreringsdag", "registrationdate",
    "registration_date", "bildat", "bildandedatum"
]

def norm(s):
    return re.sub(r"[^a-z0-9åäö]", "", str(s).strip().lower())

def find_col(columns, aliases):
    normalized = {norm(c): c for c in columns}
    for a in aliases:
        if norm(a) in normalized:
            return normalized[norm(a)]
    for c in columns:
        nc = norm(c)
        if any(norm(a) in nc for a in aliases):
            return c
    return None

def clean_org(value):
    if pd.isna(value):
        return ""
    digits = re.sub(r"\D", "", str(value))
    return digits[-10:] if len(digits) >= 10 else digits

def parse_date(value):
    if pd.isna(value):
        return None
    if isinstance(value, (datetime, date)):
        return value.date() if isinstance(value, datetime) else value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y", "%Y%m%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    try:
        return pd.to_datetime(text, dayfirst=True, errors="coerce").date()
    except Exception:
        return None

def read_input(path):
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path, dtype=str)
    return pd.read_csv(path, dtype=str, sep=None, engine="python")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--limit", type=int, default=100)
    args = ap.parse_args()

    src = Path(args.input)
    if not src.exists():
        raise SystemExit(f"Input file not found: {src}")

    df = read_input(src)
    if df.empty:
        raise SystemExit("Input file contains no rows.")

    org_col = find_col(df.columns, ORG_ALIASES)
    name_col = find_col(df.columns, NAME_ALIASES)
    date_col = find_col(df.columns, DATE_ALIASES)

    if not org_col or not name_col or not date_col:
        raise SystemExit(
            "Could not identify required columns. Need organization number, "
            "company name and registration date."
        )

    df["_orgnr"] = df[org_col].map(clean_org)
    df["_registration_date"] = df[date_col].map(parse_date)

    cutoff = date.today() - timedelta(days=args.days)
    df = df[
        (df["_orgnr"].str.len() == 10) &
        (df["_registration_date"].notna()) &
        (df["_registration_date"] >= cutoff)
    ].copy()

    df = df.sort_values("_registration_date", ascending=False)
    df = df.drop_duplicates(subset=["_orgnr"], keep="first")

    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    EXPORTS.mkdir(parents=True, exist_ok=True)

    seen = set()
    if HISTORY.exists():
        seen = {x.strip() for x in HISTORY.read_text(encoding="utf-8").splitlines() if x.strip()}

    new_df = df[~df["_orgnr"].isin(seen)].head(args.limit).copy()

    output = EXPORTS / f"nya_foretag_{date.today().isoformat()}.csv"

    # Keep all source columns plus two normalized fields.
    new_df["organization_number"] = new_df["_orgnr"]
    new_df["registration_date"] = new_df["_registration_date"].map(
        lambda x: x.isoformat() if x else ""
    )
    new_df = new_df.drop(columns=["_orgnr", "_registration_date"])

    new_df.to_csv(output, index=False, encoding="utf-8-sig", quoting=csv.QUOTE_MINIMAL)

    if not new_df.empty:
        with HISTORY.open("a", encoding="utf-8") as f:
            for org in new_df["organization_number"]:
                f.write(str(org) + "\n")

    print(f"NEW_COMPANIES={len(new_df)}")
    print(f"OUTPUT={output}")

if __name__ == "__main__":
    main()
