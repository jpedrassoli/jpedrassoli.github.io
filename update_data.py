#!/usr/bin/env python3
"""
Refresh publications.json and news.json for the website.

- Publications: OpenAlex (by ORCID), falling back to the ORCID public API.
  Extra items that are not indexed anywhere can be added in publications_manual.json.
- News: Google News RSS searches for your name. Items accumulate over time
  (Google only returns recent ones), and news_manual.json lets you add or hide items.

Standard library only — no pip install needed. Run locally with:  python update_data.py
"""
import json, os, re, sys, unicodedata, urllib.parse, urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
import xml.etree.ElementTree as ET

ORCID = "0000-0001-9762-102X"
NEWS_QUERIES = [
    ('"Julio Pedrassoli"', "pt-BR", "BR", "BR:pt-419"),
    ('"Julio Pedrassoli"', "en-US", "US", "US:en"),
    ('"Júlio Pedrassoli"', "pt-BR", "BR", "BR:pt-419"),
    ('Pedrassoli MapBiomas', "pt-BR", "BR", "BR:pt-419"),
    ('Pedrassoli MapBiomas', "en-US", "US", "US:en"),
]
MAX_NEWS = 150

ROOT = Path(__file__).resolve().parent
DATA = ROOT
NOW = datetime.now(timezone.utc).isoformat(timespec="seconds")
UA = {"User-Agent": "jpedrassoli.github.io data updater (+https://jpedrassoli.github.io)"}


def fetch(url, accept=None):
    headers = dict(UA)
    if accept:
        headers["Accept"] = accept
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
        return r.read()


def load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


JS_VAR = {"publications.json": "__PUBS", "news.json": "__NEWS"}


def save(path, obj):
    """Write data/<name>.json plus a data/<name>.js twin (window.__X = {...}).
    The .js twin lets the page work even when opened straight from disk (file://),
    where browsers block fetch() of local JSON."""
    js = path.with_suffix(".js")
    # Only rewrite when the items actually changed, so the daily run doesn't create empty commits.
    if load(path, {}).get("items") == obj["items"] and js.exists():
        print(f"{path.name}: unchanged")
        return
    text = json.dumps(obj, ensure_ascii=False, indent=2)
    path.write_text(text + "\n", encoding="utf-8")
    js.write_text(f"window.{JS_VAR[path.name]} = {text};\n", encoding="utf-8")


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


# ---------------------------------------------------------------- publications
def from_openalex():
    items, cursor = [], "*"
    mail = os.environ.get("OPENALEX_MAILTO", "")
    while cursor:
        q = {
            "filter": f"author.orcid:{ORCID}",
            "per_page": "200",
            "cursor": cursor,
            "select": "title,publication_year,primary_location,doi,type,authorships,open_access",
        }
        if mail:
            q["mailto"] = mail
        j = json.loads(fetch("https://api.openalex.org/works?" + urllib.parse.urlencode(q)))
        for w in j["results"]:
            loc = w.get("primary_location") or {}
            items.append({
                "year": w.get("publication_year"),
                "title": w.get("title"),
                "authors": [a["author"]["display_name"] for a in w.get("authorships", []) if a.get("author")],
                "venue": (loc.get("source") or {}).get("display_name") or "",
                "doi": w.get("doi") or "",
                "url": w.get("doi") or loc.get("landing_page_url") or "",
                "type": w.get("type"),
                "oa": bool((w.get("open_access") or {}).get("is_oa")),
            })
        cursor = j["meta"].get("next_cursor") if j["results"] else None
    return items


def from_orcid():
    j = json.loads(fetch(f"https://pub.orcid.org/v3.0/{ORCID}/works", accept="application/json"))
    items = []
    for g in j.get("group", []):
        s = g["work-summary"][0]
        doi = next((e["external-id-value"] for e in (s.get("external-ids") or {}).get("external-id", [])
                    if e["external-id-type"] == "doi"), "")
        year = ((s.get("publication-date") or {}).get("year") or {}).get("value")
        items.append({
            "year": int(year) if year else None,
            "title": s["title"]["title"]["value"],
            "authors": [],
            "venue": (s.get("journal-title") or {}).get("value", "") if s.get("journal-title") else "",
            "doi": f"https://doi.org/{doi}" if doi else "",
            "url": f"https://doi.org/{doi}" if doi else (s.get("url") or {}).get("value", "") if s.get("url") else "",
            "type": (s.get("type") or "").replace("_", "-").lower(),
            "oa": False,
        })
    return items


def dedupe_pubs(items):
    seen, out = set(), []
    for p in items:
        if not p.get("title"):
            continue
        key = (p.get("doi") or "").lower() or norm(p["title"])
        tkey = norm(p["title"])
        if key in seen or tkey in seen:
            continue
        seen.update({key, tkey})
        out.append(p)
    return sorted(out, key=lambda p: (p.get("year") or 0), reverse=True)


def update_publications():
    path = DATA / "publications.json"
    manual = load(DATA / "publications_manual.json", {"add": [], "hide": []})
    items = None
    for name, fn in (("OpenAlex", from_openalex), ("ORCID", from_orcid)):
        try:
            items = fn()
            print(f"publications: {len(items)} from {name}")
            break
        except Exception as e:
            print(f"publications: {name} failed: {e}", file=sys.stderr)
    if not items:
        print("publications: keeping previous file", file=sys.stderr)
        return
    hide = {norm(h) for h in manual.get("hide", [])}
    items = [p for p in manual.get("add", []) + items
             if norm(p.get("title")) not in hide and norm(p.get("doi")) not in hide]
    save(path, {"updated": NOW, "source": "OpenAlex/ORCID " + ORCID, "items": dedupe_pubs(items)})


# ---------------------------------------------------------------------- news
def google_news(query, hl, gl, ceid):
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": query, "hl": hl, "gl": gl, "ceid": ceid})
    root = ET.fromstring(fetch(url))
    out = []
    for it in root.iter("item"):
        src_el = it.find("source")
        source = (src_el.text or "").strip() if src_el is not None else ""
        title = (it.findtext("title") or "").strip()
        if source and title.endswith(" - " + source):
            title = title[: -len(" - " + source)]
        try:
            date = parsedate_to_datetime(it.findtext("pubDate")).date().isoformat()
        except Exception:
            date = NOW[:10]
        out.append({"date": date, "title": title, "source": source, "url": (it.findtext("link") or "").strip()})
    return out


def update_news():
    path = DATA / "news.json"
    manual = load(DATA / "news_manual.json", {"add": [], "hide": []})
    previous = load(path, {"items": []}).get("items", [])
    fresh, ok = [], False
    for q in NEWS_QUERIES:
        try:
            got = google_news(*q)
            fresh += got
            ok = True
            print(f"news: {len(got)} for {q[0]} ({q[1]})")
        except Exception as e:
            print(f"news: query {q[0]} failed: {e}", file=sys.stderr)
    if not ok and previous:
        print("news: keeping previous file", file=sys.stderr)

    hide = [norm(h) for h in manual.get("hide", [])]
    seen, items = set(), []
    # manual first, then newly found, then what we already had
    for it in manual.get("add", []) + fresh + previous:
        k = norm(it.get("title"))
        if not k or k in seen:
            continue
        if any(h and (h in k or h == norm(it.get("url"))) for h in hide):
            continue
        seen.add(k)
        items.append(it)
    items.sort(key=lambda it: it.get("date", ""), reverse=True)
    save(path, {"updated": NOW, "items": items[:MAX_NEWS]})


if __name__ == "__main__":
    update_publications()
    update_news()
