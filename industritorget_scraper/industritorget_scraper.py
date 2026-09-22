#!/usr/bin/env python3
import argparse
import csv
import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse, quote

import requests
from bs4 import BeautifulSoup

BASE = "https://www.industritorget.se"
DEFAULT_START = f"{BASE}/företag/lista/sverige/4020/63/60/3076/"
ROLE_KEYWORDS = [
    "vd", "verkställande direktör", "ceo", "hr", "personalchef", "hr-chef",
    "inköp", "inköpschef", "inköpsansvarig", "procurement", "purchase",
    "ekonomichef", "ekonomi", "finanschef", "cfo", "försäljning", "försäljningschef",
    "sales", "säljchef", "marknadschef", "marketing", "ägare", "delägare",
    "ledning", "administrationschef", "administrativ chef", "chef", "grundare",
    "produktionschef", "inköpare", "kundansvarig", "affärsutveckling", "sales manager"
]
HEADERS = {
    "User-Agent": "TonyDjurbergConsulting-IndustritorgetResearch/1.1",
    "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.8",
}
PHONE_RE = re.compile(r"(?<!\d)(?:\+\d{1,3}[\s-]?(?:\d[\s-]?){7,13}|0\d{1,4}[\s-]?(?:\d[\s-]?){5,11})(?!\d)")
ORG_RE = re.compile(r"\b\d{6}-\d{4}\b")
session = requests.Session()
session.headers.update(HEADERS)

def clean(s): return re.sub(r"\s+", " ", s or "").strip()

def normalize_phone(s):
    s = re.sub(r"[^0-9+]", "", clean(s))
    if s.startswith("00"): s = "+" + s[2:]
    return s

def is_mobile(phone):
    p = normalize_phone(phone)
    return bool(re.match(r"^(?:\+46|0046)7", p) or p.startswith("07"))

def get(url, delay=0.8, timeout=30):
    time.sleep(delay)
    r = session.get(url, timeout=timeout)
    r.raise_for_status()
    return r.text

def page_url(page, country):
    if country.lower() in ("sverige", "sweden"):
        if page <= 1: return DEFAULT_START
        return DEFAULT_START.rstrip("/") + f"/{page}/"
    # Country slugs are passed directly; the scraper also supports a custom start URL.
    return f"{BASE}/företag/lista/{quote(country.strip().lower())}/" if page <= 1 else f"{BASE}/företag/lista/{quote(country.strip().lower())}/{page}/"

def extract_directory_rows(html):
    soup = BeautifulSoup(html, "html.parser")
    rows, seen = [], set()
    for a in soup.find_all("a", href=True):
        href = urljoin(BASE, a["href"]).split("#")[0]
        txt = clean(a.get_text(" ", strip=True))
        if not txt or len(txt) < 2: continue
        if urlparse(href).netloc.endswith("industritorget.se") and ("/objekt/" in href.lower() or "/foretag/" in href.lower()):
            if href not in seen:
                seen.add(href); rows.append({"url": href, "anchor": txt})
    return rows

def parse_contacts(soup):
    lines = [clean(x) for x in soup.get_text("\n", strip=True).splitlines() if clean(x)]
    contacts = []
    for i, line in enumerate(lines):
        low = line.lower()
        matched = [k for k in ROLE_KEYWORDS if k in low]
        if not matched: continue
        role = line
        window = lines[max(0, i-3):min(len(lines), i+6)]
        phones = list(dict.fromkeys(normalize_phone(p) for w in window for p in PHONE_RE.findall(w)))
        phones = [p for p in phones if p]
        emails = list(dict.fromkeys(e for w in window for e in re.findall(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", w, re.I)))
        name = ""
        for w in reversed(window[:4]):
            if w == role or any(x in w.lower() for x in ["skicka", "maila", "ring"]): continue
            if re.fullmatch(r"[A-Za-zÅÄÖåäöÉéÈèÜüØøÆæ'’-]{2,}(?:\s+[A-Za-zÅÄÖåäöÉéÈèÜüØøÆæ'’-]{2,})+", w) and not PHONE_RE.search(w):
                name = w; break
        if name:
            contacts.append({
                "name": name, "role": role, "mobile": next((p for p in phones if is_mobile(p)), ""),
                "email": emails[0] if emails else "", "phones": "; ".join(phones)
            })
    out, seen = [], set()
    for c in contacts:
        k = tuple(c.values())
        if k not in seen: seen.add(k); out.append(c)
    return out

def parse_profile(url, html, country):
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    title = clean(h1.get_text(" ", strip=True)) if h1 else clean(soup.title.get_text(" ", strip=True) if soup.title else "")
    body = soup.get_text("\n", strip=True)
    lines = [clean(x) for x in body.splitlines() if clean(x)]
    phones = list(dict.fromkeys(normalize_phone(p) for p in PHONE_RE.findall(body)))
    phones = [p for p in phones if p]
    emails = list(dict.fromkeys(re.findall(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", body, re.I)))
    websites = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith("http") and "industritorget.se" not in urlparse(href).netloc:
            websites.append(href)
    websites = list(dict.fromkeys(websites))
    org = (ORG_RE.search(body).group(0) if ORG_RE.search(body) else "")
    postal = city = address = ""
    for i, line in enumerate(lines):
        m = re.search(r"\b\d{3}\s?\d{2}\b", line)
        if m:
            postal = m.group(0).replace(" ", "")
            city = clean(line.replace(m.group(0), "").strip(" ,"))
            if i: address = lines[i-1]
            break
    contacts = parse_contacts(soup)
    return {
        "company_name": title, "org_number": org, "address": address,
        "postal_code": postal, "city": city, "country": country,
        "main_phone": next((p for p in phones if not is_mobile(p)), ""),
        "mobile_phones": "; ".join(p for p in phones if is_mobile(p)),
        "website": websites[0] if websites else "", "emails": "; ".join(emails),
        "profile_url": url, "contacts_json": json.dumps(contacts, ensure_ascii=False),
        "contact_count": len(contacts)
    }, contacts

def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore"); w.writeheader(); w.writerows(rows)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--country", default="Sverige", help="Country name/slug, e.g. Sverige, Norge, Finland, Danmark")
    ap.add_argument("--start-url", default="", help="Exact Industritorget directory URL; overrides country")
    ap.add_argument("--pages", type=int, default=5)
    ap.add_argument("--delay", type=float, default=0.8)
    ap.add_argument("--out", default="exports")
    args = ap.parse_args()
    out = Path(args.out); companies=[]; contacts=[]; seen_profiles=set()
    for page in range(1, args.pages+1):
        url = args.start_url if args.start_url and page == 1 else page_url(page, args.country)
        print(f"[directory] {url}", flush=True)
        try: html = get(url, args.delay)
        except Exception as e: print(f"[WARN] directory failed: {e}", flush=True); continue
        rows = extract_directory_rows(html); print(f"  candidate links: {len(rows)}", flush=True)
        for row in rows:
            u=row["url"]
            if u in seen_profiles: continue
            seen_profiles.add(u)
            try:
                ph=get(u,args.delay); company, cs=parse_profile(u,ph,args.country)
                if company["company_name"]:
                    companies.append(company)
                    for c in cs: contacts.append({"company_name":company["company_name"],"org_number":company["org_number"],"company_profile_url":u,**c})
                    print(f"  + {company['company_name']} | contacts={len(cs)}", flush=True)
            except Exception as e: print(f"  [WARN] profile failed {u}: {e}", flush=True)
    companies=list({c["profile_url"]:c for c in companies}.values())
    seen=set(); dc=[]
    for c in contacts:
        k=(c["company_profile_url"],c["name"].lower(),c["role"].lower(),c["mobile"],c["phones"])
        if k not in seen: seen.add(k); dc.append(c)
    write_csv(out/"industritorget_companies.csv",companies,["company_name","org_number","address","postal_code","city","country","main_phone","mobile_phones","website","emails","profile_url","contacts_json","contact_count"])
    write_csv(out/"industritorget_contacts.csv",dc,["company_name","org_number","company_profile_url","name","role","mobile","email","phones"])
    (out/"summary.json").write_text(json.dumps({"country":args.country,"pages":args.pages,"profile_urls":len(seen_profiles),"companies":len(companies),"contacts":len(dc)},ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"country":args.country,"pages":args.pages,"profile_urls":len(seen_profiles),"companies":len(companies),"contacts":len(dc)},ensure_ascii=False),flush=True)

if __name__ == "__main__": main()
