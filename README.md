# Havineini – episode list and website

Data for the **Havineini App** (Rabbi Shimon Spitzer's shiurim).

- `app/catalog.json` – the episode list the app downloads (rebuilt every 15 minutes by `.github/workflows/build.yml`).
- `app/catalog/archive.json` – **our hard copy**: every episode ever seen, with its categories. It only grows; nothing is removed automatically.
- `app/catalog/hidden.json` – take an episode out of the app (it stays in the archive).
- `app/catalog/videos.json` – `{guid: video URL}`; episodes listed here show a video in the app.
- `app/catalog/category_icons.json` – short label drawn on each category icon.
- `app/tools/build_catalog.py` – all category / section / order rules.

Sources: the Libsyn feed (episodes) and [podcast-feeds](https://github.com/rssfeedcategories/podcast-feeds) (categories from the Libsyn portal, read-only).
If either can't be read, the run keeps the archive as it is and only warns.
