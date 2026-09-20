import argparse, csv, re, sys, time
from urllib.parse import urljoin, urlparse, parse_qs
import requests
from bs4 import BeautifulSoup

BASE="https://fmi.se"
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36"

def clean(s):
    return re.sub(r"\s+", " ", s or "").strip()

def absolute(base, href):
    return urljoin(base, href)

def extract_id(url):
    try:
        q=parse_qs(urlparse(url).query)
        for k in ("id","ID","Id"):
            if q.get(k): return q[k][0]
    except Exception: pass
    return ""

def extract_record(url, soup):
    text=clean(soup.get_text(" ", strip=True))
    title=clean(soup.title.get_text(" ", strip=True) if soup.title else "")
    h1=clean(soup.find("h1").get_text(" ", strip=True) if soup.find("h1") else "")
    labels=["Namn","Företag","Kontor","Ort","Telefon","E-post","Webbplats","Registreringsnummer"]
    data={"source_url":url,"fmi_id":extract_id(url),"name":"","company":"","office":"","city":"","phone":"","email":"","website":"","registration_number":""}
    for label in labels:
        node=soup.find(string=re.compile(r"^\s*"+re.escape(label)+r"\s*:?",re.I))
        if node:
            parent=node.parent
            val=clean(parent.get_text(" ",strip=True))
            val=re.sub(r"^"+re.escape(label)+r"\s*:?[\s-]*","",val,flags=re.I).strip()
            key={"Namn":"name","Företag":"company","Kontor":"office","Ort":"city","Telefon":"phone","E-post":"email","Webbplats":"website","Registreringsnummer":"registration_number"}[label]
            if val: data[key]=val
    if not data["name"] and h1: data["name"]=h1
    if not data["name"] and title:
        data["name"]=re.sub(r"\s*[-|].*?$","",title).strip()
    for a in soup.select("a[href]"):
        href=a.get("href","")
        txt=clean(a.get_text(" ",strip=True))
        if href.lower().startswith("mailto:") and not data["email"]: data["email"]=href[7:].split("?")[0]
        if href.lower().startswith("tel:") and not data["phone"]: data["phone"]=href[4:]
        if href.startswith("http") and "fmi.se" not in href and not data["website"]: data["website"]=href
    if not data["city"]:
        m=re.search(r"\b(Stockholm|Göteborg|Malmö|Uppsala|Västerås|Örebro|Linköping|Helsingborg|Jönköping|Norrköping|Lund|Umeå|Gävle|Borås|Södertälje|Eskilstuna|Halmstad|Växjö|Karlstad|Sundsvall|Trollhättan|Östersund)\b",text,re.I)
        if m: data["city"]=m.group(1)
    return data

def scrape(start_urls, max_records=500, delay=0.8):
    session=requests.Session()
    session.headers.update({"User-Agent":UA,"Accept-Language":"sv-SE,sv;q=0.9,en;q=0.7"})
    queue=list(start_urls); seen=set(); rows=[]; record_urls=set()
    while queue and len(rows)<max_records:
        url=queue.pop(0)
        if url in seen: continue
        seen.add(url)
        try:
            r=session.get(url,timeout=30)
            r.raise_for_status()
        except Exception as e:
            print("SKIP",url,e,file=sys.stderr); continue
        soup=BeautifulSoup(r.text,"html.parser")
        rid=extract_id(url)
        if rid or re.search(r"\?id=",url,re.I):
            if url not in record_urls:
                row=extract_record(url,soup)
                if any(row[k] for k in row if k not in ("source_url","fmi_id")):
                    rows.append(row); record_urls.add(url); print(f"[{len(rows)}] {row['name'] or row['company'] or rid}")
        for a in soup.select("a[href]"):
            href=a.get("href")
            if not href: continue
            u=absolute(url,href)
            p=urlparse(u)
            if p.netloc and p.netloc!=urlparse(BASE).netloc: continue
            if "fmi.se" not in u: continue
            if re.search(r"\?id=",u,re.I):
                if u not in record_urls: queue.append(u)
            elif any(x in p.path.lower() for x in ("/sok","/search","/register","/maklare","/fastighetsmaklare")):
                if u not in seen: queue.append(u)
        time.sleep(delay)
    return rows

def main():
    ap=argparse.ArgumentParser(description="MäklarScraper v2 - FMI records to CSV")
    ap.add_argument("urls", nargs="*", help="FMI search/direct URLs")
    ap.add_argument("-o","--output",default="maklare_resultat.csv")
    ap.add_argument("-m","--max",type=int,default=500)
    ap.add_argument("--delay",type=float,default=0.8)
    args=ap.parse_args()
    urls=args.urls or [BASE]
    rows=scrape(urls,args.max,args.delay)
    fields=["fmi_id","name","company","office","city","phone","email","website","registration_number","source_url"]
    with open(args.output,"w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
    print(f"KLAR: {len(rows)} poster sparade i {args.output}")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
