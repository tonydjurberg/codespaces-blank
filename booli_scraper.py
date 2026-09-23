import csv
import json
import os
import re
import threading
import time
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

BASE_URL = "https://www.booli.se/sok/maklare"
PROFILE_RE = re.compile(r"^https?://(?:www\.)?booli\.se/maklare/[^/?#]+", re.I)
FIELDS = [
    "name", "profile_url", "agency", "office", "location", "phone", "email",
    "website", "registration", "rating", "review_count", "recommendations",
    "sales_count", "sales_value", "active_listings", "bio", "source"
]


class BooliScraperApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Booli Mäklarscraper")
        self.root.geometry("760x520")
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.pause_event.set()
        self.worker = None
        self.browser = None
        self.context = None
        self.page = None

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

        top = ttk.Frame(root, padding=12)
        top.pack(fill="x")
        ttk.Label(top, text="Booli Mäklarscraper", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(top, textvariable=self.status).pack(anchor="w", pady=(4, 0))
        ttk.Label(top, textvariable=self.count).pack(anchor="w")

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

        self.log = tk.Text(root, height=21, wrap="word")
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
                return json.loads(self.state_path.read_text(encoding="utf-8"))
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
        self.progress["value"] = done

    def launch_browser(self, headless=False):
        if self.page and not self.page.is_closed():
            return
        if not hasattr(self, "_pw"):
            self._pw = sync_playwright().start()
        # Windows normally includes Microsoft Edge. Using the installed browser
        # avoids requiring a separate Playwright browser download.
        self.context = self._pw.chromium.launch_persistent_context(
            str(self.profile_dir),
            channel="msedge",
            headless=headless,
            viewport={"width": 1440, "height": 1000},
            accept_downloads=True,
        )
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()

    def open_login(self):
        try:
            self.launch_browser(False)
            self.page.goto(BASE_URL, wait_until="domcontentloaded", timeout=60000)
            self.set_status("Booli is open. Log in manually if required, then press Start scraper.")
            self.log_msg("Browser opened. Credentials are never stored by this program.")
        except Exception as e:
            self.log_msg(f"Could not open browser: {e}")
            messagebox.showerror("Browser error", str(e))

    def start(self):
        if self.worker and self.worker.is_alive():
            return
        self.stop_event.clear()
        self.pause_event.set()
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.pause_btn.configure(state="normal")
        self.worker = threading.Thread(target=self.run_scraper, daemon=True)
        self.worker.start()

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
        self.set_status("Stopping after current safe operation...")
        self.log_msg("Stop requested.")

    def discover_profiles(self):
        self.set_status("Discovering individual agent profiles...")
        self.page.goto(BASE_URL, wait_until="domcontentloaded", timeout=60000)
        self.page.wait_for_timeout(1500)

        seen = set(self.state.get("discovered", []))
        stagnant = 0
        last_count = len(seen)

        for _ in range(1000):
            if self.stop_event.is_set():
                break

            urls = self.page.locator('a[href*="/maklare/"]').evaluate_all(
                """els => els.map(a => new URL(a.href, location.href).href)"""
            )
            for url in urls:
                url = url.split("?")[0].split("#")[0].rstrip("/")
                if PROFILE_RE.match(url) and url.lower() != "https://www.booli.se/maklare":
                    seen.add(url)

            if len(seen) == last_count:
                stagnant += 1
            else:
                stagnant = 0
                last_count = len(seen)

            self.state["discovered"] = sorted(seen)
            self.save_state()
            self.root.after(0, self.refresh_counts)
            self.log_msg(f"Directory discovery: {len(seen)} profiles found.")

            # Try normal pagination/load-more controls before stopping.
            clicked = False
            for selector in [
                'button:has-text("Visa fler")',
                'button:has-text("Nästa")',
                'a:has-text("Nästa")',
                'button[aria-label*="Nästa"]',
                'a[rel="next"]',
            ]:
                try:
                    loc = self.page.locator(selector).first
                    if awaitable_count(loc) > 0 and loc.is_visible() and loc.is_enabled():
                        awaitable_click(loc)
                        self.page.wait_for_timeout(1200)
                        clicked = True
                        break
                except Exception:
                    pass

            if not clicked:
                # Scroll to trigger infinite loading.
                before = len(seen)
                self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                self.page.wait_for_timeout(1200)
                after_urls = self.page.locator('a[href*="/maklare/"]').evaluate_all(
                    "els => els.map(a => new URL(a.href, location.href).href)"
                )
                for url in after_urls:
                    url = url.split("?")[0].split("#")[0].rstrip("/")
                    if PROFILE_RE.match(url):
                        seen.add(url)
                if len(seen) == before:
                    stagnant += 1
                else:
                    stagnant = 0
                if stagnant >= 4:
                    break

        self.state["discovered"] = sorted(seen)
        self.save_state()
        self.root.after(0, self.refresh_counts)

    def scrape_profile(self, url):
        page = self.page
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(700)

        # Give client-side profile data a moment to render.
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass

        text = page.locator("body").inner_text(timeout=15000)
        title = page.title()

        def first(pattern):
            m = re.search(pattern, text, re.I | re.M)
            return m.group(1).strip() if m else ""

        name = ""
        h1 = page.locator("h1").first
        if h1.count():
            try:
                name = h1.inner_text().strip()
            except Exception:
                pass
        if not name:
            name = first(r"^([^\n]{2,100})$") or title.split("|")[0].strip()

        phones = page.locator('a[href^="tel:"]').evaluate_all(
            "els => els.map(a => a.href.replace(/^tel:/i,''))"
        )
        emails = page.locator('a[href^="mailto:"]').evaluate_all(
            "els => els.map(a => a.href.replace(/^mailto:/i,'').split('?')[0])"
        )
        websites = page.locator('a[href^="http"]').evaluate_all(
            """els => els.map(a => a.href).filter(u => !u.includes('booli.se'))"""
        )

        def label_value(labels):
            for label in labels:
                m = re.search(rf"{re.escape(label)}\s*[:\n]\s*([^\n]+)", text, re.I)
                if m:
                    return m.group(1).strip()
            return ""

        data = {
            "name": name,
            "profile_url": url,
            "agency": label_value(["Mäklare", "Byrå", "Företag", "Agency"]),
            "office": label_value(["Kontor", "Office"]),
            "location": label_value(["Ort", "Område", "Stad"]),
            "phone": phones[0] if phones else label_value(["Telefon", "Tel"]),
            "email": emails[0] if emails else "",
            "website": websites[0] if websites else "",
            "registration": label_value(["Registrerad", "Reg. mäklare", "Registrering"]),
            "rating": label_value(["Betyg", "Rating"]),
            "review_count": label_value(["Omdömen", "Reviews"]),
            "recommendations": label_value(["Rekommendationer", "Rekommendation"]),
            "sales_count": label_value(["Försäljningar", "Sålda"]),
            "sales_value": label_value(["Försäljningsvärde", "Försäljning"]),
            "active_listings": label_value(["Aktiva objekt", "Till salu"]),
            "bio": "",
            "source": "Booli",
        }

        # JSON-LD can provide clean person/organization data.
        try:
            scripts = page.locator('script[type="application/ld+json"]').all_inner_texts()
            for raw in scripts:
                try:
                    obj = json.loads(raw)
                    objs = obj if isinstance(obj, list) else [obj]
                    for item in objs:
                        if isinstance(item, dict):
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

        return data

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

    def run_scraper(self):
        try:
            self.launch_browser(False)
            self.set_status("Checking Booli session...")
            self.page.goto(BASE_URL, wait_until="domcontentloaded", timeout=60000)
            self.page.wait_for_timeout(1200)

            # A real login is deliberately left to the user; no credentials are embedded.
            if "login" in self.page.url.lower():
                self.set_status("Please log in to Booli in the browser. Scraper is paused.")
                self.log_msg("Booli login page detected. Complete login manually, then click Start scraper again.")
                return

            self.discover_profiles()

            completed = set(self.state.get("completed", []))
            failed = set(self.state.get("failed", []))
            profiles = [u for u in self.state.get("discovered", []) if u not in completed]

            self.log_msg(f"Starting profile extraction: {len(profiles)} remaining.")
            for index, url in enumerate(profiles, 1):
                if self.stop_event.is_set():
                    break
                self.pause_event.wait()
                if self.stop_event.is_set():
                    break

                self.set_status(f"Opening profile {index}/{len(profiles)}")
                try:
                    row = self.scrape_profile(url)
                    self.write_row(row)
                    completed.add(url)
                    self.state["completed"] = sorted(completed)
                    self.save_state()
                    self.root.after(0, self.refresh_counts)
                    self.log_msg(f"OK {index}/{len(profiles)}: {row.get('name') or url}")
                except PlaywrightTimeoutError as e:
                    failed.add(url)
                    self.write_failed(url, f"Timeout: {e}")
                    self.state["failed"] = sorted(failed)
                    self.save_state()
                    self.root.after(0, self.refresh_counts)
                    self.log_msg(f"TIMEOUT: {url}")
                except Exception as e:
                    failed.add(url)
                    self.write_failed(url, e)
                    self.state["failed"] = sorted(failed)
                    self.save_state()
                    self.root.after(0, self.refresh_counts)
                    self.log_msg(f"FAILED: {url} -> {e}")

                # Polite pacing and checkpointing.
                self.page.wait_for_timeout(800)

            self.set_status("Finished current run. Data is saved continuously.")
            self.log_msg(f"Run ended. CSV: {self.csv_path}")
        except Exception as e:
            self.set_status("Stopped with an error.")
            self.log_msg(f"FATAL: {e}")
        finally:
            self.root.after(0, lambda: self.start_btn.configure(state="normal"))
            self.root.after(0, lambda: self.stop_btn.configure(state="disabled"))
            self.root.after(0, lambda: self.pause_btn.configure(state="disabled"))

    def open_export(self):
        try:
            os.startfile(str(self.export_dir))
        except Exception as e:
            messagebox.showerror("Export folder", str(e))

    def close(self):
        self.stop_event.set()
        try:
            if self.context:
                self.context.close()
            if hasattr(self, "_pw"):
                self._pw.stop()
        except Exception:
            pass
        self.root.destroy()


def awaitable_count(locator):
    return locator.count()


def awaitable_click(locator):
    locator.click(timeout=3000)


if __name__ == "__main__":
    root = tk.Tk()
    BooliScraperApp(root)
    root.mainloop()
