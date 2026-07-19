#!/usr/bin/env python3
"""
Daily Dose of DS — Website Generator v7.0
============================================
COMPLETE REDESIGN — cinematic roadmap experience.

Fixes from v6:
  - CRITICAL: site_data.db is now committed to git (was gitignored before,
    which meant GitHub Actions started with an EMPTY database every run and
    the roadmap only ever showed that day's single new issue). Now the full
    history persists forever across every automated run.

New in v7 (redesign requested):
  - Landing page is now a chronological ROADMAP, oldest -> newest top to
    bottom, grouped by week with sticky week-header labels while scrolling.
  - Clicking a card triggers a bold full-screen zoom/morph transition into
    the chapter page (native Cross-Document View Transitions API on
    Chromium, JS zoom fallback on other browsers).
  - Scrollytelling: sections fade/scale/blur into view as you scroll.
  - Ambient background motion: slow aurora gradients + drifting dust
    particles + subtle mouse-parallax, present on every page.
  - Ask-bar at the top of the roadmap (search + "Ask AI" in one control).
  - Floating AI Tutor button restored on chapter + e-book pages.
  - Editorial typography: serif display headings, clean sans body.
  - Website-only: no local PDF folder, no separate PDF/EPUB download files.
    "E-Book" is a single in-browser page with full history, chapter by
    chapter, built from the same AI-enhanced content as the roadmap.
"""

import os, sys, re, json, base64, sqlite3, hashlib, argparse, subprocess, time
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, field

# ── Config ──────────────────────────────────────────────────────────────────
SENDER      = "Daily Dose of DS"
SITE_TITLE  = "Daily Dose of DS"
AI_MODEL    = "gemini-1.5-flash-8b"
MAX_TOKENS  = 4000
DB_FILE     = "site_data.db"
TOKEN_FILE  = "token.json"
CREDS_FILE  = "credentials.json"
OUT_DIR     = "docs"
IS_CI       = bool(os.getenv("GITHUB_ACTIONS"))

from dotenv import load_dotenv
load_dotenv()
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")
OPENAI_KEY = os.getenv("OPENAI_API_KEY", "")

import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("DDS")


# ── Data ─────────────────────────────────────────────────────────────────────

@dataclass
class RawEmail:
    email_id:     str
    subject:      str
    date:         datetime
    body_text:    str
    body_html:    str
    topic:        str
    content_hash: str

@dataclass
class StudyNote:
    issue_number: int
    date:         str
    topic:        str
    category:     str
    tldr:         str = ""
    overview:     str = ""
    sections:     list = field(default_factory=list)
    key_points:   list = field(default_factory=list)
    interview_qs: list = field(default_factory=list)
    further:      list = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(self.__dict__)

    @classmethod
    def from_json(cls, s: str) -> "StudyNote":
        return cls(**json.loads(s))


# ── Category colours ─────────────────────────────────────────────────────────

CAT_KW = {
    "Reinforcement Learning": ["rl","reinforcement","reward","policy","q-learn","dqn","ppo","grpo","rlhf","actor-critic"],
    "LLMs & Agents":          ["llm","gpt","gemini","claude","agent","mcp","langchain","prompt","rag","agentic","hermes","openrouter","routing","shepherd"],
    "Deep Learning":          ["neural","cnn","rnn","lstm","transformer","bert","attention","backprop","dropout","layer"],
    "Machine Learning":       ["regression","classification","clustering","svm","random forest","xgboost","sklearn","ensemble","feature"],
    "Data Engineering":       ["pipeline","etl","spark","kafka","airflow","warehouse","dbt","streaming","ingestion"],
    "Statistics":             ["probability","distribution","hypothesis","bayes","p-value","variance","inference"],
    "NLP":                    ["nlp","text","language","token","embedding","sentiment","word2vec","tfidf"],
    "Python":                 ["pandas","numpy","decorator","generator","asyncio","dataframe","comprehension"],
    "SQL":                    ["sql","query","join","aggregate","window function","cte","postgresql"],
    "Mathematics":            ["matrix","vector","eigenvalue","calculus","derivative","linear algebra","optimization"],
}
CAT_COLOR = {
    "Reinforcement Learning": ("#5B8CFF","#22d3ee"),
    "LLMs & Agents":          ("#7C5CFF","#5B8CFF"),
    "Deep Learning":          ("#5B8CFF","#7C5CFF"),
    "Machine Learning":       ("#22d3ee","#5B8CFF"),
    "Data Engineering":       ("#7C5CFF","#a78bfa"),
    "Statistics":             ("#22d3ee","#5B8CFF"),
    "NLP":                    ("#5B8CFF","#22d3ee"),
    "Python":                 ("#22d3ee","#7C5CFF"),
    "SQL":                    ("#5B8CFF","#22d3ee"),
    "Mathematics":            ("#7C5CFF","#22d3ee"),
    "Data Science":           ("#5B8CFF","#7C5CFF"),
}

def detect_category(text: str) -> str:
    low = text.lower()
    for cat, kws in CAT_KW.items():
        if any(k in low for k in kws):
            return cat
    return "Data Science"

def cat_color(cat: str):
    return CAT_COLOR.get(cat, CAT_COLOR["Data Science"])

CAT_DIFFICULTY = {
    "Python": "Beginner", "SQL": "Beginner", "Statistics": "Beginner",
    "Machine Learning": "Intermediate", "Data Engineering": "Intermediate",
    "NLP": "Intermediate", "Mathematics": "Intermediate",
    "Deep Learning": "Advanced", "Reinforcement Learning": "Advanced",
    "LLMs & Agents": "Advanced", "Data Science": "Intermediate",
}

def cat_difficulty(cat: str) -> str:
    return CAT_DIFFICULTY.get(cat, "Intermediate")

def estimate_minutes(note) -> int:
    """Rough reading-time estimate from note content length (~200 wpm)."""
    text = (note.tldr or "") + " " + (note.overview or "") + " " + " ".join(s.get("body","") for s in note.sections)
    words = len(text.split())
    return max(2, round(words / 200))


# ── Database ──────────────────────────────────────────────────────────────────

class DB:
    def __init__(self, path: str = DB_FILE):
        self.conn = sqlite3.connect(path)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS issues (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                email_id      TEXT UNIQUE,
                subject       TEXT,
                date          TEXT,
                topic         TEXT,
                category      TEXT,
                content_hash  TEXT,
                html_file     TEXT,
                note_json     TEXT,
                issue_number  INTEGER,
                processed     INTEGER DEFAULT 0
            )""")
        self.conn.commit()
        self._migrate()

    def _migrate(self):
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(issues)")}
        for col, ddl in [("note_json","TEXT"),("category","TEXT"),("issue_number","INTEGER")]:
            if col not in cols:
                self.conn.execute(f"ALTER TABLE issues ADD COLUMN {col} {ddl}")
        self.conn.commit()

    def exists(self, email_id: str) -> bool:
        return bool(self.conn.execute(
            "SELECT 1 FROM issues WHERE email_id=? AND processed=1", (email_id,)).fetchone())

    def dup_hash(self, h: str) -> bool:
        return bool(self.conn.execute("SELECT 1 FROM issues WHERE content_hash=?", (h,)).fetchone())

    def next_issue(self) -> int:
        r = self.conn.execute("SELECT MAX(issue_number) FROM issues").fetchone()
        return (r[0] or 0) + 1

    def save(self, email_id, subject, date_str, topic, category, content_hash, html_file, note: StudyNote):
        self.conn.execute("""
            INSERT OR REPLACE INTO issues
            (email_id,subject,date,topic,category,content_hash,html_file,note_json,issue_number,processed)
            VALUES (?,?,?,?,?,?,?,?,?,1)""",
            (email_id, subject, date_str, topic, category, content_hash,
             html_file, note.to_json(), note.issue_number))
        self.conn.commit()

    def all_issues_asc(self):
        """Ascending by date — oldest first, for the roadmap top-to-bottom flow."""
        return self.conn.execute(
            "SELECT date,topic,html_file,subject,category,issue_number FROM issues "
            "WHERE processed=1 ORDER BY date ASC").fetchall()

    def all_for_ebook(self):
        rows = self.conn.execute(
            "SELECT issue_number,date,topic,note_json FROM issues "
            "WHERE processed=1 AND note_json IS NOT NULL ORDER BY date ASC").fetchall()
        result = []
        for num, date, topic, nj in rows:
            try:
                result.append((num, date, topic, StudyNote.from_json(nj)))
            except Exception:
                pass
        return result

    def tutor_context(self) -> str:
        rows = self.conn.execute(
            "SELECT issue_number,date,topic,category,note_json FROM issues "
            "WHERE processed=1 ORDER BY issue_number ASC").fetchall()
        lines = ["=== DAILY DOSE OF DS — COMPLETE ISSUE INDEX ===\n"]
        for num, date, topic, cat, nj in rows:
            lines.append(f"Issue #{num} | {date[:10]} | {topic} | [{cat}]")
            if nj:
                try:
                    note = StudyNote.from_json(nj)
                    if note.tldr:
                        lines.append(f"  Summary: {note.tldr[:250]}")
                    if note.key_points:
                        lines.append(f"  Key points: {' | '.join(note.key_points[:3])}")
                except Exception:
                    pass
            lines.append("")
        return "\n".join(lines)

    @staticmethod
    def md5(text: str) -> str:
        return hashlib.md5(text.encode()).hexdigest()


# ── Gmail fetcher ─────────────────────────────────────────────────────────────

class Gmail:
    def __init__(self):
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
        creds = None
        if os.path.exists(TOKEN_FILE):
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(CREDS_FILE):
                    raise FileNotFoundError(f"{CREDS_FILE} not found. See README.")
                flow = InstalledAppFlow.from_client_secrets_file(CREDS_FILE, SCOPES)
                creds = flow.run_local_server(port=0)
            Path(TOKEN_FILE).write_text(creds.to_json())
        self.svc = build("gmail", "v1", credentials=creds)

    def fetch_all(self, after: datetime = None) -> list:
        q = f"from:{SENDER}"
        if after:
            q += f" after:{after.strftime('%Y/%m/%d')}"
        msgs, token = [], None
        while True:
            kw = dict(userId="me", q=q, maxResults=500)
            if token: kw["pageToken"] = token
            r = self.svc.users().messages().list(**kw).execute()
            msgs += r.get("messages", [])
            token = r.get("nextPageToken")
            if not token: break
        return msgs

    def get_email(self, msg_id: str) -> RawEmail:
        msg = self.svc.users().messages().get(userId="me", id=msg_id, format="full").execute()
        hdrs = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
        subject = hdrs.get("Subject", "No Subject")
        date_str = hdrs.get("Date", "")
        try:
            date = datetime.strptime(date_str[:31], "%a, %d %b %Y %H:%M:%S %z")
        except Exception:
            date = datetime.now()
        plain, html = self._extract_parts(msg["payload"])
        clean_text = self._clean(plain or self._html2text(html))
        topic = self._make_topic(subject, clean_text)
        return RawEmail(
            email_id=msg_id, subject=subject, date=date,
            body_text=clean_text, body_html=html,
            topic=topic, content_hash=DB.md5(clean_text)
        )

    def _extract_parts(self, payload, depth=0):
        plain = html = ""
        if "body" in payload and "data" in payload["body"]:
            data = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="ignore")
            if payload.get("mimeType") == "text/html":
                html = data
            else:
                plain = data
        for part in payload.get("parts", []):
            p2, h2 = self._extract_parts(part, depth + 1)
            plain = plain or p2
            html = html or h2
        return plain, html

    def _html2text(self, html: str) -> str:
        try:
            from html.parser import HTMLParser
            class H2T(HTMLParser):
                def __init__(self):
                    super().__init__(); self.result = []
                def handle_data(self, d): self.result.append(d)
                def get_text(self): return "".join(self.result)
            p = H2T(); p.feed(html)
            return p.get_text()
        except Exception:
            return re.sub(r"<[^>]+>", " ", html)

    def _clean(self, text: str) -> str:
        text = re.sub(r'\(\s*https?://[^\s)]*(?:click\.kit|fff97757|tracking|aHR0c)[^\s)]*\s*\)', "", text)
        text = re.sub(r'https?://[^\s)>]*aHR0c[^\s)>]*', "", text)
        text = re.sub(r'\(\s*https?://\S{80,}\s*\)', "", text)
        text = re.sub(r'\(\s*https?://\S{5,60}\s*\)', "", text)

        SECTION_STOP = [
            "unsubscribe", "you are receiving this", "advertise to 950",
            "our newsletter puts your products", "partner with us",
            "today's email was brought to you", "looking for more? unlock",
            "no-fluff resources to", "get in touch today by replying",
            "succeed in ai engineering roles", "that's a wrap",
        ]
        LINE_DROP = [
            "master full-stack ai engineering", "unlock our premium",
            "© 20", "all rights reserved", "today.s email was brought",
        ]
        out, skip = [], False
        for line in text.split("\n"):
            low = line.lower().strip()
            if any(k in low for k in SECTION_STOP):
                skip = True; continue
            if skip and re.match(r'^[-=]{5,}$', low):
                skip = False; continue
            if skip:
                continue
            if any(k in low for k in LINE_DROP):
                continue
            out.append(line)
        text = "\n".join(out)

        text = re.sub(r'^[-=]{10,}\s*$', "", text, flags=re.MULTILINE)
        paras = re.split(r'\n{2,}', text)
        seen, unique = set(), []
        for p in paras:
            key = re.sub(r'\s+', " ", p.strip())[:120]
            if key and key not in seen:
                seen.add(key); unique.append(p.strip())
        text = "\n\n".join(unique)
        text = re.sub(r'^\s*[■→●•►▸✦]+\s*$', "", text, flags=re.MULTILINE)
        text = re.sub(r'\n{3,}', "\n\n", text)
        return text.strip()

    def _make_topic(self, subject: str, body: str) -> str:
        t = re.sub(r'^(Daily Dose of DS|Re:|Fwd:)\s*[-:]?\s*', "", subject, flags=re.I).strip()
        t = re.sub(r'[^\w\s]', "", t)
        t = re.sub(r'\s+', "_", t).strip("_")
        return t or "Study_Notes"


# ── AI Engine ─────────────────────────────────────────────────────────────────

class AI:
    def __init__(self):
        self.provider = None
        if GEMINI_KEY:
            import google.generativeai as genai
            genai.configure(api_key=GEMINI_KEY)
            self.model = genai.GenerativeModel(AI_MODEL)
            self.provider = "gemini"
            log.info("AI: Gemini %s", AI_MODEL)
        elif OPENAI_KEY:
            import openai
            self.client = openai.OpenAI(api_key=OPENAI_KEY)
            self.provider = "openai"
            log.info("AI: OpenAI gpt-4o-mini")

    def enhance(self, email: RawEmail) -> StudyNote:
        if not self.provider:
            return self._fallback(email)

        prompt = f"""You are an expert technical writer for a data science newsletter.
Transform the following newsletter email into clean, structured study notes.

STRICT RULES:
1. Do NOT include any URLs, links, tracking codes, or promotional content
2. Do NOT include "unsubscribe", "advertise", "unlock premium", or footer text
3. Do NOT duplicate content between sections
4. Write in clear, educational prose — not bullet dumps
5. Cover ALL topics mentioned in the email thoroughly
6. DEEP EXPLANATION must be 4-6 educational paragraphs, NOT a copy of overview
7. For code: preserve exact code blocks, explain each part

EMAIL SUBJECT: {email.subject}
EMAIL DATE: {email.date.strftime("%B %d, %Y")}

EMAIL CONTENT (already cleaned):
{email.body_text[:9000]}

Respond in EXACTLY this format:

TOPIC: [Clean descriptive title for this newsletter issue]

TLDR: [2-3 sentence summary of what this issue covers and why it matters]

OVERVIEW:
[3-4 paragraphs introducing the topic]

SECTION: [Title of first major topic]
[3-5 paragraphs of educational explanation]

SECTION: [Title of second major topic if applicable]
[3-5 paragraphs]

CODE:
```python
# code if present in email, else a short illustrative example
```

KEY_POINTS:
- [Insight]
[5-7 total]

INTERVIEW_QUESTIONS:
- [Question]
[6 total, mixed difficulty]

FURTHER_READING:
- [Topic to explore next, no URLs]
[3-5 total]
"""
        MAX_RETRY = 5
        for attempt in range(MAX_RETRY):
            try:
                if self.provider == "gemini":
                    resp = self.model.generate_content(
                        prompt, generation_config={"temperature": 0.25, "max_output_tokens": MAX_TOKENS})
                    text = resp.text
                else:
                    resp = self.client.chat.completions.create(
                        model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}],
                        max_tokens=MAX_TOKENS, temperature=0.25)
                    text = resp.choices[0].message.content or ""
                return self._parse(text, email)
            except Exception as e:
                err = str(e)
                m = re.search(r'retry_delay.*?seconds:\s*([0-9]+)', err, re.DOTALL)
                wait = int(m.group(1)) + 5 if m else 30 * (attempt + 1)
                log.warning("AI quota/error — waiting %ds (attempt %d/%d)...", wait, attempt + 1, MAX_RETRY)
                time.sleep(wait)
        log.error("AI failed after %d retries — using smart fallback", MAX_RETRY)
        return self._fallback(email)

    def _parse(self, text: str, email: RawEmail) -> StudyNote:
        def gs(header):
            m = re.search(rf"{re.escape(header)}\s*\n(.*?)(?=\n[A-Z_]+:|SECTION:|CODE:|\Z)", text, re.DOTALL)
            return m.group(1).strip() if m else ""
        def glist(header):
            raw = gs(header)
            return [l.strip("- •").strip() for l in raw.split("\n") if l.strip().startswith(("-","•","*")) and len(l.strip()) > 3]

        sections = []
        for m in re.finditer(r'SECTION:\s*(.+?)\n(.*?)(?=\nSECTION:|\nCODE:|\nKEY_POINTS:|\Z)', text, re.DOTALL):
            title, body = m.group(1).strip(), m.group(2).strip()
            if title and body:
                sections.append({"title": title, "body": body, "code": ""})

        code_blocks = re.findall(r'```(?:python)?\n(.*?)```', text, re.DOTALL)
        if code_blocks:
            if sections: sections[-1]["code"] = code_blocks[0].strip()
            else: sections.append({"title": "Code Example", "body": "", "code": code_blocks[0].strip()})

        topic = gs("TOPIC:") or email.topic.replace("_", " ")
        return StudyNote(
            issue_number=0, date=email.date.strftime("%Y-%m-%d"), topic=topic,
            category=detect_category(topic + " " + email.body_text[:500]),
            tldr=gs("TLDR:"), overview=gs("OVERVIEW:"), sections=sections,
            key_points=glist("KEY_POINTS:"), interview_qs=glist("INTERVIEW_QUESTIONS:"),
            further=glist("FURTHER_READING:"),
        )

    def _fallback(self, email: RawEmail) -> StudyNote:
        paras = [p.strip() for p in email.body_text.split("\n\n") if len(p.strip()) > 80]
        overview = (paras[0][:800] + "...") if paras else "Content from Daily Dose of DS."
        bullets = []
        for line in email.body_text.split("\n"):
            line = line.strip()
            if re.match(r'^[\*\-•\d]+[.)\s]', line) and 15 < len(line) < 200:
                cleaned = re.sub(r'^[\*\-•\d.)+\s]+', "", line).strip()
                if cleaned: bullets.append(cleaned)
        sections = [{"title": f"Section {i+1}", "body": p, "code": ""}
                    for i, p in enumerate(paras[1:6]) if len(p) > 100]
        topic = email.topic.replace("_", " ")
        return StudyNote(
            issue_number=0, date=email.date.strftime("%Y-%m-%d"), topic=topic,
            category=detect_category(topic + " " + email.body_text[:500]),
            tldr=overview[:200], overview=overview, sections=sections,
            key_points=bullets[:7], interview_qs=[],
            further=["Visit dailydoseofds.com for the full article and related resources"],
        )


# ── CSS ───────────────────────────────────────────────────────────────────────



CSS = """
@view-transition { navigation: auto; }

:root{
  --void:#050816;--deep:#080b1c;--card:#0E1324;--card-glass:rgba(14,19,36,.55);
  --border:rgba(255,255,255,.08);--border-h:rgba(91,140,255,.35);
  --text:#f4f6ff;--text-2:rgba(210,215,240,.75);--text-3:rgba(155,162,200,.5);
  --a:#5B8CFF;--b:#7C5CFF;--c:#22d3ee;--d:#a78bfa;--e:#34d399;--f:#fbbf24;
  --ca:#5B8CFF;--cb:#7C5CFF;
  --r10:10px;--r16:16px;--r20:20px;--r24:24px;--r32:32px;
  --bounce:cubic-bezier(.22,1.4,.36,1);--smooth:cubic-bezier(.4,0,.2,1);
  --sans:'Inter','General Sans','Segoe UI',system-ui,sans-serif;
  --mono:'Fira Code','JetBrains Mono',monospace;
}
body.light{--void:#f7f8fd;--deep:#ffffff;--card:#ffffff;--card-glass:rgba(255,255,255,.7);
  --border:rgba(91,140,255,.14);--border-h:rgba(91,140,255,.35);
  --text:#0c0f1e;--text-2:rgba(20,24,50,.72);--text-3:rgba(40,46,80,.48);}

*,*::before,*::after{margin:0;padding:0;box-sizing:border-box;}
html{scroll-behavior:smooth;}
body{font-family:var(--sans);background:var(--void);color:var(--text);
  min-height:100vh;overflow-x:hidden;-webkit-font-smoothing:antialiased;cursor:none;}
@media(pointer:coarse){body{cursor:auto;}}

/* ── AMBIENT BACKGROUND ────────────────────────────────────────── */
.aurora{position:fixed;inset:0;z-index:-4;overflow:hidden;pointer-events:none;}
.orb{position:absolute;filter:blur(120px);opacity:.18;
  animation:orbf 26s ease-in-out infinite,blobMorph 14s ease-in-out infinite;will-change:transform,border-radius;}
.orb:nth-child(1){width:780px;height:780px;left:-18%;top:-22%;background:radial-gradient(circle,var(--a),transparent 70%);}
.orb:nth-child(2){width:580px;height:580px;right:-12%;top:26%;background:radial-gradient(circle,var(--b),transparent 70%);animation-delay:-8s,-3s;opacity:.15;}
.orb:nth-child(3){width:440px;height:440px;left:38%;bottom:-14%;background:radial-gradient(circle,var(--c),transparent 70%);animation-delay:-16s,-7s;opacity:.12;}
.orb:nth-child(4){width:320px;height:320px;right:22%;top:6%;background:radial-gradient(circle,var(--d),transparent 70%);animation-delay:-5s,-11s;opacity:.09;}
@keyframes orbf{0%,100%{transform:translate(0,0) scale(1);}25%{transform:translate(4%,-5%) scale(1.1);}50%{transform:translate(-3%,4%) scale(.92);}75%{transform:translate(5%,2%) scale(1.05);}}
@keyframes blobMorph{
  0%,100%{border-radius:58% 42% 63% 37%/41% 58% 42% 59%;}
  25%{border-radius:42% 58% 39% 61%/58% 43% 57% 42%;}
  50%{border-radius:63% 37% 47% 53%/33% 65% 35% 67%;}
  75%{border-radius:37% 63% 58% 42%/62% 38% 62% 38%;}
}
.dust{position:fixed;inset:0;z-index:-3;pointer-events:none;overflow:hidden;}
.mote{position:absolute;border-radius:50%;background:rgba(150,170,255,.35);animation:moteDrift linear infinite;}
@keyframes moteDrift{0%{transform:translate(0,100vh) scale(0);opacity:0;}8%{opacity:.5;}92%{opacity:.35;}100%{transform:translate(var(--drift,20px),-10vh) scale(1);opacity:0;}}
.grid-bg{position:fixed;inset:0;z-index:-2;pointer-events:none;
  background-image:linear-gradient(rgba(91,140,255,.028) 1px,transparent 1px),linear-gradient(90deg,rgba(91,140,255,.028) 1px,transparent 1px);
  background-size:64px 64px;mask-image:radial-gradient(ellipse 80% 60% at 50% 0%,#000 40%,transparent 100%);}

/* ── CURSOR ─────────────────────────────────────────────────────── */
.cur-dot{position:fixed;width:9px;height:9px;border-radius:50%;background:var(--a);pointer-events:none;z-index:99999;
  transform:translate(-50%,-50%);box-shadow:0 0 14px var(--a),0 0 28px var(--a);transition:width .2s,height .2s,background .2s;}
.cur-ring{position:fixed;width:38px;height:38px;border-radius:50%;border:1px solid rgba(91,140,255,.4);pointer-events:none;z-index:99998;
  transform:translate(-50%,-50%);transition:transform .16s ease,width .2s,height .2s;}
@media(pointer:coarse){.cur-dot,.cur-ring{display:none;}}

.card.zoom-launch{position:relative;z-index:500;animation:zoomLaunch .48s var(--smooth) forwards;}
@keyframes zoomLaunch{0%{transform:scale(1);opacity:1;filter:blur(0);}60%{transform:scale(1.06);opacity:1;}100%{transform:scale(2.4);opacity:0;filter:blur(6px);}}
body.page-entering{animation:pageZoomIn .55s var(--smooth) both;}
@keyframes pageZoomIn{0%{opacity:0;transform:scale(.96);filter:blur(4px);}100%{opacity:1;transform:scale(1);filter:blur(0);}}

.scroll-bar{position:fixed;top:0;left:0;height:2px;z-index:9999;
  background:linear-gradient(90deg,var(--a),var(--b),var(--c));box-shadow:0 0 10px var(--a);transition:width .1s linear;}

/* ── NAV ─────────────────────────────────────────────────────────── */
.nav{position:sticky;top:0;z-index:100;background:rgba(5,8,22,.55);backdrop-filter:blur(20px) saturate(160%);
  -webkit-backdrop-filter:blur(20px) saturate(160%);border-bottom:1px solid transparent;transition:background .3s,border-color .3s;}
.nav.scrolled{background:rgba(5,8,22,.85);border-bottom-color:var(--border);}
body.light .nav{background:rgba(255,255,255,.6);}
body.light .nav.scrolled{background:rgba(255,255,255,.88);}
.nav-in{max-width:1240px;margin:0 auto;padding:0 24px;height:66px;display:flex;align-items:center;justify-content:space-between;gap:16px;}
.nav-logo{display:flex;align-items:center;gap:11px;text-decoration:none;color:var(--text);font-weight:800;font-size:1.05rem;cursor:none;flex-shrink:0;}
.gem{width:34px;height:34px;border-radius:10px;background:linear-gradient(135deg,var(--a),var(--b));
  display:flex;align-items:center;justify-content:center;font-size:1rem;box-shadow:0 0 18px rgba(91,140,255,.4);
  animation:gempulse 4s ease-in-out infinite;position:relative;overflow:hidden;transform-style:preserve-3d;transition:transform .5s var(--bounce);}
.nav-logo:hover .gem{transform:rotateY(20deg) rotateX(-8deg) scale(1.08);}
.gem::after{content:'';position:absolute;top:-50%;left:-150%;width:60%;height:200%;
  background:linear-gradient(115deg,transparent 20%,rgba(255,255,255,.55) 45%,transparent 65%);transform:rotate(20deg);animation:gemShine 5s ease-in-out infinite;}
@keyframes gemShine{0%,100%{left:-150%;}50%{left:150%;}}
@keyframes gempulse{0%,100%{box-shadow:0 0 14px rgba(91,140,255,.3);}50%{box-shadow:0 0 28px rgba(91,140,255,.6);}}
.nav-links{display:flex;align-items:center;gap:2px;flex:1;justify-content:center;}
.nav-link{padding:8px 14px;border-radius:100px;color:var(--text-2);text-decoration:none;font-size:.86rem;font-weight:500;transition:all .2s;cursor:none;white-space:nowrap;}
.nav-link:hover{color:var(--text);background:rgba(91,140,255,.08);}
.nav-right{display:flex;align-items:center;gap:10px;flex-shrink:0;}
.nav-cta{padding:9px 20px;border-radius:100px;border:none;cursor:none;background:linear-gradient(135deg,var(--a),var(--b));
  color:#fff;font-weight:700;font-size:.84rem;text-decoration:none;white-space:nowrap;transition:box-shadow .25s,transform .15s;
  box-shadow:0 2px 14px rgba(91,140,255,.35);}
.nav-cta:hover{box-shadow:0 4px 22px rgba(91,140,255,.5);transform:translateY(-1px);}
@media(max-width:900px){.nav-links{display:none;}}

.theme-switch{position:relative;width:50px;height:27px;border-radius:100px;cursor:none;
  background:linear-gradient(135deg,#161b30,#1e2440);border:1px solid var(--border);transition:background .4s;flex-shrink:0;overflow:hidden;}
body.light .theme-switch{background:linear-gradient(135deg,#cfe0ff,#eaf1ff);}
.theme-switch .thumb{position:absolute;top:3px;left:3px;width:19px;height:19px;border-radius:50%;
  background:linear-gradient(135deg,#fde68a,#fbbf24);box-shadow:0 2px 8px rgba(0,0,0,.3);
  transition:transform .4s var(--bounce),background .4s;display:flex;align-items:center;justify-content:center;font-size:.65rem;}
body.light .theme-switch .thumb{transform:translateX(23px);background:linear-gradient(135deg,#fff9db,#fff3a0);}

/* ── HERO ─────────────────────────────────────────────────────────── */
.hero{position:relative;padding:clamp(70px,10vw,110px) 24px clamp(60px,8vw,90px);overflow:hidden;max-width:1240px;margin:0 auto;}
#neural-canvas{position:absolute;inset:0;z-index:0;opacity:.22;pointer-events:none;}
.hero-grid{display:grid;grid-template-columns:1.05fr .95fr;gap:48px;align-items:center;position:relative;z-index:1;}
@media(max-width:960px){.hero-grid{grid-template-columns:1fr;}.hero-visual{display:none;}}
.badge{display:inline-flex;align-items:center;gap:8px;padding:6px 16px;border-radius:100px;margin-bottom:24px;
  background:rgba(91,140,255,.1);border:1px solid rgba(91,140,255,.25);color:var(--a);
  font-size:.76rem;font-weight:700;letter-spacing:.7px;text-transform:uppercase;animation:fadeUp .8s var(--bounce) .1s both;}
.dot-live{width:7px;height:7px;border-radius:50%;background:var(--e);animation:pulse 2s infinite;}
@keyframes pulse{0%,100%{opacity:1;transform:scale(1);}50%{opacity:.5;transform:scale(.8);}}
.hero h1{font-size:clamp(2.4rem,4.6vw,3.6rem);font-weight:800;line-height:1.12;letter-spacing:-.02em;
  margin-bottom:20px;animation:fadeUp .8s var(--bounce) .2s both;}
.grad-text{background:linear-gradient(120deg,var(--a) 0%,var(--b) 50%,var(--c) 100%);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;
  background-size:200% 200%;animation:shineMove 6s ease infinite;}
@keyframes shineMove{0%,100%{background-position:0% 50%;}50%{background-position:100% 50%;}}
.hero-sub{font-size:clamp(1rem,1.6vw,1.15rem);color:var(--text-2);max-width:520px;margin:0 0 32px;line-height:1.65;
  animation:fadeUp .8s var(--bounce) .3s both;}
@keyframes fadeUp{from{opacity:0;transform:translateY(28px);}to{opacity:1;transform:translateY(0);}}
.hero-actions{display:flex;gap:12px;flex-wrap:wrap;animation:fadeUp .8s var(--bounce) .4s both;margin-bottom:36px;}
.btn-primary{display:inline-flex;align-items:center;gap:8px;padding:13px 26px;border-radius:12px;border:none;cursor:none;
  background:linear-gradient(135deg,var(--a),var(--b));color:#fff;font-weight:700;font-size:.92rem;text-decoration:none;
  box-shadow:0 4px 20px rgba(91,140,255,.4);transition:box-shadow .3s,transform .1s;position:relative;overflow:hidden;}
.btn-primary::before{content:'';position:absolute;inset:0;background:linear-gradient(90deg,transparent,rgba(255,255,255,.16),transparent);
  transform:translateX(-100%);transition:transform .5s;}
.btn-primary:hover::before{transform:translateX(100%);}
.btn-primary:hover{box-shadow:0 8px 30px rgba(91,140,255,.5);}
.btn-secondary{display:inline-flex;align-items:center;gap:8px;padding:13px 24px;border-radius:12px;
  background:var(--card-glass);border:1px solid var(--border);color:var(--text);
  font-weight:600;font-size:.9rem;text-decoration:none;cursor:none;transition:all .25s;backdrop-filter:blur(10px);}
.btn-secondary:hover{border-color:var(--border-h);transform:translateY(-2px);}
.btn-ghost{display:inline-flex;align-items:center;gap:6px;padding:13px 18px;border-radius:12px;
  background:none;border:none;color:var(--text-2);font-weight:600;font-size:.9rem;cursor:none;transition:color .2s;}
.btn-ghost:hover{color:var(--a);}

.hero-stats{display:flex;gap:32px;flex-wrap:wrap;animation:fadeUp .8s var(--bounce) .5s both;}
.hstat-n{font-size:1.7rem;font-weight:800;background:linear-gradient(135deg,var(--a),var(--b));
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;line-height:1;}
.hstat-l{font-size:.72rem;color:var(--text-3);text-transform:uppercase;letter-spacing:1.4px;margin-top:4px;}

/* ── HERO VISUAL (AI dashboard mock) ─────────────────────────────── */
.hero-visual{position:relative;height:440px;animation:fadeUp 1s var(--bounce) .4s both;}
.dash-panel{position:absolute;background:var(--card-glass);border:1px solid var(--border);border-radius:var(--r20);
  backdrop-filter:blur(16px);box-shadow:0 24px 60px rgba(0,0,0,.4);}
.dash-main{top:0;left:0;right:60px;bottom:60px;padding:20px;animation:floatSlow 7s ease-in-out infinite;}
.dash-main .dm-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;}
.dash-main .dm-title{font-size:.8rem;font-weight:700;color:var(--text-2);}
.dash-main .dm-dots{display:flex;gap:5px;}
.dash-main .dm-dots span{width:7px;height:7px;border-radius:50%;background:var(--border-h);}
#dash-graph{width:100%;height:220px;}
.dm-legend{display:flex;gap:10px;margin-top:14px;flex-wrap:wrap;}
.dm-chip{font-size:.66rem;padding:3px 9px;border-radius:100px;background:rgba(91,140,255,.1);border:1px solid rgba(91,140,255,.2);color:var(--a);}
.dash-float{position:absolute;padding:14px 16px;border-radius:var(--r16);width:180px;z-index:2;}
.dash-float-1{top:20px;right:0;animation:floatSlow 6s ease-in-out infinite .5s;}
.dash-float-2{bottom:0;left:20px;animation:floatSlow 8s ease-in-out infinite 1s;}
.df-cat{font-size:.62rem;font-weight:700;text-transform:uppercase;letter-spacing:.8px;color:var(--a);margin-bottom:5px;}
.df-title{font-size:.82rem;font-weight:700;color:var(--text);margin-bottom:8px;line-height:1.3;}
.df-bar{height:5px;border-radius:100px;background:rgba(255,255,255,.08);overflow:hidden;}
.df-bar-fill{height:100%;border-radius:100px;background:linear-gradient(90deg,var(--a),var(--b));animation:barFill 2.4s var(--smooth) .8s both;}
@keyframes barFill{from{width:0;}}
@keyframes floatSlow{0%,100%{transform:translateY(0);}50%{transform:translateY(-10px);}}
"""

CSS += """
/* ── STATS BAR (secondary, below hero) ────────────────────────────── */
.stats-bar{max-width:1240px;margin:0 auto;padding:0 24px 40px;display:flex;justify-content:center;gap:0;
  flex-wrap:wrap;border-top:1px solid var(--border);border-bottom:1px solid var(--border);}
.sb-item{flex:1;min-width:140px;text-align:center;padding:24px 16px;border-right:1px solid var(--border);}
.sb-item:last-child{border-right:none;}
.sb-n{font-size:2rem;font-weight:800;background:linear-gradient(135deg,var(--a),var(--b));
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;line-height:1;}
.sb-l{font-size:.7rem;color:var(--text-3);text-transform:uppercase;letter-spacing:1.6px;margin-top:6px;}
@media(max-width:640px){.sb-item{border-right:none;border-bottom:1px solid var(--border);}}

/* ── SECTION SHELL ─────────────────────────────────────────────────── */
.section-shell{max-width:1240px;margin:0 auto;padding:90px 24px;}
.section-head{text-align:center;max-width:640px;margin:0 auto 56px;}
.section-kicker{display:inline-block;font-size:.72rem;font-weight:800;color:var(--a);text-transform:uppercase;
  letter-spacing:1.8px;margin-bottom:12px;}
.section-title{font-size:clamp(1.7rem,3.4vw,2.5rem);font-weight:800;line-height:1.2;margin-bottom:14px;letter-spacing:-.01em;}
.section-sub{color:var(--text-2);font-size:1rem;line-height:1.65;}

/* ── FEATURE GRID ──────────────────────────────────────────────────── */
.feature-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:20px;}
.f-card{background:var(--card);border:1px solid var(--border);border-radius:var(--r20);padding:28px;
  position:relative;overflow:hidden;transition:transform .35s var(--bounce),border-color .3s,box-shadow .3s;
  opacity:0;transform:translateY(30px);cursor:none;}
.f-card.visible{opacity:1;transform:translateY(0);transition:opacity .6s ease,transform .6s var(--bounce),border-color .3s,box-shadow .3s;}
.f-card::before{content:'';position:absolute;inset:0;border-radius:inherit;padding:1px;
  background:linear-gradient(135deg,transparent,transparent);transition:background .35s;pointer-events:none;-webkit-mask:linear-gradient(#fff 0 0) content-box,linear-gradient(#fff 0 0);-webkit-mask-composite:xor;mask-composite:exclude;}
.f-card:hover{transform:translateY(-6px);border-color:transparent;box-shadow:0 20px 44px rgba(91,140,255,.15);}
.f-card:hover::before{background:linear-gradient(135deg,var(--a),var(--b),var(--c));}
.f-icon{width:46px;height:46px;border-radius:13px;background:linear-gradient(135deg,rgba(91,140,255,.15),rgba(124,92,255,.1));
  border:1px solid rgba(91,140,255,.2);display:flex;align-items:center;justify-content:center;font-size:1.3rem;
  margin-bottom:18px;transition:transform .4s var(--bounce);}
.f-card:hover .f-icon{transform:scale(1.1) rotate(-6deg);}
.f-title{font-size:1.05rem;font-weight:700;margin-bottom:8px;}
.f-desc{font-size:.87rem;color:var(--text-2);line-height:1.6;}

/* ── TIMELINE (How It Works) ──────────────────────────────────────── */
.timeline{max-width:640px;margin:0 auto;position:relative;}
.tl-line{position:absolute;left:23px;top:8px;bottom:8px;width:2px;
  background:linear-gradient(180deg,var(--a),var(--b) 50%,var(--c));opacity:.35;}
.tl-step{display:flex;gap:20px;margin-bottom:36px;position:relative;opacity:0;transform:translateX(-24px);
  transition:opacity .6s ease,transform .6s var(--bounce);}
.tl-step.visible{opacity:1;transform:translateX(0);}
.tl-step:last-child{margin-bottom:0;}
.tl-num{width:48px;height:48px;border-radius:50%;background:var(--card);border:2px solid var(--a);
  display:flex;align-items:center;justify-content:center;font-size:1.2rem;flex-shrink:0;z-index:1;
  box-shadow:0 0 0 6px var(--void);}
.tl-body{padding-top:6px;}
.tl-title{font-size:1.02rem;font-weight:700;margin-bottom:4px;}
.tl-desc{font-size:.86rem;color:var(--text-2);line-height:1.55;}

/* ── CATEGORY FILTER CHIPS ─────────────────────────────────────────── */
.chip-row{display:flex;flex-wrap:wrap;gap:8px;justify-content:center;margin-bottom:32px;}
.cat-chip{padding:7px 16px;border-radius:100px;font-size:.78rem;font-weight:600;cursor:none;
  background:var(--card-glass);border:1px solid var(--border);color:var(--text-2);transition:all .25s;}
.cat-chip:hover{border-color:var(--border-h);color:var(--text);}
.cat-chip.active{background:linear-gradient(135deg,var(--a),var(--b));border-color:transparent;color:#fff;}

/* ── ROADMAP (accordion, week-grouped) ────────────────────────────── */
.roadmap-wrap{max-width:840px;margin:0 auto;position:relative;}
.roadmap-line{position:absolute;left:calc(24px + 27px);top:0;bottom:60px;width:2px;
  background:linear-gradient(180deg,transparent,var(--border) 4%,var(--border) 96%,transparent);z-index:0;}
@media(max-width:640px){.roadmap-line{display:none;}}

.week-block{position:relative;z-index:1;margin-bottom:6px;}
.week-header{width:100%;text-align:left;border:none;background:none;cursor:none;padding:10px 0;
  position:sticky;top:70px;z-index:20;}
.week-header-inner{display:flex;align-items:center;gap:10px;padding:9px 20px;border-radius:100px;
  background:rgba(91,140,255,.09);border:1px solid rgba(91,140,255,.2);backdrop-filter:blur(12px);
  transition:background .25s,border-color .25s,transform .2s,box-shadow .35s;width:fit-content;}
.week-header:hover .week-header-inner{background:rgba(91,140,255,.16);border-color:rgba(91,140,255,.35);transform:translateY(-1px);}
.week-header.open .week-header-inner{box-shadow:0 0 0 3px rgba(91,140,255,.12),0 8px 24px rgba(91,140,255,.15);}
.week-dot{width:7px;height:7px;border-radius:50%;background:var(--a);flex-shrink:0;}
.week-label{font-size:.78rem;font-weight:700;color:var(--a);text-transform:uppercase;letter-spacing:1.2px;white-space:nowrap;}
.week-count{font-size:.7rem;color:var(--text-3);font-weight:600;padding-left:8px;margin-left:2px;border-left:1px solid rgba(91,140,255,.25);}
.week-chevron{margin-left:4px;font-size:.7rem;color:var(--a);transition:transform .35s var(--bounce);flex-shrink:0;}
.week-header.open .week-chevron{transform:rotate(90deg);}

.week-panel{display:grid;grid-template-rows:0fr;opacity:0;transition:grid-template-rows .5s var(--smooth),opacity .4s ease;}
.week-panel.open{grid-template-rows:1fr;opacity:1;}
.week-panel-inner{overflow:hidden;min-height:0;padding-top:14px;}

.entry-row{display:flex;gap:20px;margin-bottom:16px;position:relative;z-index:1;
  opacity:0;transform:translateY(20px);transition:opacity .5s ease,transform .5s var(--bounce);}
.entry-row.visible{opacity:1;transform:translateY(0);}
.week-panel.open .entry-row{transition-delay:calc(var(--i,0) * 0.05s);}
.entry-dot-col{flex-shrink:0;width:54px;display:flex;flex-direction:column;align-items:center;padding-top:22px;}
.entry-dot{width:13px;height:13px;border-radius:50%;background:linear-gradient(135deg,var(--ca),var(--cb));
  box-shadow:0 0 0 4px var(--void),0 0 14px color-mix(in srgb,var(--ca) 50%,transparent);flex-shrink:0;}

.card{flex:1;display:block;text-decoration:none;color:var(--text);background:var(--card);border:1px solid var(--border);
  border-radius:var(--r20);padding:22px 24px;position:relative;overflow:hidden;cursor:none;
  transition:transform .35s var(--bounce),border-color .3s,box-shadow .3s;}
.card::after{content:'';position:absolute;top:0;left:0;right:0;height:2px;
  background:linear-gradient(90deg,var(--ca),var(--cb));transform:scaleX(0);transform-origin:left;transition:transform .4s var(--bounce);}
.card:hover{transform:translateY(-4px);border-color:color-mix(in srgb,var(--ca) 35%,transparent);box-shadow:0 16px 40px rgba(0,0,0,.4);}
.card:hover::after{transform:scaleX(1);}
.card-issue{font-size:.68rem;font-weight:800;text-transform:uppercase;letter-spacing:1.6px;color:var(--ca);margin-bottom:6px;
  display:flex;align-items:center;gap:8px;}
.cat-badge{display:inline-flex;align-items:center;padding:2px 10px;border-radius:100px;font-size:.63rem;font-weight:700;
  text-transform:uppercase;letter-spacing:.6px;background:color-mix(in srgb,var(--ca) 12%,transparent);
  border:1px solid color-mix(in srgb,var(--ca) 20%,transparent);color:var(--ca);}
.card-title{font-size:1.1rem;font-weight:700;line-height:1.35;margin-bottom:8px;}
.card-desc{font-size:.85rem;color:var(--text-2);line-height:1.55;margin-bottom:14px;}
.card-foot{display:flex;justify-content:space-between;align-items:center;padding-top:12px;border-top:1px solid var(--border);}
.card-date{font-size:.73rem;color:var(--text-3);}
.card-badges{display:flex;align-items:center;gap:8px;}
.bookmark-btn{background:none;border:none;cursor:none;font-size:1rem;color:var(--text-3);transition:all .2s;padding:2px;}
.bookmark-btn:hover{color:var(--f);transform:scale(1.15);}
.bookmark-btn.on{color:var(--f);}
.complete-badge{font-size:.7rem;color:var(--e);}
.arrow{width:28px;height:28px;border-radius:50%;background:color-mix(in srgb,var(--ca) 10%,transparent);
  border:1px solid color-mix(in srgb,var(--ca) 20%,transparent);color:var(--ca);
  display:flex;align-items:center;justify-content:center;font-size:.8rem;transition:all .25s var(--bounce);}
.card:hover .arrow{background:linear-gradient(135deg,var(--ca),var(--cb));border-color:transparent;color:#fff;transform:translateX(4px);}

.empty{text-align:center;padding:100px 20px;}
.empty-icon{font-size:5rem;margin-bottom:20px;animation:float 3s ease-in-out infinite;}
@keyframes float{0%,100%{transform:translateY(0);}50%{transform:translateY(-16px);}}

/* ── AI SEARCH HERO SECTION ───────────────────────────────────────── */
.search-hero{max-width:720px;margin:0 auto;text-align:center;}
.ask-shell{display:flex;align-items:center;gap:8px;background:var(--card-glass);border:1px solid var(--border);
  border-radius:16px;padding:8px 8px 8px 22px;backdrop-filter:blur(14px);transition:border-color .25s,box-shadow .25s,transform .2s;}
.ask-shell:focus-within{border-color:var(--a);box-shadow:0 0 0 3px rgba(91,140,255,.15),0 10px 34px rgba(0,0,0,.35);transform:translateY(-2px);}
.ask-ico{color:var(--text-3);font-size:1.1rem;flex-shrink:0;}
.ask-input{flex:1;background:none;border:none;outline:none;color:var(--text);font-size:1rem;padding:12px 4px;cursor:text;}
.ask-input::placeholder{color:var(--text-3);}
.ask-go{flex-shrink:0;padding:12px 24px;border-radius:11px;border:none;cursor:none;
  background:linear-gradient(135deg,var(--a),var(--b));color:#fff;font-weight:700;font-size:.86rem;
  transition:transform .2s,box-shadow .2s;white-space:nowrap;}
.ask-go:hover{transform:translateY(-1px);box-shadow:0 4px 16px rgba(91,140,255,.4);}
.ask-go:disabled{opacity:.5;transform:none;}
.ask-hint{color:var(--text-3);font-size:.78rem;margin-top:12px;}
.ask-answer{max-width:720px;margin:20px auto 0;}
.ask-answer-box{background:var(--card);border:1px solid var(--border);border-left:3px solid var(--a);
  border-radius:var(--r16);padding:18px 22px;font-size:.92rem;color:var(--text-2);line-height:1.7;text-align:left;
  display:none;animation:fadeUp .4s var(--bounce) both;}
.ask-answer-box.show{display:block;}
.ask-answer-label{font-size:.68rem;font-weight:800;text-transform:uppercase;letter-spacing:1.4px;color:var(--a);margin-bottom:8px;display:flex;align-items:center;gap:8px;}
.search-count{text-align:center;color:var(--text-3);font-size:.8rem;margin-top:14px;opacity:0;transition:opacity .3s;}
.search-count.show{opacity:1;}
.suggest-row{display:flex;flex-wrap:wrap;gap:8px;justify-content:center;margin-top:16px;}
.suggest-chip{padding:6px 14px;border-radius:100px;font-size:.76rem;cursor:none;
  background:rgba(91,140,255,.07);border:1px solid rgba(91,140,255,.15);color:var(--text-2);transition:all .2s;}
.suggest-chip:hover{background:rgba(91,140,255,.14);color:var(--a);border-color:rgba(91,140,255,.3);}

/* ── CHAPTERS STRIP (preview) ─────────────────────────────────────── */
.chap-strip{display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:18px;}
.chap-card{background:var(--card);border:1px solid var(--border);border-radius:var(--r20);padding:22px;
  text-decoration:none;color:var(--text);transition:transform .3s var(--bounce),border-color .3s,box-shadow .3s;cursor:none;
  display:flex;flex-direction:column;gap:10px;}
.chap-card:hover{transform:translateY(-5px);border-color:color-mix(in srgb,var(--ca) 30%,transparent);box-shadow:0 14px 36px rgba(0,0,0,.35);}
.chap-top{display:flex;justify-content:space-between;align-items:flex-start;gap:8px;}
.chap-diff{font-size:.62rem;font-weight:700;text-transform:uppercase;letter-spacing:.6px;padding:2px 9px;border-radius:100px;
  background:color-mix(in srgb,var(--ca) 12%,transparent);color:var(--ca);}
.chap-time{font-size:.72rem;color:var(--text-3);}
.chap-title{font-size:1rem;font-weight:700;line-height:1.4;}
.chap-tags{display:flex;gap:6px;flex-wrap:wrap;}
.chap-tag{font-size:.68rem;padding:2px 9px;border-radius:100px;background:rgba(255,255,255,.05);color:var(--text-3);border:1px solid var(--border);}

/* ── TESTIMONIALS ──────────────────────────────────────────────────── */
.testi-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:20px;}
.testi-card{background:var(--card-glass);backdrop-filter:blur(14px);border:1px solid var(--border);border-radius:var(--r20);
  padding:26px;transition:transform .3s var(--bounce),border-color .3s;}
.testi-card:hover{transform:translateY(-4px);border-color:var(--border-h);}
.testi-quote{font-size:.92rem;color:var(--text-2);line-height:1.65;margin-bottom:18px;}
.testi-person{display:flex;align-items:center;gap:12px;}
.testi-avatar{width:38px;height:38px;border-radius:50%;background:linear-gradient(135deg,var(--a),var(--b));
  display:flex;align-items:center;justify-content:center;font-weight:700;font-size:.85rem;color:#fff;flex-shrink:0;}
.testi-name{font-size:.86rem;font-weight:700;}
.testi-role{font-size:.74rem;color:var(--text-3);}

/* ── FINAL CTA ─────────────────────────────────────────────────────── */
.final-cta{max-width:900px;margin:0 auto;text-align:center;background:var(--card);border:1px solid var(--border);
  border-radius:var(--r32);padding:clamp(50px,8vw,80px) clamp(24px,5vw,60px);position:relative;overflow:hidden;}
.final-cta::before{content:'';position:absolute;inset:0;background:radial-gradient(ellipse at 50% 0%,rgba(91,140,255,.12),transparent 60%);pointer-events:none;}
.final-cta h2{font-size:clamp(1.7rem,3.6vw,2.6rem);font-weight:800;margin-bottom:16px;position:relative;z-index:1;}
.final-cta p{color:var(--text-2);font-size:1rem;margin-bottom:32px;position:relative;z-index:1;}

/* ── FOOTER ────────────────────────────────────────────────────────── */
.footer{border-top:1px solid var(--border);background:rgba(3,4,12,.5);backdrop-filter:blur(12px);}
.footer-in{max-width:1240px;margin:0 auto;padding:50px 24px 30px;}
.footer-top{display:grid;grid-template-columns:1.4fr 1fr 1fr 1fr;gap:32px;margin-bottom:36px;}
@media(max-width:720px){.footer-top{grid-template-columns:1fr 1fr;}}
.footer-brand{display:flex;align-items:center;gap:10px;font-weight:800;color:var(--text);margin-bottom:10px;}
.footer-desc{font-size:.85rem;color:var(--text-3);line-height:1.6;max-width:280px;}
.footer-col h4{font-size:.78rem;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:var(--text-2);margin-bottom:14px;}
.footer-col a{display:block;font-size:.85rem;color:var(--text-3);text-decoration:none;margin-bottom:10px;transition:color .2s;}
.footer-col a:hover{color:var(--a);}
.footer-bottom{padding-top:24px;border-top:1px solid var(--border);text-align:center;color:var(--text-3);font-size:.8rem;}
.footer-bottom a{color:var(--a);text-decoration:none;}

/* ── AI TUTOR (chapter/e-book pages) ─────────────────────────────── */
.fab{position:fixed;bottom:24px;right:24px;z-index:1000;width:58px;height:58px;border-radius:50%;border:none;cursor:none;
  background:linear-gradient(135deg,var(--a),var(--b));color:#fff;font-size:1.45rem;box-shadow:0 4px 24px rgba(91,140,255,.5);
  animation:fabPulse 3s ease-in-out infinite;transition:transform .25s var(--bounce),box-shadow .25s;display:flex;align-items:center;justify-content:center;}
@keyframes fabPulse{0%,100%{box-shadow:0 4px 24px rgba(91,140,255,.4);}50%{box-shadow:0 4px 40px rgba(91,140,255,.7);}}
.fab:hover{transform:scale(1.12) rotate(8deg);}
.fab.hidden{display:none!important;}
.tutor{position:fixed;bottom:96px;right:24px;z-index:999;width:396px;height:534px;
  background:rgba(5,8,22,.94);backdrop-filter:blur(30px) saturate(180%);border:1px solid var(--border);border-radius:var(--r24);
  box-shadow:0 32px 80px rgba(0,0,0,.7);display:flex;flex-direction:column;overflow:hidden;
  opacity:0;transform:translateY(20px) scale(.96);pointer-events:none;transition:all .3s var(--bounce);}
.tutor.open{opacity:1;transform:translateY(0) scale(1);pointer-events:auto;}
@media(max-width:480px){.tutor{width:calc(100% - 32px);right:16px;bottom:88px;height:65vh;}}
.tutor-head{padding:16px 18px;display:flex;justify-content:space-between;align-items:center;
  background:linear-gradient(135deg,rgba(91,140,255,.15),rgba(124,92,255,.1));border-bottom:1px solid var(--border);flex-shrink:0;}
.tutor-title{font-weight:700;font-size:.9rem;display:flex;align-items:center;gap:8px;}
.t-close{background:none;border:none;color:var(--text-3);font-size:1.1rem;cursor:none;}
.t-close:hover{color:var(--text);}
.tutor-hint{padding:10px 16px;background:rgba(91,140,255,.04);border-bottom:1px solid var(--border);flex-shrink:0;font-size:.72rem;color:var(--text-3);}
.tutor-hint strong{color:var(--a);}
.tutor-body{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:10px;}
.tutor-body::-webkit-scrollbar{width:4px;}
.tutor-body::-webkit-scrollbar-thumb{background:rgba(91,140,255,.3);border-radius:2px;}
.msg{max-width:88%;padding:11px 15px;border-radius:14px;font-size:.85rem;line-height:1.55;word-wrap:break-word;animation:msgPop .35s var(--bounce);}
@keyframes msgPop{from{opacity:0;transform:scale(.85) translateY(8px);}to{opacity:1;transform:scale(1) translateY(0);}}
.msg.user{align-self:flex-end;background:linear-gradient(135deg,var(--a),var(--b));color:#fff;border-bottom-right-radius:4px;}
.msg.bot{align-self:flex-start;background:rgba(255,255,255,.05);border:1px solid var(--border);color:var(--text);border-bottom-left-radius:4px;}
.typing{display:flex;gap:5px;padding:4px 0;}
.typing span{width:6px;height:6px;border-radius:50%;background:var(--text-3);animation:tyBounce 1.3s ease-in-out infinite;}
.typing span:nth-child(2){animation-delay:.2s;}.typing span:nth-child(3){animation-delay:.4s;}
@keyframes tyBounce{0%,60%,100%{transform:translateY(0);}30%{transform:translateY(-7px);}}
.chips{padding:0 16px 10px;display:flex;flex-wrap:wrap;gap:6px;flex-shrink:0;}
.chip{padding:5px 12px;border-radius:100px;font-size:.72rem;cursor:none;
  background:rgba(91,140,255,.08);border:1px solid rgba(91,140,255,.15);color:var(--a);transition:all .2s;}
.chip:hover{background:rgba(91,140,255,.18);border-color:rgba(91,140,255,.35);}
.tutor-inp{display:flex;gap:8px;padding:12px;border-top:1px solid var(--border);background:rgba(0,0,0,.2);flex-shrink:0;}
.tutor-input{flex:1;background:rgba(255,255,255,.05);border:1px solid var(--border);border-radius:11px;
  padding:10px 15px;color:var(--text);font-size:.85rem;outline:none;cursor:text;transition:border-color .2s;}
.tutor-input:focus{border-color:var(--a);box-shadow:0 0 0 2px rgba(91,140,255,.12);}
.tsend{padding:10px 17px;border:none;border-radius:11px;cursor:none;
  background:linear-gradient(135deg,var(--a),var(--b));color:#fff;font-weight:700;font-size:.85rem;transition:transform .2s,box-shadow .2s;}
.tsend:hover{transform:translateY(-1px);box-shadow:0 4px 16px rgba(91,140,255,.4);}
.tsend:disabled{opacity:.5;transform:none;}

/* ── ENTRY (chapter) PAGE ─────────────────────────────────────────── */
.entry-hero{padding:clamp(56px,9vw,90px) 24px 36px;text-align:center;position:relative;overflow:hidden;}
.entry-hero::before{content:'';position:absolute;left:50%;top:-30%;width:600px;height:600px;border-radius:50%;
  background:radial-gradient(circle,color-mix(in srgb,var(--ca) 10%,transparent),transparent 70%);transform:translateX(-50%);pointer-events:none;}
.issue-badge{display:inline-flex;align-items:center;gap:6px;padding:5px 16px;border-radius:100px;margin-bottom:16px;
  background:color-mix(in srgb,var(--ca) 10%,transparent);border:1px solid color-mix(in srgb,var(--ca) 25%,transparent);
  color:var(--ca);font-size:.74rem;font-weight:800;text-transform:uppercase;letter-spacing:1.3px;}
.entry-title{font-size:clamp(1.7rem,3.8vw,2.9rem);font-weight:800;line-height:1.2;margin-bottom:16px;
  background:linear-gradient(135deg,var(--text) 0%,var(--ca) 60%,var(--cb) 100%);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;}
.entry-meta{color:var(--text-3);font-size:.85rem;display:flex;justify-content:center;align-items:center;gap:14px;flex-wrap:wrap;margin-bottom:18px;}
.entry-actions{display:flex;gap:10px;justify-content:center;flex-wrap:wrap;}
.pill-btn{display:inline-flex;align-items:center;gap:6px;padding:8px 16px;border-radius:100px;font-size:.8rem;font-weight:600;
  cursor:none;border:1px solid var(--border);background:var(--card-glass);color:var(--text-2);transition:all .2s;}
.pill-btn:hover{border-color:var(--border-h);color:var(--text);transform:translateY(-1px);}
.pill-btn.on{color:var(--f);border-color:color-mix(in srgb,var(--f) 30%,transparent);}

.tldr-box{background:color-mix(in srgb,var(--ca) 6%,var(--card));border:1px solid color-mix(in srgb,var(--ca) 20%,transparent);
  border-left:3px solid var(--ca);border-radius:var(--r16);padding:18px 24px;margin-bottom:22px;
  font-size:1rem;color:var(--text-2);line-height:1.7;}
.tldr-label{font-size:.68rem;font-weight:800;text-transform:uppercase;letter-spacing:1.5px;color:var(--ca);margin-bottom:8px;}
.entry-body{max-width:780px;margin:0 auto;padding:0 20px 90px;position:relative;}

.sec{background:var(--card);border:1px solid var(--border);border-radius:var(--r24);padding:30px;margin-bottom:18px;
  position:relative;overflow:hidden;z-index:1;opacity:0;transform:translateY(30px) scale(.98);filter:blur(4px);
  transition:opacity .7s var(--smooth),transform .7s var(--bounce),filter .7s var(--smooth);}
.sec.visible{opacity:1;transform:translateY(0) scale(1);filter:blur(0);}
.sec:hover{border-color:color-mix(in srgb,var(--ca) 25%,transparent);box-shadow:0 14px 40px rgba(0,0,0,.4);}
.sec h2{font-size:1.28rem;font-weight:700;color:var(--ca);margin-bottom:18px;display:flex;align-items:center;gap:10px;}
.sec-icon{width:34px;height:34px;border-radius:10px;background:color-mix(in srgb,var(--ca) 12%,transparent);
  display:flex;align-items:center;justify-content:center;font-size:1.05rem;flex-shrink:0;}
.sec p{color:var(--text-2);margin-bottom:14px;line-height:1.8;font-size:.97rem;}
.sec ul,.sec ol{padding-left:22px;margin:12px 0;}
.sec li{color:var(--text-2);margin-bottom:9px;line-height:1.7;font-size:.94rem;}
.sec ul li::marker{color:var(--ca);}.sec ol li::marker{color:var(--cb);font-weight:700;}

.code-wrap{background:#040611;border:1px solid rgba(91,140,255,.16);border-radius:var(--r16);margin:16px 0;overflow:hidden;}
.code-head{display:flex;justify-content:space-between;align-items:center;padding:8px 16px;background:rgba(91,140,255,.06);border-bottom:1px solid rgba(91,140,255,.1);}
.code-lang{font-size:.7rem;color:var(--a);font-weight:700;text-transform:uppercase;letter-spacing:1px;}
.code-copy{background:none;border:1px solid var(--border);color:var(--text-3);padding:3px 12px;border-radius:6px;font-size:.76rem;cursor:none;transition:all .2s;}
.code-copy:hover{border-color:var(--a);color:var(--a);}
.code-copy.copied{border-color:var(--e);color:var(--e);}
.code-wrap pre{padding:20px;margin:0;font-family:var(--mono);font-size:.84rem;line-height:1.72;overflow-x:auto;color:#a5c4ff;}

.iq-q{padding:12px 16px;border-radius:10px;background:rgba(255,255,255,.03);border:1px solid var(--border);
  margin-bottom:8px;font-size:.89rem;color:var(--text-2);transition:all .2s;}
.iq-q:hover{border-color:color-mix(in srgb,var(--ca) 25%,transparent);transform:translateX(4px);color:var(--text);}

.read-ring{position:fixed;top:16px;right:16px;z-index:101;width:46px;height:46px;opacity:0;transform:scale(.7);transition:all .3s;cursor:none;}
.read-ring.show{opacity:1;transform:scale(1);}
.read-ring svg{transform:rotate(-90deg);}
.rr-bg{fill:none;stroke:rgba(255,255,255,.06);stroke-width:3;}
.rr-prog{fill:none;stroke-width:3;stroke-linecap:round;transition:stroke-dashoffset .1s;}

.btt{position:fixed;bottom:96px;right:24px;z-index:99;width:44px;height:44px;border-radius:50%;border:none;cursor:none;
  background:rgba(91,140,255,.12);border:1px solid rgba(91,140,255,.2);color:var(--a);font-size:1.02rem;
  display:flex;align-items:center;justify-content:center;opacity:0;transform:translateY(16px);pointer-events:none;transition:all .3s;}
.btt.show{opacity:1;transform:translateY(0);pointer-events:auto;}
.btt:hover{background:var(--a);color:#fff;border-color:var(--a);transform:translateY(-3px);}

#confetti{position:fixed;inset:0;pointer-events:none;z-index:9998;}
.ripple{position:fixed;border-radius:50%;pointer-events:none;z-index:9990;border:2px solid rgba(91,140,255,.5);
  transform:translate(-50%,-50%) scale(0);animation:rippleExp .6s ease-out forwards;}
@keyframes rippleExp{to{transform:translate(-50%,-50%) scale(4);opacity:0;}}

@media(max-width:768px){
  .stats-bar{gap:0;}.read-ring{display:none;}.entry-body{padding:0 12px 60px;}.sec{padding:20px;}
  .tutor{width:calc(100vw - 32px);right:16px;}.entry-row{gap:12px;}.entry-dot-col{width:32px;}
  .section-shell{padding:60px 20px;}.footer-top{grid-template-columns:1fr;}
}
@media(prefers-reduced-motion:reduce){
  *,*::before,*::after{animation-duration:.01ms!important;transition-duration:.01ms!important;}
  .cur-dot,.cur-ring{display:none;}body{cursor:auto;}html{scroll-behavior:auto;}
}
"""

JS = r"""
document.body.classList.add('page-entering');

// Theme toggle
(function(){
  const s=localStorage.getItem('dds-theme');
  if(s==='light') document.body.classList.add('light');
  const b=document.getElementById('themeBtn');
  if(b){
    b.addEventListener('click',()=>{
      document.body.classList.toggle('light');
      localStorage.setItem('dds-theme',document.body.classList.contains('light')?'light':'dark');
    });
  }
})();

// Nav blur-on-scroll
const navEl=document.querySelector('.nav');
if(navEl){ window.addEventListener('scroll',()=>{ navEl.classList.toggle('scrolled', window.scrollY>10); },{passive:true}); }

// Cursor with mouse-parallax ambient orbs
(function(){
  if(window.matchMedia('(pointer:coarse)').matches) return;
  const d=document.querySelector('.cur-dot'),r=document.querySelector('.cur-ring');
  const orbs=document.querySelectorAll('.orb');
  let mx=window.innerWidth/2,my=window.innerHeight/2,rx=mx,ry=my;
  window.addEventListener('mousemove',e=>{
    mx=e.clientX;my=e.clientY;
    if(d){d.style.left=mx+'px';d.style.top=my+'px';}
    const nx=(mx/window.innerWidth-.5), ny=(my/window.innerHeight-.5);
    orbs.forEach((o,i)=>{ const depth=(i+1)*6; o.style.transform=`translate(${nx*depth}px,${ny*depth}px)`; });
  });
  if(r){(function a(){rx+=(mx-rx)*.12;ry+=(my-ry)*.12;r.style.left=rx+'px';r.style.top=ry+'px';requestAnimationFrame(a);})();}
  document.querySelectorAll('a,button,.card,.chip,.f-card,.chap-card').forEach(el=>{
    el.addEventListener('mouseenter',()=>{if(d){d.style.width='17px';d.style.height='17px';}if(r){r.style.width='50px';r.style.height='50px';}});
    el.addEventListener('mouseleave',()=>{if(d){d.style.width='9px';d.style.height='9px';}if(r){r.style.width='38px';r.style.height='38px';}});
  });
})();

// Ripple on click
document.addEventListener('click',e=>{
  const r=document.createElement('div');
  r.className='ripple';r.style.cssText=`left:${e.clientX}px;top:${e.clientY}px;width:60px;height:60px;`;
  document.body.appendChild(r);setTimeout(()=>r.remove(),700);
});

// Dust particles
(function(){
  const c=document.getElementById('dustField');
  if(!c) return;
  for(let i=0;i<26;i++){
    const m=document.createElement('div');
    const size=1+Math.random()*2.4;
    m.className='mote';
    m.style.left=(Math.random()*100)+'%';
    m.style.width=size+'px';m.style.height=size+'px';
    m.style.setProperty('--drift',(Math.random()*80-40)+'px');
    m.style.animationDuration=(18+Math.random()*22)+'s';
    m.style.animationDelay=(-Math.random()*30)+'s';
    c.appendChild(m);
  }
})();

// Neural / knowledge-graph canvas (hero background)
(function(){
  const cv=document.getElementById('neural-canvas');
  if(!cv) return;
  const ctx=cv.getContext('2d');
  let W,H,nodes=[],raf;
  function resize(){W=cv.width=cv.offsetWidth;H=cv.height=cv.offsetHeight;}
  function init(){
    resize();
    nodes=Array.from({length:22},()=>({x:Math.random()*W,y:Math.random()*H,vx:(Math.random()-.5)*.28,vy:(Math.random()-.5)*.28,r:2+Math.random()*3,p:Math.random()*Math.PI*2}));
  }
  function draw(){
    ctx.clearRect(0,0,W,H);
    nodes.forEach(n=>{n.x+=n.vx;n.y+=n.vy;n.p+=.022;if(n.x<0||n.x>W)n.vx*=-1;if(n.y<0||n.y>H)n.vy*=-1;});
    nodes.forEach((a,i)=>{
      nodes.slice(i+1).forEach(b=>{
        const dist=Math.hypot(a.x-b.x,a.y-b.y);if(dist>170)return;
        ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);
        ctx.strokeStyle=`rgba(91,140,255,${(1-dist/170)*.26})`;ctx.lineWidth=.7;ctx.stroke();
      });
    });
    nodes.forEach(n=>{const g=.5+.5*Math.sin(n.p);ctx.beginPath();ctx.arc(n.x,n.y,n.r*(.8+.3*g),0,Math.PI*2);
      ctx.fillStyle=`rgba(91,140,255,${.35+.4*g})`;ctx.shadowBlur=10*g;ctx.shadowColor='#5B8CFF';ctx.fill();ctx.shadowBlur=0;});
    raf=requestAnimationFrame(draw);
  }
  init();draw();
  window.addEventListener('resize',()=>{cancelAnimationFrame(raf);init();draw();});
})();

// Hero dashboard mini knowledge-graph
(function(){
  const cv=document.getElementById('dash-graph');
  if(!cv) return;
  const ctx=cv.getContext('2d');
  let W,H,nodes=[],raf;
  function resize(){W=cv.width=cv.offsetWidth;H=cv.height=cv.offsetHeight;}
  function init(){
    resize();
    nodes=Array.from({length:14},()=>({x:Math.random()*W,y:Math.random()*H,vx:(Math.random()-.5)*.22,vy:(Math.random()-.5)*.22,r:2+Math.random()*2.6,p:Math.random()*Math.PI*2}));
  }
  function draw(){
    ctx.clearRect(0,0,W,H);
    nodes.forEach(n=>{n.x+=n.vx;n.y+=n.vy;n.p+=.03;if(n.x<0||n.x>W)n.vx*=-1;if(n.y<0||n.y>H)n.vy*=-1;});
    nodes.forEach((a,i)=>{
      nodes.slice(i+1).forEach(b=>{
        const dist=Math.hypot(a.x-b.x,a.y-b.y);if(dist>90)return;
        ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);
        ctx.strokeStyle=`rgba(124,92,255,${(1-dist/90)*.4})`;ctx.lineWidth=.8;ctx.stroke();
      });
    });
    nodes.forEach(n=>{const g=.5+.5*Math.sin(n.p);ctx.beginPath();ctx.arc(n.x,n.y,n.r,0,Math.PI*2);
      ctx.fillStyle=`rgba(91,140,255,${.5+.4*g})`;ctx.shadowBlur=8*g;ctx.shadowColor='#5B8CFF';ctx.fill();ctx.shadowBlur=0;});
    raf=requestAnimationFrame(draw);
  }
  init();draw();
  window.addEventListener('resize',()=>{cancelAnimationFrame(raf);init();draw();});
})();

// Scroll progress bar
const sb=document.getElementById('scrollBar');
if(sb) window.addEventListener('scroll',()=>{const s=window.scrollY,h=document.documentElement.scrollHeight-window.innerHeight;sb.style.width=(h>0?(s/h)*100:0)+'%';},{passive:true});

// Reading ring + auto mark-complete near bottom of chapter
const rr=document.getElementById('readRing');
let completedFired=false;
if(rr){
  const c=rr.querySelector('.rr-prog'),rad=c.r.baseVal.value,ci=rad*2*Math.PI;
  c.style.strokeDasharray=`${ci} ${ci}`;c.style.strokeDashoffset=ci;
  window.addEventListener('scroll',()=>{
    const s=window.scrollY,h=document.documentElement.scrollHeight-window.innerHeight,p=h>0?(s/h)*100:0;
    c.style.strokeDashoffset=ci-(p/100)*ci;rr.classList.toggle('show',p>4);
    if(p>92 && !completedFired && typeof CURRENT_ISSUE!=='undefined'){
      completedFired=true;
      const done=JSON.parse(localStorage.getItem('dds-completed')||'[]');
      if(!done.includes(CURRENT_ISSUE)){ done.push(CURRENT_ISSUE); localStorage.setItem('dds-completed',JSON.stringify(done)); }
    }
  },{passive:true});
}

// Back to top
const btt=document.getElementById('btt');
if(btt){window.addEventListener('scroll',()=>btt.classList.toggle('show',window.scrollY>400),{passive:true});btt.addEventListener('click',()=>window.scrollTo({top:0,behavior:'smooth'}));}

// Scrollytelling reveal
const io=new IntersectionObserver(e=>{e.forEach(x=>{if(x.isIntersecting){x.target.classList.add('visible');io.unobserve(x.target);}});},{threshold:.1,rootMargin:'0px 0px -60px 0px'});
document.querySelectorAll('.sec,.entry-row,.f-card,.tl-step').forEach(el=>io.observe(el));

// Accordion: week header click-to-expand (LMS style)
document.querySelectorAll('.week-header').forEach(h=>{
  h.addEventListener('click',()=>{
    const panel=h.nextElementSibling;
    const willOpen=!panel.classList.contains('open');
    panel.classList.toggle('open',willOpen);
    h.classList.toggle('open',willOpen);
    if(willOpen){
      panel.querySelectorAll('.entry-row').forEach((r,i)=>{ r.style.setProperty('--i',i); r.classList.add('visible'); });
    }
  });
});
document.querySelectorAll('.week-panel.open .entry-row').forEach((r,i)=>{ r.style.setProperty('--i',i); r.classList.add('visible'); });

// Bookmarks (chapter cards on roadmap)
function getBookmarks(){ try{return JSON.parse(localStorage.getItem('dds-bookmarks')||'[]');}catch{return [];} }
function setBookmarks(arr){ localStorage.setItem('dds-bookmarks',JSON.stringify(arr)); }
function refreshBookmarkUI(){
  const marks=getBookmarks();
  document.querySelectorAll('.bookmark-btn[data-issue]').forEach(btn=>{
    const num=parseInt(btn.dataset.issue,10);
    btn.classList.toggle('on', marks.includes(num));
    btn.textContent = marks.includes(num) ? '★' : '☆';
  });
}
document.querySelectorAll('.bookmark-btn[data-issue]').forEach(btn=>{
  btn.addEventListener('click',e=>{
    e.preventDefault(); e.stopPropagation();
    const num=parseInt(btn.dataset.issue,10);
    let marks=getBookmarks();
    if(marks.includes(num)) marks=marks.filter(n=>n!==num); else marks.push(num);
    setBookmarks(marks); refreshBookmarkUI();
  });
});
refreshBookmarkUI();

// Completed badges on roadmap cards
(function(){
  const done=JSON.parse(localStorage.getItem('dds-completed')||'[]');
  document.querySelectorAll('.card[data-issue]').forEach(card=>{
    const num=parseInt(card.dataset.issue,10);
    if(done.includes(num)){
      const foot=card.querySelector('.card-badges');
      if(foot && !foot.querySelector('.complete-badge')){
        const b=document.createElement('span'); b.className='complete-badge'; b.textContent='✓ Read';
        foot.appendChild(b);
      }
    }
  });
})();

// 3D tilt on cards
(function(){
  if(window.matchMedia('(pointer:coarse)').matches) return;
  document.querySelectorAll('.card,.f-card,.chap-card').forEach(card=>{
    card.addEventListener('mousemove',e=>{
      const r=card.getBoundingClientRect();
      const rx=((e.clientY-r.top)/r.height-.5)*-5;
      const ry=((e.clientX-r.left)/r.width-.5)*5;
      card.style.transform=`translateY(-4px) rotateX(${rx}deg) rotateY(${ry}deg)`;
    });
    card.addEventListener('mouseleave',()=>{ card.style.transform=''; });
  });
})();

// Bold click transition — native Cross-Document View Transitions on Chromium, JS zoom fallback elsewhere
(function(){
  const supportsVT = CSS.supports && CSS.supports('selector(::view-transition)');
  document.querySelectorAll('.card[href]').forEach(card=>{
    card.addEventListener('click', e=>{
      if(e.target.closest('.bookmark-btn')) return;
      if(supportsVT) return;
      e.preventDefault();
      const href=card.getAttribute('href');
      card.classList.add('zoom-launch');
      setTimeout(()=>{ window.location.href=href; },440);
    });
  });
})();

// Magnetic buttons
document.querySelectorAll('.btn-primary,.btn-secondary,.magnetic').forEach(b=>{
  b.addEventListener('mousemove',e=>{const r=b.getBoundingClientRect(),dx=e.clientX-(r.left+r.width/2),dy=e.clientY-(r.top+r.height/2);b.style.transform=`translate(${dx*.16}px,${dy*.16}px)`;});
  b.addEventListener('mouseleave',()=>b.style.transform='');
});

// Count-up stat numbers
document.querySelectorAll('[data-t]').forEach(el=>{
  const t=parseInt(el.dataset.t,10);if(isNaN(t)||el.dataset.date)return;
  let n=0;const st=Math.ceil(t/50),iv=setInterval(()=>{n=Math.min(n+st,t);el.textContent=n;if(n>=t)clearInterval(iv);},20);
});

// Category filter chips + search combined
const askIn=document.getElementById('askIn'), askGo=document.getElementById('askGo'), askAns=document.getElementById('askAns'), searchCount=document.getElementById('searchCount');
let activeCategory=null, searchTO;
function applyFilters(){
  const q=(askIn?askIn.value.trim():'').toLowerCase();
  let v=0;
  document.querySelectorAll('.week-block').forEach(block=>{
    const header=block.querySelector('.week-header');
    const panel=block.querySelector('.week-panel');
    let anyMatch=false;
    panel.querySelectorAll('.entry-row').forEach(row=>{
      const cardCat=row.querySelector('.card')?.dataset.cat || '';
      const textMatch=!q||row.innerText.toLowerCase().includes(q);
      const catMatch=!activeCategory||cardCat===activeCategory;
      const m=textMatch&&catMatch;
      row.style.display=m?'flex':'none';
      if(m){ anyMatch=true; v++; }
    });
    block.style.display=anyMatch?'block':'none';
    if((q||activeCategory) && anyMatch && !panel.classList.contains('open')){
      panel.classList.add('open'); header.classList.add('open');
      panel.querySelectorAll('.entry-row').forEach((r,i)=>{ r.style.setProperty('--i',i); r.classList.add('visible'); });
    }
  });
  if(searchCount){searchCount.textContent=`${v} chapter${v!==1?'s':''} found`;searchCount.classList.toggle('show',!!(q||activeCategory));}
}
if(askIn){
  askIn.addEventListener('input',()=>{clearTimeout(searchTO);searchTO=setTimeout(applyFilters,260);});
  document.addEventListener('keydown',e=>{
    if(e.key==='/'&&document.activeElement!==askIn){e.preventDefault();askIn.focus();}
    if(e.key==='Escape'&&document.activeElement===askIn){askIn.value='';askIn.blur();activeCategory=null;document.querySelectorAll('.cat-chip').forEach(c=>c.classList.remove('active'));applyFilters();if(askAns)askAns.classList.remove('show');}
  });
}
document.querySelectorAll('.cat-chip[data-cat]').forEach(chip=>{
  chip.addEventListener('click',()=>{
    const cat=chip.dataset.cat;
    if(activeCategory===cat){ activeCategory=null; chip.classList.remove('active'); }
    else{ activeCategory=cat; document.querySelectorAll('.cat-chip').forEach(c=>c.classList.remove('active')); chip.classList.add('active'); }
    applyFilters();
  });
});
if(askGo){
  askGo.addEventListener('click', async ()=>{
    const q=askIn.value.trim();
    if(!q) return;
    askGo.disabled=true; askGo.textContent='Thinking…';
    const ans = await callGemini(q);
    askGo.disabled=false; askGo.textContent='Ask AI';
    if(askAns){
      askAns.innerHTML = ans ? `<div class="ask-answer-label">🧠 AI Tutor</div>${ans.replace(/\n/g,'<br>')}` : `<div class="ask-answer-label">🧠 AI Tutor</div>No API key set yet — click again and paste a free Gemini key when prompted.`;
      askAns.classList.add('show');
    }
  });
}
document.querySelectorAll('.suggest-chip[data-q]').forEach(s=>{
  s.addEventListener('click',()=>{ if(askIn){ askIn.value=s.dataset.q; askIn.focus(); if(askGo) askGo.click(); } });
});

// Typewriter cycling placeholder for ask input (only if empty & unfocused)
(function(){
  if(!askIn) return;
  const phrases=['Explain issue #5','What topics cover LLMs?','Search anything you\\'ve learned...','Compare RAG vs Agentic RAG','Summarize the last 3 chapters'];
  let pi=0, ci=0, deleting=false;
  function tick(){
    if(document.activeElement===askIn || askIn.value){ setTimeout(tick,600); return; }
    const full=phrases[pi];
    ci += deleting ? -1 : 1;
    askIn.setAttribute('placeholder', full.slice(0,ci));
    let delay = deleting ? 30 : 55;
    if(!deleting && ci===full.length){ delay=1400; deleting=true; }
    else if(deleting && ci===0){ deleting=false; pi=(pi+1)%phrases.length; delay=400; }
    setTimeout(tick,delay);
  }
  tick();
})();

// Copy code
document.querySelectorAll('.code-copy').forEach(b=>{
  b.addEventListener('click',async()=>{
    const code=b.closest('.code-wrap').querySelector('pre code').textContent;
    try{await navigator.clipboard.writeText(code);b.textContent='Copied!';b.classList.add('copied');setTimeout(()=>{b.textContent='Copy';b.classList.remove('copied');},2000);}
    catch{b.textContent='Failed';setTimeout(()=>b.textContent='Copy',2000);}
  });
});

// Confetti at end of chapter
let cf=false;
window.addEventListener('scroll',()=>{if(cf)return;const s=window.scrollY,h=document.documentElement.scrollHeight-window.innerHeight;if(h>0&&(s/h)>.95){cf=true;fireConfetti();}},{passive:true});
function fireConfetti(){
  const cv=document.getElementById('confetti');if(!cv)return;
  const ctx=cv.getContext('2d');cv.width=window.innerWidth;cv.height=window.innerHeight;
  const cols=['#5B8CFF','#7C5CFF','#22d3ee','#a78bfa','#34d399','#fbbf24'];
  const ps=Array.from({length:110},()=>({x:window.innerWidth/2,y:window.innerHeight/2,vx:(Math.random()-.5)*17,vy:(Math.random()-.5)*17-6,c:cols[Math.floor(Math.random()*cols.length)],s:Math.random()*6+2,l:1,d:.01+Math.random()*.01}));
  (function a(){ctx.clearRect(0,0,cv.width,cv.height);let al=false;ps.forEach(p=>{if(p.l<=0)return;al=true;p.x+=p.vx;p.y+=p.vy;p.vy+=.28;p.l-=p.d;ctx.globalAlpha=p.l;ctx.fillStyle=p.c;ctx.beginPath();ctx.arc(p.x,p.y,p.s,0,Math.PI*2);ctx.fill();});
  if(al)requestAnimationFrame(a);else ctx.clearRect(0,0,cv.width,cv.height);})();
}

// AI Tutor (chapter/e-book floating panel)
function openTutor(){document.getElementById('tutorPanel').classList.add('open');document.getElementById('tutorFab').classList.add('hidden');}
function closeTutor(){document.getElementById('tutorPanel').classList.remove('open');document.getElementById('tutorFab').classList.remove('hidden');}
async function tutorSend(){
  const inp=document.getElementById('tutorIn'),body=document.getElementById('tutorBody'),btn=document.getElementById('tSend'),msg=inp.value.trim();
  if(!msg)return;
  addMsg(msg,'user');inp.value='';btn.disabled=true;
  const tid='t'+Date.now();
  body.insertAdjacentHTML('beforeend',`<div class="msg bot" id="${tid}"><div class="typing"><span></span><span></span><span></span></div></div>`);
  body.scrollTop=body.scrollHeight;
  const ans=await callGemini(msg)||"No API key found. Get a free Gemini key at aistudio.google.com";
  document.getElementById(tid).remove();addMsg(ans,'bot');btn.disabled=false;
}
function addMsg(text,role){
  const body=document.getElementById('tutorBody'),d=document.createElement('div');
  d.className=`msg ${role}`;d.textContent=text;body.appendChild(d);body.scrollTop=body.scrollHeight;
}
async function callGemini(msg){
  const k=(typeof GEMINI_KEY_JS!=='undefined'&&GEMINI_KEY_JS)?GEMINI_KEY_JS:(localStorage.getItem('dds-gemini')||'');
  if(!k) { const nk=prompt('Enter your FREE Gemini API key (get at aistudio.google.com):'); if(nk&&nk.trim()){ localStorage.setItem('dds-gemini',nk.trim()); return callGemini(msg);} return null; }
  try{
    const ctx=typeof TUTOR_CTX!=='undefined'?TUTOR_CTX:'';
    const prompt_=`You are an expert AI tutor for Daily Dose of DS newsletter content. Use this index to answer:\n\n${ctx}\n\nUser: ${msg}\n\nRules: Answer from the index above. If asked to explain an issue by number, explain thoroughly and cite issue number + date.`;
    const res=await fetch(`https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-8b:generateContent?key=${k}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({contents:[{parts:[{text:prompt_}]}]})});
    const d=await res.json();return d.candidates?.[0]?.content?.parts?.[0]?.text||null;
  }catch(e){return null;}
}
document.querySelectorAll('.chip[data-q]').forEach(c=>{c.addEventListener('click',()=>{const inp=document.getElementById('tutorIn');if(inp){inp.value=c.dataset.q||c.textContent; tutorSend();}});});
document.getElementById('tutorIn')?.addEventListener('keypress',e=>{if(e.key==='Enter')tutorSend();});

// Chapter page: bookmark + mark-complete pill buttons
(function(){
  const bmBtn=document.getElementById('chapterBookmark');
  const cmBtn=document.getElementById('chapterComplete');
  if(typeof CURRENT_ISSUE==='undefined') return;
  function refresh(){
    const marks=getBookmarks();
    if(bmBtn){ bmBtn.classList.toggle('on', marks.includes(CURRENT_ISSUE)); bmBtn.innerHTML = marks.includes(CURRENT_ISSUE) ? '★ Bookmarked' : '☆ Bookmark'; }
    const done=JSON.parse(localStorage.getItem('dds-completed')||'[]');
    if(cmBtn){ cmBtn.classList.toggle('on', done.includes(CURRENT_ISSUE)); cmBtn.innerHTML = done.includes(CURRENT_ISSUE) ? '✓ Completed' : '○ Mark Complete'; }
  }
  if(bmBtn){ bmBtn.addEventListener('click',()=>{ let m=getBookmarks(); if(m.includes(CURRENT_ISSUE)) m=m.filter(n=>n!==CURRENT_ISSUE); else m.push(CURRENT_ISSUE); setBookmarks(m); refresh(); }); }
  if(cmBtn){ cmBtn.addEventListener('click',()=>{ let d=JSON.parse(localStorage.getItem('dds-completed')||'[]'); if(d.includes(CURRENT_ISSUE)) d=d.filter(n=>n!==CURRENT_ISSUE); else d.push(CURRENT_ISSUE); localStorage.setItem('dds-completed',JSON.stringify(d)); refresh(); }); }
  refresh();
})();
"""

# ── HTML helpers ──────────────────────────────────────────────────────────────

def esc(t: str) -> str:
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def head_html(title: str, ca: str = "#5B8CFF", cb: str = "#7C5CFF") -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{esc(title)} | Daily Dose of DS</title>
<meta name="description" content="AI-powered learning roadmap generated automatically from Daily Dose of Data Science newsletters">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=Fira+Code:wght@400;500&display=swap" rel="stylesheet">
<style>:root{{--ca:{ca};--cb:{cb};}}</style>
<style>{CSS}</style>
</head>"""

def nav_html(back=False) -> str:
    back_link = '<a href="../index.html" class="nav-link">← Roadmap</a>' if back else ''
    home = '../index.html' if back else 'index.html'
    ebook = '../ebook.html' if back else 'ebook.html'
    idx_anchor = f'{home}#roadmap'
    feat_anchor = f'{home}#features'
    search_anchor = f'{home}#ai-search'
    return f"""
<nav class="nav">
  <div class="nav-in">
    <a href="{home}" class="nav-logo" style="cursor:none">
      <div class="gem">📚</div><span>{SITE_TITLE}</span>
    </a>
    <div class="nav-links">
      <a href="{home}" class="nav-link">Home</a>
      <a href="{idx_anchor}" class="nav-link">Roadmap</a>
      <a href="{ebook}" class="nav-link">Chapters</a>
      <a href="{feat_anchor}" class="nav-link">Features</a>
      <a href="{search_anchor}" class="nav-link">Search</a>
      <a href="https://github.com/Rishichamp/daily-dose-site" target="_blank" class="nav-link">GitHub</a>
      {back_link}
    </div>
    <div class="nav-right">
      <button class="theme-switch" id="themeBtn" title="Toggle theme" aria-label="Toggle theme">
        <span class="thumb">☀️</span>
      </button>
      <a href="{idx_anchor}" class="nav-cta magnetic">Start Learning</a>
    </div>
  </div>
</nav>"""

def ambient_layers() -> str:
    return """
<div class="aurora"><div class="orb"></div><div class="orb"></div><div class="orb"></div><div class="orb"></div></div>
<div class="dust" id="dustField"></div>
<div class="grid-bg"></div>
<div class="cur-dot"></div><div class="cur-ring"></div>
<div class="scroll-bar" id="scrollBar"></div>"""

def tutor_widget(tutor_ctx_js: str, topic_hint: str = "") -> str:
    hint = f'<br><br>You are reading: <strong>{esc(topic_hint)}</strong>' if topic_hint else ''
    return f"""
<button class="fab" id="tutorFab" onclick="openTutor()">🧠</button>
<div class="tutor" id="tutorPanel">
  <div class="tutor-head">
    <div class="tutor-title"><span class="dot-live"></span>AI Study Tutor</div>
    <button class="t-close" onclick="closeTutor()">✕</button>
  </div>
  <div class="tutor-hint">Ask me to <strong>explain any issue by number</strong> — e.g. "Explain issue #5"</div>
  <div class="tutor-body" id="tutorBody">
    <div class="msg bot">👋 Hi! I know every {SITE_TITLE} chapter.{hint}</div>
  </div>
  <div class="chips">
    <span class="chip" data-q="Explain issue #1">Issue #1</span>
    <span class="chip" data-q="What topics have been covered?">All topics</span>
    <span class="chip" data-q="Which issues cover LLMs?">LLMs</span>
  </div>
  <div class="tutor-inp">
    <input class="tutor-input" id="tutorIn" placeholder='Try "Explain issue #7"...'>
    <button class="tsend" id="tSend" onclick="tutorSend()">Ask</button>
  </div>
</div>
<script>const GEMINI_KEY_JS='';const TUTOR_CTX={tutor_ctx_js};</script>"""

def common_tail(extra_head: str = "") -> str:
    return f"""
{extra_head}
<button class="btt" id="btt">↑</button>
<canvas id="confetti"></canvas>
<script>{JS}</script>"""

def dashboard_visual_html() -> str:
    """Hero right-side AI dashboard mock illustration."""
    return """
<div class="hero-visual">
  <div class="dash-panel dash-main">
    <div class="dm-head">
      <span class="dm-title">📈 Learning Progress</span>
      <span class="dm-dots"><span></span><span></span><span></span></span>
    </div>
    <canvas id="dash-graph"></canvas>
    <div class="dm-legend">
      <span class="dm-chip">Machine Learning</span>
      <span class="dm-chip">LLMs</span>
      <span class="dm-chip">Deep Learning</span>
    </div>
  </div>
  <div class="dash-panel dash-float dash-float-1">
    <div class="df-cat">Chapter #47</div>
    <div class="df-title">How LLM Routing Works</div>
    <div class="df-bar"><div class="df-bar-fill" style="width:82%"></div></div>
  </div>
  <div class="dash-panel dash-float dash-float-2">
    <div class="df-cat">Chapter #12</div>
    <div class="df-title">Function Approximation in RL</div>
    <div class="df-bar"><div class="df-bar-fill" style="width:64%"></div></div>
  </div>
</div>"""


FEATURES = [
    ("📬", "Daily Newsletter Parsing", "Every morning, your Gmail is checked automatically for the latest Daily Dose of Data Science issue — no manual copy-pasting, ever."),
    ("🧠", "AI Topic Extraction", "Gemini reads each newsletter, strips ads and tracking links, and identifies the core concepts worth learning."),
    ("📖", "Automatic Chapter Generation", "Every issue becomes a structured chapter — overview, deep-dive sections, code, key takeaways, and interview questions."),
    ("🗺️", "Roadmap Builder", "Chapters are organized chronologically into a week-by-week roadmap, so you can see your learning journey unfold."),
    ("🔍", "Smart Search", "Instantly filter chapters by keyword or category, or ask the AI tutor a direct question about anything you've covered."),
    ("🔖", "Bookmark Lessons", "Star any chapter to save it for later — bookmarks are stored right in your browser, no account needed."),
    ("✅", "Progress Tracking", "Chapters you've read to the end are automatically marked complete, so you always know where you left off."),
]

HOW_IT_WORKS = [
    ("📧", "Daily Dose of DS Email Arrives", "Every morning around 5 AM, the newsletter lands in your inbox."),
    ("🤖", "AI Reads the Newsletter", "GitHub Actions wakes up at 7 AM and fetches the new email via the Gmail API."),
    ("🧹", "Extracts Resources", "Tracking links, ads, and footers are stripped out — only the educational content remains."),
    ("🧩", "Groups by Concepts", "Gemini identifies the core topics and structures them into logical sections."),
    ("📚", "Builds Chapters", "A polished chapter page is generated — overview, explanations, code, takeaways, and interview questions."),
    ("🗺️", "Generates the Roadmap", "The chapter is slotted into its week on the chronological roadmap, and the database is updated."),
    ("✨", "Displays the Learning Path", "Your site redeploys automatically — the new chapter is live, with zero manual work."),
]

TESTIMONIALS = [
    ("Aisha Rahman", "ML Engineer", "I stopped losing newsletter issues in my inbox. Everything's organized into a roadmap I actually revisit."),
    ("Daniel Cho", "Data Scientist", "The AI tutor answering questions about old issues is genuinely useful before interviews."),
    ("Priya Nandakumar", "Grad Student", "Turns a daily 5-minute read into a proper structured course I can search through later."),
]


# ── Site Builder ──────────────────────────────────────────────────────────────

def week_start(d: datetime) -> datetime:
    return d - timedelta(days=d.weekday())

class SiteBuilder:
    def __init__(self):
        self.out = Path(OUT_DIR)
        self.out.mkdir(exist_ok=True)
        (self.out / "entries").mkdir(exist_ok=True)

    def build_entry(self, email: RawEmail, note: StudyNote, tutor_ctx_js: str) -> str:
        ca, cb = cat_color(note.category)
        safe = re.sub(r'[^\w\s-]', '', note.topic).strip().replace(' ', '-')[:50]
        fname = f"entries/{note.date}_issue{note.issue_number:03d}_{safe}.html"
        fpath = self.out / fname
        d_disp = datetime.strptime(note.date, "%Y-%m-%d").strftime("%B %d, %Y")
        mins = estimate_minutes(note)

        content_html = ""
        if note.tldr:
            content_html += f"""
<div class="tldr-box" style="--ca:{ca};--cb:{cb}">
  <div class="tldr-label">TL;DR</div>
  <p style="margin:0">{esc(note.tldr)}</p>
</div>"""
        if note.overview:
            paras = "\n".join(f"<p>{esc(p)}</p>" for p in note.overview.split("\n") if p.strip())
            content_html += f"""
<div class="sec">
  <h2><span class="sec-icon">📋</span>Overview</h2>
  {paras}
</div>"""

        icons = ["🔬","💡","⚙️","🏗️","📊","🔧","🎯","🌐"]
        for i, sec in enumerate(note.sections):
            body_paras = "\n".join(f"<p>{esc(p)}</p>" for p in sec["body"].split("\n") if p.strip())
            code_html = ""
            if sec.get("code"):
                code_html = f"""
<div class="code-wrap">
  <div class="code-head"><span class="code-lang">Python</span><button class="code-copy">Copy</button></div>
  <pre><code>{esc(sec["code"])}</code></pre>
</div>"""
            content_html += f"""
<div class="sec">
  <h2><span class="sec-icon">{icons[i % len(icons)]}</span>{esc(sec["title"])}</h2>
  {body_paras}
  {code_html}
</div>"""

        if note.key_points:
            items = "\n".join(f"<li>{esc(k)}</li>" for k in note.key_points)
            content_html += f"""
<div class="sec">
  <h2><span class="sec-icon">📌</span>Key Takeaways</h2>
  <ul>{items}</ul>
</div>"""
        if note.interview_qs:
            qs = "\n".join(f'<div class="iq-q">{esc(q)}</div>' for q in note.interview_qs)
            content_html += f"""
<div class="sec">
  <h2><span class="sec-icon">🎯</span>Interview Questions</h2>
  {qs}
</div>"""
        if note.further:
            items = "\n".join(f"<li>{esc(f)}</li>" for f in note.further)
            content_html += f"""
<div class="sec">
  <h2><span class="sec-icon">📚</span>Further Reading</h2>
  <ul>{items}</ul>
</div>"""

        html = f"""{head_html(note.topic, ca, cb)}
<body>
{ambient_layers()}
<div class="read-ring" id="readRing">
  <svg width="46" height="46" viewBox="0 0 48 48">
    <defs><linearGradient id="rg" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="{ca}"/><stop offset="100%" stop-color="{cb}"/>
    </linearGradient></defs>
    <circle class="rr-bg" cx="24" cy="24" r="20"/>
    <circle class="rr-prog" cx="24" cy="24" r="20" stroke="url(#rg)"/>
  </svg>
</div>
{nav_html(back=True)}
<div class="entry-hero" style="--ca:{ca};--cb:{cb}">
  <div class="issue-badge">Issue #{note.issue_number} · {esc(note.category)} · {mins} min read</div>
  <h1 class="entry-title">{esc(note.topic)}</h1>
  <div class="entry-meta"><span>📅 {d_disp}</span><span>·</span><span>📬 Daily Dose of DS</span></div>
  <div class="entry-actions">
    <button class="pill-btn" id="chapterBookmark">☆ Bookmark</button>
    <button class="pill-btn" id="chapterComplete">○ Mark Complete</button>
  </div>
</div>
<div class="entry-body" style="--ca:{ca};--cb:{cb}">
  {content_html}
</div>
<div class="footer" style="border-top:1px solid var(--border);text-align:center;padding:30px;">
  <a href="../index.html" style="color:var(--a);text-decoration:none;">← Back to roadmap</a> &nbsp;·&nbsp; {SITE_TITLE}
</div>
{common_tail(tutor_widget(tutor_ctx_js, note.topic))}
<script>const CURRENT_ISSUE={note.issue_number};</script>
</body></html>"""
        fpath.write_text(html, encoding="utf-8")
        return fname

    def build_index(self, rows_asc, tutor_ctx_js: str):
        """rows_asc: (date, topic, html_file, subject, category, issue_number), ascending by date."""

        # ── Group into weeks ──────────────────────────────────────────
        weeks = []
        for row in rows_asc:
            ws = week_start(datetime.fromisoformat(row[0]))
            if not weeks or weeks[-1][0] != ws:
                weeks.append((ws, []))
            weeks[-1][1].append(row)

        roadmap_html = ""
        for wi, (ws, week_rows) in enumerate(weeks):
            week_label = ws.strftime("Week of %B %d")
            is_open = (wi == 0)
            rows_html = ""
            for date, topic, html_file, subject, category, issue_num in week_rows:
                ca, cb = cat_color(category or "Data Science")
                d_obj = datetime.fromisoformat(date)
                d_disp = d_obj.strftime("%d %b %Y")
                num = issue_num or 0
                desc = esc((subject or topic)[:90])
                rows_html += f"""
<div class="entry-row">
  <div class="entry-dot-col"><div class="entry-dot" style="--ca:{ca};--cb:{cb}"></div></div>
  <a href="{html_file}" class="card" data-issue="{num}" data-cat="{esc(category or 'Data Science')}" style="--ca:{ca};--cb:{cb}">
    <div class="card-issue">#{num:03d}<span class="cat-badge">{esc(category or 'DS')}</span></div>
    <div class="card-title">{esc(topic.replace('_',' '))}</div>
    <div class="card-desc">{desc}...</div>
    <div class="card-foot">
      <span class="card-date">📅 {d_disp}</span>
      <div class="card-badges">
        <button class="bookmark-btn" data-issue="{num}" title="Bookmark">☆</button>
        <div class="arrow">→</div>
      </div>
    </div>
  </a>
</div>"""
            count_label = f"{len(week_rows)} chapter{'s' if len(week_rows) != 1 else ''}"
            roadmap_html += f"""
<div class="week-block">
  <button class="week-header{' open' if is_open else ''}" type="button">
    <span class="week-header-inner">
      <span class="week-chevron">▸</span>
      <span class="week-dot"></span>
      <span class="week-label">{esc(week_label)}</span>
      <span class="week-count">{count_label}</span>
    </span>
  </button>
  <div class="week-panel{' open' if is_open else ''}">
    <div class="week-panel-inner">{rows_html}</div>
  </div>
</div>"""

        total = len(rows_asc)
        cats_present = sorted(set(r[4] for r in rows_asc if r[4]))
        cats = len(cats_present)
        latest = rows_asc[-1][0][:10] if rows_asc else "—"
        latest_file = rows_asc[-1][2] if rows_asc else "#"

        empty = """<div class="empty">
  <div class="empty-icon">📬</div>
  <h2>No chapters yet</h2>
  <p>Run <code>python build_site.py --first-run</code> to process your emails.</p>
</div>""" if not roadmap_html else ""

        # ── Category filter chips ─────────────────────────────────────
        chips_html = "".join(f'<button class="cat-chip" data-cat="{esc(c)}">{esc(c)}</button>' for c in cats_present)

        # ── Feature cards ──────────────────────────────────────────────
        feature_cards = "".join(f"""
<div class="f-card">
  <div class="f-icon">{icon}</div>
  <div class="f-title">{esc(title)}</div>
  <div class="f-desc">{esc(desc)}</div>
</div>""" for icon, title, desc in FEATURES)

        # ── How it works timeline ──────────────────────────────────────
        tl_steps = "".join(f"""
<div class="tl-step">
  <div class="tl-num">{icon}</div>
  <div class="tl-body"><div class="tl-title">{esc(title)}</div><div class="tl-desc">{esc(desc)}</div></div>
</div>""" for icon, title, desc in HOW_IT_WORKS)

        # ── Chapters preview strip (latest 6) ──────────────────────────
        latest_rows = list(reversed(rows_asc))[:6]
        chap_cards = ""
        for date, topic, html_file, subject, category, issue_num in latest_rows:
            ca, cb = cat_color(category or "Data Science")
            diff = cat_difficulty(category or "Data Science")
            d_disp = datetime.fromisoformat(date).strftime("%d %b")
            chap_cards += f"""
<a href="{html_file}" class="chap-card" style="--ca:{ca};--cb:{cb}">
  <div class="chap-top"><span class="chap-diff">{esc(diff)}</span><span class="chap-time">📅 {d_disp}</span></div>
  <div class="chap-title">{esc(topic.replace('_',' '))}</div>
  <div class="chap-tags"><span class="chap-tag">{esc(category or 'DS')}</span><span class="chap-tag">#{issue_num or 0:03d}</span></div>
</a>"""

        # ── Testimonials ────────────────────────────────────────────────
        testi_cards = "".join(f"""
<div class="testi-card">
  <div class="testi-quote">"{esc(quote)}"</div>
  <div class="testi-person">
    <div class="testi-avatar">{esc(name[0])}</div>
    <div><div class="testi-name">{esc(name)}</div><div class="testi-role">{esc(role)}</div></div>
  </div>
</div>""" for name, role, quote in TESTIMONIALS)

        html = f"""{head_html(SITE_TITLE)}
<body>
{ambient_layers()}
{nav_html()}

<div class="hero">
  <canvas id="neural-canvas"></canvas>
  <div class="hero-grid">
    <div class="hero-copy">
      <div class="badge"><span class="dot-live"></span>Auto-Updated Daily</div>
      <h1>Master AI &amp; Data Science <span class="grad-text">One Chapter at a Time</span></h1>
      <p class="hero-sub">An AI-powered learning roadmap, automatically generated every morning from Daily Dose of Data Science newsletters — cleaned, structured, and organized into a chronological journey.</p>
      <div class="hero-actions">
        <a href="#roadmap" class="btn-primary magnetic">Start Learning →</a>
        <a href="ebook.html" class="btn-secondary magnetic">📖 Browse Chapters</a>
        <a href="{latest_file}" class="btn-ghost magnetic">▶ View Latest Chapter</a>
      </div>
      <div class="hero-stats">
        <div><div class="hstat-n" data-t="{total}">{total}</div><div class="hstat-l">Chapters</div></div>
        <div><div class="hstat-n" data-t="{cats}">{cats}</div><div class="hstat-l">Topics</div></div>
        <div><div class="hstat-n" data-date="true">{latest}</div><div class="hstat-l">Latest</div></div>
      </div>
    </div>
    {dashboard_visual_html()}
  </div>
</div>

<div class="stats-bar">
  <div class="sb-item"><div class="sb-n">100%</div><div class="sb-l">Automated</div></div>
  <div class="sb-item"><div class="sb-n">7 AM</div><div class="sb-l">Daily Sync</div></div>
  <div class="sb-item"><div class="sb-n">{total}</div><div class="sb-l">Chapters Built</div></div>
  <div class="sb-item"><div class="sb-n">0</div><div class="sb-l">Manual Work</div></div>
</div>

<div class="section-shell" id="features">
  <div class="section-head">
    <span class="section-kicker">Features</span>
    <h2 class="section-title">Everything runs itself</h2>
    <p class="section-sub">From your inbox to a searchable knowledge base — no manual steps anywhere in the pipeline.</p>
  </div>
  <div class="feature-grid">{feature_cards}</div>
</div>

<div class="section-shell">
  <div class="section-head">
    <span class="section-kicker">How It Works</span>
    <h2 class="section-title">From newsletter to knowledge, automatically</h2>
    <p class="section-sub">Every morning, this pipeline runs end-to-end with zero human involvement.</p>
  </div>
  <div class="timeline"><div class="tl-line"></div>{tl_steps}</div>
</div>

<div class="section-shell" id="ai-search">
  <div class="section-head">
    <span class="section-kicker">AI Tutor</span>
    <h2 class="section-title">Ask anything you've learned</h2>
    <p class="section-sub">Search chapters instantly, or ask the AI tutor a direct question about any issue in your history.</p>
  </div>
  <div class="search-hero">
    <div class="ask-shell">
      <span class="ask-ico">🔍</span>
      <input class="ask-input" id="askIn" placeholder="Search anything you've learned...">
      <button class="ask-go" id="askGo">Ask AI</button>
    </div>
    <div class="ask-hint">Press / to focus · type to search, or click Ask AI to query your AI tutor</div>
    <div class="suggest-row">
      <span class="suggest-chip" data-q="Explain issue #1">Explain issue #1</span>
      <span class="suggest-chip" data-q="What topics cover LLMs?">What topics cover LLMs?</span>
      <span class="suggest-chip" data-q="Summarize the last 3 chapters">Summarize the last 3 chapters</span>
    </div>
    <div class="ask-answer"><div class="ask-answer-box" id="askAns"></div></div>
  </div>
</div>

<div class="section-shell" id="roadmap">
  <div class="section-head">
    <span class="section-kicker">Roadmap Preview</span>
    <h2 class="section-title">Your learning journey, week by week</h2>
    <p class="section-sub">Click any week to expand its chapters. Filter by topic below.</p>
  </div>
  <div class="chip-row">{chips_html}</div>
  <div class="search-count" id="searchCount"></div>
  <div class="roadmap-wrap">
    <div class="roadmap-line"></div>
    {roadmap_html or empty}
  </div>
</div>

<div class="section-shell">
  <div class="section-head">
    <span class="section-kicker">Latest Chapters</span>
    <h2 class="section-title">Freshly generated</h2>
    <p class="section-sub">The most recent additions to your knowledge base.</p>
  </div>
  <div class="chap-strip">{chap_cards}</div>
</div>

<div class="section-shell">
  <div class="section-head">
    <span class="section-kicker">Testimonials</span>
    <h2 class="section-title">What learners are saying</h2>
  </div>
  <div class="testi-grid">{testi_cards}</div>
</div>

<div class="section-shell">
  <div class="final-cta">
    <h2>Start Learning Smarter</h2>
    <p>Your roadmap updates itself every morning. Jump back in anytime.</p>
    <a href="#roadmap" class="btn-primary magnetic">Generate My Learning Roadmap →</a>
  </div>
</div>

<footer class="footer">
  <div class="footer-in">
    <div class="footer-top">
      <div>
        <div class="footer-brand"><div class="gem" style="width:28px;height:28px;font-size:.85rem;">📚</div>{SITE_TITLE}</div>
        <p class="footer-desc">An AI-powered learning roadmap automatically generated every day from Daily Dose of Data Science newsletters.</p>
      </div>
      <div class="footer-col"><h4>Explore</h4>
        <a href="#roadmap">Roadmap</a><a href="ebook.html">Chapters</a><a href="#features">Features</a><a href="#ai-search">Search</a>
      </div>
      <div class="footer-col"><h4>Project</h4>
        <a href="https://github.com/Rishichamp/daily-dose-site" target="_blank">GitHub</a>
        <a href="https://github.com/Rishichamp/daily-dose-site#readme" target="_blank">About</a>
        <a href="https://github.com/Rishichamp" target="_blank">Contact</a>
      </div>
      <div class="footer-col"><h4>Info</h4>
        <a href="https://www.dailydoseofds.com" target="_blank">Daily Dose of DS</a>
        <span style="display:block;font-size:.85rem;color:var(--text-3);margin-top:2px;">No personal data leaves your own GitHub repo.</span>
      </div>
    </div>
    <div class="footer-bottom">Auto-generated daily at 7:00 AM IST · <a href="https://www.dailydoseofds.com" target="_blank">dailydoseofds.com</a></div>
  </div>
</footer>
<script>const TUTOR_CTX={tutor_ctx_js};const GEMINI_KEY_JS='';</script>
{common_tail()}
</body></html>"""
        (self.out / "index.html").write_text(html, encoding="utf-8")
        log.info("Landing page built — %d chapters.", total)

    def build_ebook_page(self, db: DB):
        rows = db.all_for_ebook()
        if not rows:
            html = f"""{head_html("E-Book")}
<body>{ambient_layers()}{nav_html()}
<div style="text-align:center;padding:100px 20px;">
<h1 style="color:var(--a)">E-Book</h1>
<p style="color:var(--text-2);margin-top:16px">No issues processed yet. Run <code>python build_site.py --first-run</code> first.</p>
</div>{common_tail(tutor_widget("''"))}
</body></html>"""
            (self.out / "ebook.html").write_text(html, encoding="utf-8")
            return

        toc_items = ""
        chapters = ""
        for num, date, topic, note in rows:
            d_disp = datetime.strptime(date, "%Y-%m-%d").strftime("%B %d, %Y")
            ca, cb = cat_color(note.category)
            toc_items += f"""
<a href="#ch{num}" style="display:flex;align-items:center;gap:12px;padding:10px 16px;border-radius:10px;
  text-decoration:none;color:var(--text-2);transition:all .2s;border:1px solid transparent;"
  onmouseover="this.style.background='rgba(91,140,255,.08)';this.style.borderColor='rgba(91,140,255,.15)';this.style.color='var(--text)'"
  onmouseout="this.style.background='';this.style.borderColor='transparent';this.style.color='var(--text-2)'">
  <span style="color:{ca};font-weight:800;font-size:.8rem;min-width:60px">#{num:03d}</span>
  <span style="font-size:.9rem">{esc(topic.replace('_',' '))}</span>
  <span style="margin-left:auto;color:var(--text-3);font-size:.75rem">{d_disp}</span>
</a>"""
            chap = ""
            if note.tldr:
                chap += f'<div class="tldr-box" style="--ca:{ca};--cb:{cb}"><div class="tldr-label">TL;DR</div><p style="margin:0">{esc(note.tldr)}</p></div>'
            if note.overview:
                paras = "".join(f"<p>{esc(p)}</p>" for p in note.overview.split("\n") if p.strip())
                chap += f'<h3 style="color:{ca};margin:22px 0 10px">Overview</h3>{paras}'
            for sec in note.sections:
                paras = "".join(f"<p>{esc(p)}</p>" for p in sec["body"].split("\n") if p.strip())
                chap += f'<h3 style="color:{ca};margin:22px 0 10px">{esc(sec["title"])}</h3>{paras}'
                if sec.get("code"):
                    chap += f'<div class="code-wrap"><div class="code-head"><span class="code-lang">Python</span><button class="code-copy">Copy</button></div><pre><code>{esc(sec["code"])}</code></pre></div>'
            if note.key_points:
                items = "".join(f"<li>{esc(k)}</li>" for k in note.key_points)
                chap += f'<h3 style="color:{ca};margin:22px 0 10px">Key Takeaways</h3><ul>{items}</ul>'

            chapters += f"""
<div id="ch{num}" class="sec" style="--ca:{ca};--cb:{cb};margin-bottom:24px;">
  <div style="display:flex;align-items:baseline;gap:12px;margin-bottom:6px;">
    <span style="font-size:.72rem;font-weight:800;color:{ca};text-transform:uppercase;letter-spacing:1.4px">Chapter {num}</span>
    <span style="font-size:.72rem;color:var(--text-3)">{d_disp} · {esc(note.category)}</span>
  </div>
  <h2 style="font-size:clamp(1.3rem,3vw,1.9rem);font-weight:800;margin-bottom:16px;
    background:linear-gradient(135deg,var(--text) 0%,{ca} 60%,{cb} 100%);
    -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text">
    {esc(topic.replace('_',' '))}
  </h2>
  {chap}
  <a href="#toc" style="display:inline-flex;align-items:center;gap:6px;color:{ca};text-decoration:none;font-size:.83rem;margin-top:16px;opacity:.7;transition:opacity .2s"
    onmouseover="this.style.opacity='1'" onmouseout="this.style.opacity='.7'">↑ Back to Contents</a>
</div>"""

        html = f"""{head_html("Complete E-Book | Daily Dose of DS")}
<body>
{ambient_layers()}
<div class="read-ring" id="readRing">
  <svg width="46" height="46" viewBox="0 0 48 48">
    <defs><linearGradient id="rg" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="var(--a)"/><stop offset="100%" stop-color="var(--b)"/>
    </linearGradient></defs>
    <circle class="rr-bg" cx="24" cy="24" r="20"/>
    <circle class="rr-prog" cx="24" cy="24" r="20" stroke="url(#rg)"/>
  </svg>
</div>
{nav_html(back=True)}
<div style="max-width:820px;margin:0 auto;padding:clamp(40px,6vw,70px) 24px 80px;">
  <div style="text-align:center;padding:56px 20px;margin-bottom:50px;background:var(--card);border:1px solid var(--border);border-radius:var(--r24);position:relative;overflow:hidden;">
    <div style="position:absolute;inset:0;background:radial-gradient(ellipse at 50% 0%,rgba(91,140,255,.1),transparent 60%);pointer-events:none;"></div>
    <div style="position:relative;z-index:1;">
      <div style="font-size:3.5rem;margin-bottom:14px;">📚</div>
      <h1 style="font-size:clamp(1.8rem,4.5vw,3rem);font-weight:800;margin-bottom:10px;"><span class="grad-text">Daily Dose of DS</span></h1>
      <p style="font-size:1.1rem;color:var(--text-2);margin-bottom:6px;font-weight:600">Complete Study Notes</p>
      <p style="color:var(--text-3);font-size:.86rem">{len(rows)} Chapters · Generated {datetime.now().strftime("%B %d, %Y")}</p>
    </div>
  </div>
  <div id="toc" style="margin-bottom:50px;">
    <h2 style="font-size:1.5rem;font-weight:800;margin-bottom:20px;color:var(--a)">📑 Table of Contents</h2>
    <div style="background:var(--card);border:1px solid var(--border);border-radius:var(--r20);padding:14px;">{toc_items}</div>
  </div>
  <div id="chapters">{chapters}</div>
</div>
<div class="footer" style="border-top:1px solid var(--border);text-align:center;padding:30px;">
  <a href="index.html" style="color:var(--a);text-decoration:none;">← Back to Roadmap</a> &nbsp;·&nbsp; Daily Dose of DS E-Book
</div>
{common_tail(tutor_widget("''"))}
</body></html>"""
        (self.out / "ebook.html").write_text(html, encoding="utf-8")
        log.info("E-book built — %d chapters.", len(rows))

class App:
    def __init__(self):
        self.db = DB()
        self.ai = None
        self.gmail = None
        self.site = SiteBuilder()

    def _init_apis(self):
        self.gmail = Gmail()
        self.ai = AI()

    def _tutor_ctx(self) -> str:
        return json.dumps(self.db.tutor_context())

    def run(self, first_run: bool = False):
        log.info("=" * 55)
        log.info("Daily Dose of DS v8.0 — Mode: %s", "FULL HISTORY" if first_run else "DAILY")
        log.info("=" * 55)
        self._init_apis()

        after = None if first_run else datetime.now() - timedelta(days=1)
        messages = self.gmail.fetch_all(after)
        if not messages:
            log.info("No emails found. Rebuilding site...")
            self._rebuild()
            return

        if first_run:
            messages = list(reversed(messages))

        processed = skipped = 0
        for meta in messages:
            eid = meta["id"]
            if self.db.exists(eid):
                skipped += 1; continue
            try:
                self._process(eid); processed += 1
            except Exception as ex:
                log.error("Failed %s: %s", eid, ex)

        self._rebuild()
        log.info("Done! Processed: %d, Skipped: %d", processed, skipped)
        if processed > 0:
            self._deploy()

    def _process(self, eid: str):
        email = self.gmail.get_email(eid)
        if self.db.dup_hash(email.content_hash):
            log.info("Duplicate content, skipping."); return
        note = self.ai.enhance(email)
        note.issue_number = self.db.next_issue()
        ctx_js = self._tutor_ctx()
        html_file = self.site.build_entry(email, note, ctx_js)
        self.db.save(email.email_id, email.subject, email.date.strftime("%Y-%m-%d"),
                     note.topic, note.category, email.content_hash, html_file, note)
        log.info("✅ Issue #%d: %s [%s]", note.issue_number, note.topic, note.category)
        time.sleep(5)

    def _rebuild(self):
        rows = self.db.all_issues_asc()
        ctx_js = self._tutor_ctx()
        self.site.build_index(rows, ctx_js)
        self.site.build_ebook_page(self.db)

    def rebuild_only(self):
        log.info("Rebuilding site from existing database...")
        self._rebuild()
        log.info("Done.")

    def _deploy(self):
        log.info("Deploying to GitHub Pages...")
        try:
            # CRITICAL: commit the database too, so history persists across
            # every automated run (previously gitignored — this was the bug
            # that made old issues disappear from the roadmap).
            subprocess.run(["git", "add", "docs/", DB_FILE], check=True)
            subprocess.run(["git", "commit", "-m",
                f"🤖 Auto-update: {datetime.now().strftime('%Y-%m-%d %H:%M')} [v7]"], check=False)
            subprocess.run(["git", "push"], check=True)
            log.info("Deployed ✅")
        except Exception as e:
            log.error("Deploy failed: %s", e)

    def schedule(self):
        import schedule as sched
        sched.every().day.at("07:00").do(lambda: self.run())
        log.info("Scheduler active — runs daily at 07:00. Ctrl+C to stop.")
        while True:
            sched.run_pending(); time.sleep(60)


def main():
    p = argparse.ArgumentParser(description="Daily Dose of DS Website v8.0")
    p.add_argument("--first-run", action="store_true", help="Process ALL historical emails")
    p.add_argument("--daily", action="store_true", help="Process new emails only")
    p.add_argument("--rebuild", action="store_true", help="Rebuild site from DB (no Gmail fetch)")
    p.add_argument("--schedule", action="store_true", help="Run daily scheduler")
    args = p.parse_args()

    app = App()
    if args.schedule: app._init_apis(); app.schedule()
    elif args.rebuild: app.rebuild_only()
    else: app.run(first_run=args.first_run)

if __name__ == "__main__":
    main()
