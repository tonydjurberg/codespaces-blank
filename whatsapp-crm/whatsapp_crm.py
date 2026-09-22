import csv
import datetime as dt
import json
import os
import re
import sqlite3
import sys
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

try:
    from openpyxl import Workbook
except Exception:
    Workbook = None

APP_NAME = "WhatsApp CRM"
APP_VERSION = "3.0.0"

if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

DB = os.path.join(APP_DIR, "whatsapp_crm.db")
CSV_FILE = os.path.join(APP_DIR, "customers.csv")
XLSX_FILE = os.path.join(APP_DIR, "customers.xlsx")
SETTINGS_FILE = os.path.join(APP_DIR, "crm_settings.json")

GREEN = "#075E54"
GREEN2 = "#128C7E"
BRIGHT = "#25D366"
LIGHT = "#F0F2F5"
BUBBLE = "#D9FDD3"
TEXT = "#111B21"
MUTED = "#667781"

STATUSES = ["New", "Contacted", "Quoted", "Booked", "Won", "Lost"]
DIRECTIONS = ["outbound", "inbound", "note"]

DEFAULT_SETTINGS = {
    "company_name": "My Company",
    "owner_name": "",
    "whatsapp_number": "",
    "email": "",
    "industry": "",
    "currency": "BRL",
    "timezone": "America/Sao_Paulo",
    "open_time": "08:00",
    "close_time": "18:00",
    "slot_step": 15,
}

def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def setup_db():
    c = db()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS customers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        phone TEXT,
        company TEXT,
        email TEXT,
        status TEXT NOT NULL DEFAULT 'New',
        notes TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        sku TEXT,
        price_cents INTEGER NOT NULL DEFAULT 0,
        currency TEXT NOT NULL DEFAULT 'BRL',
        duration_minutes INTEGER NOT NULL DEFAULT 60,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER NOT NULL UNIQUE,
        created_at TEXT NOT NULL,
        FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id INTEGER NOT NULL,
        direction TEXT NOT NULL,
        body TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS sales (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL DEFAULT 1,
        unit_price_cents INTEGER NOT NULL,
        currency TEXT NOT NULL,
        total_cents INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE CASCADE,
        FOREIGN KEY(product_id) REFERENCES products(id)
    );
    CREATE TABLE IF NOT EXISTS appointments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER NOT NULL,
        conversation_id INTEGER,
        product_id INTEGER,
        appointment_date TEXT NOT NULL,
        start_time TEXT NOT NULL,
        end_time TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'Booked',
        notes TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE CASCADE,
        FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE SET NULL,
        FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE SET NULL
    );
    """)
    c.commit()
    c.close()

def now():
    return dt.datetime.now().replace(microsecond=0).isoformat(sep=" ")

def load_settings():
    data = DEFAULT_SETTINGS.copy()
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f)
        if isinstance(saved, dict):
            for k in data:
                if k in saved:
                    data[k] = saved[k]
    except Exception:
        pass
    return data

settings = load_settings()

def save_settings():
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)

def money(cents, currency=None):
    currency = currency or settings["currency"]
    return f"{cents / 100:.2f} {currency}"

def price_to_cents(value):
    s = str(value or "").strip().replace(" ", "").replace(",", ".")
    if not s:
        return 0
    return int(round(float(s) * 100))

def normalized_phone(value):
    return re.sub(r"[^0-9]", "", value or "")

def wa_url(phone, text=""):
    n = normalized_phone(phone)
    if not n:
        return ""
    url = "https://wa.me/" + n
    if text:
        from urllib.parse import quote
        url += "?text=" + quote(text)
    return url

def open_whatsapp(phone, text=""):
    url = wa_url(phone, text)
    if not url:
        messagebox.showwarning("WhatsApp", "Enter the customer's WhatsApp number with country code.")
        return False
    webbrowser.open(url)
    return True

def ensure_conversation(customer_id):
    c = db()
    row = c.execute("SELECT id FROM conversations WHERE customer_id=?", (customer_id,)).fetchone()
    if row:
        c.close()
        return row["id"]
    cur = c.execute(
        "INSERT INTO conversations(customer_id,created_at) VALUES(?,?)",
        (customer_id, now())
    )
    cid = cur.lastrowid
    c.commit()
    c.close()
    return cid

def log_message(customer_id, direction, body):
    conversation_id = ensure_conversation(customer_id)
    c = db()
    c.execute(
        "INSERT INTO messages(conversation_id,direction,body,created_at) VALUES(?,?,?,?)",
        (conversation_id, direction, body.strip(), now())
    )
    c.commit()
    c.close()
    return conversation_id

def export_data():
    c = db()
    customers = c.execute(
        "SELECT name,phone,company,email,status,notes,created_at,updated_at "
        "FROM customers ORDER BY name COLLATE NOCASE"
    ).fetchall()
    with open(CSV_FILE, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["Name","WhatsApp","Company","Email","Status","Notes","Created","Updated"])
        for r in customers:
            w.writerow(list(r))
    if Workbook:
        wb = Workbook()
        ws = wb.active
        ws.title = "Customers"
        ws.append(["Name","WhatsApp","Company","Email","Status","Notes","Created","Updated"])
        for r in customers:
            ws.append(list(r))
        wb.save(XLSX_FILE)
    c.close()

def parse_time(s):
    return dt.datetime.strptime(s, "%H:%M")

def end_from_duration(start, minutes):
    return (parse_time(start) + dt.timedelta(minutes=int(minutes))).strftime("%H:%M")

class CRM(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} {APP_VERSION}")
        self.geometry("1400x850")
        self.minsize(1150, 700)
        self.configure(bg=LIGHT)
        self.selected_customer_id = None
        self.selected_product_id = None
        self.selected_appointment_id = None
        self.pages = {}
        self.build_style()
        self.build_shell()
        self.show_page("Dashboard")
        self.refresh_all()

    def build_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("Treeview", rowheight=30, background="white", fieldbackground="white",
                        foreground=TEXT, borderwidth=0)
        style.configure("Treeview.Heading", background=GREEN, foreground="white",
                        relief="flat", font=("Segoe UI", 10, "bold"))
        style.map("Treeview", background=[("selected", BUBBLE)], foreground=[("selected", TEXT)])
        style.configure("TButton", padding=7, font=("Segoe UI", 10))
        style.configure("TEntry", padding=6)
        style.configure("TCombobox", padding=5)
        style.configure("TNotebook", background=LIGHT, borderwidth=0)
        style.configure("TLabel", background=LIGHT, foreground=TEXT)

    def build_shell(self):
        top = tk.Frame(self, bg=GREEN, height=70)
        top.pack(fill="x")
        top.pack_propagate(False)
        self.brand = tk.Label(top, text=settings["company_name"], bg=GREEN, fg="white",
                              font=("Segoe UI", 21, "bold"), padx=22)
        self.brand.pack(side="left")
        self.title_label = tk.Label(top, text="WhatsApp CRM", bg=GREEN, fg="#D9FDD3",
                                    font=("Segoe UI", 11))
        self.title_label.pack(side="left", padx=4)
        self.status_label = tk.Label(top, text="", bg=GREEN, fg="white",
                                     font=("Segoe UI", 10))
        self.status_label.pack(side="right", padx=22)

        body = tk.Frame(self, bg=LIGHT)
        body.pack(fill="both", expand=True)

        nav = tk.Frame(body, bg="#0B4F47", width=205)
        nav.pack(side="left", fill="y")
        nav.pack_propagate(False)

        for name in ["Dashboard", "Customers", "Products", "Sales", "Agenda", "Settings"]:
            b = tk.Button(nav, text=name, anchor="w", bg="#0B4F47", fg="white",
                          activebackground=GREEN2, activeforeground="white",
                          relief="flat", bd=0, padx=18, pady=12,
                          font=("Segoe UI", 11, "bold"),
                          command=lambda n=name: self.show_page(n))
            b.pack(fill="x")

        self.content = tk.Frame(body, bg=LIGHT)
        self.content.pack(side="left", fill="both", expand=True)

        self.pages["Dashboard"] = self.dashboard_page()
        self.pages["Customers"] = self.customers_page()
        self.pages["Products"] = self.products_page()
        self.pages["Sales"] = self.sales_page()
        self.pages["Agenda"] = self.agenda_page()
        self.pages["Settings"] = self.settings_page()

    def page_wrap(self, title):
        frame = tk.Frame(self.content, bg=LIGHT, padx=22, pady=18)
        title_label = tk.Label(frame, text=title, bg=LIGHT, fg=TEXT,
                               font=("Segoe UI", 20, "bold"))
        title_label.pack(anchor="w", pady=(0, 14))
        return frame

    def show_page(self, name):
        for p in self.pages.values():
            p.pack_forget()
        self.pages[name].pack(fill="both", expand=True)

    def refresh_all(self):
        self.refresh_dashboard()
        self.refresh_customers()
        self.refresh_products()
        self.refresh_sales()
        self.refresh_agenda()
        self.refresh_settings_header()
        export_data()

    def refresh_settings_header(self):
        self.brand.config(text=settings["company_name"] or "My Company")
        self.status_label.config(text=f"WhatsApp: {settings.get('whatsapp_number') or 'not set'}")

    def dashboard_page(self):
        f = self.page_wrap("Dashboard")
        self.dash_cards = tk.Frame(f, bg=LIGHT)
        self.dash_cards.pack(fill="x")
        self.dash_values = {}
        for key, label in [("customers","Customers"),("products","Products"),
                           ("sales","Sales"),("appointments","Upcoming bookings")]:
            card = tk.Frame(self.dash_cards, bg="white", bd=0, highlightthickness=1,
                            highlightbackground="#d1d7db", padx=18, pady=15)
            card.pack(side="left", fill="x", expand=True, padx=(0, 12))
            tk.Label(card, text=label, bg="white", fg=MUTED,
                     font=("Segoe UI", 10)).pack(anchor="w")
            v = tk.Label(card, text="0", bg="white", fg=GREEN,
                         font=("Segoe UI", 25, "bold"))
            v.pack(anchor="w", pady=(4,0))
            self.dash_values[key] = v

        quick = tk.Frame(f, bg="white", padx=18, pady=18, highlightthickness=1,
                         highlightbackground="#d1d7db")
        quick.pack(fill="x", pady=20)
        tk.Label(quick, text="Quick actions", bg="white", fg=TEXT,
                 font=("Segoe UI", 13, "bold")).pack(anchor="w", pady=(0,10))
        for text, command in [
            ("+ Customer", lambda: self.show_page("Customers")),
            ("+ Product / Service", lambda: self.show_page("Products")),
            ("+ Booking", lambda: self.show_page("Agenda")),
            ("Settings", lambda: self.show_page("Settings")),
        ]:
            tk.Button(quick, text=text, command=command, bg=GREEN2, fg="white",
                      relief="flat", padx=14, pady=8).pack(side="left", padx=(0,8))

        info = tk.Frame(f, bg="white", padx=18, pady=18, highlightthickness=1,
                        highlightbackground="#d1d7db")
        info.pack(fill="both", expand=True)
        self.dash_info = tk.Label(info, justify="left", anchor="nw", bg="white",
                                  fg=TEXT, font=("Segoe UI", 11))
        self.dash_info.pack(fill="both", expand=True)
        return f

    def refresh_dashboard(self):
        if not self.dash_values:
            return
        c = db()
        vals = {
            "customers": c.execute("SELECT COUNT(*) n FROM customers").fetchone()["n"],
            "products": c.execute("SELECT COUNT(*) n FROM products WHERE active=1").fetchone()["n"],
            "sales": c.execute("SELECT COUNT(*) n FROM sales").fetchone()["n"],
            "appointments": c.execute(
                "SELECT COUNT(*) n FROM appointments WHERE status='Booked' AND appointment_date>=?",
                (dt.date.today().isoformat(),)
            ).fetchone()["n"],
        }
        for k,v in vals.items():
            self.dash_values[k].config(text=str(v))
        due = c.execute(
            "SELECT appointment_date,start_time,customers.name,products.name service "
            "FROM appointments JOIN customers ON customers.id=appointments.customer_id "
            "LEFT JOIN products ON products.id=appointments.product_id "
            "WHERE appointments.status='Booked' AND appointment_date>=? "
            "ORDER BY appointment_date,start_time LIMIT 8",
            (dt.date.today().isoformat(),)
        ).fetchall()
        c.close()
        lines = [
            f"Company: {settings['company_name']}",
            f"Industry: {settings['industry'] or '-'}",
            f"Your WhatsApp: {settings['whatsapp_number'] or '-'}",
            "",
            "Next bookings:",
        ]
        lines += [f"• {r['appointment_date']} {r['start_time']} — {r['name']} — {r['service'] or '-'}" for r in due]
        if len(lines) == 5:
            lines.append("• None")
        self.dash_info.config(text="\n".join(lines))

    def customers_page(self):
        f = self.page_wrap("Customers & WhatsApp")
        toolbar = tk.Frame(f, bg=LIGHT)
        toolbar.pack(fill="x", pady=(0,10))
        tk.Label(toolbar, text="Search", bg=LIGHT, fg=MUTED).pack(side="left")
        self.customer_search = tk.StringVar()
        e = ttk.Entry(toolbar, textvariable=self.customer_search, width=30)
        e.pack(side="left", padx=8)
        self.customer_search.trace_add("write", lambda *_: self.refresh_customers())
        ttk.Button(toolbar, text="New customer", command=self.clear_customer).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Export", command=self.export_now).pack(side="left", padx=4)

        pane = tk.PanedWindow(f, orient="horizontal", bg=LIGHT, sashwidth=6)
        pane.pack(fill="both", expand=True)
        left = tk.Frame(pane, bg="white")
        right = tk.Frame(pane, bg="white", padx=18, pady=14)
        pane.add(left, width=610)
        pane.add(right, width=520)

        self.customer_tree = ttk.Treeview(left, columns=("name","phone","company","status"), show="headings")
        for col, title, width in [("name","Name",180),("phone","WhatsApp",145),
                                  ("company","Company",150),("status","Status",100)]:
            self.customer_tree.heading(col,text=title)
            self.customer_tree.column(col,width=width)
        sy=ttk.Scrollbar(left,orient="vertical",command=self.customer_tree.yview)
        self.customer_tree.configure(yscrollcommand=sy.set)
        self.customer_tree.grid(row=0,column=0,sticky="nsew")
        sy.grid(row=0,column=1,sticky="ns")
        left.rowconfigure(0,weight=1); left.columnconfigure(0,weight=1)
        self.customer_tree.bind("<<TreeviewSelect>>", self.load_customer)

        self.c_vars = {k:tk.StringVar() for k in ["name","phone","company","email","status","notes","product","quantity","message"]}
        self.customer_labels = {}
        form = tk.Frame(right,bg="white")
        form.pack(fill="both",expand=True)
        fields=[("name","Name *"),("phone","WhatsApp"),("company","Company"),("email","Email"),("status","Status")]
        for i,(key,label) in enumerate(fields):
            tk.Label(form,text=label,bg="white",fg=MUTED).grid(row=i,column=0,sticky="w",pady=5)
            self.customer_labels[key]=tk.Label(form,text="",bg="white")
            if key=="status":
                w=ttk.Combobox(form,textvariable=self.c_vars[key],values=STATUSES,state="readonly",width=30)
            else:
                w=ttk.Entry(form,textvariable=self.c_vars[key],width=34)
            w.grid(row=i,column=1,sticky="ew",pady=5)

        tk.Label(form,text="Notes",bg="white",fg=MUTED).grid(row=5,column=0,sticky="nw",pady=5)
        self.customer_notes=tk.Text(form,height=4,width=34)
        self.customer_notes.grid(row=5,column=1,sticky="ew",pady=5)

        btns=tk.Frame(form,bg="white"); btns.grid(row=6,column=0,columnspan=2,sticky="ew",pady=8)
        ttk.Button(btns,text="Save",command=self.save_customer).pack(side="left",padx=(0,5))
        ttk.Button(btns,text="Delete",command=self.delete_customer).pack(side="left",padx=5)
        ttk.Button(btns,text="Open WhatsApp",command=self.open_customer_wa).pack(side="left",padx=5)

        tk.Label(form,text="Register sale",bg="white",fg=TEXT,font=("Segoe UI",11,"bold")).grid(row=7,column=0,columnspan=2,sticky="w",pady=(12,4))
        tk.Label(form,text="Product / service",bg="white",fg=MUTED).grid(row=8,column=0,sticky="w",pady=4)
        self.sale_product=ttk.Combobox(form,textvariable=self.c_vars["product"],state="readonly",width=30)
        self.sale_product.grid(row=8,column=1,sticky="ew",pady=4)
        tk.Label(form,text="Quantity",bg="white",fg=MUTED).grid(row=9,column=0,sticky="w",pady=4)
        ttk.Entry(form,textvariable=self.c_vars["quantity"],width=34).grid(row=9,column=1,sticky="ew",pady=4)
        ttk.Button(form,text="Register sale + WhatsApp",command=self.register_sale).grid(row=10,column=1,sticky="w",pady=6)

        tk.Label(form,text="Conversation",bg="white",fg=TEXT,font=("Segoe UI",11,"bold")).grid(row=11,column=0,columnspan=2,sticky="w",pady=(14,4))
        self.msgs=tk.Text(form,height=8,width=40,state="disabled",bg="#F7F8FA")
        self.msgs.grid(row=12,column=0,columnspan=2,sticky="nsew",pady=4)
        ttk.Entry(form,textvariable=self.c_vars["message"],width=35).grid(row=13,column=0,columnspan=2,sticky="ew",pady=4)
        ttk.Button(form,text="Send message in WhatsApp",command=self.send_message).grid(row=14,column=1,sticky="w",pady=4)
        form.columnconfigure(1,weight=1); form.rowconfigure(12,weight=1)
        return f

    def refresh_customers(self):
        if not hasattr(self,"customer_tree"): return
        self.customer_tree.delete(*self.customer_tree.get_children())
        q=self.customer_search.get().strip().lower()
        c=db()
        rows=c.execute("SELECT id,name,phone,company,status FROM customers ORDER BY name COLLATE NOCASE").fetchall()
        c.close()
        for r in rows:
            vals=[r["name"],r["phone"] or "",r["company"] or "",r["status"]]
            if q and not any(q in str(v).lower() for v in vals):
                continue
            self.customer_tree.insert("", "end", iid=str(r["id"]), values=vals)
        products=self.get_product_names()
        self.sale_product["values"]=products

    def clear_customer(self):
        self.selected_customer_id=None
        for k in ["name","phone","company","email","status","product","quantity","message"]:
            self.c_vars[k].set("")
        self.c_vars["status"].set("New"); self.c_vars["quantity"].set("1")
        self.customer_notes.delete("1.0","end")
        self.render_messages()

    def load_customer(self,_=None):
        sel=self.customer_tree.selection()
        if not sel:return
        cid=int(sel[0]); self.selected_customer_id=cid
        c=db(); r=c.execute("SELECT * FROM customers WHERE id=?",(cid,)).fetchone(); c.close()
        if not r:return
        for k in ["name","phone","company","email","status"]:
            self.c_vars[k].set(r[k] or "")
        self.customer_notes.delete("1.0","end"); self.customer_notes.insert("1.0",r["notes"] or "")
        self.render_messages()

    def save_customer(self):
        name=self.c_vars["name"].get().strip()
        if not name:
            messagebox.showwarning("Customer","Name is required."); return
        vals=(name,self.c_vars["phone"].get().strip(),self.c_vars["company"].get().strip(),
              self.c_vars["email"].get().strip(),self.c_vars["status"].get() or "New",
              self.customer_notes.get("1.0","end").strip(),now())
        c=db()
        if self.selected_customer_id:
            c.execute("UPDATE customers SET name=?,phone=?,company=?,email=?,status=?,notes=?,updated_at=? WHERE id=?",
                      vals+(self.selected_customer_id,))
            cid=self.selected_customer_id
        else:
            cur=c.execute("INSERT INTO customers(name,phone,company,email,status,notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                          vals[:6]+(now(),now()))
            cid=cur.lastrowid
        ensure_id=cid
        c.commit(); c.close()
        ensure_conversation(ensure_id)
        self.selected_customer_id=cid
        self.refresh_all()

    def delete_customer(self):
        if not self.selected_customer_id:return
        if not messagebox.askyesno("Delete","Delete this customer and linked history?"):return
        c=db(); c.execute("DELETE FROM customers WHERE id=?",(self.selected_customer_id,)); c.commit(); c.close()
        self.clear_customer(); self.refresh_all()

    def open_customer_wa(self):
        if self.selected_customer_id:
            open_whatsapp(self.c_vars["phone"].get())
            if self.c_vars["phone"].get(): ensure_conversation(self.selected_customer_id)

    def render_messages(self):
        if not hasattr(self,"msgs"): return
        self.msgs.config(state="normal"); self.msgs.delete("1.0","end")
        if not self.selected_customer_id:
            self.msgs.insert("end","Select a customer to see the conversation.\n")
        else:
            c=db()
            rows=c.execute(
                "SELECT m.direction,m.body,m.created_at FROM messages m "
                "JOIN conversations x ON x.id=m.conversation_id WHERE x.customer_id=? ORDER BY m.created_at",
                (self.selected_customer_id,)
            ).fetchall(); c.close()
            for r in rows:
                self.msgs.insert("end",f"[{r['created_at']}] {r['direction'].upper()}: {r['body']}\n\n")
        self.msgs.config(state="disabled")

    def send_message(self):
        if not self.selected_customer_id:return
        text=self.c_vars["message"].get().strip()
        if not text:return
        if open_whatsapp(self.c_vars["phone"].get(),text):
            log_message(self.selected_customer_id,"outbound",text)
            self.c_vars["message"].set(""); self.render_messages()

    def register_sale(self):
        if not self.selected_customer_id:
            messagebox.showwarning("Sale","Select a customer first."); return
        name=self.sale_product.get().strip()
        if not name:return
        try: qty=max(1,int(self.c_vars["quantity"].get() or "1"))
        except ValueError:
            messagebox.showwarning("Sale","Quantity must be a number."); return
        c=db()
        p=c.execute("SELECT * FROM products WHERE name=? AND active=1",(name,)).fetchone()
        if not p:
            c.close(); messagebox.showwarning("Sale","Select an active product."); return
        total=p["price_cents"]*qty
        c.execute("INSERT INTO sales(customer_id,product_id,quantity,unit_price_cents,currency,total_cents,created_at) VALUES(?,?,?,?,?,?,?)",
                  (self.selected_customer_id,p["id"],qty,p["price_cents"],p["currency"],total,now()))
        c.commit(); c.close()
        msg=f"{p['name']} — {money(total,p['currency'])}"
        if open_whatsapp(self.c_vars["phone"].get(),msg):
            log_message(self.selected_customer_id,"outbound",msg)
        self.refresh_all()
        messagebox.showinfo("Sale",f"Sale registered: {money(total,p['currency'])}")

    def products_page(self):
        f=self.page_wrap("Products & Services")
        pane=tk.PanedWindow(f,orient="horizontal",bg=LIGHT,sashwidth=6); pane.pack(fill="both",expand=True)
        left=tk.Frame(pane,bg="white"); right=tk.Frame(pane,bg="white",padx=18,pady=14)
        pane.add(left,width=620); pane.add(right,width=500)
        self.product_tree=ttk.Treeview(left,columns=("name","sku","price","currency","duration","active"),show="headings")
        for col,title,width in [("name","Name",190),("sku","Code",90),("price","Price",100),("currency","Currency",80),("duration","Min",70),("active","Active",70)]:
            self.product_tree.heading(col,text=title); self.product_tree.column(col,width=width)
        sy=ttk.Scrollbar(left,orient="vertical",command=self.product_tree.yview); self.product_tree.configure(yscrollcommand=sy.set)
        self.product_tree.grid(row=0,column=0,sticky="nsew"); sy.grid(row=0,column=1,sticky="ns")
        left.rowconfigure(0,weight=1); left.columnconfigure(0,weight=1)
        self.product_tree.bind("<<TreeviewSelect>>",self.load_product)

        self.pv={k:tk.StringVar() for k in ["name","sku","price","currency","duration","description","active"]}
        labels=[("name","Product / service *"),("sku","SKU / code"),("price","Price"),("currency","Currency"),("duration","Duration (minutes)"),("active","Active")]
        for i,(k,lbl) in enumerate(labels):
            tk.Label(right,text=lbl,bg="white",fg=MUTED).grid(row=i,column=0,sticky="w",pady=5)
            if k=="active":
                w=ttk.Combobox(right,textvariable=self.pv[k],values=["Yes","No"],state="readonly",width=30)
            else:
                w=ttk.Entry(right,textvariable=self.pv[k],width=34)
            w.grid(row=i,column=1,sticky="ew",pady=5)
        tk.Label(right,text="Description",bg="white",fg=MUTED).grid(row=6,column=0,sticky="nw",pady=5)
        self.product_desc=tk.Text(right,height=5,width=34); self.product_desc.grid(row=6,column=1,sticky="ew",pady=5)
        ttk.Button(right,text="Save product",command=self.save_product).grid(row=7,column=1,sticky="w",pady=6)
        ttk.Button(right,text="Delete",command=self.delete_product).grid(row=8,column=1,sticky="w",pady=6)
        right.columnconfigure(1,weight=1)
        return f

    def get_product_names(self):
        c=db(); rows=c.execute("SELECT name FROM products WHERE active=1 ORDER BY name COLLATE NOCASE").fetchall(); c.close()
        return [r["name"] for r in rows]

    def refresh_products(self):
        if not hasattr(self,"product_tree"): return
        self.product_tree.delete(*self.product_tree.get_children())
        c=db(); rows=c.execute("SELECT * FROM products ORDER BY name COLLATE NOCASE").fetchall(); c.close()
        for r in rows:
            self.product_tree.insert("", "end", iid=str(r["id"]),
                                     values=(r["name"],r["sku"] or "",f"{r['price_cents']/100:.2f}",
                                             r["currency"],r["duration_minutes"],"Yes" if r["active"] else "No"))

    def load_product(self,_=None):
        sel=self.product_tree.selection()
        if not sel:return
        pid=int(sel[0]); self.selected_product_id=pid
        c=db(); r=c.execute("SELECT * FROM products WHERE id=?",(pid,)).fetchone(); c.close()
        if not r:return
        for k in ["name","sku","currency","duration"]:
            self.pv[k].set(r[k] if k!="duration" else str(r[k]))
        self.pv["price"].set(f"{r['price_cents']/100:.2f}")
        self.pv["active"].set("Yes" if r["active"] else "No")
        self.product_desc.delete("1.0","end"); self.product_desc.insert("1.0",r["description"] or "")

    def clear_product(self):
        self.selected_product_id=None

    def save_product(self):
        name=self.pv["name"].get().strip()
        if not name:
            messagebox.showwarning("Product","Product name is required."); return
        try:
            price=price_to_cents(self.pv["price"].get())
            duration=max(5,int(self.pv["duration"].get() or "60"))
        except ValueError:
            messagebox.showwarning("Product","Price and duration must be valid numbers."); return
        vals=(name,self.pv["description"].get().strip() if False else "",self.pv["sku"].get().strip(),
              price,self.pv["currency"].get().strip() or settings["currency"],duration,
              1 if self.pv["active"].get()!="No" else 0)
        desc=self.product_desc.get("1.0","end").strip()
        c=db()
        if self.selected_product_id:
            c.execute("UPDATE products SET name=?,description=?,sku=?,price_cents=?,currency=?,duration_minutes=?,active=? WHERE id=?",
                      vals+(self.selected_product_id,))
        else:
            c.execute("INSERT INTO products(name,description,sku,price_cents,currency,duration_minutes,active,created_at) VALUES(?,?,?,?,?,?,?,?)",
                      vals+(now(),))
        c.commit(); c.close()
        self.refresh_all()
        messagebox.showinfo("Product","Saved.")

    def delete_product(self):
        if not self.selected_product_id:return
        if not messagebox.askyesno("Delete","Delete this product?"):return
        c=db(); c.execute("UPDATE products SET active=0 WHERE id=?",(self.selected_product_id,)); c.commit(); c.close()
        self.selected_product_id=None; self.refresh_all()

    def sales_page(self):
        f=self.page_wrap("Sales")
        self.sales_tree=ttk.Treeview(f,columns=("date","customer","product","qty","total","currency"),show="headings")
        for col,title,width in [("date","Date",150),("customer","Customer",180),("product","Product",220),("qty","Qty",70),("total","Total",100),("currency","Currency",90)]:
            self.sales_tree.heading(col,text=title); self.sales_tree.column(col,width=width)
        sy=ttk.Scrollbar(f,orient="vertical",command=self.sales_tree.yview); self.sales_tree.configure(yscrollcommand=sy.set)
        self.sales_tree.pack(side="left",fill="both",expand=True); sy.pack(side="right",fill="y")
        return f

    def refresh_sales(self):
        if not hasattr(self,"sales_tree"):return
        self.sales_tree.delete(*self.sales_tree.get_children())
        c=db()
        rows=c.execute(
            "SELECT s.created_at,customers.name customer,products.name product,s.quantity,s.total_cents,s.currency "
            "FROM sales s JOIN customers ON customers.id=s.customer_id JOIN products ON products.id=s.product_id "
            "ORDER BY s.created_at DESC"
        ).fetchall(); c.close()
        for i,r in enumerate(rows):
            self.sales_tree.insert("", "end", values=(r["created_at"],r["customer"],r["product"],r["quantity"],
                                                      f"{r['total_cents']/100:.2f}",r["currency"]))

    def agenda_page(self):
        f=self.page_wrap("Agenda / Booking")
        top=tk.Frame(f,bg=LIGHT); top.pack(fill="x",pady=(0,10))
        self.ag_date=tk.StringVar(value=dt.date.today().isoformat())
        self.ag_customer=tk.StringVar(); self.ag_product=tk.StringVar()
        self.ag_start=tk.StringVar(); self.ag_end=tk.StringVar(); self.ag_status=tk.StringVar(value="Booked")
        tk.Label(top,text="Date (YYYY-MM-DD)",bg=LIGHT,fg=MUTED).pack(side="left")
        ttk.Entry(top,textvariable=self.ag_date,width=13).pack(side="left",padx=6)
        ttk.Button(top,text="Today",command=lambda:self.ag_date.set(dt.date.today().isoformat())).pack(side="left",padx=4)
        body=tk.PanedWindow(f,orient="horizontal",bg=LIGHT,sashwidth=6); body.pack(fill="both",expand=True)
        form=tk.Frame(body,bg="white",padx=18,pady=16); listing=tk.Frame(body,bg="white",padx=10,pady=10)
        body.add(form,width=520); body.add(listing,width=650)
        fields=[("customer","Customer"),("product","Service / product"),("start","Start time"),("end","End time"),("status","Status")]
        for i,(k,l) in enumerate(fields):
            tk.Label(form,text=l,bg="white",fg=MUTED).grid(row=i,column=0,sticky="w",pady=6)
            if k=="customer":
                w=ttk.Combobox(form,textvariable=self.ag_customer,state="readonly",width=32)
            elif k=="product":
                w=ttk.Combobox(form,textvariable=self.ag_product,state="readonly",width=32)
            elif k=="status":
                w=ttk.Combobox(form,textvariable=self.ag_status,values=["Booked","Completed","Cancelled","No-show"],state="readonly",width=32)
            else:
                w=ttk.Combobox(form,textvariable=getattr(self,"ag_"+k),width=32)
            w.grid(row=i,column=1,sticky="ew",pady=6)
        self.ag_slots=ttk.Combobox(form,textvariable=self.ag_start,width=32)
        tk.Label(form,text="Available slots",bg="white",fg=MUTED).grid(row=5,column=0,sticky="w",pady=6)
        self.ag_slots.grid(row=5,column=1,sticky="ew",pady=6)
        self.ag_slots.bind("<<ComboboxSelected>>",lambda _ : self.calc_end())
        tk.Label(form,text="Notes",bg="white",fg=MUTED).grid(row=6,column=0,sticky="nw",pady=6)
        self.ag_notes=tk.Text(form,height=6,width=32); self.ag_notes.grid(row=6,column=1,sticky="ew",pady=6)
        ttk.Button(form,text="Create / save booking",command=self.save_appointment).grid(row=7,column=1,sticky="w",pady=8)
        ttk.Button(form,text="Cancel selected booking",command=self.cancel_appointment).grid(row=8,column=1,sticky="w",pady=4)
        self.ag_product["values"]=self.get_product_names()
        self.ag_customer.bind("<<ComboboxSelected>>",lambda _ : self.refresh_agenda_slots())
        self.ag_product.bind("<<ComboboxSelected>>",lambda _ : self.refresh_agenda_slots())

        self.ag_tree=ttk.Treeview(listing,columns=("date","start","end","customer","service","status"),show="headings")
        for col,title,width in [("date","Date",95),("start","Start",65),("end","End",65),("customer","Customer",150),("service","Service",160),("status","Status",100)]:
            self.ag_tree.heading(col,text=title); self.ag_tree.column(col,width=width)
        sy=ttk.Scrollbar(listing,orient="vertical",command=self.ag_tree.yview); self.ag_tree.configure(yscrollcommand=sy.set)
        self.ag_tree.grid(row=0,column=0,sticky="nsew"); sy.grid(row=0,column=1,sticky="ns")
        listing.rowconfigure(0,weight=1); listing.columnconfigure(0,weight=1)
        self.ag_tree.bind("<<TreeviewSelect>>",self.load_appointment)
        form.columnconfigure(1,weight=1)
        return f

    def refresh_agenda(self):
        if not hasattr(self,"ag_tree"):return
        c=db()
        self.ag_tree.delete(*self.ag_tree.get_children())
        rows=c.execute(
            "SELECT a.*, customers.name customer, products.name service "
            "FROM appointments a JOIN customers ON customers.id=a.customer_id "
            "LEFT JOIN products ON products.id=a.product_id "
            "ORDER BY a.appointment_date,a.start_time"
        ).fetchall()
        c.close()
        for r in rows:
            self.ag_tree.insert("", "end", iid=str(r["id"]),
                                values=(r["appointment_date"],r["start_time"],r["end_time"],r["customer"],
                                        r["service"] or "",r["status"]))
        c=db(); self._customers=[(r["id"],r["name"]) for r in c.execute("SELECT id,name FROM customers ORDER BY name").fetchall()]; c.close()
        self.ag_customer["values"]=[f"{i} — {n}" for i,n in self._customers]
        self.ag_product["values"]=self.get_product_names()
        self.refresh_agenda_slots()

    def refresh_agenda_slots(self):
        if not hasattr(self,"ag_slots"):return
        duration=60
        pname=self.ag_product.get()
        if pname:
            c=db(); p=c.execute("SELECT duration_minutes FROM products WHERE name=? AND active=1",(pname,)).fetchone(); c.close()
            if p: duration=max(5,int(p["duration_minutes"]))
        try:
            opening=parse_time(str(settings["open_time"]))
            closing=parse_time(str(settings["close_time"]))
        except Exception:
            opening=parse_time("08:00"); closing=parse_time("18:00")
        step=max(5,int(settings.get("slot_step",15)))
        date=self.ag_date.get().strip()
        c=db()
        rows=c.execute("SELECT start_time,end_time FROM appointments WHERE appointment_date=? AND status='Booked'",(date,)).fetchall()
        c.close()
        busy=[(parse_time(r["start_time"]),parse_time(r["end_time"])) for r in rows]
        slots=[]; t=opening
        while t+dt.timedelta(minutes=duration)<=closing:
            st=t; en=t+dt.timedelta(minutes=duration)
            if not any(st < b and en > a for a,b in busy):
                slots.append(st.strftime("%H:%M"))
            t+=dt.timedelta(minutes=step)
        self.ag_slots["values"]=slots
        if self.ag_start.get() not in slots:
            self.ag_start.set(slots[0] if slots else "")
        self.calc_end()

    def calc_end(self):
        pname=self.ag_product.get(); duration=60
        if pname:
            c=db(); p=c.execute("SELECT duration_minutes FROM products WHERE name=?",(pname,)).fetchone(); c.close()
            if p: duration=int(p["duration_minutes"])
        if self.ag_start.get():
            self.ag_end.set(end_from_duration(self.ag_start.get(),duration))

    def load_appointment(self,_=None):
        sel=self.ag_tree.selection()
        if not sel:return
        self.selected_appointment_id=int(sel[0])
        c=db(); r=c.execute("SELECT * FROM appointments WHERE id=?",(self.selected_appointment_id,)).fetchone(); c.close()
        if not r:return
        self.ag_date.set(r["appointment_date"]); self.ag_start.set(r["start_time"]); self.ag_end.set(r["end_time"]); self.ag_status.set(r["status"])
        c=db(); cr=c.execute("SELECT name FROM customers WHERE id=?",(r["customer_id"],)).fetchone(); pr=c.execute("SELECT name FROM products WHERE id=?",(r["product_id"],)).fetchone() if r["product_id"] else None; c.close()
        self.ag_customer.set(f"{r['customer_id']} — {cr['name']}" if cr else "")
        self.ag_product.set(pr["name"] if pr else "")
        self.ag_notes.delete("1.0","end"); self.ag_notes.insert("1.0",r["notes"] or "")
        self.refresh_agenda_slots()

    def save_appointment(self):
        if " — " not in self.ag_customer.get():
            messagebox.showwarning("Agenda","Select a customer."); return
        try: customer_id=int(self.ag_customer.get().split(" — ",1)[0])
        except ValueError:
            messagebox.showwarning("Agenda","Select a valid customer."); return
        pname=self.ag_product.get()
        product_id=None
        if pname:
            c=db(); p=c.execute("SELECT id FROM products WHERE name=?",(pname,)).fetchone(); c.close()
            product_id=p["id"] if p else None
        start=self.ag_start.get(); end=self.ag_end.get()
        if not start or not end:
            messagebox.showwarning("Agenda","Choose a free time slot."); return
        try: dt.datetime.strptime(self.ag_date.get(),"%Y-%m-%d")
        except ValueError:
            messagebox.showwarning("Agenda","Date must be YYYY-MM-DD."); return
        conv=ensure_conversation(customer_id)
        vals=(customer_id,conv,product_id,self.ag_date.get(),start,end,self.ag_status.get() or "Booked",
              self.ag_notes.get("1.0","end").strip(),now())
        c=db()
        if self.selected_appointment_id:
            c.execute("UPDATE appointments SET customer_id=?,conversation_id=?,product_id=?,appointment_date=?,start_time=?,end_time=?,status=?,notes=?,updated_at=? WHERE id=?",
                      vals+(self.selected_appointment_id,))
        else:
            c.execute("INSERT INTO appointments(customer_id,conversation_id,product_id,appointment_date,start_time,end_time,status,notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                      vals+(now(),))
        c.commit(); c.close()
        self.selected_appointment_id=None
        self.refresh_all()
        messagebox.showinfo("Agenda","Booking saved.")

    def cancel_appointment(self):
        sel=self.ag_tree.selection()
        if not sel:return
        aid=int(sel[0])
        c=db(); c.execute("UPDATE appointments SET status='Cancelled',updated_at=? WHERE id=?",(now(),aid)); c.commit(); c.close()
        self.refresh_all()

    def settings_page(self):
        f=self.page_wrap("Company settings")
        box=tk.Frame(f,bg="white",padx=22,pady=20,highlightthickness=1,highlightbackground="#d1d7db")
        box.pack(fill="x")
        self.sv={k:tk.StringVar(value=str(settings[k])) for k in DEFAULT_SETTINGS}
        rows=[("company_name","Company name"),("owner_name","Owner / user"),
              ("whatsapp_number","Your WhatsApp number"),("email","Email"),
              ("industry","Industry"),("currency","Currency"),("timezone","Timezone"),
              ("open_time","Opening time"),("close_time","Closing time"),("slot_step","Booking slot step (min)")]
        for i,(k,lbl) in enumerate(rows):
            tk.Label(box,text=lbl,bg="white",fg=MUTED).grid(row=i,column=0,sticky="w",pady=6)
            ttk.Entry(box,textvariable=self.sv[k],width=42).grid(row=i,column=1,sticky="ew",pady=6)
        ttk.Button(box,text="Save company settings",command=self.save_company_settings).grid(row=len(rows),column=1,sticky="w",pady=12)
        tk.Label(f,text="These settings make the CRM usable for different businesses. "
                         "For a petshop, add services such as Dog grooming with the correct duration; "
                         "for another business, use your own products/services and opening hours.",
                 bg=LIGHT,fg=TEXT,wraplength=900,justify="left").pack(anchor="w",pady=15)
        box.columnconfigure(1,weight=1)
        return f

    def refresh_settings(self):
        for k in DEFAULT_SETTINGS:
            if k in self.sv: self.sv[k].set(str(settings[k]))

    def save_company_settings(self):
        for k in self.sv:
            settings[k]=self.sv[k].get().strip()
        try:
            settings["slot_step"]=max(5,int(settings["slot_step"] or 15))
        except ValueError:
            settings["slot_step"]=15
        save_settings()
        self.refresh_settings_header()
        self.refresh_dashboard()
        self.refresh_agenda_slots()
        messagebox.showinfo("Settings","Company settings saved.")

    def export_now(self):
        export_data()
        messagebox.showinfo("Export","Customer CSV/Excel files updated.")

    def refresh_settings_header(self):
        self.brand.config(text=settings["company_name"] or "My Company")
        self.status_label.config(text=f"Your WhatsApp: {settings.get('whatsapp_number') or 'not set'}")
        if hasattr(self,"sv"): self.refresh_settings()

def self_test():
    test = sqlite3.connect(":memory:")
    test.executescript("""
    CREATE TABLE customers(id INTEGER PRIMARY KEY, name TEXT NOT NULL, phone TEXT);
    CREATE TABLE products(id INTEGER PRIMARY KEY, name TEXT NOT NULL, price_cents INTEGER, duration_minutes INTEGER);
    CREATE TABLE sales(id INTEGER PRIMARY KEY, customer_id INTEGER, product_id INTEGER, total_cents INTEGER);
    CREATE TABLE appointments(id INTEGER PRIMARY KEY, customer_id INTEGER, product_id INTEGER, start_time TEXT, end_time TEXT);
    CREATE TABLE conversations(id INTEGER PRIMARY KEY, customer_id INTEGER);
    CREATE TABLE messages(id INTEGER PRIMARY KEY, conversation_id INTEGER, body TEXT);
    """)
    test.execute("INSERT INTO customers(name,phone) VALUES (?,?)",("Test Customer","5511999999999"))
    test.execute("INSERT INTO products(name,price_cents,duration_minutes) VALUES (?,?,?)",("Dog grooming",9900,60))
    c = test.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
    p = test.execute("SELECT duration_minutes FROM products WHERE name='Dog grooming'").fetchone()[0]
    assert c == 1
    assert p == 60
    assert normalized_phone("+55 (11) 99999-9999") == "5511999999999"
    assert end_from_duration("10:00", 60) == "11:00"
    test.close()
    print("SELF_TEST_OK")

setup_db()
if "--self-test" in sys.argv:
    self_test()
    raise SystemExit(0)

app = CRM()
app.mainloop()
