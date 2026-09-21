from __future__ import annotations
import csv, io, re, sys
from pathlib import Path
import pandas as pd

EXPECTED = [
    "organisationsidentitet","namnskyddslopnummer","registreringsland",
    "organisationsnamn","organisationsform","avregistreringsdatum",
    "avregistreringsorsak","pagandeAvvecklingsEllerOmstruktureringsforfarande",
    "registreringsdatum","verksamhetsbeskrivning","postadress"
]

def clean_org(v):
    s = re.sub(r"\D","",str(v or ""))
    if len(s) == 10: return s
    if len(s) == 12 and s.startswith("16"): return s[2:]
    return ""

def parse_name(v):
    if not v: return ""
    first = str(v).split("|",1)[0]
    return first.split("$",1)[0].strip()

def read_txt(path):
    raw = Path(path).read_bytes()
    text = raw.decode("utf-8-sig", errors="replace")
    lines = text.splitlines()
    if not lines: raise ValueError("Empty Bolagsverket TXT file")
    sample = "\n".join(lines[:30])
    candidates = ["\t",";"]
    best = None
    for sep in candidates:
        rows = list(csv.reader(io.StringIO(sample), delimiter=sep))
        score = max((len(r) for r in rows), default=0)
        if best is None or score > best[0]:
            best = (score, sep)
    if best[0] < 10:
        raise ValueError("Could not identify the official TXT delimiter")
    df = pd.read_csv(path, sep=best[1], dtype=str, encoding="utf-8-sig",
                     keep_default_na=False, engine="python", quoting=csv.QUOTE_MINIMAL)
    if len(df.columns) < 10:
        raise ValueError(f"Expected ~11 columns, got {len(df.columns)}")
    df.columns = [c.strip() for c in df.columns]
    return df

def main():
    if len(sys.argv) != 3:
        raise SystemExit("Usage: build_companies.py INPUT.txt OUTPUT.csv")
    src, out = map(Path, sys.argv[1:])
    df = read_txt(src)
    # Match official field names case-insensitively.
    lookup = {c.lower(): c for c in df.columns}
    missing = [c for c in EXPECTED if c.lower() not in lookup]
    if missing:
        raise ValueError("Missing official fields: " + ", ".join(missing))
    df = df.rename(columns={lookup[c.lower()]: c for c in EXPECTED})
    outdf = pd.DataFrame()
    outdf["organisationsnummer"] = df["organisationsidentitet"].map(clean_org)
    outdf["företagsnamn"] = df["organisationsnamn"].map(parse_name)
    outdf["registreringsdatum"] = df["registreringsdatum"].replace("", pd.NA)
    outdf["status"] = df["avregistreringsdatum"].apply(lambda x: "avregistrerad" if str(x).strip() else "registrerad")
    outdf["organisationsform"] = df["organisationsform"]
    outdf["verksamhetsbeskrivning"] = df["verksamhetsbeskrivning"]
    addr = df["postadress"].astype(str).str.split("$", n=4, expand=True)
    for i,name in enumerate(["adress","c_o_adress","postnummer","ort","land"]):
        outdf[name] = addr[i] if i in addr.columns else ""
    outdf = outdf[(outdf["organisationsnummer"].str.len()==10) & outdf["företagsnamn"].ne("")]
    outdf = outdf.drop_duplicates("organisationsnummer", keep="first")
    outdf = outdf.sort_values(["registreringsdatum","företagsnamn"], ascending=[False,True], na_position="last")
    outdf.to_csv(out, index=False, encoding="utf-8-sig", quoting=csv.QUOTE_MINIMAL)
    print(f"ROWS={len(outdf)}")
    print(f"OUTPUT={out}")

if __name__ == "__main__":
    main()
