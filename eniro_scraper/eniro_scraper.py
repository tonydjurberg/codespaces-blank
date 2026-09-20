import argparse
import csv
import re
import sys
import time
from datetime import date
from urllib.parse import quote_plus, urljoin, urlparse

from selenium import webdriver
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait


FIELDS = [
    "company",
    "address",
    "postal_code",
    "city",
    "phone",
    "website",
    "profile_url",
    "source_url",
    "search_query",
    "date_fetched",
]

POSTAL_RE = re.compile(r"\b\d{3}\s?\d{2}\b")
PHONE_RE = re.compile(r"(?:\+46|0)\s*[0-9][0-9\s-]{5,}[0-9]")
HOST = "www.eniro.se"

COOKIE_WORDS = (
    "acceptera alla",
    "godkänn alla",
    "godkänn",
    "acceptera",
    "accept all",
    "allow all",
    "agree",
)


def clean(value):
    return re.sub(r"\s+", " ", value or "").strip()


def absolute_url(href):
    if not href:
        return ""
    u = urlparse(urljoin("https://www.eniro.se/", href))
    if u.scheme not in ("http", "https") or u.netloc != HOST:
        return ""
    return u._replace(fragment="").geturl()


def make_driver(headless=True):
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1600,1200")
    options.add_argument("--lang=sv-SE")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-popup-blocking")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
    )
    driver = webdriver.Chrome(options=options)
    try:
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source":
             "Object.defineProperty(navigator,'languages',{get:()=>['sv-SE','sv','en-US','en']});"
             "Object.defineProperty(navigator,'platform',{get:()=> 'Win32'});"}
        )
    except Exception:
        pass
    return driver


def click_cookie_consent(driver):
    # Normal cookie-consent handling only. No CAPTCHA or access-control bypass.
    end = time.time() + 12
    while time.time() < end:
        clicked = False
        selectors = [
            "button",
            "[role='button']",
            "input[type='button']",
            "input[type='submit']",
        ]
        for selector in selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
            except Exception:
                continue
            for el in elements:
                try:
                    label = clean(el.text).casefold()
                    aria = clean(el.get_attribute("aria-label")).casefold()
                    title = clean(el.get_attribute("title")).casefold()
                    value = clean(el.get_attribute("value")).casefold()
                    combined = " | ".join(x for x in (label, aria, title, value) if x)
                    if any(word in combined for word in COOKIE_WORDS):
                        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                        time.sleep(0.15)
                        try:
                            el.click()
                        except Exception:
                            driver.execute_script("arguments[0].click();", el)
                        time.sleep(0.8)
                        clicked = True
                        break
                except StaleElementReferenceException:
                    continue
            if clicked:
                break
        if clicked:
            return True

        # Some consent managers expose buttons in shadow DOM.
        try:
            result = driver.execute_script("""
                const words = %s;
                const seen = new Set();
                const visit = root => {
                  if (!root || seen.has(root)) return null;
                  seen.add(root);
                  for (const el of root.querySelectorAll ? root.querySelectorAll('*') : []) {
                    const txt = ((el.innerText || '') + ' ' +
                                 (el.getAttribute?.('aria-label') || '') + ' ' +
                                 (el.getAttribute?.('title') || '')).trim().toLowerCase();
                    if (words.some(w => txt === w || txt.includes(w))) {
                      if (el.tagName === 'BUTTON' || el.getAttribute('role') === 'button') {
                        el.click();
                        return true;
                      }
                    }
                    if (el.shadowRoot && visit(el.shadowRoot)) return true;
                  }
                  return false;
                };
                return visit(document);
            """ % repr(list(COOKIE_WORDS)))
            if result:
                time.sleep(1)
                return True
        except Exception:
            pass
        time.sleep(0.4)
    return False


def wait_body(driver):
    WebDriverWait(driver, 25).until(
        lambda d: d.find_elements(By.TAG_NAME, "body")
        and len(clean(d.find_element(By.TAG_NAME, "body").text)) > 80
    )


def search_url(query, page=1):
    encoded = quote_plus(query.strip())
    suffix = "" if page == 1 else f"&page={page}"
    return f"https://www.eniro.se/kartor/sok/{encoded}?fit=true&t=companies{suffix}"


def is_result_link(href):
    if not href:
        return False
    path = urlparse(href).path.casefold()
    if not path or path in ("/", "/kartor/sok", "/sok/foretag"):
        return False
    blocked = ("/hjalp/", "/kundservice/", "/om-eniro", "/jobb/", "/blogg/")
    return not any(x in path for x in blocked)


def collect_result_links(driver):
    links = []
    seen = set()

    for a in driver.find_elements(By.CSS_SELECTOR, "a[href]"):
        try:
            href = absolute_url(a.get_attribute("href"))
            text = clean(a.text)
            if not href or not text or not is_result_link(href):
                continue
            # Result cards normally contain "läs mer" or a company heading/link.
            if "läs mer" in text.casefold() or len(text) >= 2:
                key = href.split("?", 1)[0]
                if key not in seen:
                    seen.add(key)
                    links.append(href)
        except StaleElementReferenceException:
            continue

    return links


def parse_result_page(driver, url, query):
    wait_body(driver)
    click_cookie_consent(driver)
    time.sleep(0.5)

    body_lines = [clean(x) for x in driver.find_element(By.TAG_NAME, "body").text.splitlines() if clean(x)]

    name = ""
    for tag in ("h1", "h2", "h3"):
        for el in driver.find_elements(By.TAG_NAME, tag):
            try:
                t = clean(el.text)
                if t and t.casefold() not in ("företag", "personer", "platser"):
                    name = t
                    break
            except StaleElementReferenceException:
                continue
        if name:
            break

    address = ""
    postal = ""
    city = ""
    phone = ""
    website = ""

    for line in body_lines:
        m = POSTAL_RE.search(line)
        if m and not postal:
            postal = m.group(0).replace(" ", "")
            tail = clean(line[m.end():].strip(" ,-"))
            if tail:
                city = tail

        p = PHONE_RE.search(line)
        if p and not phone:
            phone = clean(p.group(0))

    for a in driver.find_elements(By.CSS_SELECTOR, "a[href]"):
        try:
            href = clean(a.get_attribute("href"))
            text = clean(a.text)
            if href.lower().startswith("tel:") and not phone:
                phone = clean(href[4:])
            elif href.lower().startswith("http") and urlparse(href).netloc not in ("www.eniro.se", "eniro.se"):
                if text.casefold() in ("hemsida", "website", "webbplats") or not website:
                    website = href
        except StaleElementReferenceException:
            continue

    if postal:
        for i, line in enumerate(body_lines):
            if postal[:3] in line.replace(" ", ""):
                address = line
                break

    return {
        "company": name,
        "address": address,
        "postal_code": postal,
        "city": city,
        "phone": phone,
        "website": website,
        "profile_url": url,
        "source_url": f"https://www.eniro.se/{quote_plus(query)}",
        "search_query": query,
        "date_fetched": date.today().isoformat(),
    }


def scrape(query, pages, max_results, headless):
    driver = make_driver(headless=headless)
    rows = []
    seen_profiles = set()

    try:
        for page in range(1, pages + 1):
            url = search_url(query, page)
            print(f"[ENIRO] LIST {page}: {url}", flush=True)
            driver.get(url)
            wait_body(driver)
            click_cookie_consent(driver)
            time.sleep(1.5)

            links = collect_result_links(driver)
            print(f"[ENIRO] LIST {page}: {len(links)} candidate links", flush=True)

            for profile_url in links:
                key = profile_url.split("?", 1)[0]
                if key in seen_profiles:
                    continue
                seen_profiles.add(key)

                if max_results and len(rows) >= max_results:
                    return rows

                try:
                    driver.get(profile_url)
                    click_cookie_consent(driver)
                    row = parse_result_page(driver, profile_url, query)
                    if row["company"]:
                        rows.append(row)
                        print(f"[ENIRO] {len(rows)}: {row['company']}", flush=True)
                except Exception as exc:
                    print(f"[ENIRO] PROFILE ERROR: {profile_url} | {exc}", file=sys.stderr, flush=True)

    finally:
        driver.quit()

    return rows


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, delimiter=";", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main():
    ap = argparse.ArgumentParser(description="ENIRO.SE public company search scraper")
    ap.add_argument("--query", default="mäklare")
    ap.add_argument("--pages", type=int, default=1)
    ap.add_argument("--max-results", type=int, default=10)
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--output", default="eniro_results.csv")
    args = ap.parse_args()

    rows = scrape(args.query, args.pages, args.max_results, args.headless)
    write_csv(args.output, rows)
    print(f"[DONE] {len(rows)} company records -> {args.output}", flush=True)
    return 0 if rows else 2


if __name__ == "__main__":
    raise SystemExit(main())
