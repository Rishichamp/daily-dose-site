# 📚 Daily Dose of DS — AI Learning Roadmap

**A fully autonomous pipeline that turns a daily newsletter into a living, premium AI-SaaS-style learning platform — zero manual maintenance, forever.**

🔗 **Live site:** [rishichamp.github.io/daily-dose-site](https://rishichamp.github.io/daily-dose-site/)
⏱️ **Runs:** Every day at 7:00 AM IST, unattended, via GitHub Actions
🧠 **Stack:** Python · Gmail API (OAuth2) · Google Gemini · SQLite · GitHub Actions · vanilla HTML/CSS/JS

---

## 👋 For Recruiters / Hiring Managers

This project is a self-contained demonstration of building a **production-style automated data pipeline** end-to-end, solo — from an external API integration, through an LLM-based content transformation layer, to a scheduled CI/CD deployment that requires no human in the loop.

**What it shows:**

| Area | What's demonstrated |
|---|---|
| **API integration** | OAuth2 authentication and pagination against the Gmail API; automatic token refresh handling |
| **Data engineering** | HTML/text extraction, deduplication, noise-stripping (tracking URLs, ads, footers) from unstructured email content |
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

All backend logic (Gmail fetching, AI content generation, database, email cleaning) is **completely unchanged** from previous versions — this release is a frontend/UI redesign only.

---

## 🏗️ Architecture

```
┌─────────────┐   OAuth2    ┌──────────────┐   clean text   ┌─────────────┐
│  Gmail API  │ ──────────► │ Email Cleaner│ ─────────────► │ Gemini API  │
└─────────────┘             │ (regex-based │                │ (prompted   │
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
        │  cron: 30 1 * * * (7:00 AM IST)
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

### 2. Get Gmail credentials
1. [Google Cloud Console](https://console.cloud.google.com/) → new project → enable **Gmail API**
2. OAuth consent screen → External → add your Gmail as a test user
3. Credentials → OAuth client ID → Desktop app → download JSON → rename to `credentials.json`

### 3. Get a free Gemini API key
[aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) → Create API key

### 4. Configure
```bash
cp .env.example .env
# edit .env, paste your GEMINI_API_KEY
```

### 5. First run (processes all historical emails)
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
| `GMAIL_TOKEN` | Full contents of your local `token.json` |

### 9. Trigger the first cloud run
Actions tab → "Daily Dose of DS — Auto Update" → Run workflow → check **first_run** → Run

---

## 🖥️ CLI Commands

```bash
python build_site.py --first-run   # Process ALL historical emails
python build_site.py --daily       # Process only new emails (what CI runs)
python build_site.py --rebuild     # Rebuild HTML from the existing database, no Gmail fetch
python build_site.py --schedule    # Run a local Python scheduler (daily at 07:00)
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

`Python 3.12` · `google-api-python-client` (Gmail OAuth2) · `google-generativeai` (Gemini) · `SQLite3` · `GitHub Actions` · `GitHub Pages` · vanilla `HTML5` / `CSS3` (custom properties, `@view-transition`, canvas, `grid-template-rows` accordions) / `JavaScript` (no frameworks, no build step, `localStorage` for bookmarks/progress)

---

## 📬 Contact

Built by **Rishi Singh** — [GitHub](https://github.com/Rishichamp)
