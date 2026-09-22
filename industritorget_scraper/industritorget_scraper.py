#!/usr/bin/env python3
import argparse
import csv
import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

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
    "User-Agent": "TonyDjurbergConsulting-IndustritorgetResearch/1.0 (+business-directory research)",
    "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.8",
}

PHONE_RE = re.compile(r"(?<!\d)(?:\+46\s?\d{1,3}[\s-]?(?:\d[\s-]?){6,10}|0\d{1,3}[\s-]?(?:\d[\s-]?){6,10})(?!\d)")
ORG_RE = re.compile(r"\b\d{6}-\d{4}\b")

session = requests.Session()
session.headers.update(HEADERS)


def clean(s):
    return re.sub(r"\s+", " ", s or "").strip()


def normalize_phone(s):
    s = clean(s)
    if not s:
        return ""
    s = re.sub(r"[^0-9+]", "", s)
    if s.startswith("0046"):
        s = "+" + s[2:]
    return s


def is_mobile(phone):
    p = normalize_phone(phone)
    return p.startswith("+467") or p.startswith("07")


def get(url, delay=0.7, timeout=30):
    time.sleep(delay)
    r = session.get(url, timeout=timeout)
    r.raise_for_status()
    return r.text


def page_url(page):
    if page <= 1:
        return DEFAULT_START
    return DEFAULT_START.rstrip("/") + f"/{page}/"


def extract_company_links(html):
    soup = BeautifulSoup(html, "html.parser")
    links = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        full = urljoin(BASE, href)
        if urlparse(full).netloc.endswith("industritorget.se") and "/foretag/" not in full.lower():
            # Company profiles on this site may be under /objekt/ as well as other paths.
            # Keep likely profile links whose anchor looks like a company name/address entry.
            txt = clean(a.get_text(" ", strip=True))
            if txt and len(txt) >= 2 and ("industritorget.se" in full):
                if "/foretag/" in full.lower() or "/objekt/" in full.lower():
                    links.add(full)
    return sorted(links)


def extract_directory_rows(html):
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    # The directory is server-rendered. Capture links plus nearby text and let profile parsing
    # produce the authoritative company record.
    seen = set()
    for a in soup.find_all("a", href=True):
        href = urljoin(BASE, a["href"])
        txt = clean(a.get_text(" ", strip=True))
        if not txt or len(txt) < 2:
            continue
        if urlparse(href).netloc.endswith("industritorget.se") and (
            "/foretag/" in href.lower() or "/objekt/" in href.lower()
        ):
            key = href.split("#")[0]
            if key not in seen:
                seen.add(key)
                rows.append({"url": key, "anchor": txt})
    return rows


def find_labeled_value(soup, labels):
    text = soup.get_text("\n", strip=True)
    lines = [clean(x) for x in text.splitlines() if clean(x)]
    for i, line in enumerate(lines):
        low = line.lower()
        if any(label in low for label in labels):
            # Prefer the next one or two lines when the label is standalone.
            if ":" in line:
                val = clean(line.split(":", 1)[1])
                if val:
                    return val
            if i + 1 < len(lines):
                return lines[i + 1]
    return ""


def parse_contacts(soup):
    contacts = []
    text_lines = [clean(x) for x in soup.get_text("\n", strip=True).splitlines() if clean(x)]

    # Contact blocks are usually rendered as name -> role -> phone(s) -> email.
    # We build small windows and detect names/roles/phones without assuming one fixed CSS class.
    for i, line in enumerate(text_lines):
        if not any(k in line.lower() for k in ROLE_KEYWORDS):
            continue
        role = line
        window = text_lines[max(0, i - 2): min(len(text_lines), i + 5)]
        phones = []
        emails = []
        for w in window:
            phones += [normalize_phone(x) for x in PHONE_RE.findall(w)]
            emails += re.findall(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", w, re.I)
        phones = list(dict.fromkeys([p for p in phones if p]))
        emails = list(dict.fromkeys(emails))
        name = ""
        for w in reversed(window[:3]):
            if w == role or any(k in w.lower() for k in ["skicka", "maila", "ring"]):
                continue
            if re.search(r"[A-Za-zÅÄÖåäöÉéÈèÜü]{2,}\s+[A-Za-zÅÄÖåäöÉéÈèÜü'-]{2,}", w) and not PHONE_RE.search(w):
                name = w
                break
        if name:
            contacts.append({
                "name": name,
                "role": role,
                "phones": phones,
                "mobile": next((p for p in phones if is_mobile(p)), ""),
                "email": emails[0] if emails else "",
            })

    # Deduplicate contact records.
    out, seen = [], set()
    for c in contacts:
        key = (c["name"].lower(), c["role"].lower(), tuple(c["phones"]), c["email"].lower())
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


def parse_profile(url, html):
    soup = BeautifulSoup(html, "html.parser")
    title = clean(soup.find("h1").get_text(" ", strip=True)) if soup.find("h1") else ""
    if not title:
        title = clean(soup.title.get_text(" ", strip=True)) if soup.title else ""

    body = soup.get_text("\n", strip=True)
    org = ""
    m = ORG_RE.search(body)
    if m:
        org = m.group(0)

    lines = [clean(x) for x in body.splitlines() if clean(x)]
    phones = []
    for p in PHONE_RE.findall(body):
        p = normalize_phone(p)
        if p and p not in phones:
            phones.append(p)

    emails = list(dict.fromkeys(re.findall(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", body, re.I)))
    websites = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith("http") and "industritorget.se" not in urlparse(href).netloc:
            websites.append(href)
    websites = list(dict.fromkeys(websites))

    contacts = parse_contacts(soup)

    # Best-effort address extraction from lines around Sweden/postcode.
    address = ""
    postal = ""
    city = ""
    for i, line in enumerate(lines):
        if re.search(r"\b\d{3}\s?\d{2}\b", line):
            postal = re.search(r"\b\d{3}\s?\d{2}\b", line).group(0).replace(" ", "")
            city = line.replace(postal, "").strip(" ,")
            if i > 0:
                address = lines[i - 1]
            break

    main_phone = next((p for p in phones if not is_mobile(p)), phones[0] if phones else "")
    return {
        "company_name": title,
        "org_number": org,
        "address": address,
        "postal_code": postal,
        "city": city,
        "country": "Sverige",
        "main_phone": main_phone,
        "mobile_phones": "; ".join([p for p in phones if is_mobile(p)]),
        "website": websites[0] if websites else "",
        "emails": "; ".join(emails),
        "profile_url": url,
        "contacts_json": json.dumps(contacts, ensure_ascii=False),
        "contact_count": len(contacts),
    }, contacts


def write_csv(path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=5, help="Directory pages to scan in this run")
    ap.add_argument("--delay", type=float, default=0.8)
    ap.add_argument("--out", default="exports")
    args = ap.parse_args()

    out = Path(args.out)
    companies, contacts = [], []
    profile_urls = set()

    for page in range(1, args.pages + 1):
        url = page_url(page)
        print(f"[directory] page {page}: {url}", flush=True)
        try:
            html = get(url, args.delay)
        except Exception as e:
            print(f"[WARN] directory failed: {e}", flush=True)
            continue

        rows = extract_directory_rows(html)
        print(f"  candidate links: {len(rows)}", flush=True)
        for row in rows:
            u = row["url"]
            if u in profile_urls:
                continue
            profile_urls.add(u)
            try:
                ph = get(u, args.delay)
                company, cs = parse_profile(u, ph)
                if company["company_name"]:
                    companies.append(company)
                    for c in cs:
                        contacts.append({
                            "company_name": company["company_name"],
                            "org_number": company["org_number"],
                            "company_profile_url": u,
                            **c
                        })
                    print(f"  + {company['company_name']} | contacts={len(cs)}", flush=True)
            except Exception as e:
                print(f"  [WARN] profile failed {u}: {e}", flush=True)

    # Deduplicate companies by profile URL and contacts by company/name/role.
    companies = list({c["profile_url"]: c for c in companies}.values())
    seen = set()
    dedup_contacts = []
    for c in contacts:
        k = (c["company_profile_url"], c["name"].lower(), c["role"].lower(), c["mobile"], tuple(c["phones"]))
        if k not in seen:
            seen.add(k)
            dedup_contacts.append(c)

    company_fields = [
        "company_name","org_number","address","postal_code","city","country",
        "main_phone","mobile_phones","website","emails","profile_url","contacts_json","contact_count"
    ]
    contact_fields = [
        "company_name","org_number","company_profile_url","name","role","mobile","email","phones"
    ]
    write_csv(out / "industritorget_companies.csv", companies, company_fields)
    write_csv(out / "industritorget_contacts.csv", dedup_contacts, contact_fields)

    summary = {
        "directory_pages": args.pages,
        "profile_urls": len(profile_urls),
        "companies": len(companies),
        "contacts": len(dedup_contacts),
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
