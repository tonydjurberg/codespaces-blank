from __future__ import annotations
import csv, io, re, sys
from pathlib import Path
import pandas as pd

def norm_col(c):
    return re.sub(r"[^a-z0-9åäöé]","",str(c).lower())

def clean_org(v):
    s = re.sub(r"\D","",str(v or ""))
    if len(s) == 10: return s
    if len(s) == 12 and s.startswith("16"): return s[2:]
    return ""

def parse_name(v):
    if not v: return ""
    return str(v).split("|",1)[0].split("$",1)[0].strip()

def read_txt(path):
    raw = Path(path).read_bytes()
    text = raw.decode("utf-8-sig", errors="replace")
    sample = "\n".join(text.splitlines()[:30])
    best = None
    for sep in ("\t",";","|"):
        rows = list(csv.reader(io.StringIO(sample), delimiter=sep))
        score = max((len(r) for r in rows), default=0)
        if best is None or score > best[0]: best = (score, sep)
    if not best or best[0] < 5:
        raise ValueError(f"Cannot detect delimiter in {path}")
    # Bolagsverket's official TXT can contain literal quote characters inside
    # free-text fields. Treat the file as delimiter-separated data rather than
    # interpreting those quotes as CSV quoting.
    return pd.read_csv(path, sep=best[1], dtype=str, encoding="utf-8-sig",
                       keep_default_na=False, engine="python",
                       quoting=csv.QUOTE_NONE, on_bad_lines="error")

def find_col(df, *names):
    m = {norm_col(c): c for c in df.columns}
    for n in names:
        k = norm_col(n)
        if k in m: return m[k]
    for c in df.columns:
        nc = norm_col(c)
        if any(norm_col(n) in nc for n in names):
            return c
    return None

def first_txt(folder, exclude=None):
    for p in Path(folder).rglob("*.txt"):
        if exclude and exclude.lower() in p.name.lower(): continue
        return p
    return None

def main():
    if len(sys.argv) != 3:
        raise SystemExit("Usage: build_companies.py INPUT_DIR OUTPUT.csv")
    srcdir, out = map(Path, sys.argv[1:])
    bv = first_txt(srcdir, "scb")
    if not bv: raise ValueError("No Bolagsverket TXT found")
    bdf = read_txt(bv)
    orgc = find_col(bdf, "organisationsidentitet","orgnr","organisationsnummer")
    namec = find_col(bdf, "organisationsnamn","företagsnamn","namn")
    regc = find_col(bdf, "registreringsdatum")
    formc = find_col(bdf, "organisationsform","juridiskform")
    desc = find_col(bdf, "verksamhetsbeskrivning")
    addrc = find_col(bdf, "postadress")
    if not all([orgc,namec,regc]):
        raise ValueError("Required Bolagsverket fields missing")
    outdf = pd.DataFrame()
    outdf["organisationsnummer"] = bdf[orgc].map(clean_org)
    outdf["företagsnamn"] = bdf[namec].map(parse_name)
    outdf["registreringsdatum"] = bdf[regc]
    outdf["status"] = bdf[find_col(bdf,"avregistreringsdatum")].apply(lambda x: "avregistrerad" if str(x).strip() else "registrerad") if find_col(bdf,"avregistreringsdatum") else ""
    outdf["organisationsform"] = bdf[formc] if formc else ""
    outdf["verksamhetsbeskrivning"] = bdf[desc] if desc else ""
    if addrc:
        addr = bdf[addrc].astype(str).str.split("$", n=4, expand=True)
        for i,n in enumerate(["adress","c_o_adress","postnummer","ort","land"]):
            outdf[n] = addr[i] if i in addr.columns else ""
    else:
        for n in ["adress","c_o_adress","postnummer","ort","land"]: outdf[n]=""

    scb = None
    for p in Path(srcdir).rglob("*.txt"):
        if "scb" in p.name.lower():
            scb = p; break
    if scb:
        sdf = read_txt(scb)
        so = find_col(sdf,"OrgNr","PeOrgNr","organisationsnummer")
        if so:
            s = pd.DataFrame()
            s["organisationsnummer"] = sdf[so].map(clean_org)
            mappings = {
                "telefon":("Telefon","telefonnummer"),
                "e_post":("E-post","Epost","email"),
                "sni_1":("Ng1","SNI","Bransch_1"),
                "sni_2":("Ng2",),
                "sni_3":("Ng3",),
                "sni_4":("Ng4",),
                "sni_5":("Ng5",),
                "anstallda_storleksklass":("AnstSME","Storleksklass","Antal anställda"),
                "reklam":("Reklam",),
                "arbetsstallen":("Antal arbetsställen","AntalArbetsställen"),
                "webbplats":("Webbplats","Hemsida","Internetadress"),
            }
            for outname,names in mappings.items():
                c=find_col(sdf,*names)
                s[outname]=sdf[c] if c else ""
            s=s.drop_duplicates("organisationsnummer")
            outdf=outdf.merge(s,on="organisationsnummer",how="left")
        else:
            for n in ["telefon","e_post","sni_1","sni_2","sni_3","sni_4","sni_5","anstallda_storleksklass","reklam","arbetsstallen","webbplats"]: outdf[n]=""
    else:
        for n in ["telefon","e_post","sni_1","sni_2","sni_3","sni_4","sni_5","anstallda_storleksklass","reklam","arbetsstallen","webbplats"]: outdf[n]=""

    outdf["mobil"] = ""
    outdf["telefon_kalla"] = outdf["telefon"].apply(lambda x: "SCB" if str(x).strip() else "")
    outdf["mobil_kalla"] = ""
    outdf = outdf[(outdf["organisationsnummer"].str.len()==10) & outdf["företagsnamn"].ne("")]
    outdf = outdf.drop_duplicates("organisationsnummer", keep="first")
    outdf = outdf.sort_values(["registreringsdatum","företagsnamn"], ascending=[False,True], na_position="last")
    outdf.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"ROWS={len(outdf)}")
    print(f"WITH_PHONE={outdf['telefon'].astype(str).str.strip().ne('').sum()}")
    print(f"WITH_MOBILE={outdf['mobil'].astype(str).str.strip().ne('').sum()}")
    print(f"OUTPUT={out}")

if __name__ == "__main__":
    main()
