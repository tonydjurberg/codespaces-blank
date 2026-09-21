import os, re, webbrowser, tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

APP_TITLE = "SocialPoster"
PROFILE = {
    "name": "Tony Djurberg",
    "username": "Tony Djurberg",
    "email": "admin@suecodigital.com",
    "website": "https://suecodigital.com",
}

# Broad social/profile destinations. X is intentionally excluded.
NETWORKS = [
    ("LinkedIn", "https://www.linkedin.com/signup", "https://www.linkedin.com/"),
    ("Facebook", "https://www.facebook.com/r.php", "https://www.facebook.com/"),
    ("Instagram", "https://www.instagram.com/accounts/emailsignup/", "https://www.instagram.com/"),
    ("TikTok", "https://www.tiktok.com/signup", "https://www.tiktok.com/"),
    ("Pinterest", "https://www.pinterest.com/signup/", "https://www.pinterest.com/"),
    ("Reddit", "https://www.reddit.com/register/", "https://www.reddit.com/"),
    ("Threads", "https://www.threads.net/", "https://www.threads.net/"),
    ("Bluesky", "https://bsky.app/", "https://bsky.app/"),
    ("Mastodon", "https://joinmastodon.org/", "https://joinmastodon.org/"),
    ("Discord", "https://discord.com/register", "https://discord.com/app"),
    ("YouTube", "https://www.youtube.com/", "https://www.youtube.com/"),
    ("Quora", "https://www.quora.com/", "https://www.quora.com/"),
    ("Tumblr", "https://www.tumblr.com/register", "https://www.tumblr.com/"),
    ("Snapchat", "https://accounts.snapchat.com/accounts/signup", "https://www.snapchat.com/"),
    ("VK", "https://vk.com/", "https://vk.com/"),
    ("Telegram", "https://web.telegram.org/", "https://web.telegram.org/"),
    ("WhatsApp", "https://www.whatsapp.com/", "https://web.whatsapp.com/"),
    ("Medium", "https://medium.com/m/signin", "https://medium.com/"),
    ("Dev.to", "https://dev.to/enter", "https://dev.to/"),
    ("Hashnode", "https://hashnode.com/", "https://hashnode.com/"),
    ("Substack", "https://substack.com/signup", "https://substack.com/"),
    ("Patreon", "https://www.patreon.com/signup", "https://www.patreon.com/"),
    ("Ko-fi", "https://ko-fi.com/", "https://ko-fi.com/"),
    ("Buy Me a Coffee", "https://www.buymeacoffee.com/signup", "https://www.buymeacoffee.com/"),
    ("Behance", "https://www.behance.net/signup", "https://www.behance.net/"),
    ("Dribbble", "https://dribbble.com/signup", "https://dribbble.com/"),
    ("GitHub", "https://github.com/signup", "https://github.com/"),
    ("GitLab", "https://gitlab.com/users/sign_up", "https://gitlab.com/"),
    ("Twitch", "https://www.twitch.tv/signup", "https://www.twitch.tv/"),
    ("Vimeo", "https://vimeo.com/join", "https://vimeo.com/"),
    ("Flickr", "https://www.flickr.com/signup", "https://www.flickr.com/"),
    ("500px", "https://500px.com/signup", "https://500px.com/"),
    ("Goodreads", "https://www.goodreads.com/user/sign_up", "https://www.goodreads.com/"),
    ("Letterboxd", "https://letterboxd.com/join/", "https://letterboxd.com/"),
    ("Meetup", "https://www.meetup.com/register/", "https://www.meetup.com/"),
    ("Product Hunt", "https://www.producthunt.com/", "https://www.producthunt.com/"),
    ("SoundCloud", "https://soundcloud.com/signup", "https://soundcloud.com/"),
    ("Bandcamp", "https://bandcamp.com/signup", "https://bandcamp.com/"),
    ("Mixcloud", "https://www.mixcloud.com/signup/", "https://www.mixcloud.com/"),
    ("Rumble", "https://rumble.com/register", "https://rumble.com/"),
    ("Dailymotion", "https://www.dailymotion.com/register", "https://www.dailymotion.com/"),
    ("PeerTube", "https://joinpeertube.org/instances", "https://joinpeertube.org/"),
    ("Steemit", "https://steemit.com/", "https://steemit.com/"),
    ("MeWe", "https://mewe.com/", "https://mewe.com/"),
    ("Gab", "https://gab.com/auth/sign_up", "https://gab.com/"),
    ("Minds", "https://www.minds.com/register", "https://www.minds.com/"),
    ("Lemmy", "https://join-lemmy.org/instances", "https://join-lemmy.org/instances"),
    ("Nostr", "https://nostr.com/", "https://nostr.com/"),
    ("Flipboard", "https://flipboard.com/", "https://flipboard.com/"),
    ("Disqus", "https://disqus.com/profile/signup/", "https://disqus.com/"),
    ("Gravatar", "https://en.gravatar.com/site/signup/", "https://en.gravatar.com/"),
]

INDEX_LINKS = [
    ("Google Search Console", "https://search.google.com/search-console"),
    ("Bing Webmaster Tools", "https://www.bing.com/webmasters/"),
    ("IndexNow", "https://www.indexnow.org/"),
]

STOP = set("the and for with that this from into your you are was were have has will can our their about using use how what why when where which these those article business company website digital marketing seo ai a an of to in on is it as by or be".split())

def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()

def extract_text(path):
    ext = Path(path).suffix.lower()
    if ext in (".txt", ".md", ".html", ".htm"):
        raw = Path(path).read_text(encoding="utf-8", errors="ignore")
        raw = re.sub(r"<[^>]+>", " ", raw)
        return clean(raw)
    raise ValueError("Use a .txt, .md, .html or .htm article.")

def keywords(text, n=12):
    words = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9][A-Za-zÀ-ÖØ-öø-ÿ0-9'-]{2,}", text.lower())
    counts = {}
    for w in words:
        w = w.strip("'-")
        if w in STOP or w.isdigit():
            continue
        counts[w] = counts.get(w, 0) + 1
    return [w for w, _ in sorted(counts.items(), key=lambda x: (-x[1], x[0]))[:n]]

def hashtags(keys):
    return " ".join("#" + re.sub(r"[^\wÀ-ÖØ-öø-ÿ]", "", clean(k)) for k in keys if clean(k))

def make_caption(text, keys):
    title = clean(text)[:180]
    if len(clean(text)) > 180:
        title += "…"
    return f"{title}\n\nRead the full article on {PROFILE['website']}\n\n{hashtags(keys)}"

def font(size, bold=False):
    candidates = [
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()

def create_poster(text, keys, out):
    W, H = 1600, 900
    im = Image.new("RGB", (W, H), (11, 11, 11))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((70, 70, W-70, H-70), radius=35, outline=(201, 162, 39), width=4)
    for i in range(8):
        x, y = 1120 + i * 45, 115 + i * 38
        d.ellipse((x, y, x+230, y+230), outline=(226, 193, 78), width=2)
    d.polygon([(80, 760), (520, 330), (760, 760)], outline=(226, 193, 78), width=5)
    d.line((110, 760, 1490, 760), fill=(201, 162, 39), width=3)
    title = clean(text).split("\n")[0][:80] or "New Article"
    d.text((120, 150), title, font=font(64, True), fill=(245, 245, 245))
    d.text((120, 300), "TONY DJURBERG", font=font(30, True), fill=(226, 193, 78))
    d.text((120, 350), "Independent digital consultant", font=font(28), fill=(210, 210, 210))
    d.multiline_text((120, 610), "  ".join("#" + re.sub(r"[^\wÀ-ÖØ-öø-ÿ]", "", clean(k)) for k in keys[:6]), font=font(25), fill=(226, 193, 78), spacing=14)
    im.save(out, "PNG")

def open_url(url):
    webbrowser.open(clean(url))

def main():
    root = tk.Tk()
    root.title(APP_TITLE)
    root.geometry("1000x820")
    root.minsize(900, 700)
    root.configure(bg="#0b0b0b")
    state = {"article": "", "keys": [], "poster": ""}

    def upload():
        p = filedialog.askopenfilename(title="Upload article", filetypes=[("Articles", "*.txt *.md *.html *.htm"), ("All files", "*.*")])
        if not p:
            return
        try:
            txt = extract_text(p)
        except Exception as e:
            messagebox.showerror(APP_TITLE, str(e))
            return
        state["article"] = txt
        state["keys"] = keywords(txt)
        article_name.config(text=clean(os.path.basename(p)))
        kw_var.set(hashtags(state["keys"]))
        caption.delete("1.0", "end")
        caption.insert("1.0", make_caption(txt, state["keys"]))
        status.config(text="Article loaded — keywords and hashtags created automatically.")

    def create():
        if not state["article"]:
            messagebox.showinfo(APP_TITLE, "Upload an article first.")
            return
        out = Path.home() / "SocialPoster_Output"
        out.mkdir(exist_ok=True)
        poster = out / "poster.png"
        create_poster(state["article"], state["keys"], poster)
        state["poster"] = str(poster)
        status.config(text=f"Poster created: {poster}")
        webbrowser.open(poster.resolve().as_uri())

    def copy_caption():
        root.clipboard_clear()
        root.clipboard_append(clean(caption.get("1.0", "end")))
        root.update()
        status.config(text="Caption copied to clipboard.")

    header = tk.Frame(root, bg="#0b0b0b")
    header.pack(fill="x", padx=24, pady=(20, 10))
    tk.Label(header, text="SOCIALPOSTER", bg="#0b0b0b", fg="#e2c14e", font=("Arial", 26, "bold")).pack()
    tk.Label(header, text="Article → Poster → Hashtags → Social profiles → Posting → Indexing", bg="#0b0b0b", fg="#ddd", font=("Arial", 12)).pack(pady=(2, 12))

    top = tk.Frame(root, bg="#151515", highlightbackground="#c9a227", highlightthickness=1)
    top.pack(fill="x", padx=24)
    tk.Button(top, text="UPLOAD ARTICLE", command=upload, bg="#c9a227", fg="#0b0b0b", font=("Arial", 12, "bold"), padx=20, pady=10).pack(side="left", padx=14, pady=14)
    article_name = tk.Label(top, text="No article selected", bg="#151515", fg="#ddd", anchor="w")
    article_name.pack(side="left", fill="x", expand=True)

    body = tk.Frame(root, bg="#0b0b0b")
    body.pack(fill="both", expand=True, padx=24, pady=14)

    tk.Label(body, text="HASHTAGS (AUTOMATIC)", bg="#0b0b0b", fg="#e2c14e", font=("Arial", 11, "bold")).pack(anchor="w")
    kw_var = tk.StringVar()
    tk.Entry(body, textvariable=kw_var, bg="#151515", fg="#eee", insertbackground="white").pack(fill="x", pady=(5, 12))

    tk.Label(body, text="CAPTION", bg="#0b0b0b", fg="#e2c14e", font=("Arial", 11, "bold")).pack(anchor="w")
    caption = tk.Text(body, height=6, bg="#151515", fg="#eee", insertbackground="white", wrap="word")
    caption.pack(fill="x", pady=5)

    btns = tk.Frame(body, bg="#0b0b0b")
    btns.pack(fill="x", pady=7)
    tk.Button(btns, text="CREATE POSTER", command=create, bg="#c9a227", fg="#0b0b0b", font=("Arial", 11, "bold"), padx=15, pady=8).pack(side="left")
    tk.Button(btns, text="COPY CAPTION", command=copy_caption, bg="#222", fg="#eee", padx=15, pady=8).pack(side="left", padx=8)

    outer = tk.Frame(body, bg="#151515", highlightbackground="#333", highlightthickness=1)
    outer.pack(fill="both", expand=True, pady=(8, 0))

    canvas = tk.Canvas(outer, bg="#151515", highlightthickness=0)
    scrollbar = tk.Scrollbar(outer, orient="vertical", command=canvas.yview)
    scroll = tk.Frame(canvas, bg="#151515")
    scroll.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=scroll, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    left = tk.Frame(scroll, bg="#151515")
    left.pack(fill="x", padx=16, pady=12)
    tk.Label(left, text=f"SOCIAL MEDIA — {len(NETWORKS)} DESTINATIONS (X EXCLUDED)", bg="#151515", fg="#e2c14e", font=("Arial", 11, "bold")).pack(anchor="w")
    tk.Label(left, text="Use PROFILE to open the signup/profile page. Use POST to open the platform. The app does not bypass platform signup or posting restrictions.", bg="#151515", fg="#aaa", wraplength=850, justify="left").pack(anchor="w", pady=(3, 8))

    for raw_name, signup_url, post_url in NETWORKS:
        name = clean(raw_name)
        row = tk.Frame(left, bg="#202020")
        row.pack(fill="x", pady=2)
        tk.Label(row, text=name, bg="#202020", fg="#eee", anchor="w", width=24).pack(side="left", padx=8, pady=4)
        tk.Button(row, text="PROFILE ↗", command=lambda u=signup_url: open_url(u), bg="#292929", fg="#eee", relief="flat").pack(side="left", padx=3, pady=3)
        tk.Button(row, text="POST ↗", command=lambda u=post_url: open_url(u), bg="#292929", fg="#e2c14e", relief="flat").pack(side="left", padx=3, pady=3)

    idx = tk.Frame(scroll, bg="#151515")
    idx.pack(fill="x", padx=16, pady=(16, 12))
    tk.Label(idx, text="FAST INDEXING", bg="#151515", fg="#e2c14e", font=("Arial", 11, "bold")).pack(anchor="w")
    for name, url in INDEX_LINKS:
        tk.Button(idx, text=clean(name) + "  ↗", command=lambda u=url: open_url(u), bg="#222", fg="#eee", relief="flat", anchor="w").pack(fill="x", pady=2)

    prof = tk.Frame(scroll, bg="#151515")
    prof.pack(fill="x", padx=16, pady=(8, 16))
    tk.Label(prof, text="PROFILE", bg="#151515", fg="#e2c14e", font=("Arial", 11, "bold")).pack(anchor="w")
    tk.Label(prof, text=f"Name: {clean(PROFILE['name'])}\nUsername: {clean(PROFILE['username'])}\nEmail: {clean(PROFILE['email'])}\nWebsite: {clean(PROFILE['website'])}", bg="#151515", fg="#ddd", justify="left", anchor="w").pack(anchor="w", pady=(4, 0))

    status = tk.Label(root, text="Ready.", bg="#0b0b0b", fg="#aaa", anchor="w")
    status.pack(fill="x", padx=24, pady=(0, 14))
    root.mainloop()

if __name__ == "__main__":
    main()
