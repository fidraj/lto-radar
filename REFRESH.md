# Daily data refresh playbook

You are refreshing **LTO Radar**, a tracker of limited-time offers (LTOs) at US fast-food
chains. This repo is a static site served by GitHub Pages: `index.html` renders `data.json`
at runtime. Your job is to bring `data.json` and `images/` up to date, then commit and push
to `main`. Do NOT redesign or edit `index.html` unless it is broken.

## Chains to cover (all of them, every run)

McDonald's, Burger King, Wendy's, Taco Bell, Starbucks, KFC, Chick-fil-A, Dunkin', Krispy Kreme,
Sonic, Arby's, Jack in the Box, Dairy Queen, Popeyes, Wingstop, Raising Cane's, Zaxby's,
Chipotle, Pizza Hut, Domino's, Subway.

## Research rules — completeness is the top priority

A promo was once missed because research relied on news search alone. Never repeat that.
For EVERY chain do BOTH:

1. **Fetch the chain's official promo/newsroom index** and enumerate everything listed:
   - https://www.krispykreme.com/promos
   - https://news.dunkindonuts.com/news
   - https://corporate.mcdonalds.com/corpmcd/our-stories.html
   - https://news.bk.com/blog-posts
   - https://www.wendys.com/blog and https://www.wendys.com/offers
   - https://www.tacobell.com/news
   - https://about.starbucks.com/press/
   - https://global.kfc.com/press-releases/ and KFC US news coverage
   - https://www.chick-fil-a.com/press-room
   - https://www.sonicdrivein.com/menu (plus Sonic news coverage)
   - https://arbys.com/menu (plus Arby's news coverage)
   - https://www.jackinthebox.com/food (plus press coverage)
   - https://www.dairyqueen.com/en-us/blizzard-of-the-month/ and DQ news
   - https://www.popeyes.com/menu (plus press coverage)
   - https://www.wingstop.com/menu and Wingstop news
   - https://www.raisingcanes.com/news
   - https://www.zaxbys.com/news
   - https://newsroom.chipotle.com/
   - https://blog.pizzahut.com/ and Pizza Hut press coverage
   - https://ir.dominos.com/news-releases and Domino's menu news
   - https://newsroom.subway.com/
2. **Web-search** for "<chain> new menu item <current month/year>", "<chain> limited time offer",
   and food-news roundups (brandeating.com, chewboom.com, fastfoodpost.com).

## Updating data.json

Schema per item:
```json
{
  "chain": "...", "item": "...", "description": "...",
  "category": "burger|sandwich|taco|drink|dessert|donut|chicken|food|event",
  "startDate": "YYYY-MM-DD or null",
  "endDate": "YYYY-MM-DD or 'while supplies last' or null",
  "status": "active|upcoming|ending-soon",
  "source": "url",
  "image": "filename-in-images-dir.jpg or null"
}
```

- **Add** newly found offers (including short flash drops and rewards/value deals).
- **Update** existing items whose dates/status changed; fix dates when chains announce exact windows.
- **Keep** ended items in the file (the app hides anything past its endDate automatically);
  they are the historical record. Set their real endDate.
- **Never delete** an item unless it was factually wrong.
- Mark rumored/leaked items clearly in the item name or description ("leaked, unconfirmed").
- Convert vague dates to concrete best-estimate `YYYY-MM-DD`; prefer official dates when known.
- Set the top-level `"researched"` field to today's date (YYYY-MM-DD).

### Dates: the board is only as good as these

Only CURRENT promotions belong on the board. Before adding anything, check the
announcement is for this season - not a look-alike promo the chain ran last year.

- Every item needs a `startDate`. Use the announced launch date; estimate from the
  article date if you must, but do not leave it null.
- **Take the year from the article itself, never from today's date.** A Burger King
  SpongeBob menu was once filed as starting Dec 2026 because the run assumed the
  current year; the press release was from Dec 2025 and the promo was long over.
  Check the publication date of every source before writing a date.
- Sanity-check anything starting more than ~90 days out. Chains announce LTOs weeks
  ahead, not a year ahead, so a far-future date usually means a misread year. CI
  prints a warning for these on every push.
- Prefer a real `endDate`. Use `"while supplies last"` or null only when the chain
  genuinely announced no end.
- **Re-verify open-ended items every run.** For every item with no hard `endDate`
  that started more than 45 days ago, check whether it is still running:
  - if it has ended, set its real `endDate` (best estimate if unannounced);
  - if it is confirmed still running, set `"lastConfirmed": "<today>"`;
  - if it turned into a permanent menu item, set an `endDate` on the day it went
    permanent - the board tracks limited-time offers, not the standing menu.
- The site hides an open-ended item 90 days after its `startDate` (or its
  `lastConfirmed`, when newer). So an unconfirmed promo ages off the board by
  itself - but a still-running one silently disappears unless you confirm it.

## Images — not your job

CI handles images. A GitHub Action scans each item's `source` article after every
push, picks the product photo, resizes it into `images/` and commits it back.

- Do NOT run `fetch_images.py` and do NOT try to download images.
- Leave `"image": null` on new items. Do not touch `image` on existing items.
- `imageSkip: true` means a human rejected the auto-picked photo — leave it alone.
- Optional: if you happen to have a direct URL to an official product photo, put it
  in `"imageUrl"` and CI will prefer it over its own pick. Never guess one.

What matters far more is a good `source` URL: CI can only find a photo if the
source article actually shows the product. A press release or a food-news article
beats a chain's generic menu page.

## Validate before pushing

```
python3 -c "import json; d=json.load(open('data.json')); assert d['items'], 'empty'; print(len(d['items']), 'items OK')"
```

Also sanity-check: every item has chain/item/description/status; every new item either has
an `imageUrl` or intentionally has none.

## Commit and push

```
git add data.json
git commit -m "data refresh <YYYY-MM-DD>"
git push origin main
```

GitHub Pages redeploys automatically, and the fetch-images Action fills in images in a
follow-up commit. Done.
