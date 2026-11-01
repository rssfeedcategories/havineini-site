"""Build the Havineini app's episode list (catalog.json) and keep our own hard copy.

Inputs
  catalog/archive.json         OUR HARD COPY: every episode ever seen, with its categories.
                               Only ever grows - nothing is deleted automatically.
  Libsyn feed (--feed)         new episodes and edits (titles, audio links, dates)
  podcast-feeds (--cats DIR)   rssfeedcategories/podcast-feeds checkout: checkpoint.json +
                               output_feeds/*.xml, one feed per Libsyn portal category.
                               Gives each episode (by guid) its categories.
Output
  catalog.json                 what the app downloads (same format as the Birkas app's)

Safety rules (Izzy, Nov 1 2026)
  - If the feed or podcast-feeds can't be read, the run keeps the archive as it is,
    warns, and still builds the app list from the archive.
  - An episode missing from the feed stays in the app. Remove one only through
    catalog/hidden.json.
  - An episode keeps its last known categories when it is missing from every
    category feed (outage, renamed title, ...). It only changes category when a
    category feed actually lists it somewhere else.
"""
import argparse, collections, datetime, json, os, pathlib, re, sys, urllib.request
import xml.etree.ElementTree as ET

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from hebrew_text import (norm, heb_num, heb_display, strict_num, level3_numbers, level3_label,
                         parshiyos_from_title, PARSHIYOS, gemara_amudim, parse_date, fmt_dur, dur_secs)

FEED_URL = "https://rss.libsyn.com/shows/93012/destinations/468609.xml"
HERE = pathlib.Path(__file__).resolve().parent.parent          # app/
ARCHIVE = HERE / "catalog" / "archive.json"
ITUNES = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"
ATOM_LINK = "{http://www.w3.org/2005/Atom}link"

# ---------------------------------------------------------------- categories
# Names exactly as in the Libsyn portal / podcast-feeds. Order = order in the app.
DAILY = "Daily Shiur - שיעור יומי"
CATEGORY_ORDER = [
    "הבינני בהלכה", DAILY, "דף היומי", "תלמוד ירושלמי", "ספר חפץ חיים", "חובת הלבבות",
    "אור החיים הקדוש", "ליל שישי", "עיון תפילה", "שבת קודש", "ENGLISH SHIURIM", "יארצייטען",
    "לימוד התורה", "אמונת חכמים בדורינו", "טעמו וראו", "שיעורים מיוחדים",
    # Yomim Tovim in calendar order, from Elul
    "חודש אלול - ראש השנה", "עשרת ימי תשובה - יום כיפור", "חג הסוכות", "חנוכה", "שובב\"ים",
    "ט\"ו בשבט", "פורים", "פסח", "פסח שני", "ל\"ג בעומר", "חג השבועות", "ט' באב",
    "GENERAL", "הודעות", "general",
]
LABELS = {"general": "שונות"}
WEAK = {DAILY, "GENERAL", "הודעות"}   # lose to any specific category the episode is also in

# Untagged episodes (podcast-feeds hasn't caught up yet, ~15 min): guess from the title.
TITLE_RULES = [
    ("הבינני בהלכה", "הבינני בהלכה"), ("תלמוד ירושלמי", "תלמוד ירושלמי"), ("חפץ חיים", "ספר חפץ חיים"),
    ("חובות הלבבות", "חובת הלבבות"), ("חובת הלבבות", "חובת הלבבות"), ("אור החיים", "אור החיים הקדוש"),
    ("עיון תפילה", "עיון תפילה"), ("עניני שבת קודש", "שבת קודש"), ("מסכת ", "דף היומי"),
]
FALLBACK = DAILY

SHAS = ["ברכות","שבת","עירובין","פסחים","שקלים","יומא","סוכה","ביצה","ראש השנה","תענית","מגילה","מועד קטן",
        "חגיגה","יבמות","כתובות","נדרים","נזיר","סוטה","גיטין","קידושין","בבא קמא","בבא מציעא","בבא בתרא",
        "סנהדרין","מכות","שבועות","עבודה זרה","הוריות","זבחים","מנחות","חולין","בכורות","ערכין","תמורה",
        "כריתות","מעילה","תמיד","נדה"]
YERUSHALMI = ["ברכות","פאה","דמאי","כלאים","שביעית","תרומות","מעשרות","מעשר שני","חלה","ערלה","ביכורים",
              "שבת","עירובין","פסחים","שקלים","יומא","סוכה","ביצה","ראש השנה","תענית","מגילה","מועד קטן",
              "חגיגה","יבמות","סוטה","כתובות","נדרים","נזיר","גיטין","קידושין","בבא קמא","בבא מציעא",
              "בבא בתרא","סנהדרין","מכות","שבועות","עבודה זרה","הוריות","נדה"]
CHOVOS = ["הקדמה","שער היחוד","שער הבחינה","שער עבודת האלהים","שער הבטחון","שער יחוד המעשה","שער הכניעה",
          "שער התשובה","שער חשבון הנפש","שער הפרישות","שער אהבת ה'"]
CHOVOS_ALIAS = {"שער הביטחון": "שער הבטחון", "שער עבודת האלקים": "שער עבודת האלהים",
                "שער עבודת האלוקים": "שער עבודת האלהים", "שער אהבת השם": "שער אהבת ה'"}
CHAFETZ = ["הקדמה", "פתיחה", "הלכות לשון הרע", "הלכות רכילות"]
# הבינני בהלכה goes through אורח חיים in order: section = חלק of the משנה ברורה, third column = סימן.
MB_RANGES = [(1, 127), (128, 241), (242, 344), (345, 428), (429, 529), (530, 697)]
MB_PARTS = [f"חלק {heb_display(i)}" for i in range(1, 7)]
def mb_part(siman):
    return next((MB_PARTS[i] for i, (lo, hi) in enumerate(MB_RANGES) if lo <= siman <= hi), None)

# HebrewBooks page maps (copied from Birkas): siman -> pages of the משנה ברורה, per חלק.
MB_SOURCES = {}
for _f in sorted((pathlib.Path(__file__).resolve().parent.parent / "catalog" / "sources").glob("mb_*.json")):
    _d = json.loads(_f.read_text(encoding="utf-8"))
    MB_SOURCES[_d["part"]] = _d

# Third column (points) per category: the word whose numbers follow in the title.
LEVEL3 = {"הבינני בהלכה": "סימן", "דף היומי": "דף", "תלמוד ירושלמי": "דף", "ספר חפץ חיים": "חלק"}

def masechta(title, order):
    t = norm(title)
    for m in sorted(order, key=len, reverse=True):       # בבא מציעא before ...
        if re.search(r"מסכת\s+" + re.escape(m) + r"(\s|$)", t):
            return "מסכת " + m
    return None

def section_of(cat, title):
    """[] or [section name] for an episode."""
    t = norm(title)
    if cat == "הבינני בהלכה":
        n = level3_numbers(title, "סימן")
        part = mb_part(n[0]) if n else None
        return [part] if part else []
    if cat == "דף היומי":
        m = masechta(title, SHAS)
        return [m] if m else []
    if cat == "תלמוד ירושלמי":
        m = masechta(title, YERUSHALMI)
        return [m] if m else []
    if cat == "ספר חפץ חיים":
        for s in CHAFETZ:
            if s in t:
                return [s]
        return []
    if cat == "חובת הלבבות":
        for a, c in CHOVOS_ALIAS.items():
            t = t.replace(norm(a), c)
        for s in CHOVOS[1:]:
            if norm(s) in t:
                return [s]
        return []
    if cat == "אור החיים הקדוש":
        return parshiyos_from_title(title)[:1]
    return []

def section_order(cat, present):
    """Order of the sections that exist in this category."""
    if cat == "הבינני בהלכה":
        return [s for s in MB_PARTS if s in present]
    if cat == "דף היומי":
        return ["מסכת " + m for m in SHAS if "מסכת " + m in present]
    if cat == "תלמוד ירושלמי":
        return ["מסכת " + m for m in YERUSHALMI if "מסכת " + m in present]
    if cat == "ספר חפץ חיים":
        return [s for s in CHAFETZ if s in present]
    if cat == "חובת הלבבות":
        return [s for s in CHOVOS if s in present]
    if cat == "אור החיים הקדוש":
        return [p for p in PARSHIYOS if p in present]
    return sorted(present)

def shiur_num(title):
    m = re.search(r"#\s*(\d+)", title or "")
    return int(m.group(1)) if m else None

def position(title):
    """Place in the sefer from the title (סימן/סעיף, דף), for ordering un-numbered shiurim."""
    t = norm(title)
    m = re.search(r"סימן\s+(\S+)(?:.*?סעיף\s+(\S+))?", t)
    if m and heb_num(m.group(1)):
        return heb_num(m.group(1)) * 100 + (heb_num((m.group(2) or "").split("-")[0]) or 0)
    m = re.search(r"דף\s+(\S+)", t)
    if m and heb_num(m.group(1)):
        return heb_num(m.group(1))
    return None

# ---------------------------------------------------------------- reading sources
def fetch(url, timeout=90):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 havineini-catalog"})
    return urllib.request.urlopen(req, timeout=timeout).read()

def item_record(it):
    enc = it.find("enclosure")
    img = it.find(ITUNES + "image")
    return {
        "t": (it.findtext("title") or "").strip(),
        "d": iso(parse_date(it.findtext("pubDate"))),
        "a": enc.get("url") if enc is not None else None,
        "ty": enc.get("type") if enc is not None else None,
        "sec": dur_secs(it.findtext(ITUNES + "duration")),
        "img": img.get("href") if img is not None else None,
        "l": it.findtext("link"),
        "desc": (it.findtext("description") or it.findtext(ITUNES + "summary") or "").strip() or None,
    }

def read_feed(url, max_pages=25):
    """(channel info, {guid: record}) following <atom:link rel="next"> pages."""
    root = ET.fromstring(fetch(url))
    ch = root.find("channel")
    img = ch.find("image")
    info = {"title": ch.findtext("title"), "author": ch.findtext(ITUNES + "author"),
            "image": (ch.find(ITUNES + "image").get("href") if ch.find(ITUNES + "image") is not None
                      else (img.findtext("url") if img is not None else None))}
    items, seen = list(ch.findall("item")), {url}
    while len(seen) < max_pages:
        nxt = next((l.get("href") for l in ch.findall(ATOM_LINK) if l.get("rel") == "next" and l.get("href")), None)
        if not nxt or nxt in seen:
            break
        seen.add(nxt)
        ch = ET.fromstring(fetch(nxt)).find("channel")
        items += ch.findall("item")
    out = {}
    for it in items:
        g = (it.findtext("guid") or "").strip()
        if g and g not in out:
            out[g] = item_record(it)
    return info, out

def safe_filename(name):          # same as podcast-feeds/generate_category_feeds.py
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = re.sub(r'\s+', '_', name.strip())
    return name[:80] or "category"

def read_categories(cats_dir):
    """({guid: [categories]}, {guid: record}, {category: count}) from a podcast-feeds checkout."""
    d = pathlib.Path(cats_dir)
    names = list(json.loads((d / "checkpoint.json").read_text(encoding="utf-8")).keys())
    by_guid, records, counts = collections.defaultdict(list), {}, {}
    for name in names:
        f = d / "output_feeds" / (safe_filename(name) + ".xml")
        if not f.exists():
            print(f"  ! no feed file for category {name}")
            continue
        its = ET.parse(f).getroot().find("channel").findall("item")
        counts[name] = len(its)
        for it in its:
            g = (it.findtext("guid") or "").strip()
            if not g:
                continue
            if name not in by_guid[g]:
                by_guid[g].append(name)
            records.setdefault(g, item_record(it))
    return by_guid, records, counts

# ---------------------------------------------------------------- archive (our hard copy)
def iso(d):
    return d.isoformat().replace("+00:00", "Z") if d else None

def load_archive():
    if not ARCHIVE.exists():
        return {"channel": {}, "category_counts": {}, "episodes": {}}
    return json.loads(ARCHIVE.read_text(encoding="utf-8"))

def save_archive(arc):
    """One episode per line, so git shows exactly what changed. Written atomically."""
    eps = arc["episodes"]
    lines = ['{"_about": ' + json.dumps("Havineini hard copy: every episode ever seen, by Libsyn guid. "
                                        "Only grows. Built by tools/build_catalog.py.", ensure_ascii=False) + ",",
             ' "channel": ' + json.dumps(arc.get("channel", {}), ensure_ascii=False, sort_keys=True) + ",",
             ' "category_counts": ' + json.dumps(arc.get("category_counts", {}), ensure_ascii=False, sort_keys=True) + ",",
             ' "episodes": {']
    keys = sorted(eps, key=lambda g: (eps[g].get("d") or "", g), reverse=True)
    for i, g in enumerate(keys):
        lines.append("  " + json.dumps(g) + ": " + json.dumps(eps[g], ensure_ascii=False, sort_keys=True)
                     + ("," if i < len(keys) - 1 else ""))
    lines += [" }", "}", ""]
    tmp = ARCHIVE.with_suffix(".tmp")
    tmp.write_text("\n".join(lines), encoding="utf-8")
    json.loads(tmp.read_text(encoding="utf-8"))           # never replace the archive with a broken file
    os.replace(tmp, ARCHIVE)

def merge(eps, records, now, prefer=True):
    """Add new episodes; update fields. prefer=False only fills fields that are empty."""
    added = changed = 0
    for g, rec in records.items():
        cur = eps.get(g)
        if cur is None:
            eps[g] = {**{k: v for k, v in rec.items() if v not in (None, "")}, "cats": [], "first_seen": now}
            added += 1
            continue
        for k, v in rec.items():
            if v in (None, ""):
                continue
            if (prefer or cur.get(k) in (None, "")) and cur.get(k) != v:
                cur[k] = v
                changed += 1
    return added, changed

# ---------------------------------------------------------------- classify + order
def desc_text(html):
    """First line of the description as plain text (that is where the סימן etc. is)."""
    t = re.sub(r"<br\s*/?>|</p>", "\n", html or "", flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t).replace("&nbsp;", " ").replace("&quot;", '"').replace("&#39;", "'")
    lines = [l.strip() for l in t.splitlines() if l.strip()]
    return " ".join(lines[:2])[:300]

def primary(cats):
    strong = [c for c in cats if c not in WEAK] or list(cats)
    rank = {c: i for i, c in enumerate(CATEGORY_ORDER)}
    return min(strong, key=lambda c: rank.get(c, len(rank))) if strong else None

def classify(e):
    cat = primary(e["cats"])
    if cat is None:
        t = norm(e["t"])
        cat = next((c for p, c in TITLE_RULES if norm(p) in t), FALLBACK)
        e["guessed"] = True
    e["c"] = cat
    e["s"] = section_of(cat, e["t"])
    kw = LEVEL3.get(cat)
    e["p"] = level3_numbers(e["t"], kw) if kw else []
    # Older shiurim often have the סימן / מסכת / פרשה only in the description.
    if not e["s"] and e.get("desc"):
        d = desc_text(e["desc"])
        e["s"] = section_of(cat, d)
        if e["s"] and kw:
            e["p"] = level3_numbers(d, kw)
    e["n"], e["pos"] = shiur_num(e["t"]), position(e["t"])
    e["dt"] = parse_date(e.get("d"))

def inherit_sections(eps):
    """A numbered shiur with no section takes the section of the shiur before it."""
    by_cat = collections.defaultdict(list)
    for e in eps:
        if e["n"] is not None and e["c"] in ("הבינני בהלכה", "ספר חפץ חיים", "חובת הלבבות"):
            by_cat[e["c"]].append(e)
    moved = 0
    for lst in by_cat.values():
        lst.sort(key=lambda e: (e["n"], ts(e)))
        last = None
        for e in lst:
            if e["s"]:
                last = e
            elif last and 0 < e["n"] - last["n"] <= 5:
                e["s"] = list(last["s"]); moved += 1
    return moved

EPOCH0 = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)
def ts(e):
    return (e.get("dt") or EPOCH0).timestamp()

def order_within(lst, flat=False):
    numbered = [e for e in lst if e["n"] is not None]
    if lst and len(numbered) * 2 >= len(lst):
        rest = [e for e in lst if e["n"] is None]
        return sorted(numbered, key=lambda e: (e["n"], ts(e))) + sorted(rest, key=ts)
    posd = [e for e in lst if e["pos"] is not None]
    if lst and len(posd) * 2 >= len(lst):
        rest = [e for e in lst if e["pos"] is None]
        return sorted(posd, key=lambda e: (e["pos"], ts(e))) + sorted(rest, key=ts)
    return sorted(lst, key=lambda e: -ts(e)) if flat else sorted(lst, key=ts)

def build(eps):
    cats = collections.OrderedDict((c, []) for c in CATEGORY_ORDER)
    for e in eps:
        cats.setdefault(e["c"], []).append(e)
    meta = []
    for cat, lst in cats.items():
        if not lst:
            continue
        present = collections.OrderedDict()
        for e in lst:
            for s in e["s"]:
                present.setdefault(s, []).append(e)
        sec_order = section_order(cat, present) if len(present) > 1 else []   # one section = no chooser
        if not sec_order:
            for e in lst:
                e["s"] = []
        ordered, seen = [], set()
        for s in sec_order:
            for e in order_within(present[s]):
                if e["id"] not in seen:
                    ordered.append(e); seen.add(e["id"])
        rest = [e for e in lst if e["id"] not in seen]
        ordered += order_within(rest, flat=not sec_order) if not sec_order else sorted(rest, key=ts)
        for i, e in enumerate(ordered):
            e["o"] = i
        kw = LEVEL3.get(cat)
        sec_meta = []
        for s in sec_order:
            m = {"name": s, "count": len(present[s])}
            if kw:
                pts = sorted({n for e in present[s] for n in e["p"]})
                if pts:
                    m["points"] = [level3_label(kw, n) for n in pts]
            sec_meta.append(m)
        meta.append({"name": cat, "label": LABELS.get(cat, cat), "count": len(lst), "sections": sec_meta})
    return meta

# ---------------------------------------------------------------- main
def load_json(path, default):
    try:
        return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--feed", nargs="?", const=FEED_URL, default=None, help="merge the live Libsyn feed")
    ap.add_argument("--cats", default=None, help="podcast-feeds checkout (categories)")
    ap.add_argument("--out", default=str(HERE / "catalog.json"))
    ap.add_argument("--report", default=None)
    a = ap.parse_args()

    log = []
    def say(s):
        print(s); log.append(s)
    now = iso(datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0))
    arc = load_archive()
    eps = arc["episodes"]
    before = len(eps)
    say(f"archive: {before} episodes")

    # 1. live feed (wins for titles, links, dates)
    if a.feed:
        try:
            info, recs = read_feed(a.feed)
            if before and len(recs) < before * 0.5:
                say(f"WARNING: feed gave only {len(recs)} episodes (archive has {before}) - "
                    "nothing is removed; new and changed episodes are still taken.")
            ad, ch = merge(eps, recs, now)
            arc["channel"] = {k: v for k, v in info.items() if v} or arc.get("channel", {})
            say(f"feed: {len(recs)} episodes, {ad} new, {ch} field updates")
        except Exception as ex:
            say(f"WARNING: feed not readable ({ex}) - keeping the archive as it is")

    # 2. categories from podcast-feeds (also a second copy of every episode's data)
    if a.cats:
        try:
            by_guid, recs, counts = read_categories(a.cats)
            prev = arc.get("category_counts", {})
            shrunk = {c for c, n in counts.items() if prev.get(c, 0) >= 10 and n < prev[c] * 0.5}
            for c in shrunk:
                say(f"WARNING: category {c} shrank {prev[c]} -> {counts[c]}; its episodes keep their old categories")
            ad, _ = merge(eps, recs, now, prefer=False)
            moved = 0
            rank = lambda c: CATEGORY_ORDER.index(c) if c in CATEGORY_ORDER else 99
            for g, cs in by_guid.items():
                e = eps[g]
                new = set(cs)
                if shrunk:   # a half-empty list can't take an episode out of that category
                    new |= set(e.get("cats", [])) & shrunk
                new = sorted(new, key=rank)
                if new != e.get("cats"):
                    e["cats"] = new; moved += 1
            arc["category_counts"] = {c: max(n, prev.get(c, 0)) if c in shrunk else n for c, n in counts.items()}
            say(f"categories: {len(counts)} lists, {len(by_guid)} episodes listed, {ad} new from lists, "
                f"{moved} category changes")
        except Exception as ex:
            say(f"WARNING: categories not readable ({ex}) - every episode keeps its saved categories")

    assert len(eps) >= before, "archive lost episodes - refusing to save"
    save_archive(arc)
    say(f"archive saved: {len(eps)} episodes ({len(eps) - before} new)")

    # 3. app list, built only from the archive
    videos = {k: v for k, v in load_json(HERE / "catalog" / "videos.json", {}).items()
              if not k.startswith("_") and isinstance(v, str) and v}
    hid = {"ids": [], "titles_contain": [], **load_json(HERE / "catalog" / "hidden.json", {})}
    items = [{"id": g, **e} for g, e in eps.items()]
    is_hidden = lambda e: e["id"] in hid["ids"] or any(t and t in e.get("t", "") for t in hid["titles_contain"])
    hidden_ids = sorted(e["id"] for e in items if is_hidden(e))
    items = [e for e in items if not is_hidden(e) and e.get("a")]
    for e in items:
        classify(e)
    inherited = inherit_sections(items)
    meta = build(items)
    icons = load_json(HERE / "catalog" / "category_icons.json", {})
    for m in meta:
        v = icons.get(m["name"])
        if isinstance(v, str) and v.strip():
            m["iconLabel"] = v.strip()
        elif isinstance(v, dict):
            if v.get("label"): m["iconLabel"] = v["label"]
            if v.get("image"): m["icon"] = v["image"]

    default_img = arc.get("channel", {}).get("image")
    out = []
    for e in sorted(items, key=lambda e: -ts(e)):
        r = {"id": e["id"], "t": e["t"], "d": e.get("d"), "a": e["a"], "c": e["c"], "s": e["s"], "o": e["o"]}
        if videos.get(e["id"]): r["v"] = videos[e["id"]]
        if e.get("ty") and e["ty"] != "audio/mpeg": r["ty"] = e["ty"]
        if e.get("sec"): r["dur"] = fmt_dur(e["sec"])
        if e.get("img") and e["img"] != default_img: r["img"] = e["img"]
        if e.get("l"): r["l"] = e["l"]
        if e["n"] is not None: r["n"] = e["n"]
        if e["p"] and e["s"]: r["p"] = [level3_label(LEVEL3[e["c"]], n) for n in e["p"]]
        # View PDF: Daf Yomi -> HebrewBooks Vilna Shas pages (masechta number = Shas order)
        if e["c"] == "דף היומי" and e["s"]:
            mas = e["s"][0].replace("מסכת ", "")
            am = gemara_amudim(e["t"])
            if mas in SHAS and am:
                r["pg"] = {"src": "hb-shas", "m": SHAS.index(mas) + 1, "pages": am}
        # View PDF: הבינני בהלכה -> the משנה ברורה pages of that סימן (same maps as Birkas)
        if e["c"] == "הבינני בהלכה" and e["s"] and e["p"]:
            src = MB_SOURCES.get(e["s"][0])
            nums = [n for n in e["p"] if src and str(n) in src["simanim"]]
            if nums:
                spans = [src["simanim"][str(n)] for n in nums]
                lbl = level3_label("סימן", min(nums))
                if len(nums) > 1:
                    lbl += " – " + heb_display(max(nums))
                r["pg"] = {"src": "hb-book", "b": src["book"], "from": min(a for a, _ in spans),
                           "to": max(b for _, b in spans), "lbl": lbl}
        out.append(r)

    doc = {"version": 1, "generated": now, "defaultImage": default_img, "categories": meta,
           "episodes": out, "hidden": hidden_ids}
    prev = load_json(a.out, None)
    if prev and {**prev, "generated": None} == {**doc, "generated": None}:
        say("catalog unchanged")
    else:
        pathlib.Path(a.out).write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        say(f"catalog written: {len(out)} episodes in {len(meta)} categories")

    if a.report:
        guessed = [e for e in items if e.get("guessed")]
        nosec = collections.Counter(e["c"] for e in items if not e["s"] and any(m["name"] == e["c"] and m["sections"] for m in meta))
        rep = log + ["", f"sections inherited from previous shiur: {inherited}",
                     f"category guessed from title (not in any category list yet): {len(guessed)}"]
        rep += [f"  {e['d']}  {e['c']}  <-  {e['t']}" for e in sorted(guessed, key=lambda e: -ts(e))[:40]]
        rep += ["", "categories:"] + [f"  {m['count']:5}  {m['name']}  ({len(m['sections'])} sections)" for m in meta]
        rep += ["", "episodes without a section in a sectioned category:"] + [f"  {n:5}  {c}" for c, n in nosec.items()]
        pathlib.Path(a.report).write_text("\n".join(rep) + "\n", encoding="utf-8")

if __name__ == "__main__":
    main()
