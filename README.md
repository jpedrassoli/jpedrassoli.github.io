# jpedrassoli.github.io

Personal site. Static HTML — no build step.

## What updates by itself

A GitHub Action (`.github/workflows/update-data.yml`) runs every day and refreshes:

- `data/publications.json` — from OpenAlex using the ORCID 0000-0001-9762-102X (falls back to the ORCID API).
  Keep ORCID up to date (turn on Crossref auto-update in ORCID) and the site follows.
- `data/news.json` — Google News searches for "Julio Pedrassoli" and "Pedrassoli MapBiomas". Items accumulate over time.

If `publications.json` is missing, the page fetches OpenAlex directly in the browser.

## Editing by hand

- `data/news_manual.json` — add press coverage Google misses, or hide wrong matches (`hide`: title or URL).
- `data/publications_manual.json` — add items that aren't indexed, or hide wrong ones.
- Text, projects and links: `index.html`. Colors and layout: `assets/style.css`.
- Profile photo: put a square image at `assets/photo.jpg`.

Saving a `*_manual.json` file triggers the update automatically. To run it now: Actions → "Update publications and news" → Run workflow.

## One-time setup

1. Settings → Actions → General → Workflow permissions → **Read and write permissions**.
2. (Optional) Settings → Secrets and variables → Actions → Variables → `OPENALEX_MAILTO` = your e-mail (faster OpenAlex quota).
3. Actions tab → run the workflow once.

Local preview: `python -m http.server` in this folder, then open http://localhost:8000.
