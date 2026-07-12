# 📚 Daily Dose of DS — Auto Website

Automatically transforms your **Daily Dose of DS** newsletter emails into a beautiful, searchable study website — updated every day at 7 AM.

**Live site:** `https://YOUR_USERNAME.github.io/Daily_Dose_Site/`

---

## ✨ What it does

Every morning:
1. Fetches the new Daily Dose of DS email from Gmail
2. Strips all tracking URLs, ads, footers, and spam
3. Sends clean content to Gemini AI → generates structured study notes
4. Builds a new page with: Overview, Deep Explanation, Code, Key Takeaways, Interview Questions
5. Updates the index and e-book
6. Deploys to GitHub Pages automatically

---

## 🚀 Setup (one time)

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Get Gmail credentials
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create project → Enable **Gmail API**
3. OAuth consent screen → External → add your Gmail as test user
4. Credentials → OAuth client ID → Desktop app → Download JSON
5. Rename to `credentials.json` and place in project root

### 3. Get Gemini API key (free)
- Go to [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)
- Create API key → copy it

### 4. Create .env file
```bash
cp .env.example .env
# Edit .env and add your GEMINI_API_KEY
```

### 5. First run (processes all historical emails)
```bash
python build_site.py --first-run
```
A browser will open → log in with the Gmail that receives Daily Dose emails → Allow.

### 6. Push to GitHub
```bash
git init
git add .
git commit -m "🚀 Initial deployment"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/Daily_Dose_Site.git
git push -u origin main
```

### 7. Enable GitHub Pages
- Go to repo → **Settings → Pages**
- Source: `Deploy from branch` | Branch: `main` | Folder: `/docs`
- Save → your site is live!

### 8. Add GitHub Secrets
Go to **Settings → Secrets → Actions → New repository secret**:

| Secret | Value |
|--------|-------|
| `GEMINI_API_KEY` | Your Gemini API key |
| `GMAIL_TOKEN` | Contents of your `token.json` file |

### 9. Trigger first-run on GitHub
- Actions tab → `Daily Dose of DS — Auto Update` → Run workflow
- Check **"Process ALL historical emails"** → Run

---

## 📁 Structure

```
Daily_Dose_Site/
├── build_site.py          # Main builder
├── requirements.txt
├── .env.example
├── .gitignore
├── .github/
│   └── workflows/
│       └── daily-update.yml
└── docs/                  # Generated website (GitHub Pages)
    ├── index.html          # Issue index
    ├── ebook.html          # Complete e-book (all issues)
    └── entries/
        └── YYYY-MM-DD_issue###_Topic.html
```

---

## 🖥️ Commands

```bash
python build_site.py --first-run   # Process ALL historical emails
python build_site.py --daily       # Process only new emails
python build_site.py --rebuild     # Rebuild site from existing DB (no Gmail)
python build_site.py --schedule    # Run Python scheduler (daily at 07:00)
```

---

## 📖 E-Book

Click **"Download E-Book"** on the homepage to open `ebook.html` — a complete book with:
- Cover page
- Clickable Table of Contents (all issues, date-ordered)
- One chapter per issue with full AI-enhanced content
- Zero tracking URLs, ads, or spam

---

## ✅ Yes — fully automatic!

Once set up, **zero manual work** is needed:
- 5:00 AM — Daily Dose email arrives in Gmail
- 7:00 AM — GitHub Actions automatically fetches, processes, and deploys
- Your site updates itself every single day
