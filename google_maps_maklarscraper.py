import csv
import json
import threading
import urllib.request
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

API_URL = "https://places.googleapis.com/v1/places:searchText"
FIELDS = ",".join(["places.id","places.displayName","places.formattedAddress","places.nationalPhoneNumber","places.internationalPhoneNumber","places.websiteUri","places.googleMapsUri","places.location","places.businessStatus","places.types"])

class App:
    def __init__(self, root):
        self.root=root; self.root.title("MäklarScraper — Google Maps"); self.root.geometry("1180x700"); self.rows=[]; self.stop_flag=False
        top=ttk.Frame(root,padding=12); top.pack(fill="x")
        ttk.Label(top,text="Google Maps MäklarScraper",font=("Segoe UI",18,"bold")).grid(row=0,column=0,columnspan=4,sticky="w",pady=(0,10))
        ttk.Label(top,text="Google Maps API key").grid(row=1,column=0,sticky="w")
        self.key=ttk.Entry(top,show="*",width=48); self.key.grid(row=1,column=1,sticky="ew",padx=8)
        ttk.Label(top,text="Stad / område").grid(row=2,column=0,sticky="w")
        self.city=ttk.Entry(top,width=32); self.city.insert(0,"Malmö"); self.city.grid(row=2,column=1,sticky="w",padx=8)
        ttk.Label(top,text="Kategori").grid(row=2,column=2,sticky="e")
        self.category=ttk.Entry(top,width=32); self.category.insert(0,"mäklare"); self.category.grid(row=2,column=3,sticky="w",padx=8)
        ttk.Label(top,text="Max resultat").grid(row=3,column=0,sticky="w")
        self.limit=ttk.Spinbox(top,from_=1,to=60,width=8); self.limit.set(60); self.limit.grid(row=3,column=1,sticky="w",padx=8)
        ttk.Label(top,text="Extra sökning").grid(row=3,column=2,sticky="e")
        self.extra=ttk.Entry(top,width=32); self.extra.insert(0,"fastighetsmäklare"); self.extra.grid(row=3,column=3,sticky="w",padx=8)
        b=ttk.Frame(top); b.grid(row=4,column=0,columnspan=4,sticky="w",pady=12)
        self.start_btn=ttk.Button(b,text="STARTA SÖKNING",command=self.start); self.start_btn.pack(side="left",padx=(0,8))
        self.stop_btn=ttk.Button(b,text="STOPPA",command=self.stop,state="disabled"); self.stop_btn.pack(side="left",padx=(0,8))
        self.export_btn=ttk.Button(b,text="EXPORTERA CSV",command=self.export,state="disabled"); self.export_btn.pack(side="left")
        self.status=tk.StringVar(value="Redo."); ttk.Label(top,textvariable=self.status).grid(row=5,column=0,columnspan=4,sticky="w")
        frame=ttk.Frame(root,padding=(12,0,12,12)); frame.pack(fill="both",expand=True)
        cols=("name","address","phone","website","maps","status"); self.tree=ttk.Treeview(frame,columns=cols,show="headings")
        heads={"name":"Företag","address":"Adress","phone":"Telefon","website":"Webbplats","maps":"Google Maps","status":"Status"}
        widths={"name":220,"address":300,"phone":150,"website":260,"maps":90,"status":100}
        for c in cols: self.tree.heading(c,text=heads[c]); self.tree.column(c,width=widths[c],anchor="w")
        y=ttk.Scrollbar(frame,orient="vertical",command=self.tree.yview); x=ttk.Scrollbar(frame,orient="horizontal",command=self.tree.xview)
        self.tree.configure(yscrollcommand=y.set,xscrollcommand=x.set); self.tree.grid(row=0,column=0,sticky="nsew"); y.grid(row=0,column=1,sticky="ns"); x.grid(row=1,column=0,sticky="ew")
        frame.rowconfigure(0,weight=1); frame.columnconfigure(0,weight=1)
    def stop(self): self.stop_flag=True; self.status.set("Stoppar...")
    def start(self):
        key=self.key.get().strip(); city=self.city.get().strip(); category=self.category.get().strip(); extra=self.extra.get().strip()
        if not key: messagebox.showerror("API-nyckel saknas","Ange din Google Maps Platform API-nyckel."); return
        if not city: messagebox.showerror("Stad saknas","Ange stad eller område."); return
        self.rows=[]
        for i in self.tree.get_children(): self.tree.delete(i)
        self.stop_flag=False; self.start_btn.configure(state="disabled"); self.stop_btn.configure(state="normal"); self.export_btn.configure(state="disabled")
        threading.Thread(target=self.run,args=(key,city,category,extra),daemon=True).start()
    def run(self,key,city,category,extra):
        try:
            limit=int(self.limit.get()); queries=[f"{category} in {city}"]
            if extra and extra.lower() not in category.lower(): queries.append(f"{extra} in {city}")
            places={}
            for q in queries:
                if self.stop_flag: break
                self.ui(f"Söker: {q}")
                for p in self.search(key,q):
                    if p.get("id"): places[p["id"]]=p
                    if len(places)>=limit: break
            selected=list(places.values())[:limit]
            for i,p in enumerate(selected,1):
                if self.stop_flag: break
                r=self.normalize(p); self.rows.append(r); self.root.after(0,lambda r=r:self.insert(r)); self.ui(f"Bearbetar {i}/{len(selected)}: {r["name"]}")
            self.ui(f"Klar. {len(self.rows)} unika företag hittades.")
            self.root.after(0,lambda:self.export_btn.configure(state="normal" if self.rows else "disabled"))
        except Exception as e: self.root.after(0,lambda:messagebox.showerror("Fel",str(e))); self.ui("Fel.")
        finally: self.root.after(0,lambda:self.start_btn.configure(state="normal")); self.root.after(0,lambda:self.stop_btn.configure(state="disabled"))
    def search(self,key,q):
        body=json.dumps({"textQuery":q,"pageSize":20}).encode(); req=urllib.request.Request(API_URL,data=body,method="POST")
        req.add_header("Content-Type","application/json"); req.add_header("X-Goog-Api-Key",key); req.add_header("X-Goog-FieldMask",FIELDS)
        with urllib.request.urlopen(req,timeout=30) as r: return json.loads(r.read().decode()).get("places",[])
    def normalize(self,p):
        d=p.get("displayName") or {}; loc=p.get("location") or {}
        return {"name":d.get("text",""),"address":p.get("formattedAddress",""),"phone":p.get("nationalPhoneNumber") or p.get("internationalPhoneNumber",""),"website":p.get("websiteUri",""),"maps":p.get("googleMapsUri",""),"status":p.get("businessStatus",""),"place_id":p.get("id",""),"lat":loc.get("latitude",""),"lng":loc.get("longitude",""),"types":"; ".join(p.get("types") or [])}
    def insert(self,r): self.tree.insert("", "end", values=(r["name"],r["address"],r["phone"],r["website"],"Google Maps",r["status"]))
    def ui(self,s): self.root.after(0,lambda:self.status.set(s))
    def export(self):
        if not self.rows: return
        path=filedialog.asksaveasfilename(title="Spara resultat",defaultextension=".csv",filetypes=[("CSV","*.csv")])
        if not path: return
        fields=["name","address","phone","website","maps","status","place_id","lat","lng","types"]
        with open(path,"w",newline="",encoding="utf-8-sig") as f: w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(self.rows)
        messagebox.showinfo("Klart",f"Sparade {len(self.rows)} företag.\n{path}")

if __name__=="__main__":
    root=tk.Tk(); App(root); root.mainloop()