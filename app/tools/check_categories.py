"""Daily category check (Izzy, Nov 2026): find shiurim that need a person's look
and ask Izzy through a GitHub issue. No AI involved.

Looks at shiurim published in the last 30 days that have been in the feed for
at least 6 hours (so podcast-feeds had time to file them), and reports:
  1. In the main feed but in none of the category lists (podcast-feeds).
  2. The title points to a category (TITLE_RULES in build_catalog.py) that the
     shiur is not in, e.g. "ספר חפץ חיים שיעור #139" filed only under Daily Shiur.
  3. The title contains a watch word (catalog/watch_words.json, e.g. תהלים),
     for topics that may need a new category.
Shiurim filed only under Daily Shiur/GENERAL/הודעות whose title starts with a
series name are moved by build_catalog.py on its own (we can't change Libsyn);
those are listed as "moved automatically, nothing to do". Shiurim in
catalog/category_fixes.json (moved by hand) are skipped.
Each shiur is reported once (catalog/alerts_sent.json remembers them).

Writes the issue text to --out (nothing written = nothing new to report).
"""
import argparse, datetime, json, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import build_catalog as bc
from hebrew_text import norm

HERE = pathlib.Path(__file__).resolve().parent.parent
SENT = HERE / "catalog" / "alerts_sent.json"
WATCH = HERE / "catalog" / "watch_words.json"
DAYS = 30
GRACE = datetime.timedelta(hours=6)


def load(p, default):
    try:
        return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    now = datetime.datetime.now(datetime.timezone.utc)
    eps = bc.load_archive()["episodes"]
    sent = load(SENT, {"_about": "Shiurim already reported by check_categories.py (id -> reason).", "ids": {}})
    words = [w for w in load(WATCH, {}).get("words", []) if w.strip()]
    fixes = load(HERE / "catalog" / "category_fixes.json", {}).get("ids", {})

    found = []  # (reason, episode, text)
    for g, e in eps.items():
        if not e.get("a") or g in sent["ids"] or g in fixes:
            continue
        d = bc.parse_date(e.get("d"))
        seen = bc.parse_date(e.get("first_seen")) or d
        if not d or (now - d).days > DAYS or (seen and now - seen < GRACE):
            continue
        cats = e.get("cats") or []
        t = norm(e.get("t", ""))
        guess = next((c for p, c in bc.TITLE_RULES if norm(p) in t), None)
        if not cats:
            found.append(("no-category", g, e, "in the main feed but in **no category** on Libsyn"
                          + (f" – the title suggests **{guess}**" if guess else "")))
        elif all(c in bc.WEAK for c in cats) and bc.series_of(e.get("t", "")):
            found.append(("moved", g, e, f"Libsyn has it under **{', '.join(cats)}** – moved automatically to "
                          f"**{bc.series_of(e.get('t', ''))}** (nothing to do)"))
        elif guess and guess not in cats:
            found.append(("other-category", g, e, f"filed under **{', '.join(cats)}**, but the title suggests **{guess}**"))
        else:
            hit = next((w for w in words if norm(w) in t), None)
            if hit:
                found.append(("watch-word", g, e, f"title mentions **{hit}** (filed under {', '.join(cats)}) – new category?"))

    if not found:
        print("nothing new to report")
        return
    ask = any(r != "moved" for r, *_ in found)
    lines = ["Hi Izzy – the daily check found shiurim that may need a different category:" if ask
             else "Hi Izzy – FYI, these shiurim were moved to their series automatically:", ""]
    for reason, g, e, text in sorted(found, key=lambda x: x[2].get("d", ""), reverse=True):
        lines.append(f"- {e.get('d', '')[:10]} · **{e.get('t', '').strip()}**  \n  {text}")
    lines += ["",
              ("**What to do:** tell Claude where each one should go (or to leave it). Claude moves it in our own "
               "list (app/catalog/category_fixes.json); the app and website follow within about 15 minutes. "
               "For a new series, Claude can add a new category."
               if ask else "**Nothing to do.** If one of them is wrong, tell Claude and it will be moved back."),
              "",
              "_Each shiur is reported only once. Watch words: app/catalog/watch_words.json._"]
    pathlib.Path(a.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    for reason, g, e, _ in found:
        sent["ids"][g] = reason
    SENT.write_text(json.dumps(sent, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{len(found)} shiurim to report")


if __name__ == "__main__":
    main()
