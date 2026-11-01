"""Hebrew text, number, date and Gemara-page helpers.
Copied unchanged from the Birkas Shiur builder (rssfeedcategories/shiur-site), where they are tested on real titles."""
import re, datetime, email.utils
# ---------------------------------------------------------------- text utils
GERESH = re.compile("[׳״'\"`‘’“”]")
def norm(s):
    s = re.sub(r"[֑-ׇ]", "", s or "")
    s = GERESH.sub("", s)
    return re.sub(r"\s+", " ", s).strip()

LET = dict(zip("אבגדהוזחטיכךלמםנןסעפףצץקרשת",
               [1,2,3,4,5,6,7,8,9,10,20,20,30,40,40,50,50,60,70,80,80,90,90,100,200,300,400]))
def heb_num(w):
    w = re.sub("[^\u05D0-\u05EA]", "", w or "")
    if not w or len(w) > 5 or any(c not in LET for c in w):
        return None
    return sum(LET[c] for c in w)

ORD = {"ראשון":1,"ראשונה":1,"שני":2,"שניה":2,"שנייה":2,"שלישי":3,"שלישית":3,"רביעי":4,"רביעית":4,
       "חמישי":5,"חמישית":5,"שישי":6,"ששי":6,"שביעי":7,"שמיני":8,"תשיעי":9,"עשירי":10}
HEB_LETTERS = "אבגדהוזחטיכלמנסעפצקרשת"
def heb_word(n):  # 1..499 -> letters (no geresh), used for canonical names
    out = ""
    for v, ch in [(400,"ת"),(300,"ש"),(200,"ר"),(100,"ק"),(90,"צ"),(80,"פ"),(70,"ע"),(60,"ס"),(50,"נ"),
                  (40,"מ"),(30,"ל"),(20,"כ"),(10,"י"),(9,"ט"),(8,"ח"),(7,"ז"),(6,"ו"),(5,"ה"),(4,"ד"),(3,"ג"),(2,"ב"),(1,"א")]:
        while n >= v:
            if n in (15, 16):
                return out + ("טו" if n == 15 else "טז")
            out += ch; n -= v
    return out
def heb_display(n):  # with geresh/gershayim
    w = heb_word(n)
    return w + "'" if len(w) == 1 else w[:-1] + '"' + w[-1]


PARSHA_CAT = 'ד"ת על הפרשה'
PARSHIYOS = ["בראשית","נח","לך לך","וירא","חיי שרה","תולדות","ויצא","וישלח","וישב","מקץ","ויגש","ויחי",
             "שמות","וארא","בא","בשלח","יתרו","משפטים","תרומה","תצוה","כי תשא","ויקהל","פקודי",
             "ויקרא","צו","שמיני","תזריע","מצורע","אחרי מות","קדושים","אמור","בהר","בחקתי",
             "במדבר","נשא","בהעלתך","שלח","קרח","חקת","בלק","פינחס","מטות","מסעי",
             "דברים","ואתחנן","עקב","ראה","שופטים","כי תצא","כי תבא","נצבים","וילך","האזינו","וזאת הברכה"]
PARSHA_ALIAS = {"טהרה": "מצורע", "אחרי": "אחרי מות", "שלח לך": "שלח"}

def _pkey(w):
    """Spelling-insensitive key: drop ו/י except as a word's first letter."""
    out = []
    for tok in norm(w).split(" "):
        out.append(tok[:1] + tok[1:].replace("ו", "").replace("י", ""))
    return " ".join(out)

_PKEYS = {_pkey(p): p for p in PARSHIYOS}
_PKEYS.update({_pkey(a): t for a, t in PARSHA_ALIAS.items()})

def parshiyos_from_title(title):
    t = norm(title)
    if "הפרשה -" in t:
        t = t.split("הפרשה -", 1)[1]
    t = t.strip()
    if t.startswith("פרשת "):
        t = t[5:]
    seg = t.split(" - ")[0]
    toks = [x for x in re.split(r"[\s\-]+", seg) if x]
    found, i = [], 0
    while i < len(toks):
        two = _pkey(" ".join(toks[i:i + 2])) if i + 1 < len(toks) else None
        if two and two in _PKEYS:
            p = _PKEYS[two]; i += 2
        elif _pkey(toks[i]) in _PKEYS:
            p = _PKEYS[_pkey(toks[i])]; i += 1
        else:
            i += 1; continue
        if p not in found:
            found.append(p)
    return found

def strict_num(tok):
    """A real Hebrew numeral (descending letters, one tens, one unit), else None.
    Rejects ordinary words such as חזרה / שבת."""
    w = re.sub("[^\u05D0-\u05EA]", "", tok or "")
    if not w or len(w) > 5:
        return None
    # hundreds + טו/טז (e.g. קט"ו = 115, רט"ז = 216)
    if w.endswith(("טו", "טז")):
        head = w[:-2]
        if all(c in "קרשת" for c in head) and all(
                LET[a] >= LET[b] for a, b in zip(head, head[1:])):
            return sum(LET[c] for c in head) + (15 if w.endswith("טו") else 16)
    vals = []
    for c in w:
        if c not in LET or c in "ךםןףץ":
            return None
        vals.append(LET[c])
    if any(b > a for a, b in zip(vals, vals[1:])):
        return None
    if sum(1 for v in vals if 10 <= v <= 90) > 1 or sum(1 for v in vals if v < 10) > 1:
        return None
    return sum(vals)

AMUD = {"עא", "עב"}

def loose_num(tok):
    """Hebrew letters in any order summed (רח"צ -> 298). Only used right after
    the word סימן, where a typo'd numeral is the only thing that can appear."""
    w = re.sub("[^\u05D0-\u05EA]", "", tok or "")
    if not 1 <= len(w) <= 4 or any(c not in LET or c in "ךםןףץ" for c in w):
        return None
    n = sum(LET[c] for c in w)
    return n if 1 <= n <= 697 else None

def level3_numbers(title, kw):
    """All numbers that follow `kw` in the title, with ranges (X-Y) expanded."""
    # The word עד ("until", no quote marks) must not become ע"ד = 74 once the
    # quote marks are dropped: mark it before norm() removes them.
    raw = re.sub(r"(?<![\u05D0-\u05EA\"'׳״])עד(?![\u05D0-\u05EA\"'׳״])", " UNTIL ", title or "")
    t = norm(raw).replace(".", " ").replace(":", " ").replace(",", " ")
    if kw == "פסוק":  # stay inside the first פרק mentioned
        parts = t.split("פרק")
        t = "פרק".join(parts[:2]) if len(parts) > 2 else t
    t = t.replace("-", " - ")
    toks = t.split()
    nums = set()
    i = 0
    while i < len(toks):
        if toks[i] != kw:
            i += 1; continue
        i += 1
        last, pending_range = None, False
        while i < len(toks):
            tk = toks[i]
            if tk in AMUD and kw == "דף":
                i += 1; continue
            if tk in AMUD:  # סימן ע"א / ע"ב are simanim 71 / 72, not amudim
                tk = "עא" if tk == "עא" else "עב"
            if tk == "UNTIL":
                if last is None:
                    tk = "עד"  # "סימן עד" with nothing before it: siman 74
                else:
                    tk = "-"  # "רמ"ד עד רמ"ו" = a range; "רמ"ד עד סעיף ו'" stops here
            if tk == "-":
                pending_range = last is not None; i += 1; continue
            if tk == kw:  # "סימן X - סימן Y"
                i += 1; continue
            n = strict_num(tk)
            if n is None and kw == "סימן" and last is None:
                n = loose_num(tk)  # letters typed out of order, e.g. רח"צ = רצ"ח (298)
            if n is None:
                break
            if pending_range and last is not None and 0 < n - last <= 40:
                nums.update(range(last, n + 1))
            else:
                nums.add(n)
            last, pending_range = n, False
            i += 1
    return sorted(nums)

# ---------------------------------------------------------------- Mishlei pages

def gemara_amudim(title):
    """Amudim a Gemara shiur covers, e.g. "דף ה' ע"ב - ו' ע"א" -> ["5b","6a"].
    "." / ":" after the daf also mark amud a / b. No amud given -> both."""
    raw = re.sub(r"[\u0591-\u05C7]", "", title or "")
    m = re.search(r"דף\s+(.*)", raw)
    if not m:
        return []
    t = m.group(1)
    t = t.replace("ע\"א", " עא ").replace("ע\"ב", " עב ").replace("ע׳׳א", " עא ").replace("ע׳׳ב", " עב ")
    t = re.sub(r"([\u05D0-\u05EA\"'׳״]+)\.", r"\1 עא ", t)
    t = re.sub(r"([\u05D0-\u05EA\"'׳״]+):", r"\1 עב ", t)
    t = t.replace("-", " - ")
    marks = []  # sequence of (daf, amud|None)
    daf, saw_range = None, False
    toks = t.split()
    for k, tok in enumerate(toks):
        nxt = toks[k + 1] if k + 1 < len(toks) else ""
        # דף ע"א / ע"ב (71/72) look like amud markers: it's a daf when it comes
        # first, or right after "-" and followed by an amud marker.
        is_daf_word = tok in ("עא", "עב") and (daf is None or (saw_range and nxt in ("עא", "עב")))
        if is_daf_word:
            daf = 71 if tok == "עא" else 72
            marks.append((daf, None)); saw_range = False
            continue
        if tok in ("עא", "עב"):
            if daf is not None:
                if marks and marks[-1][0] == daf and marks[-1][1] is None and saw_range:
                    # "דף ע"א - ע"ב": whole daf, amud a to b
                    marks[-1] = (daf, "a"); marks.append((daf, "a" if tok == "עא" else "b")); saw_range = False
                elif marks and marks[-1][0] == daf and marks[-1][1] is None:
                    marks[-1] = (daf, "a" if tok == "עא" else "b")
                else:
                    marks.append((daf, "a" if tok == "עא" else "b"))
            continue
        if tok == "-":
            saw_range = True; continue
        n = strict_num(tok)
        if n is None or n < 2 or n > 200:
            if marks:
                break
            continue
        daf = n
        marks.append((n, None)); saw_range = False
    if not marks:
        return []
    def idx(d, a): return d * 2 + (1 if a == "b" else 0)
    first, last = marks[0], marks[-1]
    start = idx(first[0], first[1] or "a")
    end = idx(last[0], last[1] or ("b" if last[1] is None and len(marks) == 1 else "a"))
    if last[1] is None and len(marks) > 1:
        end = idx(last[0], "b")
    if end < start:
        end = start
    end = min(end, start + 3)  # at most 4 amudim
    return [f"{i // 2}{'b' if i % 2 else 'a'}" for i in range(start, end + 1)]

def level3_label(kw, n):
    return f"{kw} {heb_display(n)}"

# ---------------------------------------------------------------- parsing helpers

def parse_date(s):
    if not s:
        return None
    try:
        return email.utils.parsedate_to_datetime(s).astimezone(datetime.timezone.utc)
    except Exception:
        pass
    try:
        d = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=datetime.timezone.utc)
    except Exception:
        return None

def fmt_dur(sec):
    if not sec:
        return None
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

def dur_secs(v):
    if v is None:
        return None
    v = str(v).strip()
    try:
        if ":" in v:
            t = 0
            for p in v.split(":"):
                t = t * 60 + int(p)
            return t
        return int(v)
    except ValueError:
        return None

