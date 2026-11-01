import json, re, urllib.request
from concurrent.futures import ThreadPoolExecutor

PATS = [
    (r"(?:boards|job-boards)(?:\.eu)?\.greenhouse\.io/(?!embed)([\w-]+)", "https://boards.greenhouse.io/{}"),
    (r"greenhouse\.io/embed/job_board(?:/js)?\?for=([\w-]+)", "https://boards.greenhouse.io/{}"),
    (r"jobs\.lever\.co/([\w-]+)", "https://jobs.lever.co/{}"),
    (r"jobs\.ashbyhq\.com/([\w.%-]+)", "https://jobs.ashbyhq.com/{}"),
    (r"https://([\w-]+\.wd\d+\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?[\w-]+)", "https://{}"),
]

def page(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=5) as r:
            return r.read(600000).decode("utf-8", "ignore")
    except Exception:
        return ""

def find(name):
    n = re.sub(r"[^a-z0-9]", "", name.lower())
    urls = [f"https://{h}{n}.{t}{p}" for t in ("com", "io", "in", "ai") for h, p in (("careers.", ""), ("jobs.", ""), ("www.", "/careers"))]
    for u in urls:
        t = page(u)
        for pat, fmt in PATS:
            m = re.search(pat, t)
            if m:
                print("FOUND   ", name, fmt.format(m.group(1)), flush=True); return name, fmt.format(m.group(1))
    print("no match", name, flush=True); return name, None

cfg = json.load(open("companies.json"))
failed = [c["name"] for c in json.load(open("status.json"))["companies"] if c["status"] == "failed"]
with ThreadPoolExecutor(25) as ex:
    res = list(ex.map(find, failed))
cfg.setdefault("urls", [])
cfg["urls"] += [u for _, u in res if u and u not in cfg["urls"]]
json.dump(cfg, open("companies.json", "w"), indent=1)
print("\nAdded", sum(1 for _, u in res if u), "links to companies.json. Now run: python fetch_jobs.py")