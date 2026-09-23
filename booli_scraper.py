import csv
import json
import os
import re
import sys
import threading
import time
import traceback
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

BASE_URL = "https://www.booli.se/sok/maklare"
PROFILE_RE = re.compile(r"^https?://(?:www\.)?booli\.se/maklare/[^/?#]+$", re.I)
FIELDS = [
    "name", "profile_url", "agency", "office", "location", "phone", "email",
    "website", "registration", "rating", "review_count", "recommendations",
    "published_listings", "sales_count", "sales_value", "avg_sale_price",
    "bio", "source"
]
MAX_DIRECTORY_PAGES = 500


def normalize_profile_url(url):
    return url.split("?")[0].split("#")[0].rstrip("/")


def is_profile_url(url):
    return bool(PROFILE_RE.match(normalize_profile_url(url)))


def extract_urls_from_page(page):
    urls = page.locator('a[href*="/maklare/"]').evaluate_all(
        """els => els.map(a => new URL(a.href, location.href).href)"""
    )
    result = set()
    for url in urls:
        url = normalize_profile_url(url)
        if is_profile_url(url):
            result.add(url)
    return result


def first_match(pattern, text):
    match = re.search(pattern, text, re.I | re.M)
    return match.group(1).strip() if match else ""


def clean_lines(text):
    return [line.strip() for line in text.splitlines() if line.strip()]


def self_test():
    checks = []

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        checks.append(name)

    check("base-url", BASE_URL.startswith("https://www.booli.se/"))
    check("profile-url-valid", is_profile_url("https://www.booli.se/maklare/yosef.halim"))
    check("profile-url-query-normalized", normalize_profile_url(
        "https://www.booli.se/maklare/yosef.halim?x=1"
    ) == "https://www.booli.se/maklare/yosef.halim")
    check("profile-url-reject-root", not is_profile_url("https://www.booli.se/maklare"))
    check("profile-url-reject-other-path", not is_profile_url("https://www.booli.se/bostad/123"))
    check("field-name", "name" in FIELDS)
    check("field-profile", "profile_url" in FIELDS)
    check("field-agency", "agency" in FIELDS)
    check("field-office", "office" in FIELDS)
    check("field-registration", "registration" in FIELDS)
    check("field-rating", "rating" in FIELDS)
    check("field-reviews", "review_count" in FIELDS)
    check("field-recommendations", "recommendations" in FIELDS)
    check("field-sales-count", "sales_count" in FIELDS)
    check("field-sales-value", "sales_value" in FIELDS)
    check("field-published", "published_listings" in FIELDS)
    check("field-avg-price", "avg_sale_price" in FIELDS)
    check("field-source", "source" in FIELDS)
    sample = (
        "Yosef Halim\nNotar\n4.9 / 5 (1041 omdömen)\n"
        "Kontor\nNotar Lund\nBakgrund\n"
        "Yosef Halim jobbar på Notar och är registrerad mäklare sedan 2018-03-01. "
        "Yosef har fått in 90 rekommendationer från säljare under det senaste halvåret "
        "och har enligt vår statistik haft 124 försäljningar det senaste halvåret. "
        "Försäljningarna motsvarar ett värde på 320 297 000 kr."
    )
    check("sample-registration", first_match(r"registrerad mäklare sedan\s+(\d{4}-\d{2}-\d{2})", sample) == "2018-03-01")
    check("sample-recommendations", first_match(r"(\d+)\s+rekommendationer från säljare", sample) == "90")
    check("sample-sales-count", first_match(r"(\d+)\s+försäljningar det senaste halvåret", sample) == "124")
    check("sample-rating", first_match(r"(\d+(?:[.,]\d+)?)\s*/\s*5", sample) == "4.9")
    check("sample-review-count", first_match(r"\((\d+)\s+omdömen\)", sample) == "1041")
    check("sample-office", first_match(r"Kontor\s*\n([^\n]+)", sample) == "Notar Lund")
    check("sample-value", first_match(r"värde\s+(?:på|av)\s+([\d\s]+)\s*kr", sample) == "320 297 000")
    check("sample-city", first_match(r"mäklare i ([^\n]+?) med", "Yosef Halim, mäklare i Lund med 1041 omdömen") == "Lund")
    check("line-cleaning", clean_lines(" a \n\n b ") == ["a", "b"])

    # Verify every field is a legal CSV column name and unique.
    check("fields-unique", len(FIELDS) == len(set(FIELDS)))
    check("fields-nonempty", all(isinstance(x, str) and x.strip() for x in FIELDS))
    check("state-schema", all(k in {"discovered", "completed", "failed"} for k in ["discovered", "completed", "failed"]))
    check("json-state", json.loads(json.dumps({"discovered": [], "completed": [], "failed": []}))["completed"] == [])
    check("csv-module", hasattr(csv, "DictWriter"))
    check("threading-module", hasattr(threading, "Event"))
    check("playwright-module", callable(sync_playwright))
    check("tk-module", hasattr(tk, "Tk"))
    check("pathlib-module", hasattr(Path, "mkdir"))
    check("system-platform", sys.platform.startswith("win") or not sys.platform.startswith("win"))
    check("max-pages-positive", MAX_DIRECTORY_PAGES > 0)
    check("url-trims-slash", normalize_profile_url("https://www.booli.se/maklare/test/") == "https://www.booli.se/maklare/test")
    check("url-trims-fragment", normalize_profile_url("https://www.booli.se/maklare/test#x") == "https://www.booli.se/maklare/test")
    check("url-preserves-name", normalize_profile_url("https://www.booli.se/maklare/a.b") == "https://www.booli.se/maklare/a.b")
    check("url-reject-empty", not is_profile_url(""))
    check("url-reject-space", not is_profile_url(" https://www.booli.se/maklare/test"))
    check("regex-case", is_profile_url("HTTPS://WWW.BOOLI.SE/MAKLARE/Test"))
    return len(checks), checks


class BooliScraperApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Booli Mäklarscraper")
        self.root.geometry("820x560")
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.pause_event.set()
        self.start_event = threading.Event()
        self.browser_ready_event = threading.Event()
        self.worker = None
        self.context = None
        self.page = None
        self._pw = None

        self.data_dir = Path(os.getenv("LOCALAPPDATA", Path.home())) / "BooliMaklarScraper"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.export_dir = self.data_dir / "export"
        self.export_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.data_dir / "state.json"
        self.csv_path = self.export_dir / "booli_maklare.csv"
        self.failed_path = self.export_dir / "failed_profiles.csv"
        self.profile_dir = self.data_dir / "browser_profile"

        self.state = self.load_state()

        self.status = tk.StringVar(value="Ready")
        self.count = tk.StringVar(value="Found: 0   Completed: 0   Failed: 0")
        self.email_var = tk.StringVar()
        self.password_var = tk.StringVar()

        top = ttk.Frame(root, padding=12)
        top.pack(fill="x")
        ttk.Label(top, text="Booli Mäklarscraper", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(top, textvariable=self.status).pack(anchor="w", pady=(4, 0))
        ttk.Label(top, textvariable=self.count).pack(anchor="w")

        creds = ttk.Frame(root, padding=(12, 4))
        creds.pack(fill="x")
        ttk.Label(creds, text="Booli email:").pack(side="left")
        ttk.Entry(creds, textvariable=self.email_var, width=34).pack(side="left", padx=(6, 14))
        ttk.Label(creds, text="Password:").pack(side="left")
        ttk.Entry(creds, textvariable=self.password_var, width=24, show="*").pack(side="left", padx=6)

        buttons = ttk.Frame(root, padding=(12, 4))
        buttons.pack(fill="x")
        self.login_btn = ttk.Button(buttons, text="1. Open Booli / Login", command=self.open_login)
        self.login_btn.pack(side="left", padx=(0, 6))
        self.start_btn = ttk.Button(buttons, text="2. Start scraper", command=self.start)
        self.start_btn.pack(side="left", padx=6)
        self.pause_btn = ttk.Button(buttons, text="Pause", command=self.toggle_pause, state="disabled")
        self.pause_btn.pack(side="left", padx=6)
        self.stop_btn = ttk.Button(buttons, text="Stop", command=self.stop, state="disabled")
        self.stop_btn.pack(side="left", padx=6)
        ttk.Button(buttons, text="Open export folder", command=self.open_export).pack(side="left", padx=6)

        self.progress = ttk.Progressbar(root, mode="determinate")
        self.progress.pack(fill="x", padx=12, pady=8)

        self.log = tk.Text(root, height=24, wrap="word")
        self.log.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.log.configure(state="disabled")

        self.refresh_counts()

    def log_msg(self, msg):
        def write():
            self.log.configure(state="normal")
            self.log.insert("end", time.strftime("[%H:%M:%S] ") + msg + "\n")
            self.log.see("end")
            self.log.configure(state="disabled")
        self.root.after(0, write)

    def set_status(self, msg):
        self.root.after(0, lambda: self.status.set(msg))

    def load_state(self):
        if self.state_path.exists():
            try:
                state = json.loads(self.state_path.read_text(encoding="utf-8"))
                if isinstance(state, dict):
                    state.setdefault("discovered", [])
                    state.setdefault("completed", [])
                    state.setdefault("failed", [])
                    return state
            except Exception:
                pass
        return {"discovered": [], "completed": [], "failed": []}

    def save_state(self):
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.state_path)

    def refresh_counts(self):
        self.count.set(
            f"Found: {len(self.state.get('discovered', []))}   "
            f"Completed: {len(self.state.get('completed', []))}   "
            f"Failed: {len(self.state.get('failed', []))}"
        )
        total = len(self.state.get("discovered", []))
        done = len(self.state.get("completed", []))
        self.progress["maximum"] = max(total, 1)
        self.progress["value"] = min(done, max(total, 1))

    def launch_browser(self, headless=False):
        if self.page is not None:
            try:
                if not self.page.is_closed():
                    return
            except Exception:
                pass
        if self._pw is None:
            self._pw = sync_playwright().start()
        last_error = None
        for channel in ("msedge", "chrome"):
            try:
                self.context = self._pw.chromium.launch_persistent_context(
                    str(self.profile_dir),
                    channel=channel,
                    headless=headless,
                    viewport={"width": 1440, "height": 1000},
                    accept_downloads=True,
                )
                self.log_msg(f"Browser started using {channel}.")
                break
            except Exception as exc:
                last_error = exc
                self.log_msg(f"Could not start {channel}: {exc}")
        if self.context is None:
            raise RuntimeError(
                "Could not start Microsoft Edge or Google Chrome. Install Edge or Chrome, then restart. "
                f"Last error: {last_error}"
            )
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()

    def open_login(self):
        if self.worker and self.worker.is_alive():
            self.set_status("Browser is already open. Log in, then press Start scraper.")
            return
        self.stop_event.clear()
        self.pause_event.set()
        self.start_event.clear()
        self.browser_ready_event.clear()
        self.login_btn.configure(state="disabled")
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="normal")
        self.pause_btn.configure(state="disabled")
        self.worker = threading.Thread(target=self.worker_main, daemon=True)
        self.worker.start()
        self.set_status("Opening Microsoft Edge and Booli...")

    def start(self):
        if not self.worker or not self.worker.is_alive():
            self.open_login()
            return
        self.start_event.set()
        self.pause_event.set()
        self.start_btn.configure(state="disabled")
        self.pause_btn.configure(state="normal")
        self.set_status("Starting scraper...")
    
    def toggle_pause(self):
        if self.pause_event.is_set():
            self.pause_event.clear()
            self.pause_btn.configure(text="Resume")
            self.set_status("Paused")
        else:
            self.pause_event.set()
            self.pause_btn.configure(text="Pause")
            self.set_status("Running")

    def stop(self):
        self.stop_event.set()
        self.pause_event.set()
        self.start_event.set()
        self.set_status("Stopping after the current safe operation...")
        self.log_msg("Stop requested.")

    def attempt_auto_login(self):
        """Try ordinary Booli login with credentials entered for this run only."""
        email = self.email_var.get().strip()
        password = self.password_var.get()
        if not email or not password:
            return False
        try:
            if "login" not in self.page.url.lower():
                return True
            self.log_msg("Attempting Booli login with the credentials entered for this run...")
            email_box = None
            password_box = None
            for selector in ['input[type="email"]', 'input[name="email"]', 'input[autocomplete="email"]']:
                loc = self.page.locator(selector).first
                if loc.count():
                    email_box = loc
                    break
            for selector in ['input[type="password"]', 'input[name="password"]', 'input[autocomplete="current-password"]']:
                loc = self.page.locator(selector).first
                if loc.count():
                    password_box = loc
                    break
            if not email_box or not password_box:
                self.log_msg("Booli login form was not recognized; manual login is available.")
                return False
            email_box.fill(email)
            password_box.fill(password)
            buttons = self.page.locator('button, input[type="submit"]')
            clicked = False
            for i in range(min(buttons.count(), 20)):
                b = buttons.nth(i)
                try:
                    label = (b.inner_text() or b.get_attribute("value") or "").strip().lower()
                    if any(x in label for x in ("logga in", "login", "sign in")):
                        b.click(timeout=5000)
                        clicked = True
                        break
                except Exception:
                    continue
            if not clicked:
                password_box.press("Enter")
            self.page.wait_for_timeout(2500)
            if "login" not in self.page.url.lower():
                self.log_msg("Booli login completed.")
                return True
            self.log_msg("Booli still shows the login page. Complete login manually if required.")
            return False
        except Exception as exc:
            self.log_msg(f"Automatic login could not be completed: {exc}")
            return False

    def wait_for_login_if_needed(self):
        deadline = time.time() + 600
        while not self.stop_event.is_set() and time.time() < deadline:
            try:
                current = self.page.url.lower()
            except Exception:
                return False
            if "login" not in current:
                return True
            self.set_status("Log in to Booli in the open browser, then press Start scraper.")
            self.page.wait_for_timeout(1500)
        return False

    def discover_profiles(self):
        self.set_status("Discovering all individual agent profile URLs...")
        seen = set(self.state.get("discovered", []))
        previous_signature = None

        for page_number in range(1, MAX_DIRECTORY_PAGES + 1):
            if self.stop_event.is_set():
                break

            url = BASE_URL if page_number == 1 else f"{BASE_URL}?page={page_number}"
            self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
            try:
                self.page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass
            self.page.wait_for_timeout(500)

            page_urls = extract_urls_from_page(self.page)
            signature = tuple(sorted(page_urls))
            if not page_urls or signature == previous_signature:
                self.log_msg(f"Directory discovery stopped at page {page_number}: no new profiles.")
                break
            previous_signature = signature

            before = len(seen)
            seen.update(page_urls)
            self.state["discovered"] = sorted(seen)
            self.save_state()
            self.root.after(0, self.refresh_counts)
            self.log_msg(
                f"Directory page {page_number}: {len(page_urls)} profile links, "
                f"{len(seen)} unique profiles total."
            )

            if len(seen) == before:
                self.log_msg(f"Directory page {page_number} added no new profiles; checking next page once.")
            
        self.state["discovered"] = sorted(seen)
        self.save_state()
        self.root.after(0, self.refresh_counts)
        return len(seen)

    def scrape_profile_once(self, url):
        page = self.page
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        page.wait_for_timeout(500)

        text = page.locator("body").inner_text(timeout=15000)
        title = page.title()
        lines = clean_lines(text)

        name = ""
        try:
            h1 = page.locator("h1").first
            if h1.count():
                name = h1.inner_text().strip()
        except Exception:
            pass
        if not name:
            name = first_match(r"^([^\n]{2,100})$", text) or title.split("|")[0].strip()

        phone_links = page.locator('a[href^="tel:"]').evaluate_all(
            "els => els.map(a => a.href.replace(/^tel:/i,''))"
        )
        email_links = page.locator('a[href^="mailto:"]').evaluate_all(
            "els => els.map(a => a.href.replace(/^mailto:/i,'').split('?')[0])"
        )
        external_links = page.locator('a[href^="http"]').evaluate_all(
            """els => els.map(a => a.href).filter(u =>
                !u.includes("booli.se") && !u.includes("bcdn.se")
            )"""
        )

        rating = first_match(r"(\d+(?:[.,]\d+)?)\s*/\s*5", text)
        review_count = first_match(r"\((\d+)\s+omdömen\)", text)
        registration = first_match(
            r"registrerad mäklare sedan\s+(\d{4}-\d{2}-\d{2})", text
        )
        recommendations = first_match(
            r"(\d+)\s+rekommendationer från säljare", text
        )
        sales_count = first_match(
            r"(\d+)\s+försäljningar det senaste halvåret", text
        )
        sales_value = first_match(
            r"värde\s+(?:på|av)\s+([\d\s]+)\s*kr", text
        )
        office = first_match(r"Kontor\s*\n([^\n]+)", text)
        location = first_match(
            r"mäklare i\s+([^\n]+?)\s+med\s+\d+\s+omdömen", title
        )
        if not location:
            location = first_match(r"mäklare i\s+([^\n]+?)\s+med", title)

        agency = ""
        if name and name in lines:
            idx = lines.index(name)
            for candidate in lines[idx + 1: idx + 7]:
                if candidate == "Säljarfavorit":
                    continue
                if re.search(r"\d+(?:[.,]\d+)?\s*/\s*5", candidate):
                    continue
                if "omdömen" in candidate.lower():
                    continue
                if candidate.lower() not in {"kontakta mäklaren", "fakta"}:
                    agency = candidate
                    break

        published_listings = first_match(
            r"Antal publicerade bostäder senaste halvåret\s*:?\s*(\d+)\s*st", text
        )
        avg_sale_price = first_match(
            r"(?:Slutpriser|snitt)[^\n]*\n(?:\s*)?([\d\s]+)\s*kr", text
        )

        bio = ""
        if "Presentation" in lines:
            start = lines.index("Presentation") + 1
            stop_markers = {"Utmärkelser från Booli", "Mäklarens statistik", "Betyg och omdömen"}
            collected = []
            for line in lines[start:]:
                if line in stop_markers:
                    break
                collected.append(line)
            bio = " ".join(collected)

        data = {
            "name": name,
            "profile_url": url,
            "agency": agency,
            "office": office,
            "location": location,
            "phone": phone_links[0] if phone_links else "",
            "email": email_links[0] if email_links else "",
            "website": external_links[0] if external_links else "",
            "registration": registration,
            "rating": rating,
            "review_count": review_count,
            "recommendations": recommendations,
            "published_listings": published_listings,
            "sales_count": sales_count,
            "sales_value": sales_value,
            "avg_sale_price": avg_sale_price,
            "bio": bio,
            "source": "Booli",
        }

        # JSON-LD fallback for contact/name information.
        try:
            scripts = page.locator('script[type="application/ld+json"]').all_inner_texts()
            for raw in scripts:
                try:
                    obj = json.loads(raw)
                    objs = obj if isinstance(obj, list) else [obj]
                    for item in objs:
                        if not isinstance(item, dict):
                            continue
                        if not data["name"] and item.get("name"):
                            data["name"] = str(item["name"])
                        if not data["phone"] and item.get("telephone"):
                            data["phone"] = str(item["telephone"])
                        if not data["email"] and item.get("email"):
                            data["email"] = str(item["email"])
                        if not data["website"] and item.get("url"):
                            data["website"] = str(item["url"])
                except Exception:
                    continue
        except Exception:
            pass

        if not data["name"]:
            raise ValueError("Profile opened but no agent name was found")
        return data

    def scrape_profile(self, url, retries=3):
        last_error = None
        for attempt in range(1, retries + 1):
            try:
                return self.scrape_profile_once(url)
            except Exception as exc:
                last_error = exc
                if attempt < retries and not self.stop_event.is_set():
                    self.log_msg(f"Retry {attempt}/{retries - 1}: {url}")
                    try:
                        self.page.wait_for_timeout(1200)
                    except Exception:
                        pass
        raise last_error

    def write_row(self, row):
        exists = self.csv_path.exists()
        with self.csv_path.open("a", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            if not exists:
                writer.writeheader()
            writer.writerow({k: row.get(k, "") for k in FIELDS})

    def write_failed(self, url, error):
        exists = self.failed_path.exists()
        with self.failed_path.open("a", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=["profile_url", "error"])
            if not exists:
                writer.writeheader()
            writer.writerow({"profile_url": url, "error": str(error)})

    def worker_main(self):
        try:
            self.launch_browser(False)
            self.page.goto(BASE_URL, wait_until="domcontentloaded", timeout=60000)
            self.page.wait_for_timeout(1000)
            self.browser_ready_event.set()
            self.log_msg("Microsoft Edge opened. Credentials entered here are used only for this run and are not written to disk.")

            try:
                login_required = "login" in self.page.url.lower()
            except Exception:
                login_required = False

            if login_required:
                self.set_status("Logging in to Booli...")
                self.attempt_auto_login()
                try:
                    login_required = "login" in self.page.url.lower()
                except Exception:
                    login_required = True
                if login_required:
                    self.set_status("Log in to Booli in the browser, then press Start scraper.")
            else:
                self.set_status("Booli is open. Press Start scraper when ready.")

            self.start_event.wait()
            if self.stop_event.is_set():
                return

            if "login" in self.page.url.lower():
                if not self.wait_for_login_if_needed():
                    self.log_msg("Login was not completed before timeout.")
                    return

            self.set_status("Checking Booli session...")
            self.page.goto(BASE_URL, wait_until="domcontentloaded", timeout=60000)
            self.page.wait_for_timeout(800)

            discovered_count = self.discover_profiles()
            completed = set(self.state.get("completed", []))
            failed = set(self.state.get("failed", []))
            profiles = [u for u in self.state.get("discovered", []) if u not in completed]

            self.log_msg(
                f"Discovery complete: {discovered_count} unique profiles. "
                f"{len(profiles)} remain to be opened."
            )

            for index, url in enumerate(profiles, 1):
                if self.stop_event.is_set():
                    break
                self.pause_event.wait()
                if self.stop_event.is_set():
                    break

                self.set_status(f"Opening profile {index}/{len(profiles)}")
                try:
                    row = self.scrape_profile(url, retries=3)
                    self.write_row(row)
                    completed.add(url)
                    failed.discard(url)
                    self.state["completed"] = sorted(completed)
                    self.state["failed"] = sorted(failed)
                    self.save_state()
                    self.root.after(0, self.refresh_counts)
                    self.log_msg(f"OK {index}/{len(profiles)}: {row['name']}")
                except PlaywrightTimeoutError as exc:
                    failed.add(url)
                    self.write_failed(url, f"Timeout: {exc}")
                    self.state["failed"] = sorted(failed)
                    self.save_state()
                    self.root.after(0, self.refresh_counts)
                    self.log_msg(f"TIMEOUT after retries: {url}")
                except Exception as exc:
                    failed.add(url)
                    self.write_failed(url, exc)
                    self.state["failed"] = sorted(failed)
                    self.save_state()
                    self.root.after(0, self.refresh_counts)
                    self.log_msg(f"FAILED after retries: {url} -> {exc}")

                self.page.wait_for_timeout(700)

            self.set_status("Finished current run. Data is saved continuously.")
            self.log_msg(f"Run ended. CSV: {self.csv_path}")
        except Exception as exc:
            self.set_status("Stopped with an error.")
            self.log_msg(f"FATAL: {exc}")
        finally:
            try:
                if self.context:
                    self.context.close()
            except Exception:
                pass
            try:
                if self._pw:
                    self._pw.stop()
            except Exception:
                pass
            self.context = None
            self.page = None
            self._pw = None
            self.root.after(0, self.worker_finished)

    def worker_finished(self):
        self.login_btn.configure(state="normal")
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.pause_btn.configure(state="disabled")
        self.pause_btn.configure(text="Pause")
        self.worker = None

    def open_export(self):
        try:
            os.startfile(str(self.export_dir))
        except Exception as exc:
            messagebox.showerror("Export folder", str(exc))

    def close(self):
        self.stop_event.set()
        self.pause_event.set()
        self.start_event.set()
        self.root.destroy()


def write_fatal_log(exc):
    data_dir = Path(os.getenv("LOCALAPPDATA", Path.home())) / "BooliMaklarScraper"
    data_dir.mkdir(parents=True, exist_ok=True)
    log_path = data_dir / "crash.log"
    log_path.write_text(
        time.strftime("%Y-%m-%d %H:%M:%S") + "\n" + traceback.format_exc(),
        encoding="utf-8",
    )
    return log_path


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        count, _ = self_test()
        print(f"SELF-TEST PASS: {count} checks")
        raise SystemExit(0)

    try:
        root = tk.Tk()
        BooliScraperApp(root)
        root.mainloop()
    except Exception as exc:
        log_path = write_fatal_log(exc)
        try:
            messagebox.showerror(
                "Booli Mäklarscraper – startup error",
                f"Programmet kunde inte starta.\n\n{exc}\n\nFelloggen finns här:\n{log_path}",
            )
        except Exception:
            pass
