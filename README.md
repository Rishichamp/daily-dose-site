# 📚 Daily Dose of DS — Learning Roadmap

A cinematic, auto-updating roadmap of every Daily Dose of DS newsletter issue — refined by AI into readable chapters, laid out chronologically week by week.

**Live site:** `https://YOUR_USERNAME.github.io/daily-dose-site/`

---

## ✨ What's new in v7

- **🐛 Fixed the critical bug** where old issues disappeared from the site. The database (`site_data.db`) is now committed to git and persists across every automated run — previously it was gitignored, so each day's GitHub Actions run started from an empty database and only showed that day's single new issue.
- **Roadmap landing page** — chronological, oldest → newest, grouped by week with sticky week-header labels as you scroll.
- **Bold page transitions** — clicking a chapter card triggers a cinematic zoom/morph (native Cross-Document View Transitions on Chromium, JS zoom fallback elsewhere).
- **Scrollytelling** — sections fade, scale, and blur into view as you scroll through a chapter.
- **Ambient background motion** — slow-morphing gradient blobs, drifting dust particles, and mouse-parallax depth on every page.
- **Ask-bar** on the roadmap — search chapters live, or click "Ask AI" to query your AI tutor about any issue.
- **Floating AI Tutor** on chapter and e-book pages — ask "Explain issue #7" and get an answer sourced from your full history.
- **Editorial typography** — serif display headings (Fraunces) + clean sans body (Inter).
- **Premium micro-animations** — rotating 3D gem logo with light sweep, animated sun/moon toggle switch, hand-drawn line-draw divider, organic blob-morphing background, subtle 3D card tilt on hover.
- **Website-only** — no local PDF folder, no separate downloadable PDF/EPUB files. The "E-Book" is a single in-browser page with the complete history, chapter by chapter.

---

## 🚀 Setup (one time)

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Get Gmail credentials
1. [Google Cloud Console](https://console.cloud.google.com/) → new project → enable **Gmail API**
2. OAuth consent screen → External → add your Gmail as test user
3. Credentials → OAuth client ID → Desktop app → Download JSON → rename to `credentials.json`

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
A browser opens → log in with the Gmail that receives Daily Dose emails → Allow.

### 6. Push to GitHub
```bash
git init
git add .
git commit -m "🚀 v7 — roadmap redesign"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/daily-dose-site.git
git push -u origin main --force   # use --force only if replacing an old repo
```

### 7. Enable GitHub Pages
Repo → **Settings → Pages** → Source: `Deploy from branch` → Branch: `main` → Folder: `/docs` → Save

### 8. Add GitHub Secrets
**Settings → Secrets → Actions → New repository secret**

| Secret | Value |
|---|---|
| `GEMINI_API_KEY` | Your Gemini API key |
| `GMAIL_TOKEN` | Full contents of your `token.json` |

### 9. Trigger first-run on GitHub
Actions tab → "Daily Dose of DS — Auto Update" → Run workflow → check "first_run" → Run

---

## 🖥️ Commands

```bash
python build_site.py --first-run   # Process ALL historical emails
python build_site.py --daily       # Process only new emails (used by the daily automation)
python build_site.py --rebuild     # Rebuild HTML from the existing database, no Gmail fetch
python build_site.py --schedule    # Run a local Python scheduler (daily at 07:00)
```

---

## ✅ Fully automatic, forever

Once secrets are set, **zero manual work is needed**:
- 5:00 AM — Daily Dose email arrives in Gmail
- 7:00 AM — GitHub Actions fetches it, cleans it, generates AI notes, builds the new chapter, updates the roadmap, and deploys
- The database commit fix means **every issue ever processed stays visible, forever** — nothing disappears on subsequent runs

---

## 📁 Structure

```
daily-dose-site/
├── build_site.py
├── site_data.db            # committed — source of truth for the roadmap history
├── requirements.txt
├── .env.example
├── .gitignore
├── .github/workflows/daily-update.yml
└── docs/                   # generated website (GitHub Pages root)
    ├── index.html           # the roadmap
    ├── ebook.html           # complete e-book, all chapters
    └── entries/
        └── YYYY-MM-DD_issue###_Topic.html
```
