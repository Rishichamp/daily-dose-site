# 📚 Daily Dose of DS — AI Learning Roadmap

**A fully autonomous pipeline that turns a daily newsletter into a living, premium AI-SaaS-style learning platform — zero manual maintenance, forever.**

🔗 **Live site:** [rishichamp.github.io/daily-dose-site](https://rishichamp.github.io/daily-dose-site/)
☁️ **Also on Render:** `render.yaml` publishes `docs/` as a static site that redeploys on every commit
⏱️ **Runs:** Twice a day (≈7:00 AM and 7:15 PM IST), unattended, via GitHub Actions
🧠 **Stack:** Python · Substack archive API / RSS · Google Gemini · SQLite · GitHub Actions · vanilla HTML/CSS/JS

---

## 👋 For Recruiters / Hiring Managers

This project is a self-contained demonstration of building a **production-style automated data pipeline** end-to-end, solo — from an external API integration, through an LLM-based content transformation layer, to a scheduled CI/CD deployment that requires no human in the loop.

**What it shows:**

| Area | What's demonstrated |
|---|---|
| **API integration** | Paginated reads of the newsletter's public Substack archive API with an RSS fallback (no credentials to expire); optional Gmail API source with OAuth2 |
| **Data engineering** | HTML/text extraction, cross-source deduplication (id + fuzzy title/date match), noise-stripping (tracking URLs, ads, footers) from unstructured newsletter content |
| **LLM integration** | Structured prompt design against Gemini, JSON/text parsing of model output, exponential-backoff retry logic that reads the provider's own rate-limit hints, and a graceful non-AI fallback so the pipeline never hard-fails |
| **Data persistence** | SQLite as a durable, git-committed source of truth — designed specifically so a stateless CI runner (GitHub Actions) can pick up exactly where the last run left off |
| **CI/CD** | A GitHub Actions workflow that runs unattended on a cron schedule, installs dependencies, authenticates, generates content, and commits/deploys — with a manual `workflow_dispatch` escape hatch for full reprocessing |
| **Frontend engineering** | A hand-built (no framework) premium SaaS-style landing page: CSS-only animation systems, scroll-linked reveal, an accordion/LMS-style navigation, native Cross-Document View Transitions with a JS fallback, client-side bookmarking/progress-tracking via localStorage, and ambient canvas-based background motion |
| **Debugging & root-causing** | Diagnosed and fixed a subtle production bug where a `.gitignore`'d database silently reset state on every CI run |

---

## ✨ Features (v8 — Premium Landing Page)

- **Premium AI-SaaS visual design** — dark theme, glassmorphism, gradient blobs, inspired by Linear/Vercel/OpenAI-style product sites (colors: `#050816` background, `#5B8CFF`/`#7C5CFF` accent gradient)
- **Full landing page structure** — hero with animated AI dashboard mock, feature grid, "How It Works" scroll-animated timeline, AI search hero section, roadmap preview, latest-chapters strip, testimonials, final CTA, structured footer
- **Roadmap accordion** — chronological, week-grouped, click any "Week of..." header to expand its chapters LMS-style, with a smooth grid-based slide animation and chapter count badge
- **Category filter chips** — instantly filter the roadmap by topic (Machine Learning, LLMs, Deep Learning, etc.)
- **Client-side bookmarks & progress** — star any chapter to bookmark it, and chapters you scroll to the end of are automatically marked complete — both stored in `localStorage`, no backend or account needed
- **Bold page transitions** — native browser View Transitions morph a clicked card into its full chapter page; older browsers get a JS zoom fallback
- **In-browser AI Tutor** — ask "explain issue #7" and get an answer generated from the full accumulated history
- **Complete e-book view** — every chapter compiled into one scrollable document with a table of contents

### v8.1 — reliability

- **No more expiring login.** New issues are read from the newsletter's public archive ([blog.dailydoseofds.com](https://blog.dailydoseofds.com)) instead of Gmail. The Gmail OAuth token expired every 7 days (the Google app was in *Testing* mode), which silently stopped the site from 2 Sep 2026. Gmail is still available with `--source gmail` / `auto`.
- **Self-healing daily runs.** Each run re-checks the last 10 days, so a post that failed once is retried; duplicates are recognised across sources by title + date.
- **Model fallback.** If the configured Gemini model is retired, the run switches to the `gemini-flash-lite-latest` alias instead of dropping to non-AI summaries.
- **Loud failures only when it matters.** The run fails (and opens a GitHub issue) if no new issue has arrived for 14 days — the sign that the source moved.
- **Schedule keep-alive.** The workflow re-enables itself each run, so GitHub's 60-day inactivity rule can't switch the schedule off.
- **Fixes:** TL;DR boxes were always empty (parser bug); categories used substring matching ("clearly" counted as "RL"); chapter titles had punctuation stripped ("8.5x" showed as "85x"). `--repair` fixes existing chapters.

---

## 🏗️ Architecture

```
┌─────────────┐  HTTPS/RSS  ┌──────────────┐   clean text   ┌─────────────┐
│ Substack    │ ──────────► │ Text Cleaner │ ─────────────► │ Gemini API  │
│ archive API │             │ (regex-based │                │ (prompted   │
                             │  noise strip)│                │  rewrite)   │
                             └──────────────┘                └──────┬──────┘
                                                                     │ structured note
                                                                     ▼
┌─────────────┐  git commit  ┌──────────────┐   generates    ┌─────────────┐
│GitHub Pages │ ◄─────────── │ site_data.db │ ◄───────────── │ HTML Builder│
│  (live site)│              │  (SQLite,    │                │ (landing +  │
└─────────────┘              │  committed)  │                │  roadmap +  │
                              └──────────────┘                │  chapters + │
                                                               │  e-book)    │
                                                               └─────────────┘
        ▲
        │  cron: 23 1 * * * and 47 13 * * * (UTC)
┌───────┴────────┐
│ GitHub Actions │
└────────────────┘
```

---

## 🚀 Setup (run it yourself)

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. (Optional) Gmail credentials

Not needed — the default source is the public newsletter archive. Only for `--source gmail`:

1. [Google Cloud Console](https://console.cloud.google.com/) → new project → enable **Gmail API**
2. OAuth consent screen → External → **publish the app to Production** (in *Testing* mode the refresh token expires after 7 days)
3. Credentials → OAuth client ID → Desktop app → download JSON → rename to `credentials.json`

### 3. Get a free Gemini API key

[aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) → Create API key

### 4. Configure

```bash
cp .env.example .env
# edit .env, paste your GEMINI_API_KEY
```

### 5. First run (processes the whole newsletter history)

```bash
python build_site.py --first-run
```

### 6. Push to GitHub

```bash
git init
git add .
git commit -m "🚀 v8 — premium landing page redesign"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/daily-dose-site.git
git push -u origin main
```

### 7. Enable GitHub Pages

Repo → **Settings → Pages** → Source: `Deploy from branch` → Branch: `main` → Folder: `/docs` → Save

### 8. Add GitHub Secrets

**Settings → Secrets and variables → Actions → New repository secret**

| Secret | Value |
|---|---|
| `GEMINI_API_KEY` | Your Gemini API key |
| `GMAIL_TOKEN` | *(optional, Gmail source only)* full contents of your local `token.json` |

### 9. Trigger the first cloud run

Actions tab → "Daily Dose of DS — Auto Update" → Run workflow → Run (tick **first_run** only for a brand-new site)

---

## 🖥️ CLI Commands

```bash
python build_site.py --daily       # Process only new issues (what CI runs)
python build_site.py --first-run   # Process the whole newsletter history
python build_site.py --rebuild     # Rebuild HTML from the existing database, no fetching
python build_site.py --renumber    # Renumber issues by date and regenerate every page
python build_site.py --repair      # Restore titles, recompute categories, then --renumber
python build_site.py --schedule    # Run a local Python scheduler (daily at 07:00)

# Source: --source feed (default, no login) | gmail | auto (Gmail, falling back to the feed)
# Infographics need Linux fonts (DejaVu) — run --renumber/--repair from the Actions tab, not on Windows.
```

---

## 📁 Project Structure

```
daily-dose-site/
├── build_site.py               # entire pipeline: fetch → clean → AI → HTML → deploy
├── site_data.db                 # committed SQLite — source of truth for the roadmap history
├── requirements.txt
├── .env.example
├── .gitignore
├── .github/workflows/daily-update.yml
└── docs/                        # generated site (GitHub Pages root)
    ├── index.html                # the premium landing page + roadmap
    ├── ebook.html                 # complete e-book, all chapters
    └── entries/
        └── YYYY-MM-DD_issue###_Topic.html
```

---

## 🛠️ Tech Stack

`Python 3.12` · Substack archive API / RSS (stdlib `urllib`) · `google-genai` (Gemini) · optional `google-api-python-client` (Gmail OAuth2) · `SQLite3` · `GitHub Actions` · `GitHub Pages` · vanilla `HTML5` / `CSS3` (custom properties, `@view-transition`, canvas, `grid-template-rows` accordions) / `JavaScript` (no frameworks, no build step, `localStorage` for bookmarks/progress)

---

## 📬 Contact

Built by **Rishi Singh** — [GitHub](https://github.com/Rishichamp)
