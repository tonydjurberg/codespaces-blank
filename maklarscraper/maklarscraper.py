import argparse
import csv
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

from selenium import webdriver
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

FMI_URL = "https://fmi.se/soktjanster/sok-maklare/"
OUT_DEFAULT = "maklare_fmi.csv"

SKANE_MUNICIPALITIES = [
    "Bjuv", "Bromölla", "Burlöv", "Båstad", "Eslöv", "Helsingborg",
    "Hässleholm", "Höganäs", "Hörby", "Höör", "Klippan", "Kristianstad",
    "Kävlinge", "Landskrona", "Lomma", "Lund", "Malmö", "Osby",
    "Perstorp", "Simrishamn", "Sjöbo", "Skurup", "Staffanstorp", "Svalöv",
    "Svedala", "Tomelilla", "Trelleborg", "Vellinge", "Ystad", "Åstorp",
    "Ängelholm", "Örkelljunga", "Östra Göinge",
]

FIELDS = [
    "name", "registration_date", "registration_type", "company",
    "company_address", "offices", "search_area", "source_url",
]

def clean(value):
    return re.sub(r"\\s+", " ", value or "").strip()

def norm(value):
    value = clean(value).casefold()
    return re.sub(r"[^a-z0-9åäö]+", "", value)

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
    return webdriver.Chrome(options=options)

def visible_elements(driver, by, selector):
    return [e for e in driver.find_elements(by, selector) if e.is_displayed()]

def click_text(driver, text):
    xpath = f"//*[self::button or self::a][contains(normalize-space(.), '{text}')]"
    for el in visible_elements(driver, By.XPATH, xpath):
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
            driver.execute_script("arguments[0].click();", el)
            return True
        except Exception:
            continue
    return False

def close_message(driver):
    # FMI currently exposes a visible "Stäng meddelandet" button.
    click_text(driver, "Stäng meddelandet")

def open_advanced(driver):
    click_text(driver, "Fler sökalternativ")
    WebDriverWait(driver, 8).until(
        lambda d: any(e.is_displayed() for e in d.find_elements(By.XPATH, "//*[contains(normalize-space(.), 'Stad')]"))
    )

def find_input_for_label(driver, label):
    label_l = label.casefold()
    candidates = driver.find_elements(By.CSS_SELECTOR, "input")
    for el in candidates:
        if not el.is_displayed() or not el.is_enabled():
            continue
        attrs = " ".join([
            el.get_attribute("name") or "",
            el.get_attribute("id") or "",
            el.get_attribute("placeholder") or "",
            el.get_attribute("aria-label") or "",
            el.get_attribute("title") or "",
        ]).casefold()
        if label_l in attrs:
            return el
        try:
            parent_text = clean(el.find_element(By.XPATH, "./..").text).casefold()
            if label_l in parent_text:
                return el
        except Exception:
            pass
    # Last resort: locate text node and use following input in the same form.
    xpath = (
        f"//*[self::label or self::span or self::div][contains("
        f"translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZÅÄÖ','abcdefghijklmnopqrstuvwxyzåäö'),"
        f"'{label_l}')]/following::input[1]"
    )
    for el in driver.find_elements(By.XPATH, xpath):
        if el.is_displayed() and el.is_enabled():
            return el
    return None

def find_select_for_label(driver, label):
    for el in driver.find_elements(By.CSS_SELECTOR, "select"):
        if not el.is_displayed() or not el.is_enabled():
            continue
        attrs = " ".join([
            el.get_attribute("name") or "",
            el.get_attribute("id") or "",
            el.get_attribute("aria-label") or "",
            el.get_attribute("title") or "",
        ]).casefold()
        if label.casefold() in attrs:
            return el
        try:
            if label.casefold() in clean(el.find_element(By.XPATH, "./..").text).casefold():
                return el
        except Exception:
            pass
    return None

def choose_option(select_el, text):
    select = Select(select_el)
    for option in select.options:
        if clean(option.text).casefold() == text.casefold():
            select.select_by_visible_text(option.text)
            return True
    return False

def click_search(driver):
    xpath = "//button[normalize-space()='Sök'] | //input[@type='submit' and contains(@value,'Sök')]"
    buttons = visible_elements(driver, By.XPATH, xpath)
    for el in reversed(buttons):
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
            driver.execute_script("arguments[0].click();", el)
            return
        except Exception:
            continue
    raise RuntimeError("FMI search button not clickable")

def wait_for_results(driver):
    WebDriverWait(driver, 15).until(
        lambda d: "Antal träffar:" in d.find_element(By.TAG_NAME, "body").text
        or "Din sökning gav inga resultat" in d.find_element(By.TAG_NAME, "body").text
    )

def search(driver, city=None, county=None, municipality=None):
    driver.get(FMI_URL)
    WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
    time.sleep(1)
    close_message(driver)
    open_advanced(driver)

    if city:
        inp = find_input_for_label(driver, "Stad")
        if inp is None:
            raise RuntimeError("FMI city input not found after opening advanced search")
        inp.click()
        inp.clear()
        inp.send_keys(city)

    if county:
        sel = find_select_for_label(driver, "Län")
        if sel is None or not choose_option(sel, county):
            raise RuntimeError(f"FMI county selector could not select {county!r}")

    if municipality:
        sel = find_select_for_label(driver, "Kommun")
        if sel is None or not choose_option(sel, municipality):
            raise RuntimeError(f"FMI municipality selector could not select {municipality!r}")

    click_search(driver)
    wait_for_results(driver)
    close_message(driver)
    return collect_result_links(driver)

def collect_result_links(driver):
    links = []
    seen = set()
    for a in driver.find_elements(By.CSS_SELECTOR, "a[href]"):
        try:
            href = a.get_attribute("href") or ""
            parsed = urlparse(href)
            if parsed.netloc == "fmi.se" and parsed.path.rstrip("/") == "/soktjanster/sok-maklare" and "id=" in parsed.query:
                href = href.split("#", 1)[0]
                if href not in seen:
                    seen.add(href)
                    links.append(href)
        except StaleElementReferenceException:
            continue
    return links

def parse_detail(driver, url, search_area):
    driver.get(url)
    WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
    time.sleep(0.4)
    close_message(driver)
    text = driver.find_element(By.TAG_NAME, "body").text
    lines = [clean(x) for x in text.splitlines() if clean(x)]

    def after(label):
        target = label.casefold()
        for i, line in enumerate(lines):
            if line.casefold().rstrip(":") == target.rstrip(":") and i + 1 < len(lines):
                return lines[i + 1]
        return ""

    name = after("Fullständigt namn:")
    registration_type = after("Typ av registrering:")
    registration_date = after("Senaste registreringsdatum:")

    company = ""
    company_address = ""
    offices = []

    for i, line in enumerate(lines):
        if line.casefold() == "företag" and i + 1 < len(lines):
            company = lines[i + 1]
            addr = []
            j = i + 2
            while j < len(lines) and lines[j].casefold() not in ("kontor inom företaget", "snabbsök"):
                if lines[j] not in ("Arbetar på:", "Företag"):
                    addr.append(lines[j])
                j += 1
            company_address = " | ".join(addr)
        if line.casefold() == "kontor inom företaget":
            j = i + 1
            while j < len(lines) and lines[j].casefold() not in ("visa länk till mäklare", "snabbsök"):
                if lines[j] not in ("Arbetar på:",):
                    offices.append(lines[j])
                j += 1

    # The result page can expose the short display name as a link; the legal
    # full name above is the authoritative name field for the CSV.
    return {
        "name": name,
        "registration_date": registration_date,
        "registration_type": registration_type,
        "company": company,
        "company_address": company_address,
        "offices": " | ".join(dict.fromkeys(offices)),
        "search_area": search_area,
        "source_url": url,
    }

def run_search(driver, label, city=None, county=None, municipality=None):
    print(f"[SEARCH] {label}", flush=True)
    links = search(driver, city=city, county=county, municipality=municipality)
    print(f"[FOUND] {label}: {len(links)} result links", flush=True)
    return links

def scrape(searches, headless=False, output=OUT_DEFAULT):
    driver = make_driver(headless=headless)
    rows = []
    seen_people = {}
    failures = []
    seen_urls = set()
    try:
        for item in searches:
            label = item["label"]
            try:
                links = run_search(driver, **item)
                for url in links:
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)
                    try:
                        row = parse_detail(driver, url, label)
                        key = norm(row["name"]) or norm(url)
                        if key in seen_people:
                            # Keep the first office/search context but never create
                            # a second lead for the same person.
                            continue
                        if not row["name"]:
                            raise RuntimeError("Detail page had no Fullständigt namn")
                        seen_people[key] = row
                        rows.append(row)
                        print(f"[OK] {row['name']} | {row['company']}", flush=True)
                    except Exception as exc:
                        failures.append((label, url, str(exc)))
                        print(f"[DETAIL ERROR] {label} | {url} | {exc}", file=sys.stderr, flush=True)
            except Exception as exc:
                failures.append((label, "", str(exc)))
                print(f"[SEARCH ERROR] {label} | {exc}", file=sys.stderr, flush=True)
    finally:
        driver.quit()

    with open(output, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)

    with open("fmi_failures.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["search_area", "url", "error"])
        w.writerows(failures)

    print(f"[DONE] {len(rows)} unique brokers -> {output}", flush=True)
    print(f"[DONE] {len(failures)} failures -> fmi_failures.csv", flush=True)
    return 0 if rows else 2

def build_searches(mode):
    if mode == "malmo":
        return [{"label": "Malmö", "city": "Malmö"}]
    if mode == "skane":
        return [{"label": "Skåne", "county": "Skåne"}]
    if mode == "skane-municipalities":
        return [{"label": municipality, "municipality": municipality} for municipality in SKANE_MUNICIPALITIES]
    raise ValueError(mode)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["malmo", "skane", "skane-municipalities"], default="malmo")
    ap.add_argument("--output", default=OUT_DEFAULT)
    ap.add_argument("--headless", action="store_true")
    args = ap.parse_args()
    searches = build_searches(args.mode)
    return scrape(searches, headless=args.headless, output=args.output)

if __name__ == "__main__":
    raise SystemExit(main())
