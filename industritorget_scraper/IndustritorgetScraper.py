import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading, subprocess, sys, os

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Industritorget Scraper")
        self.geometry("720x520")
        self.resizable(True, True)
        self.result_dir = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "Documents", "Industritorget Results"))
        self.country = tk.StringVar(value="Sverige")
        self.pages = tk.IntVar(value=5)
        self.delay = tk.DoubleVar(value=0.8)
        self.start_url = tk.StringVar()
        self.build_ui()

    def build_ui(self):
        pad={"padx":12,"pady":6}
        ttk.Label(self,text="Industritorget Company & Contact Scraper",font=("Segoe UI",16,"bold")).pack(anchor="w",**pad)
        ttk.Label(self,text="Public company-directory data only. No personnummer or hidden/private data.").pack(anchor="w",**pad)
        f=ttk.Frame(self); f.pack(fill="x",**pad)
        ttk.Label(f,text="Country:").grid(row=0,column=0,sticky="w")
        ttk.Entry(f,textvariable=self.country,width=30).grid(row=0,column=1,sticky="ew",padx=8)
        ttk.Label(f,text="Pages:").grid(row=0,column=2)
        ttk.Spinbox(f,from_=1,to=100000,textvariable=self.pages,width=10).grid(row=0,column=3,padx=8)
        f.columnconfigure(1,weight=1)
        ttk.Label(self,text="Optional exact directory URL (overrides Country):").pack(anchor="w",**pad)
        ttk.Entry(self,textvariable=self.start_url).pack(fill="x",padx=12)
        ttk.Label(self,text="Results folder:").pack(anchor="w",**pad)
        rf=ttk.Frame(self); rf.pack(fill="x",padx=12)
        ttk.Entry(rf,textvariable=self.result_dir).pack(side="left",fill="x",expand=True)
        ttk.Button(rf,text="Choose folder…",command=self.choose_folder).pack(side="left",padx=8)
        ttk.Label(self,text="The installer chooses where the program is installed. This setting chooses where CSV results are saved.").pack(anchor="w",**pad)
        self.progress=ttk.Progressbar(self,mode="indeterminate")
        self.progress.pack(fill="x",padx=12,pady=8)
        self.log=tk.Text(self,height=16,wrap="word")
        self.log.pack(fill="both",expand=True,padx=12,pady=6)
        bf=ttk.Frame(self); bf.pack(fill="x",padx=12,pady=8)
        self.run_btn=ttk.Button(bf,text="START SCRAPING",command=self.start)
        self.run_btn.pack(side="left")
        ttk.Button(bf,text="Open Results Folder",command=self.open_results).pack(side="left",padx=8)

    def choose_folder(self):
        p=filedialog.askdirectory(title="Choose results folder")
        if p:self.result_dir.set(p)

    def open_results(self):
        p=self.result_dir.get()
        os.makedirs(p,exist_ok=True)
        os.startfile(p) if sys.platform.startswith("win") else subprocess.Popen(["xdg-open",p])

    def write(self,s):
        self.log.insert("end",s+"\n"); self.log.see("end")

    def start(self):
        p=self.result_dir.get().strip()
        if not p:
            messagebox.showerror("Results folder","Choose a results folder first."); return
        os.makedirs(p,exist_ok=True)
        self.run_btn.config(state="disabled"); self.progress.start(10); self.log.delete("1.0","end")
        threading.Thread(target=self.worker,daemon=True).start()

    def worker(self):
        try:
            root=os.path.dirname(os.path.abspath(sys.argv[0]))
            script=os.path.join(root,"industritorget_scraper.py")
            cmd=[sys.executable,script,"--country",self.country.get().strip(),"--pages",str(self.pages.get()),"--delay",str(self.delay.get()),"--out",self.result_dir.get()]
            if self.start_url.get().strip(): cmd += ["--start-url",self.start_url.get().strip()]
            self.write("Starting scraper…")
            self.write("Country: "+self.country.get())
            self.write("Pages: "+str(self.pages.get()))
            self.write("Results: "+self.result_dir.get())
            p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding="utf-8",errors="replace")
            for line in p.stdout:
                self.write(line.rstrip())
            rc=p.wait()
            if rc==0:
                self.write("DONE. CSV files are in the selected results folder.")
                messagebox.showinfo("Finished","Scraping finished. Results were saved to the selected folder.")
            else:
                self.write("Scraper exited with code "+str(rc))
                messagebox.showerror("Scraper error","The scraper stopped with an error. Check the log.")
        except Exception as e:
            self.write("ERROR: "+repr(e)); messagebox.showerror("Error",str(e))
        finally:
            self.progress.stop(); self.run_btn.config(state="normal")

if __name__=="__main__":
    App().mainloop()
