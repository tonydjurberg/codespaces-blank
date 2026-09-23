import argparse
import csv
import getpass
import os
import re
import sys
import time
import html as html_lib
from urllib.request import Request, urlopen
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

from selenium import webdriver
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait


BASE_FIELDS = [
    "name", "title", "company_role", "mobile", "direct_phone", "switchboard",
    "personal_email", "general_email", "primary_office", "other_offices",
    "postal_code", "city", "profile_url", "company_website",
    "registration_date", "registration_type", "company", "company_address",
    "search_area", "source_url", "sources", "verification_status", "date_fetched",
]

SOURCE_CONFIG = {
    "booli": {
        "start": "https://www.booli.se/sok/maklare",
        "host": "www.booli.se",
        "profile_re": re.compile(r"^/maklare/[^/]+/?$"),
    },
    "hemnet": {
        "start": "https://www.hemnet.se/sok-maklare",
        "host": "www.hemnet.se",
        "profile_re": re.compile(r"^/maklare/(?:profil/)?[^?#]+$"),
    },
    "maklarsamfundet": {
        "start": "https://www.maklarsamfundet.se/maklarsok",
        "host": "www.maklarsamfundet.se",
        "profile_re": re.compile(r"^/maklare/\d+/?$"),
    },
}

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", re.I)
PHONE_RE = re.compile(r"(?:\+46|0)\s*[0-9][0-9\s-]{6,}[0-9]")
POSTAL_RE = re.compile(r"\b\d{3}\s?\d{2}\b")
NOISE = {
    "visa telefonnummer", "bli kontaktad", "kontakta mig", "boka möte",
    "mäklarens försäljningar", "om mig", "sök mäklare", "namnsök",
    "områdessök", "visa fler mäklare",
}


def clean(value):
    return re.sub(r"\s+", " ", value or "").strip()


def norm(value):
    value = clean(value).casefold()
    value = value.replace("å", "a").replace("ä", "a").replace("ö", "o")
    return re.sub(r"[^a-z0-9]+", "", value)


def make_driver(headless=False):
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1600,1200")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--lang=sv-SE")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
    )

    # Dedicated Chrome profile: the normal Booli login/security session survives
    # between runs without touching the user's normal Chrome profile.
    profile_root = Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "BooliMaklarScraper" / "browser_profile"
    profile_root.mkdir(parents=True, exist_ok=True)
    options.add_argument(f"--user-data-dir={profile_root}")

    driver = webdriver.Chrome(options=options)
    try:
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined}); Object.defineProperty(navigator, 'languages', {get: () => ['sv-SE','sv','en-US','en']}); Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});"},
        )
    except Exception:
        pass
    return driver


BOOLI_SECURITY_MARKERS = (
    "säkerhetsverifiering",
    "säkerhetstjänst",
    "verifierar att du inte är någon robot",
    "verify you are human",
    "checking your browser",
    "just a moment",
    "challenge",
)


def _page_text(driver):
    try:
        return clean(driver.find_element(By.TAG_NAME, "body").text).casefold()
    except Exception:
        return ""


def _is_booli_security_page(driver):
    text = _page_text(driver)
    return any(marker in text for marker in BOOLI_SECURITY_MARKERS)


def _has_booli_login_form(driver):
    try:
        email_present = bool(
            driver.find_elements(By.CSS_SELECTOR, 'input[type="email"]')
            or driver.find_elements(By.CSS_SELECTOR, 'input[name="email"]')
            or driver.find_elements(By.CSS_SELECTOR, 'input[autocomplete="email"]')
        )
        password_present = bool(
            driver.find_elements(By.CSS_SELECTOR, 'input[type="password"]')
            or driver.find_elements(By.CSS_SELECTOR, 'input[name="password"]')
            or driver.find_elements(By.CSS_SELECTOR, 'input[autocomplete="current-password"]')
        )
        return email_present and password_present
    except Exception:
        return False


def _looks_like_booli_directory(driver):
    text = _page_text(driver)
    if "sök mäklare i hela sverige" in text or "jämför mäklare i sverige" in text:
        return True
    try:
        for a in driver.find_elements(By.CSS_SELECTOR, 'a[href*="/maklare/"]'):
            href = a.get_attribute("href") or ""
            if is_booli_profile_url(href):
                return True
    except Exception:
        pass
    return False


def is_booli_profile_url(url):
    cleaned = url.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    return bool(
        re.match(r"^https?://(?:www\.)?booli\.se/maklare/[^/?#]+$", cleaned, re.I)
    )


def wait_for_booli_access(driver, headless=False, timeout=900):
    """
    Uses the normal Booli login flow. If Booli displays its security verification,
    leave the browser alone and wait for the user to complete it; never reload
    the page during the verification.
    """
    started = time.time()
    login_attempted = False
    email = os.getenv("BOOLI_EMAIL", "").strip()
    password = os.getenv("BOOLI_PASSWORD", "")

    while time.time() - started < timeout:
        if _looks_like_booli_directory(driver):
            return True

        if _is_booli_security_page(driver):
            if headless:
                raise RuntimeError(
                    "Booli visar säkerhetsverifiering i headless-läge. "
                    "Kör utan --headless första gången och slutför kontrollen i Chrome."
                )
            print(
                "[BOOLI] Säkerhetsverifiering visas. Slutför den i Chrome. "
                "Sidan laddas inte om under kontrollen.",
                flush=True,
            )
            time.sleep(2)
            continue

        if _has_booli_login_form(driver):
            if headless:
                raise RuntimeError(
                    "Booli kräver inloggning. Kör utan --headless första gången och logga in i Chrome."
                )

            if not login_attempted:
                login_attempted = True
                if not email:
                    email = input("Booli e-post: ").strip()
                if not password:
                    password = getpass.getpass("Booli lösenord: ")

                try:
                    email_box = next(
                        (x for x in (
                            driver.find_elements(By.CSS_SELECTOR, 'input[type="email"]'),
                            driver.find_elements(By.CSS_SELECTOR, 'input[name="email"]'),
                            driver.find_elements(By.CSS_SELECTOR, 'input[autocomplete="email"]'),
                        ) if x),
                        None,
                    )
                    password_box = next(
                        (x for x in (
                            driver.find_elements(By.CSS_SELECTOR, 'input[type="password"]'),
                            driver.find_elements(By.CSS_SELECTOR, 'input[name="password"]'),
                            driver.find_elements(By.CSS_SELECTOR, 'input[autocomplete="current-password"]'),
                        ) if x),
                        None,
                    )

                    if not email_box or not password_box:
                        raise RuntimeError("Booli login form was not recognized.")

                    email_box[0].clear()
                    email_box[0].send_keys(email)
                    password_box[0].clear()
                    password_box[0].send_keys(password)

                    clicked = False
                    for button in driver.find_elements(By.CSS_SELECTOR, "button, input[type='submit']")[:20]:
                        try:
                            label = clean(button.text or button.get_attribute("value") or "").casefold()
                            if any(word in label for word in ("logga in", "login", "sign in")):
                                button.click()
                                clicked = True
                                break
                        except Exception:
                            continue
                    if not clicked:
                        password_box[0].send_keys("\n")

                    print(
                        "[BOOLI] Login skickad. Väntar på Booli...",
                        flush=True,
                    )
                except Exception as exc:
                    print(
                        f"[BOOLI] Automatisk login kunde inte slutföras: {exc}",
                        file=sys.stderr,
                        flush=True,
                    )
                    print(
                        "[BOOLI] Slutför login manuellt i Chrome-fönstret.",
                        flush=True,
                    )

            time.sleep(2)
            continue

        time.sleep(1)

    raise TimeoutError("Booli blev inte klar med login/säkerhetskontroll inom 15 minuter.")


def page_signature(driver):
    try:
        return clean(driver.find_element(By.TAG_NAME, "body").text)[:4000]
    except Exception:
        return ""


def wait_page(driver):
    WebDriverWait(driver, 25).until(
        lambda d: d.find_elements(By.TAG_NAME, "body")
        and len(clean(d.find_element(By.TAG_NAME, "body").text)) > 100
    )


def absolute_internal(href, host):
    if not href:
        return ""
    u = urlparse(href)
    if u.scheme not in ("http", "https") or u.netloc != host:
        return ""
    return urlunparse((u.scheme, u.netloc, u.path.rstrip("/") or "/", "", u.query, ""))


def collect_profile_links(driver, source):
    cfg = SOURCE_CONFIG[source]
    links = set()

    # First use Selenium's live DOM.
    for a in driver.find_elements(By.CSS_SELECTOR, "a[href]"):
        try:
            href = absolute_internal(a.get_attribute("href"), cfg["host"])
            if href and cfg["profile_re"].match(urlparse(href).path):
                links.add(href)
        except StaleElementReferenceException:
            continue

    # React/Next-style cards may store profile URLs in non-anchor attributes.
    try:
        js_links = driver.execute_script("""
            const out = new Set();
            const re = /(?:https?:\/\/www\\.booli\\.se)?\\/maklare\\/[^"'<>\\s?#]+/gi;
            for (const el of document.querySelectorAll('*')) {
                for (const attr of el.attributes || []) {
                    const m = (attr.value || '').match(re);
                    if (m) for (const x of m) out.add(x);
                }
            }
            const html = document.documentElement.outerHTML || '';
            for (const x of html.match(re) || []) out.add(x);
            return Array.from(out);
        """)
        for raw in js_links or []:
            href = absolute_internal(urljoin(cfg["start"], raw), cfg["host"])
            if href and cfg["profile_re"].match(urlparse(href).path):
                links.add(href)
    except Exception:
        pass

    # Booli can render broker cards as client-side click targets without a
    # usable href in the DOM. For those cards, activate the heading itself
    # with JavaScript and capture the resulting profile URL.
    if source == "booli" and not links:
        try:
            candidates = driver.find_elements(By.CSS_SELECTOR, "h2, h3")
            current_list = driver.current_url
            for el in candidates[:50]:
                try:
                    text = clean(el.text)
                    if not text or text.casefold() in {"mäklare", "sök mäklare i hela sverige"}:
                        continue
                    before_url = driver.current_url
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", el)
                    time.sleep(0.8)
                    profile_url = absolute_internal(driver.current_url, cfg["host"])
                    if profile_url and cfg["profile_re"].match(urlparse(profile_url).path):
                        links.add(profile_url)
                    if driver.current_url != before_url:
                        driver.get(current_list)
                        wait_page(driver)
                        time.sleep(0.5)
                except Exception:
                    if driver.current_url != current_list:
                        try:
                            driver.get(current_list)
                            wait_page(driver)
                        except Exception:
                            pass
        except Exception:
            pass

    # Some sites hydrate links client-side and some runners receive a
    # different rendered DOM. Use page source first, then a plain HTTP
    # fallback so link discovery does not depend on one browser DOM shape.
    try:
        html = html_lib.unescape(driver.page_source or "")
        pattern = {
            "booli": r'https?://www\.booli\.se/maklare/[^"\'<>\s?#]+|/maklare/[^"\'<>\s?#]+',
            "hemnet": r'https?://www\.hemnet\.se/maklare/(?:profil/)?[^"\'<>\s?#]+|/maklare/(?:profil/)?[^"\'<>\s?#]+',
            "maklarsamfundet": r'https?://www\.maklarsamfundet\.se/maklare/\d+/?|/maklare/\d+/?',
        }[source]
        for raw in re.findall(pattern, html, flags=re.I):
            href = absolute_internal(urljoin(cfg["start"], raw), cfg["host"])
            if href and cfg["profile_re"].match(urlparse(href).path):
                links.add(href)
    except Exception:
        pass

    if not links:
        try:
            req = Request(
                cfg["start"],
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36",
                    "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.8",
                },
            )
            with urlopen(req, timeout=30) as response:
                raw_html = html_lib.unescape(response.read().decode("utf-8", errors="ignore"))
            pattern = {
                "booli": r'href=["\']([^"\']*?/maklare/[^"\']+)',
                "hemnet": r'href=["\']([^"\']*?/maklare/(?:profil/)?[^"\']+)',
                "maklarsamfundet": r'href=["\']([^"\']*?/maklare/\d+/?[^"\']*)',
            }[source]
            for raw in re.findall(pattern, raw_html, flags=re.I):
                href = absolute_internal(urljoin(cfg["start"], raw), cfg["host"])
                if href and cfg["profile_re"].match(urlparse(href).path):
                    links.add(href)
        except Exception as exc:
            print(f"[{source.upper()}] HTTP link fallback failed: {exc}", file=sys.stderr, flush=True)

    return sorted(links)


def next_page_url(driver, current_url, source):
    cfg = SOURCE_CONFIG[source]
    anchors = driver.find_elements(By.CSS_SELECTOR, "a[href]")
    for a in anchors:
        try:
            text = clean(a.text).casefold()
            href = absolute_internal(a.get_attribute("href"), cfg["host"])
            if href and text in ("nästa", "nästa sida", "next", "›", ">"):
                return href
            if href and (a.get_attribute("rel") or "").casefold() == "next":
                return href
        except StaleElementReferenceException:
            continue

    parsed = urlparse(current_url)
    qs = parse_qs(parsed.query)
    current_page = int(qs.get("page", ["1"])[0])
    if current_page >= 1000:
        return None
    qs["page"] = [str(current_page + 1)]
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, urlencode(qs, doseq=True), ""))


def collect_all_profile_links(driver, source, max_pages=1000, smoke=False, headless=False):
    cfg = SOURCE_CONFIG[source]
    current = cfg["start"]
    seen_pages = set()
    links = set()

    for page_no in range(1, max_pages + 1):
        if current in seen_pages:
            break
        seen_pages.add(current)
        print(f"[{source.upper()}] LIST {page_no}: {current}", flush=True)
        driver.get(current)
        if source == "booli":
            wait_for_booli_access(driver, headless=headless)
        wait_page(driver)
        time.sleep(2.0)
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1.0)
        except Exception:
            pass

        before = len(links)
        page_links = collect_profile_links(driver, source)
        links.update(page_links)
        added = len(links) - before
        print(f"[{source.upper()}] LIST {page_no}: +{added}, total {len(links)}", flush=True)

        if smoke:
            break
        if added == 0 and page_no > 1:
            break

        nxt = next_page_url(driver, current, source)
        if not nxt or nxt == current:
            break
        current = nxt

    return sorted(links)


def extract_contacts(driver):
    emails = []
    phones = []
    for a in driver.find_elements(By.CSS_SELECTOR, "a[href]"):
        try:
            href = clean(a.get_attribute("href"))
            text = clean(a.text)
            if href.lower().startswith("mailto:"):
                email = href[7:].split("?", 1)[0].strip()
                if EMAIL_RE.match(email):
                    emails.append(email)
            elif href.lower().startswith("tel:"):
                phone = clean(href[4:])
                if phone:
                    phones.append(phone)
            elif EMAIL_RE.match(text):
                emails.append(text)
        except StaleElementReferenceException:
            continue

    body = driver.find_element(By.TAG_NAME, "body").text
    for line in body.splitlines():
        line = clean(line)
        if EMAIL_RE.match(line):
            emails.append(line)
        for match in PHONE_RE.findall(line):
            phones.append(clean(match))

    return list(dict.fromkeys(emails)), list(dict.fromkeys(phones))


def first_heading(driver):
    for tag in ("h1", "h2"):
        els = driver.find_elements(By.TAG_NAME, tag)
        for el in els:
            try:
                t = clean(el.text)
                if t:
                    return t
            except StaleElementReferenceException:
                pass
    return ""


def infer_location(lines):
    postal = ""
    city = ""
    for line in lines:
        m = POSTAL_RE.search(line)
        if m:
            postal = m.group(0).replace(" ", "")
            tail = clean(line[m.end():].strip(" ,|-"))
            if tail:
                city = tail
            break
    return postal, city


def parse_booli(driver, url):
    name = first_heading(driver)
    emails, phones = extract_contacts(driver)
    lines = [clean(x) for x in driver.find_element(By.TAG_NAME, "body").text.splitlines() if clean(x)]
    company = ""
    for i, line in enumerate(lines):
        if line == name and i + 1 < len(lines):
            candidate = lines[i + 1]
            if candidate.casefold() not in NOISE and candidate != name:
                company = candidate
                break
    postal, city = infer_location(lines)
    return make_row("Booli", name, company, url, emails, phones, postal, city, url)


def parse_hemnet(driver, url):
    name = first_heading(driver)
    emails, phones = extract_contacts(driver)
    lines = [clean(x) for x in driver.find_element(By.TAG_NAME, "body").text.splitlines() if clean(x)]
    company = ""
    if name in lines:
        idx = lines.index(name)
        for candidate in lines[idx + 1:idx + 6]:
            if candidate and candidate.casefold() not in NOISE and not candidate.startswith("Image:"):
                company = candidate
                break
    postal, city = infer_location(lines)
    return make_row("Hemnet", name, company, url, emails, phones, postal, city, url)


def parse_maklarsamfundet(driver, url):
    name = first_heading(driver)
    emails, phones = extract_contacts(driver)
    lines = [clean(x) for x in driver.find_element(By.TAG_NAME, "body").text.splitlines() if clean(x)]
    company = ""
    address = ""
    for i, line in enumerate(lines):
        if line.casefold().startswith("epost:"):
            if i + 1 < len(lines):
                pass
        if name and line == name:
            for candidate in lines[i + 1:i + 8]:
                if candidate and candidate.casefold() not in NOISE and not candidate.startswith("Epost:"):
                    company = candidate
                    break
            break
    postal, city = infer_location(lines)
    if not postal:
        for line in lines:
            if "Tel:" in line:
                continue
            if len(line) > 8 and any(ch.isdigit() for ch in line):
                address = line
    return make_row("Mäklarsamfundet", name, company, url, emails, phones, postal, city, url, address)


def make_row(source, name, company, url, emails, phones, postal="", city="", source_url="", address=""):
    emails = list(dict.fromkeys(emails))
    phones = list(dict.fromkeys(phones))
    mobile = ""
    direct = ""
    switchboard = ""
    for p in phones:
        digits = re.sub(r"\D", "", p)
        if digits.startswith("46"):
            digits = "0" + digits[2:]
        if len(digits) >= 9 and digits[1:2] in ("7",):
            mobile = p
            break
    for p in phones:
        if p != mobile:
            direct = p
            break

    personal_email = emails[0] if emails else ""
    general_email = emails[1] if len(emails) > 1 else ""

    return {
        "name": clean(name),
        "title": "Fastighetsmäklare" if name else "",
        "company_role": "Fastighetsmäklare" if name else "",
        "mobile": mobile,
        "direct_phone": direct,
        "switchboard": switchboard,
        "personal_email": personal_email,
        "general_email": general_email,
        "primary_office": address,
        "other_offices": "",
        "postal_code": postal,
        "city": city,
        "profile_url": url,
        "company_website": "",
        "registration_date": "",
        "registration_type": "",
        "company": clean(company),
        "company_address": clean(address),
        "search_area": "Sverige",
        "source_url": source_url or url,
        "sources": source,
        "verification_status": "Källprofil hittad",
        "date_fetched": date.today().isoformat(),
    }


def parse_profile(driver, source, url, headless=False):
    driver.get(url)
    if source == "booli":
        wait_for_booli_access(driver, headless=headless)
    wait_page(driver)
    time.sleep(0.35)
    if source == "booli":
        return parse_booli(driver, url)
    if source == "hemnet":
        return parse_hemnet(driver, url)
    return parse_maklarsamfundet(driver, url)


def merge_rows(rows):
    merged = {}
    aliases = {}

    for row in rows:
        name_key = norm(row.get("name", ""))
        company_key = norm(row.get("company", ""))
        profile_key = norm(row.get("profile_url", ""))
        if not name_key:
            continue

        # Strong key: same source profile URL. Cross-source key: normalized person
        # + company. If company is missing, fall back to person + city.
        key = f"{name_key}|{company_key}" if company_key else f"{name_key}|{norm(row.get('city',''))}"
        if key not in merged and profile_key in aliases:
            key = aliases[profile_key]

        if key not in merged:
            merged[key] = dict(row)
            merged[key]["sources"] = row.get("sources", "")
            aliases[profile_key] = key
            continue

        existing = merged[key]
        for field in BASE_FIELDS:
            if field == "sources":
                continue
            if not clean(existing.get(field)) and clean(row.get(field)):
                existing[field] = row[field]

        source_names = [x for x in (existing.get("sources", "").split(";") + row.get("sources", "").split(";")) if x]
        existing["sources"] = ";".join(dict.fromkeys(source_names))

        for field in ("mobile", "direct_phone", "switchboard", "personal_email", "general_email", "other_offices"):
            vals = [x for x in (existing.get(field, "") + " | " + row.get(field, "")).split("|") if clean(x)]
            existing[field] = " | ".join(dict.fromkeys(clean(x) for x in vals))

        aliases[profile_key] = key

    return list(merged.values())


def scrape_sources(sources, headless=False, max_pages=1000, max_profiles=0, smoke=False):
    driver = make_driver(headless=headless)
    all_rows = []
    failures = []
    source_counts = {}

    parsers = {
        "booli": "Booli",
        "hemnet": "Hemnet",
        "maklarsamfundet": "Mäklarsamfundet",
    }

    try:
        for source in sources:
            print(f"[SOURCE] {source}", flush=True)
            links = collect_all_profile_links(
                driver,
                source,
                max_pages=max_pages,
                smoke=smoke,
                headless=headless,
            )
            if max_profiles:
                links = links[:max_profiles]
            source_counts[source] = len(links)
            print(f"[{source.upper()}] PROFILE LINKS: {len(links)}", flush=True)

            for i, url in enumerate(links, 1):
                try:
                    row = parse_profile(driver, source, url, headless=headless)
                    if not row["name"]:
                        raise RuntimeError("profile page has no name heading")
                    all_rows.append(row)
                    if i % 25 == 0 or smoke:
                        print(f"[{source.upper()}] PROFILES {i}/{len(links)}", flush=True)
                except Exception as exc:
                    failures.append((parsers[source], url, str(exc)))
                    print(f"[PROFILE ERROR] {source} | {url} | {exc}", file=sys.stderr, flush=True)
                    if smoke and i >= 3:
                        break
    finally:
        driver.quit()

    merged = merge_rows(all_rows)
    return merged, failures, source_counts


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=BASE_FIELDS, delimiter=";", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main():
    ap = argparse.ArgumentParser(description="Swedish broker scraper: Booli + Hemnet + Mäklarsamfundet")
    ap.add_argument("--sources", default="booli,hemnet,maklarsamfundet")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--max-pages", type=int, default=1000)
    ap.add_argument("--max-profiles", type=int, default=0)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--output", default="maklare_combined.csv")
    args = ap.parse_args()

    sources = [x.strip().lower() for x in args.sources.split(",") if x.strip()]
    invalid = [x for x in sources if x not in SOURCE_CONFIG]
    if invalid:
        raise SystemExit(f"Unknown source(s): {', '.join(invalid)}")

    rows, failures, counts = scrape_sources(
        sources,
        headless=args.headless,
        max_pages=args.max_pages,
        max_profiles=args.max_profiles,
        smoke=args.smoke,
    )

    write_csv(args.output, rows)
    with open("maklare_failures.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["source", "url", "error"])
        w.writerows(failures)

    print(f"[DONE] source profile counts: {counts}", flush=True)
    print(f"[DONE] {len(rows)} unique merged brokers -> {args.output}", flush=True)
    print(f"[DONE] {len(failures)} failures -> maklare_failures.csv", flush=True)
    if args.smoke and not rows:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
