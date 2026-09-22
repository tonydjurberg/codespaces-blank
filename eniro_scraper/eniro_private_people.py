import csv
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote, urljoin
from playwright.sync_api import sync_playwright

SEARCH_BASE = "https://www.eniro.se/kartor/sök"
OUT = Path("eniro_private_people.csv")
QUERY = sys.argv[1].strip() if len(sys.argv) > 1 and sys.argv[1].strip() else "Stockholm"
MAX_PAGES = 200
FIELDS = ["first_name","last_name","full_name","address","postcode","city","phone","profile_url","source"]

def clean(v):
    return re.sub(r"\s+", " ", v or "").strip()

def normalize_postcode(v):
    return re.sub(r"\s+", "", v or "").strip()

def is_postcode_query(v):
    return bool(re.fullmatch(r"\d{3}\s?\d{2}", v))

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
    lines = [clean(x) for x in card.inner_text().splitlines() if clean(x)]
    if not lines:
        return None

    href = ""
    try:
        href = card.locator("a").first.get_attribute("href") or ""
    except Exception:
        pass
    href = urljoin("https://www.eniro.se", href)

    name = lines[0]
    ph = phone("\n".join(lines))
    address = postcode = city = ""

    for line in lines[1:]:
        m = re.search(r"(\d{3}\s?\d{2})\s+(.+)$", line)
        if m:
            postcode = clean(m.group(1))
            city = clean(m.group(2))
            address = line
            break

    if not postcode:
        return None

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
    postcode_mode = is_postcode_query(QUERY)
    wanted_postcode = normalize_postcode(QUERY) if postcode_mode else ""

    print(f"SEARCH: {QUERY}")
    if postcode_mode:
        print(f"MODE: exact postcode {wanted_postcode}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        for n in range(1, MAX_PAGES + 1):
            encoded = quote(QUERY, safe="")
            url = f"{SEARCH_BASE}/{encoded}?fit=true&t=persons&page={n}"
            print(f"PAGE {n}: {url}")

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(2000)
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
                    if not re.search(r"/(person|privatperson)", href, re.I):
                        continue

                    # Walk upward to find the result block rather than assuming one parent level.
                    card = link
                    for _ in range(5):
                        parent = card.locator("xpath=..")
                        text = clean(parent.inner_text())
                        if re.search(r"\b\d{3}\s?\d{2}\b", text):
                            card = parent
                        else:
                            break

                    row = parse_card(card)
                    if not row or not row["full_name"]:
                        continue

                    if postcode_mode and normalize_postcode(row["postcode"]) != wanted_postcode:
                        continue

                    key = (row["full_name"], row["address"], row["phone"])
                    rows[key] = row
                except Exception:
                    pass

            save(rows)
            added = len(rows) - before
            print(f"  added={added}; total={len(rows)}")

            if added == 0 and n > 1:
                print("No new matching records; stopping.")
                break

            time.sleep(1)

        browser.close()

    print(f"DONE: {len(rows)} records -> {OUT.resolve()}")
    print("No personnummer field is collected or stored.")

if __name__ == "__main__":
    main()
