# LTO Radar 🍔

A live board of limited-time offers (LTOs) at US fast-food chains — seasonal donuts,
temporary burgers, collab meals, flash drops — organized as TV-guide-style lanes per chain.

**Live site:** https://fidraj.github.io/lto-radar/

## How it works

- `index.html` — the whole app: a static page that fetches `data.json` at runtime.
  Lanes are color-coded per chain, reorderable by dragging the chain chips, and each
  chain can be toggled on/off (preferences persist in the browser).
- `data.json` — the promo data. Items past their `endDate` are hidden automatically,
  so stale entries never show; they stay in the file as a historical record.
- `images/` — product photos, downsized to 640px JPEGs.
- `fetch_images.py` — downloads and wires product images into `data.json`.
- `REFRESH.md` — the playbook a scheduled Claude Code cloud agent follows daily:
  re-research every chain (official promo pages + news), update `data.json`, fetch
  images for new items, push. GitHub Pages redeploys on push.

## Local development

```
python3 -m http.server 8642
# open http://127.0.0.1:8642
```
