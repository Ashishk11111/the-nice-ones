import json, os, re, time, html, urllib.request, urllib.error, urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta

MAX_AGE_H = 72
INDIA = re.compile(r"india|bengaluru|bangalore|hyderabad|pune|gurgaon|gurugram|noida|delhi|mumbai|chennai|kolkata|ahmedabad", re.I)
ROLE = re.compile(r"engineer|developer|\bsde\b|\bswe\b|software|programmer|devops|\bsre\b|sdet|machine learning|data scientist|member of technical staff|\bmts\b|\bamts\b", re.I)
SKIP = re.compile(r"senior|sr\.|(?<!technical )staff|principal|lead|manager|director|head|vp|architect|intern\b|\b(?:ii|iii|iv)\b|sales|recruit|marketing|finance|legal|writer|writing|risk|compliance|account|payroll|talent|customer|solutions|consultant|support|business|operations", re.I)
TITLE_SIG = re.compile(r"graduate|new grad|trainee|early[- ]career|entry|\bassociate\b|\b(?:sde|swe|engineer|developer|analyst)[- ]?(?:i|1)\b", re.I)
FRESH = re.compile(r"fresher|new[- ]?grad|recent (?:graduate|grad)|fresh graduate|class of 2026|2026 (?:batch|graduate|grad)|batch of 2026|graduating in 2026|early[- ]career|entry[- ]level|university (?:grad|hire)|college (?:grad|hire)|campus (?:hire|recruit)|(?<!\d)0\s*(?:-|–|to)\s*[12]\s*years?|no (?:prior )?(?:work )?experience", re.I)
now = datetime.now(timezone.utc)
failed = set()

def get(url, quiet=False):
    err = None
    for _ in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            err = e
            if e.code == 404: break
        except Exception as e:
            err = e
        time.sleep(2)
    if not quiet: print("FAIL", url, err); failed.add(url)

def post(url, body):
    try:
        req = urllib.request.Request(url, json.dumps(body).encode(), {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=25) as r: return json.load(r)
    except Exception as e: print("FAIL", url, e); failed.add(url)

def iso(s): return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None

def classify(title, desc):
    raw = re.sub(r"<(?:br|/p|/li|/div)[^>]*>", "\n", html.unescape(html.unescape(desc or "")))
    raw = re.sub(r"<[^>]+>", " ", raw)
    sig = TITLE_SIG.search(title) or FRESH.search(raw)
    yrs = []
    for s in re.split(r"[.;\n•]", raw):
        if re.search(r"experience|\bexp\b", s, re.I):
            n = re.search(r"(\d{1,2})\s*(?:\+|-|–|to)?\s*\d{0,2}\s*\+?\s*(?:years?|yrs?)", s, re.I)
            if n: yrs.append(int(n.group(1)))
    mn = min(yrs) if yrs else None
    if mn is not None and mn >= 2 and not (sig and "2026" in sig.group(0)): return "no", f"{mn}+ yrs"
    if sig: return "fresher", sig.group(0).strip()[:30]
    if mn is not None: return "fresher", f"{mn} yr exp"
    return "maybe", ""

def gh(slug, label):
    d = get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true")
    for j in (d or {}).get("jobs", []):
        yield label, j["title"], j["location"]["name"], j["absolute_url"], iso(j.get("updated_at")), j.get("content", "")

def lever(slug, label):
    for j in get(f"https://api.lever.co/v0/postings/{slug}?mode=json") or []:
        d = j.get("descriptionPlain", "") + " " + " ".join(l.get("text", "") + " " + l.get("content", "") for l in j.get("lists", [])) + j.get("additionalPlain", "")
        yield label, j["text"], j["categories"].get("location") or "", j["hostedUrl"], datetime.fromtimestamp(j["createdAt"]/1000, timezone.utc), d

def ashby(slug, label):
    d = get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
    for j in (d or {}).get("jobs", []):
        yield label, j["title"], j.get("location") or "", j["jobUrl"], iso(j.get("publishedAt")), j.get("descriptionPlain") or j.get("descriptionHtml", "")

def wdesc(base, tenant, site, path):
    return lambda: ((get(f"{base}/wday/cxs/{tenant}/{site}{path}") or {}).get("jobPostingInfo") or {}).get("jobDescription", "")

def wd(spec, _):
    name, sub, tenant, site = spec.split("|")
    base = f"https://{sub}.myworkdayjobs.com"
    for q in ("software engineer India", "data engineer India", "graduate India"):
        for off in (0, 20, 40):
            d = post(f"{base}/wday/cxs/{tenant}/{site}/jobs", {"appliedFacets": {}, "limit": 20, "offset": off, "searchText": q})
            if not d: break
            for j in d.get("jobPostings", []):
                po = j.get("postedOn", "")
                m = re.search(r"(\d+)\+? Days", po)
                days = int(m.group(1)) if m else (1 if "Yesterday" in po else 0)
                yield name, j["title"], j.get("locationsText", ""), f"{base}/{site}{j['externalPath']}", now - timedelta(days=days), wdesc(base, tenant, site, j["externalPath"])

def amazon(_, __):
    for q in ("software+development+engineer", "data+engineer"):
        d = get(f"https://www.amazon.jobs/en/search.json?base_query={q}&country=IND&sort=recent&result_limit=50")
        for j in (d or {}).get("jobs", []):
            try: p = datetime.strptime(j["posted_date"], "%B %d, %Y").replace(tzinfo=timezone.utc)
            except Exception: p = None
            yield "Amazon", j["title"], j.get("location", ""), "https://www.amazon.jobs" + j["job_path"], p, " ".join(j.get(k) or "" for k in ("description", "basic_qualifications", "preferred_qualifications"))

FN = {"gh": gh, "lever": lever, "ashby": ashby, "wd": wd, "amazon": amazon}

def parse(u):
    p = urllib.parse.urlparse(u); host = p.netloc; parts = [x for x in p.path.split("/") if x]
    for key, kind in (("greenhouse.io", "gh"), ("lever.co", "lever"), ("ashbyhq.com", "ashby")):
        if key in host and parts: return kind, parts[0], parts[0]
    if "myworkdayjobs.com" in host:
        sub = host.split(".myworkdayjobs")[0]; tenant = sub.split(".")[0]
        site = [x for x in parts if not re.fullmatch(r"[a-z]{2}-[A-Z]{2}", x)][0]
        return "wd", f"{tenant.capitalize()}|{sub}|{tenant}|{site}", tenant.capitalize()
    print("Can't read link:", u)

def resolve(name):
    low = name.lower()
    for slug in dict.fromkeys([re.sub(r"[^a-z0-9]", "", low), re.sub(r"[^a-z0-9]+", "-", low).strip("-")]):
        for kind, url in (("gh", f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"), ("lever", f"https://api.lever.co/v0/postings/{slug}?mode=json"), ("ashby", f"https://api.ashbyhq.com/posting-api/job-board/{slug}")):
            if get(url, quiet=True) is not None: return [kind, slug]

load = lambda f, d: json.load(open(f)) if os.path.exists(f) else d
cfg, resolved, cls = load("companies.json", {}), load("resolved.json", {}), load("cls.json", {})
tasks = [(k, s, s) for k, key in (("gh", "greenhouse"), ("lever", "lever"), ("ashby", "ashby")) for s in cfg.get(key, [])]
tasks += [("wd", s, s.split("|")[0]) for s in cfg.get("workday", [])]
for u in cfg.get("urls", []):
    t = parse(u)
    if t: tasks.append(t)
todo = [n for n in cfg.get("names", []) if n not in resolved]
with ThreadPoolExecutor(10) as ex:
    for n, r in zip(todo, ex.map(resolve, todo)): resolved[n] = r
json.dump(resolved, open("resolved.json", "w"))
tasks += [(r[0], r[1], n) for n in cfg.get("names", []) if (r := resolved.get(n))]
tasks.append(("amazon", "", "Amazon"))
with ThreadPoolExecutor(10) as ex:
    results = list(ex.map(lambda t: list(FN[t[0]](t[1], t[2])), tasks))

seen = load("seen.json", None)
first_run = seen is None
seen = seen or {}
cands, done, new_urls = [], set(), set()
for company, title, loc, url, posted, desc in (x for r in results for x in r):
    if url in done or not ((INDIA.search(loc) or re.match(r"\d+ Locations", loc)) and ROLE.search(title) and not SKIP.search(title)): continue
    done.add(url)
    if url not in seen: seen[url] = now.isoformat(); new_urls.add(url)
    p = posted or iso(seen[url])
    if now - p <= timedelta(hours=MAX_AGE_H): cands.append((company, title, loc, url, p, desc))

def run_cls(c):
    d = c[5]() if callable(c[5]) else c[5]
    return classify(c[1], d)
need = [c for c in cands if c[3] not in cls]
with ThreadPoolExecutor(8) as ex:
    for c, r in zip(need, ex.map(run_cls, need)): cls[c[3]] = list(r)
jobs, alert = [], []
for company, title, loc, url, p, _ in cands:
    fit, why = cls[url]
    if fit == "no": continue
    jobs.append({"company": company, "title": title, "location": loc, "url": url, "posted": p.isoformat(), "fit": fit, "why": why})
    if url in new_urls and fit == "fresher": alert.append((company, title, loc, url, why))
jobs.sort(key=lambda j: (j["fit"] != "fresher", -datetime.fromisoformat(j["posted"]).timestamp()))
json.dump({"updated": now.isoformat(), "jobs": jobs}, open("jobs.json", "w"), indent=1)
json.dump(seen, open("seen.json", "w")); json.dump({u: cls[u] for u in cls if u in done}, open("cls.json", "w"))

status = []
for t, r in zip(tasks, results):
    key = t[1].split("|")[1] + ".myworkdayjobs" if t[0] == "wd" else ("amazon.jobs" if t[0] == "amazon" else t[1])
    bad = any(key in u for u in failed)
    status.append({"name": t[2], "source": t[0], "status": "failed" if (bad and not r) else ("working" if r else "no jobs"),
                   "listed": len(r), "fresh": sum(1 for j in jobs if j["company"] == t[2])})
for n in cfg.get("names", []):
    if not resolved.get(n): status.append({"name": n, "source": "?", "status": "failed", "listed": 0, "fresh": 0})
json.dump({"updated": now.isoformat(), "companies": status}, open("status.json", "w"), indent=1)

tok, chat = os.getenv("TG_TOKEN"), os.getenv("TG_CHAT")
if tok and chat and not first_run:
    for c, t, l, u, w in alert[:20]:
        data = json.dumps({"chat_id": chat, "text": f"{c}: {t}\n{l}\nFresher fit: {w}\n{u}"}).encode()
        urllib.request.urlopen(urllib.request.Request(f"https://api.telegram.org/bot{tok}/sendMessage", data, {"Content-Type": "application/json"}))
        time.sleep(1)
print(sum(j["fit"] == "fresher" for j in jobs), "fresher jobs +", sum(j["fit"] == "maybe" for j in jobs), "possible;", len(tasks), "companies tracked")
