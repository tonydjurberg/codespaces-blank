import csv
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote, urljoin
from playwright.sync_api import sync_playwright

BASE = "https://www.eniro.se/privatpersoner"
OUT = Path("eniro_private_people.csv")
QUERY = sys.argv[1].strip() if len(sys.argv) > 1 and sys.argv[1].strip() else "Stockholm"
MAX_PAGES = 200
FIELDS = ["first_name","last_name","full_name","address","postcode","city","phone","profile_url","source"]

def clean(v):
    return re.sub(r"\s+", " ", v or "").strip()

def phone(v):
    m = re.search(r"(?<!\d)(?:0\d{1,3}[ -]?\d{2,3}[ -]?\d{2,4}(?:[ -]?\d{1,4})?|07\d[ -]?\d{3}[ -]?\d{2}[ -]?\d{2})(?!\d)", v)
    return clean(m.group(0)) if m else ""

def load_existing():
    rows = {}
    if OUT.exists():
        with OUT.open("r", encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                key = (r.get("full_name",""), r.get("address",""), r.get("phone",""))
                if any(key):
                    rows[key] = r
    return rows

def save(rows):
    tmp = OUT.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows.values())
    tmp.replace(OUT)

def parse_card(card):
    text = clean(card.inner_text())
    lines = [clean(x) for x in card.inner_text().splitlines() if clean(x)]
    if not lines:
        return None
    a = card.locator("a").first
    href = a.get_attribute("href") if a.count() else ""
    href = urljoin("https://www.eniro.se", href or "")
    name = lines[0]
    ph = phone(text)
    address = postcode = city = ""
    for line in lines[1:]:
        if re.search(r"\b\d{3}\s?\d{2}\b", line):
            address = line
            m = re.search(r"(\d{3}\s?\d{2})\s+(.+)$", line)
            if m:
                postcode = clean(m.group(1))
                city = clean(m.group(2))
            break
    parts = name.split()
    return {
        "first_name": parts[0] if parts else "",
        "last_name": " ".join(parts[1:]) if len(parts) > 1 else "",
        "full_name": name,
        "address": address,
        "postcode": postcode,
        "city": city,
        "phone": ph,
        "profile_url": href if href.startswith("https://www.eniro.se") else "",
        "source": "Eniro.se",
    }

def main():
    rows = load_existing()
    print(f"SEARCH: {QUERY}")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        for n in range(1, MAX_PAGES + 1):
            url = f"{BASE}?q={quote(QUERY)}&page={n}"
            print(f"PAGE {n}: {url}")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(2500)
            except Exception as e:
                print("Navigation error:", e)
                continue
            for label in ["Acceptera alla", "Godkänn alla", "Accept all"]:
                try:
                    page.get_by_role("button", name=re.compile(label, re.I)).click(timeout=1200)
                    break
                except Exception:
                    pass
            before = len(rows)
            links = page.locator("a").all()
            for link in links:
                try:
                    href = link.get_attribute("href") or ""
                    if not re.search(r"(person|privatperson)", href, re.I):
                        continue
                    card = link.locator("xpath=..")
                    row = parse_card(card)
                    if row and row["full_name"]:
                        key = (row["full_name"], row["address"], row["phone"])
                        rows[key] = row
                except Exception:
                    pass
            save(rows)
            added = len(rows) - before
            print(f"  added={added}; total={len(rows)}")
            if added == 0 and n > 1:
                print("No new records; stopping.")
                break
            time.sleep(1)
        browser.close()
    print(f"DONE: {len(rows)} records -> {OUT.resolve()}")
    print("No personnummer field is collected or stored.")

if __name__ == "__main__":
    main()
