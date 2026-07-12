#!/usr/bin/env python3
"""
Daily Dose of DS — Website Generator v6.0
==========================================
COMPLETE REWRITE — clean slate.

What this does:
  1. Connects to Gmail (OAuth2), fetches all Daily Dose of DS emails
  2. Cleans each email: removes ALL ads, tracking URLs, footers, spam
  3. Sends clean content to Gemini AI → generates beautiful study notes
     structured like the actual email (headings, explanations, code)
  4. Builds a premium website:
       - index.html  → date-ordered list of all issues, each a clickable card
       - entries/    → one page per issue with full AI-enhanced content
  5. On-demand e-book: click "Download E-Book" → PDF with all issues,
     chapter per issue, proper TOC, clean formatting — NO junk
  6. AI Tutor: ask "explain issue #7" — answers from your knowledge base
  7. Runs automatically every day at 7:00 AM via GitHub Actions

Key design decisions:
  - AI quota safe: 5s delay between emails + smart retry with Gemini's own wait time
  - Fallback: if AI fails, content is STILL clean (not raw junk) via smart extractor
  - E-book built from AI-enhanced content stored in DB, not raw email
  - All 46+ issues indexed correctly with issue numbers
"""

import os, sys, re, json, base64, sqlite3, hashlib, argparse, subprocess, time
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

# ── Config ──────────────────────────────────────────────────────────────────
SENDER          = "Daily Dose of DS"
SITE_TITLE      = "Daily Dose of DS"
AI_MODEL        = "gemini-1.5-flash-8b"
MAX_TOKENS      = 4000
DB_FILE         = "site_data.db"
TOKEN_FILE      = "token.json"
CREDS_FILE      = "credentials.json"
OUT_DIR         = "docs"
IS_CI           = bool(os.getenv("GITHUB_ACTIONS"))

from dotenv import load_dotenv
load_dotenv()
GEMINI_KEY  = os.getenv("GEMINI_API_KEY", "")
OPENAI_KEY  = os.getenv("OPENAI_API_KEY", "")

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
    body_text:    str      # cleaned plain text
    body_html:    str      # original HTML (for image extraction)
    topic:        str
    content_hash: str

@dataclass
class StudyNote:
    """One issue worth of AI-enhanced study content."""
    issue_number: int
    date:         str          # YYYY-MM-DD
    topic:        str
    category:     str
    # Sections — all plain text / markdown, NO tracking URLs
    tldr:         str = ""     # 2-3 sentence summary
    overview:     str = ""     # 3-4 paragraph intro
    sections:     list = field(default_factory=list)  # [{"title": ..., "body": ..., "code": ...}]
    key_points:   list = field(default_factory=list)
    interview_qs: list = field(default_factory=list)
    further:      list = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(self.__dict__)

    @classmethod
    def from_json(cls, s: str) -> "StudyNote":
        d = json.loads(s)
        return cls(**d)


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
    "Reinforcement Learning": ("#f97316","#ef4444"),
    "LLMs & Agents":          ("#ec4899","#8b5cf6"),
    "Deep Learning":          ("#6366f1","#a855f7"),
    "Machine Learning":       ("#06b6d4","#3b82f6"),
    "Data Engineering":       ("#8b5cf6","#ec4899"),
    "Statistics":             ("#10b981","#059669"),
    "NLP":                    ("#f59e0b","#ef4444"),
    "Python":                 ("#10b981","#06b6d4"),
    "SQL":                    ("#3b82f6","#06b6d4"),
    "Mathematics":            ("#f59e0b","#8b5cf6"),
    "Data Science":           ("#06b6d4","#8b5cf6"),
}

def detect_category(text: str) -> str:
    low = text.lower()
    for cat, kws in CAT_KW.items():
        if any(k in low for k in kws):
            return cat
    return "Data Science"

def cat_color(cat: str):
    return CAT_COLOR.get(cat, CAT_COLOR["Data Science"])


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

    def all_issues(self, order="DESC"):
        return self.conn.execute(
            f"SELECT date,topic,html_file,subject,category,issue_number FROM issues "
            f"WHERE processed=1 ORDER BY date {order}").fetchall()

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
        msgs = []
        token = None
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
        clean_text  = self._clean(plain or self._html2text(html))
        topic       = self._make_topic(subject, clean_text)
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
            p2, h2 = self._extract_parts(part, depth+1)
            plain = plain or p2
            html  = html  or h2
        return plain, html

    def _html2text(self, html: str) -> str:
        """Convert HTML to clean plain text."""
        try:
            from html.parser import HTMLParser
            class H2T(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self.result = []
                    self.skip = False
                def handle_data(self, d): 
                    if not self.skip: self.result.append(d)
                def get_text(self): return "".join(self.result)
            p = H2T()
            p.feed(html)
            return p.get_text()
        except Exception:
            return re.sub(r"<[^>]+>", " ", html)

    def _clean(self, text: str) -> str:
        """
        Deep clean: remove ALL tracking URLs, ads, footers, promo sections.
        Keep ONLY educational content.
        """
        # 1. Strip tracking/encoded URLs
        text = re.sub(r'\(\s*https?://[^\s)]*(?:click\.kit|fff97757|tracking|aHR0c)[^\s)]*\s*\)', "", text)
        text = re.sub(r'https?://[^\s)>]*aHR0c[^\s)>]*', "", text)
        # Remove any URL in parens longer than 80 chars (always tracking)
        text = re.sub(r'\(\s*https?://\S{80,}\s*\)', "", text)
        # Remove remaining short junk URLs in parens
        text = re.sub(r'\(\s*https?://\S{5,60}\s*\)', "", text)

        # 2. Strip ad / footer sections line by line
        # SECTION_STOP: these lines BEGIN a promo/footer block — skip this line and all after
        SECTION_STOP = [
            "unsubscribe",
            "you are receiving this",
            "advertise to 950",
            "our newsletter puts your products",
            "partner with us",
            "today's email was brought to you",
            "looking for more? unlock",
            "no-fluff resources to",
            "get in touch today by replying",
            "succeed in ai engineering roles",
            "that's a wrap",
        ]
        # LINE_DROP: drop only this single line (not everything after)
        LINE_DROP = [
            "master full-stack ai engineering",
            "unlock our premium",
            "© 20",
            "all rights reserved",
            "today.s email was brought",
        ]
        out, skip = [], False
        for line in text.split("\n"):
            low = line.lower().strip()
            # Section stop — skip this and all subsequent lines
            if any(k in low for k in SECTION_STOP):
                skip = True; continue
            # Resume after a separator (new section after footer)
            if skip and re.match(r'^[-=]{5,}$', low):
                skip = False; continue
            if skip:
                continue
            # Line drop — skip only this single line
            if any(k in low for k in LINE_DROP):
                continue
            out.append(line)
        text = "\n".join(out)

        # 3. Remove separator lines
        text = re.sub(r'^[-=]{10,}\s*$', "", text, flags=re.MULTILINE)

        # 4. Deduplicate identical paragraphs
        paras = re.split(r'\n{2,}', text)
        seen, unique = set(), []
        for p in paras:
            key = re.sub(r'\s+', " ", p.strip())[:120]
            if key and key not in seen:
                seen.add(key); unique.append(p.strip())
        text = "\n\n".join(unique)

        # 5. Remove decoration lines
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
        """Transform clean email text into structured study content."""
        if not self.provider:
            return self._fallback(email)

        prompt = f"""You are an expert technical writer for a data science newsletter.
Transform the following newsletter email into clean, structured study notes.

STRICT RULES:
1. Do NOT include any URLs, links, tracking codes, or promotional content
2. Do NOT include any "unsubscribe", "advertise", "unlock premium", or footer text
3. Do NOT duplicate content between sections
4. Write in clear, educational prose — not bullet dumps
5. Cover ALL topics mentioned in the email thoroughly
6. The DEEP EXPLANATION must be 4-6 educational paragraphs, NOT a copy of overview
7. For code: preserve exact code blocks, explain each part

EMAIL SUBJECT: {email.subject}
EMAIL DATE: {email.date.strftime("%B %d, %Y")}

EMAIL CONTENT (already cleaned):
{email.body_text[:9000]}

Respond in EXACTLY this format (use these exact section headers):

TOPIC: [Clean descriptive title for this newsletter issue]

TLDR: [2-3 sentence summary of what this issue covers and why it matters]

OVERVIEW:
[3-4 paragraphs introducing the topic. What is it? Why does it matter? What will the reader learn?]

SECTION: [Title of first major topic from the email]
[3-5 paragraphs of educational explanation for this topic. Include all key concepts, how things work, concrete examples.]

SECTION: [Title of second major topic if email covers multiple topics]
[3-5 paragraphs explaining this topic]

[Add more SECTION blocks as needed — one per major topic in the email]

CODE:
```python
# If the email contains code examples, reproduce them here with explanations as comments
# If no code in email, write a short illustrative example of the main concept
```

KEY_POINTS:
- [Most important insight — a complete useful sentence]
- [Second most important]
- [Third]
- [Fourth]
- [Fifth]
[5-7 key points total]

INTERVIEW_QUESTIONS:
- [Beginner level question about this topic]
- [Beginner level question]
- [Intermediate level question]
- [Intermediate level question]
- [Advanced level question]
- [Advanced level question]

FURTHER_READING:
- [Related topic or concept to explore next — no URLs, just topic name and why]
- [Another suggestion]
- [Another suggestion]
"""
        MAX_RETRY = 5
        for attempt in range(MAX_RETRY):
            try:
                if self.provider == "gemini":
                    resp = self.model.generate_content(
                        prompt,
                        generation_config={"temperature": 0.25, "max_output_tokens": MAX_TOKENS}
                    )
                    text = resp.text
                else:
                    resp = self.client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=MAX_TOKENS, temperature=0.25
                    )
                    text = resp.choices[0].message.content or ""
                return self._parse(text, email)
            except Exception as e:
                err = str(e)
                m = re.search(r'retry_delay.*?seconds:\s*([0-9]+)', err, re.DOTALL)
                if m:
                    wait = int(m.group(1)) + 5
                else:
                    wait = 30 * (attempt + 1)
                log.warning("AI quota/error — waiting %ds (attempt %d/%d)...", wait, attempt+1, MAX_RETRY)
                time.sleep(wait)

        log.error("AI failed after %d retries — using smart fallback", MAX_RETRY)
        return self._fallback(email)

    def _parse(self, text: str, email: RawEmail) -> StudyNote:
        def gs(header: str) -> str:
            m = re.search(rf"{re.escape(header)}\s*\n(.*?)(?=\n[A-Z_]+:|SECTION:|CODE:|\Z)", text, re.DOTALL)
            return m.group(1).strip() if m else ""

        def glist(header: str) -> list:
            raw = gs(header)
            return [l.strip("- •").strip() for l in raw.split("\n") if l.strip().startswith(("-","•","*")) and len(l.strip()) > 3]

        # Extract sections (multiple SECTION: blocks)
        sections = []
        for m in re.finditer(r'SECTION:\s*(.+?)\n(.*?)(?=\nSECTION:|\nCODE:|\nKEY_POINTS:|\Z)', text, re.DOTALL):
            title = m.group(1).strip()
            body  = m.group(2).strip()
            if title and body:
                sections.append({"title": title, "body": body, "code": ""})

        # Extract code
        code_blocks = re.findall(r'```(?:python)?\n(.*?)```', text, re.DOTALL)

        # Attach code to last section or create a code section
        if code_blocks:
            if sections:
                sections[-1]["code"] = code_blocks[0].strip()
            else:
                sections.append({"title": "Code Example", "body": "", "code": code_blocks[0].strip()})

        topic = gs("TOPIC:") or email.topic.replace("_", " ")

        return StudyNote(
            issue_number=0,  # set by caller
            date=email.date.strftime("%Y-%m-%d"),
            topic=topic,
            category=detect_category(topic + " " + email.body_text[:500]),
            tldr=gs("TLDR:"),
            overview=gs("OVERVIEW:"),
            sections=sections,
            key_points=glist("KEY_POINTS:"),
            interview_qs=glist("INTERVIEW_QUESTIONS:"),
            further=glist("FURTHER_READING:"),
        )

    def _fallback(self, email: RawEmail) -> StudyNote:
        """Smart fallback — readable content even without AI."""
        paras = [p.strip() for p in email.body_text.split("\n\n") if len(p.strip()) > 80]
        overview = paras[0][:800] + "..." if paras else "Content from Daily Dose of DS."
        bullet_lines = []
        for line in email.body_text.split("\n"):
            line = line.strip()
            if re.match(r'^[\*\-•\d]+[.)\s]', line) and 15 < len(line) < 200:
                cleaned = re.sub(r'^[\*\-•\d.)+\s]+', "", line).strip()
                if cleaned: bullet_lines.append(cleaned)

        sections = []
        # Group remaining paragraphs into sections
        for i, para in enumerate(paras[1:6]):
            if len(para) > 100:
                sections.append({"title": f"Section {i+1}", "body": para, "code": ""})

        topic = email.topic.replace("_", " ")
        return StudyNote(
            issue_number=0,
            date=email.date.strftime("%Y-%m-%d"),
            topic=topic,
            category=detect_category(topic + " " + email.body_text[:500]),
            tldr=overview[:200],
            overview=overview,
            sections=sections,
            key_points=bullet_lines[:7],
            interview_qs=[],
            further=["Visit dailydoseofds.com for the full article and related resources"],
        )


# ── CSS ───────────────────────────────────────────────────────────────────────

CSS = """
:root{
  --void:#03040a;--deep:#08090f;--card:rgba(255,255,255,.04);--card-h:rgba(255,255,255,.07);
  --glass:rgba(255,255,255,.04);--border:rgba(255,255,255,.08);--border-h:rgba(255,255,255,.14);
  --text:#f0f2ff;--text-2:rgba(200,205,240,.75);--text-3:rgba(150,160,200,.5);
  --a:#6366f1;--b:#a855f7;--c:#06b6d4;--d:#ec4899;--e:#10b981;--f:#fbbf24;
  --ca:#6366f1;--cb:#a855f7;
  --r8:8px;--r12:12px;--r16:16px;--r20:20px;--r24:24px;
  --bounce:cubic-bezier(.34,1.56,.64,1);--smooth:cubic-bezier(.4,0,.2,1);
  --mono:'Fira Code','JetBrains Mono','Cascadia Code',monospace;
}
body.light{--void:#f0f2ff;--deep:#f8f9ff;--card:rgba(99,102,241,.04);--card-h:rgba(99,102,241,.08);
  --glass:rgba(255,255,255,.7);--border:rgba(99,102,241,.12);--border-h:rgba(99,102,241,.25);
  --text:#1a1b2e;--text-2:rgba(30,35,80,.7);--text-3:rgba(50,55,100,.45);}
*,*::before,*::after{margin:0;padding:0;box-sizing:border-box;}
html{scroll-behavior:smooth;}
body{font-family:'Inter','Segoe UI',system-ui,sans-serif;background:var(--void);color:var(--text);
  min-height:100vh;overflow-x:hidden;-webkit-font-smoothing:antialiased;cursor:none;}
@media(pointer:coarse){body{cursor:auto;}}

/* Aurora */
.aurora{position:fixed;inset:0;z-index:-3;overflow:hidden;pointer-events:none;}
.orb{position:absolute;border-radius:50%;filter:blur(100px);opacity:.15;animation:orbf 20s ease-in-out infinite;}
.orb:nth-child(1){width:700px;height:700px;left:-15%;top:-20%;background:radial-gradient(circle,var(--a),transparent 70%);}
.orb:nth-child(2){width:500px;height:500px;right:-10%;top:30%;background:radial-gradient(circle,var(--b),transparent 70%);animation-delay:-7s;opacity:.12;}
.orb:nth-child(3){width:400px;height:400px;left:40%;bottom:-10%;background:radial-gradient(circle,var(--c),transparent 70%);animation-delay:-13s;opacity:.1;}
.orb:nth-child(4){width:300px;height:300px;right:20%;top:10%;background:radial-gradient(circle,var(--d),transparent 70%);animation-delay:-4s;opacity:.07;}
@keyframes orbf{0%,100%{transform:translate(0,0) scale(1);}25%{transform:translate(30px,-40px) scale(1.08);}50%{transform:translate(-20px,30px) scale(.94);}75%{transform:translate(40px,15px) scale(1.04);}}

/* Grid */
.grid-bg{position:fixed;inset:0;z-index:-2;pointer-events:none;
  background-image:linear-gradient(rgba(99,102,241,.025) 1px,transparent 1px),linear-gradient(90deg,rgba(99,102,241,.025) 1px,transparent 1px);
  background-size:60px 60px;}

/* Cursor */
.cur-dot{position:fixed;width:10px;height:10px;border-radius:50%;background:var(--a);pointer-events:none;z-index:99999;
  transform:translate(-50%,-50%);box-shadow:0 0 12px var(--a),0 0 24px var(--a);transition:width .2s,height .2s,background .2s;}
.cur-ring{position:fixed;width:40px;height:40px;border-radius:50%;border:1px solid rgba(99,102,241,.4);pointer-events:none;z-index:99998;
  transform:translate(-50%,-50%);transition:transform .15s ease;}
.cur-trail{position:fixed;border-radius:50%;pointer-events:none;z-index:99997;background:var(--b);transform:translate(-50%,-50%);
  animation:trailFade .6s ease forwards;}
@keyframes trailFade{0%{opacity:.5;width:8px;height:8px;}100%{opacity:0;width:2px;height:2px;}}
@media(pointer:coarse){.cur-dot,.cur-ring{display:none;}}

/* Scroll bar */
.scroll-bar{position:fixed;top:0;left:0;height:2px;z-index:9999;
  background:linear-gradient(90deg,var(--a),var(--b),var(--d));
  box-shadow:0 0 8px var(--a);transition:width .1s linear;}

/* Nav */
.nav{position:sticky;top:0;z-index:100;background:rgba(8,9,15,.75);backdrop-filter:blur(24px) saturate(180%);
  -webkit-backdrop-filter:blur(24px) saturate(180%);border-bottom:1px solid var(--border);
  animation:slideDown .6s var(--bounce);}
body.light .nav{background:rgba(248,249,255,.85);}
@keyframes slideDown{from{transform:translateY(-100%);opacity:0;}to{transform:translateY(0);opacity:1;}}
.nav-in{max-width:1280px;margin:0 auto;padding:0 24px;height:64px;display:flex;align-items:center;justify-content:space-between;}
.nav-logo{display:flex;align-items:center;gap:12px;text-decoration:none;color:var(--text);font-weight:800;font-size:1.1rem;cursor:none;}
.gem{width:38px;height:38px;border-radius:12px;background:linear-gradient(135deg,var(--a),var(--b));
  display:flex;align-items:center;justify-content:center;font-size:1.2rem;
  box-shadow:0 0 20px rgba(99,102,241,.4);animation:gempulse 3s ease-in-out infinite;}
@keyframes gempulse{0%,100%{box-shadow:0 0 15px rgba(99,102,241,.35);}50%{box-shadow:0 0 35px rgba(99,102,241,.65);}}
.nav-links{display:flex;align-items:center;gap:6px;}
.nav-link{padding:8px 16px;border-radius:100px;color:var(--text-2);text-decoration:none;font-size:.88rem;font-weight:500;
  transition:all .2s;cursor:none;position:relative;overflow:hidden;}
.nav-link:hover{color:var(--text);background:rgba(99,102,241,.08);}
.nav-btn{padding:8px 16px;border-radius:100px;border:none;cursor:none;background:none;color:var(--text-2);font-size:.9rem;transition:all .2s;}
.nav-btn:hover{color:var(--a);}

/* Hero */
.hero{position:relative;text-align:center;padding:clamp(80px,12vw,140px) 20px clamp(60px,8vw,100px);overflow:hidden;}
#neural-canvas{position:absolute;inset:0;z-index:0;opacity:.25;pointer-events:none;}
.hero-in{position:relative;z-index:1;}
.badge{display:inline-flex;align-items:center;gap:8px;padding:6px 18px;border-radius:100px;margin-bottom:28px;
  background:rgba(99,102,241,.1);border:1px solid rgba(99,102,241,.25);
  color:var(--a);font-size:.8rem;font-weight:700;letter-spacing:.8px;text-transform:uppercase;
  animation:fadeUp .8s var(--bounce) .1s both;}
.dot-live{width:8px;height:8px;border-radius:50%;background:var(--e);animation:pulse 2s infinite;}
@keyframes pulse{0%,100%{opacity:1;transform:scale(1);}50%{opacity:.5;transform:scale(.8);}}
.hero h1{font-size:clamp(2.8rem,7vw,5.5rem);font-weight:900;line-height:1.05;letter-spacing:-.03em;margin-bottom:20px;animation:fadeUp .8s var(--bounce) .2s both;}
.shine{background:linear-gradient(135deg,#fff 0%,var(--a) 40%,var(--b) 70%,var(--d) 100%);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;
  background-size:200% 200%;animation:shineMove 5s ease infinite;}
@keyframes shineMove{0%,100%{background-position:0% 50%;}50%{background-position:100% 50%;}}
.hero-sub{font-size:clamp(1rem,2vw,1.15rem);color:var(--text-2);max-width:580px;margin:0 auto 36px;line-height:1.7;animation:fadeUp .8s var(--bounce) .3s both;}
.hero-cta{display:inline-flex;align-items:center;gap:10px;padding:14px 34px;border-radius:100px;border:none;cursor:none;
  background:linear-gradient(135deg,var(--a),var(--b));color:#fff;font-weight:700;font-size:1rem;text-decoration:none;
  box-shadow:0 4px 24px rgba(99,102,241,.4);animation:fadeUp .8s var(--bounce) .4s both;
  transition:box-shadow .3s,transform .1s;position:relative;overflow:hidden;}
.hero-cta::before{content:'';position:absolute;inset:0;background:linear-gradient(90deg,transparent,rgba(255,255,255,.15),transparent);
  transform:translateX(-100%);transition:transform .5s;}
.hero-cta:hover::before{transform:translateX(100%);}
.hero-cta:hover{box-shadow:0 8px 36px rgba(99,102,241,.5);}
@keyframes fadeUp{from{opacity:0;transform:translateY(30px);}to{opacity:1;transform:translateY(0);}}

/* Stats */
.stats{display:flex;justify-content:center;gap:48px;flex-wrap:wrap;padding:20px 24px 60px;max-width:700px;margin:0 auto;animation:fadeUp .8s var(--bounce) .5s both;}
.stat{text-align:center;}
.stat-n{font-size:2.5rem;font-weight:900;line-height:1;
  background:linear-gradient(135deg,var(--a),var(--b));-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;}
.stat-sep{width:1px;background:var(--border);align-self:stretch;margin:4px 0;}
.stat-l{font-size:.7rem;color:var(--text-3);text-transform:uppercase;letter-spacing:2px;margin-top:6px;}

/* Search */
.search-wrap{max-width:640px;margin:0 auto 20px;padding:0 24px;position:relative;animation:fadeUp .8s var(--bounce) .6s both;}
.search-in{width:100%;padding:16px 52px;background:var(--glass);border:1px solid var(--border);
  border-radius:100px;color:var(--text);font-size:1rem;outline:none;cursor:text;
  backdrop-filter:blur(12px);transition:border-color .2s,box-shadow .2s,transform .2s;}
.search-in::placeholder{color:var(--text-3);}
.search-in:focus{border-color:var(--a);box-shadow:0 0 0 3px rgba(99,102,241,.15),0 8px 32px rgba(0,0,0,.3);transform:translateY(-2px);}
.search-ico{position:absolute;left:42px;top:50%;transform:translateY(-50%);color:var(--text-3);pointer-events:none;}
.search-kbd{position:absolute;right:40px;top:50%;transform:translateY(-50%);
  background:var(--card);border:1px solid var(--border);color:var(--text-3);font-size:.7rem;padding:2px 8px;border-radius:6px;}
.search-count{text-align:center;color:var(--text-3);font-size:.82rem;margin-bottom:16px;opacity:0;transition:opacity .3s;}
.search-count.show{opacity:1;}

/* Cards */
.grid-wrap{max-width:1280px;margin:0 auto;padding:0 24px 80px;}
.card-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:20px;}
.card{display:block;text-decoration:none;color:var(--text);background:var(--card);border:1px solid var(--border);
  border-radius:var(--r20);padding:28px;position:relative;overflow:hidden;
  transition:transform .3s var(--bounce),border-color .3s,box-shadow .3s,background .3s;cursor:none;
  opacity:0;transform:translateY(40px);backdrop-filter:blur(8px);}
.card.visible{opacity:1;transform:translateY(0);transition:opacity .6s ease,transform .6s var(--bounce),border-color .3s,box-shadow .3s,background .3s;}
.card::before{content:'';position:absolute;inset:0;background:linear-gradient(135deg,color-mix(in srgb,var(--ca) 8%,transparent),color-mix(in srgb,var(--cb) 4%,transparent));opacity:0;transition:opacity .3s;border-radius:inherit;pointer-events:none;}
.card::after{content:'';position:absolute;top:0;left:0;right:0;height:2px;background:linear-gradient(90deg,var(--ca),var(--cb));transform:scaleX(0);transform-origin:left;transition:transform .4s var(--bounce);border-radius:var(--r20) var(--r20) 0 0;}
.card:hover{transform:translateY(-8px) scale(1.01);border-color:color-mix(in srgb,var(--ca) 30%,transparent);
  box-shadow:0 20px 48px rgba(0,0,0,.5),0 0 0 1px color-mix(in srgb,var(--ca) 20%,transparent);background:var(--card-h);}
.card:hover::before{opacity:1;}.card:hover::after{transform:scaleX(1);}
.card-issue{font-size:.7rem;font-weight:800;text-transform:uppercase;letter-spacing:2px;color:var(--ca);margin-bottom:6px;display:flex;align-items:center;gap:8px;}
.cat-badge{display:inline-flex;align-items:center;padding:2px 10px;border-radius:100px;font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.6px;
  background:color-mix(in srgb,var(--ca) 12%,transparent);border:1px solid color-mix(in srgb,var(--ca) 20%,transparent);color:var(--ca);}
.card-title{font-size:1.2rem;font-weight:700;line-height:1.4;margin-bottom:10px;}
.card:hover .card-title{background:linear-gradient(90deg,var(--ca),var(--cb));-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;}
.card-desc{font-size:.88rem;color:var(--text-2);line-height:1.65;margin-bottom:18px;}
.card-foot{display:flex;justify-content:space-between;align-items:center;padding-top:16px;border-top:1px solid var(--border);}
.card-date{font-size:.75rem;color:var(--text-3);}
.arrow{width:32px;height:32px;border-radius:50%;background:color-mix(in srgb,var(--ca) 10%,transparent);
  border:1px solid color-mix(in srgb,var(--ca) 20%,transparent);color:var(--ca);
  display:flex;align-items:center;justify-content:center;font-size:.9rem;transition:all .25s var(--bounce);}
.card:hover .arrow{background:linear-gradient(135deg,var(--ca),var(--cb));border-color:transparent;color:#fff;transform:translateX(4px);}

/* E-book button */
.ebook-btn{display:inline-flex;align-items:center;gap:8px;padding:12px 24px;border-radius:100px;
  background:rgba(99,102,241,.1);border:1px solid rgba(99,102,241,.25);color:var(--a);
  font-weight:600;font-size:.9rem;text-decoration:none;cursor:none;transition:all .3s;
  animation:fadeUp .8s var(--bounce) .45s both;}
.ebook-btn:hover{background:rgba(99,102,241,.2);border-color:rgba(99,102,241,.4);transform:translateY(-2px);}

/* Empty */
.empty{text-align:center;padding:100px 20px;}
.empty-icon{font-size:5rem;margin-bottom:20px;animation:float 3s ease-in-out infinite;}
@keyframes float{0%,100%{transform:translateY(0);}50%{transform:translateY(-16px);}}

/* Entry page */
.entry-hero{padding:clamp(60px,10vw,100px) 20px 40px;text-align:center;position:relative;overflow:hidden;}
.entry-hero::before{content:'';position:absolute;left:50%;top:-30%;width:600px;height:600px;border-radius:50%;
  background:radial-gradient(circle,color-mix(in srgb,var(--ca) 8%,transparent),transparent 70%);transform:translateX(-50%);pointer-events:none;}
.issue-badge{display:inline-flex;align-items:center;gap:6px;padding:5px 16px;border-radius:100px;margin-bottom:16px;
  background:color-mix(in srgb,var(--ca) 10%,transparent);border:1px solid color-mix(in srgb,var(--ca) 25%,transparent);
  color:var(--ca);font-size:.78rem;font-weight:800;text-transform:uppercase;letter-spacing:1.5px;}
.entry-title{font-size:clamp(1.8rem,4vw,3.2rem);font-weight:900;line-height:1.15;margin-bottom:14px;
  background:linear-gradient(135deg,var(--text) 0%,var(--ca) 60%,var(--cb) 100%);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;}
.entry-meta{color:var(--text-3);font-size:.88rem;display:flex;justify-content:center;align-items:center;gap:16px;flex-wrap:wrap;}

/* TLDR box */
.tldr-box{background:color-mix(in srgb,var(--ca) 6%,var(--card));border:1px solid color-mix(in srgb,var(--ca) 20%,transparent);
  border-left:4px solid var(--ca);border-radius:var(--r16);padding:20px 24px;margin-bottom:24px;
  font-size:1rem;color:var(--text-2);line-height:1.7;}
.tldr-label{font-size:.7rem;font-weight:800;text-transform:uppercase;letter-spacing:1.5px;color:var(--ca);margin-bottom:8px;}

.entry-body{max-width:820px;margin:0 auto;padding:0 20px 80px;position:relative;}

/* Sections */
.sec{background:var(--card);border:1px solid var(--border);border-radius:var(--r20);padding:32px;margin-bottom:20px;
  position:relative;overflow:hidden;z-index:1;opacity:0;transform:translateY(28px);backdrop-filter:blur(8px);transition:all .4s;}
.sec.visible{opacity:1;transform:translateY(0);}
.sec:hover{border-color:color-mix(in srgb,var(--ca) 25%,transparent);box-shadow:0 12px 40px rgba(0,0,0,.4);}
.sec::before{content:'';position:absolute;left:0;top:0;bottom:0;width:3px;
  background:linear-gradient(180deg,var(--ca),var(--cb));border-radius:inherit 0 0 inherit;opacity:0;transition:opacity .3s;}
.sec:hover::before{opacity:1;}
.sec h2{font-size:1.3rem;font-weight:700;color:var(--ca);margin-bottom:20px;display:flex;align-items:center;gap:10px;}
.sec-icon{width:36px;height:36px;border-radius:10px;background:color-mix(in srgb,var(--ca) 12%,transparent);
  display:flex;align-items:center;justify-content:center;font-size:1.1rem;flex-shrink:0;}
.sec p{color:var(--text-2);margin-bottom:14px;line-height:1.82;}
.sec ul,.sec ol{padding-left:22px;margin:12px 0;}
.sec li{color:var(--text-2);margin-bottom:9px;line-height:1.7;}
.sec ul li::marker{color:var(--ca);} .sec ol li::marker{color:var(--cb);font-weight:700;}
.sec h3{font-size:1.05rem;font-weight:700;color:var(--cb);margin:22px 0 10px;}

/* Code */
.code-wrap{background:#060810;border:1px solid rgba(99,102,241,.15);border-radius:var(--r16);margin:16px 0;overflow:hidden;}
.code-head{display:flex;justify-content:space-between;align-items:center;padding:8px 16px;
  background:rgba(99,102,241,.06);border-bottom:1px solid rgba(99,102,241,.1);}
.code-lang{font-size:.72rem;color:var(--a);font-weight:700;text-transform:uppercase;letter-spacing:1px;}
.code-copy{background:none;border:1px solid var(--border);color:var(--text-3);padding:3px 12px;
  border-radius:6px;font-size:.78rem;cursor:none;transition:all .2s;}
.code-copy:hover{border-color:var(--a);color:var(--a);}
.code-copy.copied{border-color:var(--e);color:var(--e);}
.code-wrap pre{padding:20px;margin:0;font-family:var(--mono);font-size:.86rem;line-height:1.72;overflow-x:auto;color:#a5b4fc;}

/* Interview Qs */
.iq-q{padding:12px 16px;border-radius:10px;background:rgba(255,255,255,.03);border:1px solid var(--border);
  margin-bottom:8px;font-size:.9rem;color:var(--text-2);transition:all .2s;}
.iq-q:hover{border-color:color-mix(in srgb,var(--ca) 25%,transparent);transform:translateX(4px);color:var(--text);}

/* AI Tutor */
.fab{position:fixed;bottom:24px;right:24px;z-index:1000;width:62px;height:62px;border-radius:50%;border:none;cursor:none;
  background:linear-gradient(135deg,var(--a),var(--b));color:#fff;font-size:1.5rem;
  box-shadow:0 4px 24px rgba(99,102,241,.5);animation:fabPulse 3s ease-in-out infinite;
  transition:transform .25s var(--bounce),box-shadow .25s;display:flex;align-items:center;justify-content:center;}
@keyframes fabPulse{0%,100%{box-shadow:0 4px 24px rgba(99,102,241,.4);}50%{box-shadow:0 4px 40px rgba(99,102,241,.7),0 0 60px rgba(99,102,241,.2);}}
.fab:hover{transform:scale(1.12) rotate(8deg);}
.fab.hidden{display:none!important;}

.tutor{position:fixed;bottom:100px;right:24px;z-index:999;width:420px;height:560px;
  background:rgba(8,9,15,.93);backdrop-filter:blur(32px) saturate(200%);
  border:1px solid var(--border);border-radius:var(--r24);
  box-shadow:0 32px 80px rgba(0,0,0,.7),0 0 0 1px rgba(99,102,241,.1);
  display:flex;flex-direction:column;overflow:hidden;
  opacity:0;transform:translateY(20px) scale(.96);pointer-events:none;transition:all .3s var(--bounce);}
.tutor.open{opacity:1;transform:translateY(0) scale(1);pointer-events:auto;}
@media(max-width:500px){.tutor{width:calc(100% - 32px);right:16px;bottom:90px;height:65vh;}}
.tutor-head{padding:18px 20px;display:flex;justify-content:space-between;align-items:center;
  background:linear-gradient(135deg,rgba(99,102,241,.15),rgba(168,85,247,.1));border-bottom:1px solid var(--border);flex-shrink:0;}
.tutor-title{font-weight:700;font-size:.95rem;display:flex;align-items:center;gap:8px;}
.t-close{background:none;border:none;color:var(--text-3);font-size:1.2rem;cursor:none;transition:color .2s;}
.t-close:hover{color:var(--text);}
.tutor-hint{padding:10px 16px;background:rgba(99,102,241,.04);border-bottom:1px solid var(--border);flex-shrink:0;font-size:.75rem;color:var(--text-3);}
.tutor-hint strong{color:var(--a);}
.tutor-body{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:10px;}
.tutor-body::-webkit-scrollbar{width:4px;}
.tutor-body::-webkit-scrollbar-thumb{background:rgba(99,102,241,.3);border-radius:2px;}
.msg{max-width:88%;padding:12px 16px;border-radius:16px;font-size:.88rem;line-height:1.55;word-wrap:break-word;animation:msgPop .35s var(--bounce);}
@keyframes msgPop{from{opacity:0;transform:scale(.85) translateY(8px);}to{opacity:1;transform:scale(1) translateY(0);}}
.msg.user{align-self:flex-end;background:linear-gradient(135deg,var(--a),var(--b));color:#fff;border-bottom-right-radius:4px;}
.msg.bot{align-self:flex-start;background:rgba(255,255,255,.05);border:1px solid var(--border);color:var(--text);border-bottom-left-radius:4px;}
.typing{display:flex;gap:5px;padding:4px 0;}
.typing span{width:7px;height:7px;border-radius:50%;background:var(--text-3);animation:tyBounce 1.3s ease-in-out infinite;}
.typing span:nth-child(2){animation-delay:.2s;}.typing span:nth-child(3){animation-delay:.4s;}
@keyframes tyBounce{0%,60%,100%{transform:translateY(0);}30%{transform:translateY(-7px);}}
.chips{padding:0 16px 10px;display:flex;flex-wrap:wrap;gap:6px;flex-shrink:0;}
.chip{padding:5px 12px;border-radius:100px;font-size:.75rem;cursor:none;
  background:rgba(99,102,241,.08);border:1px solid rgba(99,102,241,.15);color:var(--a);transition:all .2s;}
.chip:hover{background:rgba(99,102,241,.18);border-color:rgba(99,102,241,.35);}
.tutor-inp{display:flex;gap:8px;padding:12px;border-top:1px solid var(--border);background:rgba(0,0,0,.2);flex-shrink:0;}
.tutor-input{flex:1;background:rgba(255,255,255,.05);border:1px solid var(--border);border-radius:12px;
  padding:11px 16px;color:var(--text);font-size:.88rem;outline:none;cursor:text;transition:border-color .2s;}
.tutor-input:focus{border-color:var(--a);box-shadow:0 0 0 2px rgba(99,102,241,.12);}
.tsend{padding:11px 18px;border:none;border-radius:12px;cursor:none;
  background:linear-gradient(135deg,var(--a),var(--b));color:#fff;font-weight:700;font-size:.88rem;transition:transform .2s,box-shadow .2s;}
.tsend:hover{transform:translateY(-1px);box-shadow:0 4px 16px rgba(99,102,241,.4);}
.tsend:disabled{opacity:.5;transform:none;}

/* Reading ring */
.read-ring{position:fixed;top:18px;right:18px;z-index:101;width:48px;height:48px;opacity:0;transform:scale(.7);transition:all .3s;cursor:none;}
.read-ring.show{opacity:1;transform:scale(1);}
.read-ring svg{transform:rotate(-90deg);}
.rr-bg{fill:none;stroke:rgba(255,255,255,.06);stroke-width:3;}
.rr-prog{fill:none;stroke-width:3;stroke-linecap:round;transition:stroke-dashoffset .1s;}

/* BTT */
.btt{position:fixed;bottom:100px;right:24px;z-index:99;width:46px;height:46px;border-radius:50%;border:none;cursor:none;
  background:rgba(99,102,241,.12);border:1px solid rgba(99,102,241,.2);color:var(--a);font-size:1.1rem;
  display:flex;align-items:center;justify-content:center;opacity:0;transform:translateY(16px);pointer-events:none;transition:all .3s;}
.btt.show{opacity:1;transform:translateY(0);pointer-events:auto;}
.btt:hover{background:var(--a);color:#fff;border-color:var(--a);transform:translateY(-3px);}

/* Footer */
.footer{text-align:center;padding:40px 24px;border-top:1px solid var(--border);
  color:var(--text-3);font-size:.82rem;background:rgba(3,4,10,.5);backdrop-filter:blur(12px);}
.footer a{color:var(--a);text-decoration:none;}

/* Confetti */
#confetti{position:fixed;inset:0;pointer-events:none;z-index:9998;}
/* Ripple */
.ripple{position:fixed;border-radius:50%;pointer-events:none;z-index:9990;border:2px solid rgba(99,102,241,.5);
  transform:translate(-50%,-50%) scale(0);animation:rippleExp .6s ease-out forwards;}
@keyframes rippleExp{to{transform:translate(-50%,-50%) scale(4);opacity:0;}}

/* Responsive */
@media(max-width:768px){
  .card-grid{grid-template-columns:1fr;}.stats{gap:24px;}.read-ring{display:none;}
  .entry-body{padding:0 12px 60px;}.sec{padding:20px;}.tutor{width:calc(100vw - 32px);right:16px;}
}
@media(prefers-reduced-motion:reduce){
  *,*::before,*::after{animation-duration:.01ms!important;transition-duration:.01ms!important;}
  .cur-dot,.cur-ring{display:none;}body{cursor:auto;}html{scroll-behavior:auto;}
}
/* Particles */
@keyframes prise{0%{transform:translateY(100vh) scale(0);opacity:0;}10%{opacity:.6;}90%{opacity:.3;}100%{transform:translateY(-10vh) scale(1);opacity:0;}}
"""

# ── JavaScript ────────────────────────────────────────────────────────────────

JS = r"""
// Theme
(function(){
  const s=localStorage.getItem('dds-theme');
  if(s==='light') document.body.classList.add('light');
  const b=document.getElementById('themeBtn');
  if(b){
    b.textContent=document.body.classList.contains('light')?'🌙':'☀️';
    b.addEventListener('click',()=>{
      document.body.classList.toggle('light');
      localStorage.setItem('dds-theme',document.body.classList.contains('light')?'light':'dark');
      b.textContent=document.body.classList.contains('light')?'🌙':'☀️';
    });
  }
})();

// Cursor
(function(){
  if(window.matchMedia('(pointer:coarse)').matches) return;
  const d=document.querySelector('.cur-dot'),r=document.querySelector('.cur-ring');
  if(!d||!r) return;
  let mx=0,my=0,rx=0,ry=0;
  window.addEventListener('mousemove',e=>{
    mx=e.clientX;my=e.clientY;
    d.style.left=mx+'px';d.style.top=my+'px';
    const t=document.createElement('div');
    t.className='cur-trail';t.style.cssText=`left:${mx}px;top:${my}px;width:7px;height:7px;`;
    document.body.appendChild(t);setTimeout(()=>t.remove(),600);
  });
  (function a(){rx+=(mx-rx)*.11;ry+=(my-ry)*.11;r.style.left=rx+'px';r.style.top=ry+'px';requestAnimationFrame(a);})();
  document.querySelectorAll('a,button,.card,.chip').forEach(el=>{
    el.addEventListener('mouseenter',()=>{d.style.width='18px';d.style.height='18px';r.style.width='54px';r.style.height='54px';});
    el.addEventListener('mouseleave',()=>{d.style.width='10px';d.style.height='10px';r.style.width='40px';r.style.height='40px';});
  });
})();

// Ripple
document.addEventListener('click',e=>{
  const r=document.createElement('div');
  r.className='ripple';r.style.cssText=`left:${e.clientX}px;top:${e.clientY}px;width:60px;height:60px;`;
  document.body.appendChild(r);setTimeout(()=>r.remove(),700);
});

// Neural canvas
(function(){
  const cv=document.getElementById('neural-canvas');
  if(!cv) return;
  const ctx=cv.getContext('2d');
  let W,H,nodes=[],raf;
  function resize(){W=cv.width=cv.offsetWidth;H=cv.height=cv.offsetHeight;}
  function init(){
    resize();
    nodes=Array.from({length:24},()=>({x:Math.random()*W,y:Math.random()*H,vx:(Math.random()-.5)*.35,vy:(Math.random()-.5)*.35,r:2+Math.random()*3,p:Math.random()*Math.PI*2}));
  }
  function draw(){
    ctx.clearRect(0,0,W,H);
    nodes.forEach(n=>{n.x+=n.vx;n.y+=n.vy;n.p+=.025;if(n.x<0||n.x>W)n.vx*=-1;if(n.y<0||n.y>H)n.vy*=-1;});
    nodes.forEach((a,i)=>{
      nodes.slice(i+1).forEach(b=>{
        const d=Math.hypot(a.x-b.x,a.y-b.y);if(d>190)return;
        ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);
        ctx.strokeStyle=`rgba(99,102,241,${(1-d/190)*.3})`;ctx.lineWidth=.7;ctx.stroke();
        if(Math.sin(a.p)>.75){const t=(Math.sin(a.p)-.75)/.25,sx=a.x+(b.x-a.x)*t,sy=a.y+(b.y-a.y)*t;
          ctx.beginPath();ctx.arc(sx,sy,2,0,Math.PI*2);ctx.fillStyle='rgba(168,85,247,.9)';ctx.fill();}
      });
    });
    nodes.forEach(n=>{const g=.5+.5*Math.sin(n.p);ctx.beginPath();ctx.arc(n.x,n.y,n.r*(.8+.3*g),0,Math.PI*2);
      ctx.fillStyle=`rgba(99,102,241,${.4+.4*g})`;ctx.shadowBlur=12*g;ctx.shadowColor='#6366f1';ctx.fill();ctx.shadowBlur=0;});
    raf=requestAnimationFrame(draw);
  }
  init();draw();
  window.addEventListener('resize',()=>{cancelAnimationFrame(raf);init();draw();});
})();

// Scroll bar
const sb=document.getElementById('scrollBar');
if(sb) window.addEventListener('scroll',()=>{const s=window.scrollY,h=document.documentElement.scrollHeight-window.innerHeight;sb.style.width=(h>0?(s/h)*100:0)+'%';},{passive:true});

// Reading ring
const rr=document.getElementById('readRing');
if(rr){
  const c=rr.querySelector('.rr-prog'),r=c.r.baseVal.value,ci=r*2*Math.PI;
  c.style.strokeDasharray=`${ci} ${ci}`;c.style.strokeDashoffset=ci;
  window.addEventListener('scroll',()=>{const s=window.scrollY,h=document.documentElement.scrollHeight-window.innerHeight,p=h>0?(s/h)*100:0;
    c.style.strokeDashoffset=ci-(p/100)*ci;rr.classList.toggle('show',p>5);},{passive:true});
}

// BTT
const btt=document.getElementById('btt');
if(btt){window.addEventListener('scroll',()=>btt.classList.toggle('show',window.scrollY>400),{passive:true});btt.addEventListener('click',()=>window.scrollTo({top:0,behavior:'smooth'}));}

// Intersection observer
const io=new IntersectionObserver(e=>{e.forEach(x=>{if(x.isIntersecting){x.target.classList.add('visible');io.unobserve(x.target);}});},{threshold:.08,rootMargin:'0px 0px -40px 0px'});
document.querySelectorAll('.card,.sec').forEach(el=>io.observe(el));

// 3D tilt
document.querySelectorAll('.card').forEach(c=>{
  c.addEventListener('mousemove',e=>{const r=c.getBoundingClientRect(),rx=(e.clientY-r.top-r.height/2)/22,ry=(r.width/2-(e.clientX-r.left))/22;c.style.transform=`perspective(1000px) rotateX(${rx}deg) rotateY(${ry}deg) translateY(-8px) scale(1.01)`;});
  c.addEventListener('mouseleave',()=>c.style.transform='');
});

// Magnetic CTA
document.querySelectorAll('.hero-cta,.magnetic').forEach(b=>{
  b.addEventListener('mousemove',e=>{const r=b.getBoundingClientRect(),dx=e.clientX-(r.left+r.width/2),dy=e.clientY-(r.top+r.height/2);b.style.transform=`translate(${dx*.22}px,${dy*.22}px)`;});
  b.addEventListener('mouseleave',()=>b.style.transform='');
});

// Counter
document.querySelectorAll('.stat-n[data-t]').forEach(el=>{
  const t=parseInt(el.dataset.t,10);if(isNaN(t)||el.dataset.date)return;
  let n=0;const st=Math.ceil(t/60),iv=setInterval(()=>{n=Math.min(n+st,t);el.textContent=n;if(n>=t)clearInterval(iv);},18);
});

// Search
const si=document.getElementById('searchIn'),sc=document.getElementById('searchCount');
let to;
if(si){
  si.addEventListener('input',()=>{clearTimeout(to);to=setTimeout(()=>{const q=si.value.toLowerCase().trim();let v=0;
    document.querySelectorAll('.card').forEach(c=>{const m=!q||c.innerText.toLowerCase().includes(q);c.style.display=m?'block':'none';if(m)v++;});
    if(sc){sc.textContent=`${v} issue${v!==1?'s':''} found`;sc.classList.toggle('show',!!q);}},280);});
  document.addEventListener('keydown',e=>{
    if(e.key==='/'&&document.activeElement!==si){e.preventDefault();si.focus();}
    if(e.key==='Escape'&&document.activeElement===si){si.value='';si.blur();document.querySelectorAll('.card').forEach(c=>c.style.display='');if(sc)sc.classList.remove('show');}
  });
}

// Copy code
document.querySelectorAll('.code-copy').forEach(b=>{
  b.addEventListener('click',async()=>{
    const code=b.closest('.code-wrap').querySelector('pre code').textContent;
    try{await navigator.clipboard.writeText(code);b.textContent='Copied!';b.classList.add('copied');setTimeout(()=>{b.textContent='Copy';b.classList.remove('copied');},2000);}
    catch{b.textContent='Failed';setTimeout(()=>b.textContent='Copy',2000);}
  });
});

// Confetti
let cf=false;
window.addEventListener('scroll',()=>{if(cf)return;const s=window.scrollY,h=document.documentElement.scrollHeight-window.innerHeight;if(h>0&&(s/h)>.95){cf=true;fireConfetti();}},{passive:true});
function fireConfetti(){
  const cv=document.getElementById('confetti');if(!cv)return;
  const ctx=cv.getContext('2d');cv.width=window.innerWidth;cv.height=window.innerHeight;
  const cols=['#6366f1','#a855f7','#06b6d4','#ec4899','#10b981','#fbbf24'];
  const ps=Array.from({length:120},()=>({x:window.innerWidth/2,y:window.innerHeight/2,vx:(Math.random()-.5)*18,vy:(Math.random()-.5)*18-6,c:cols[Math.floor(Math.random()*cols.length)],s:Math.random()*7+2,l:1,d:.009+Math.random()*.01}));
  (function a(){ctx.clearRect(0,0,cv.width,cv.height);let al=false;ps.forEach(p=>{if(p.l<=0)return;al=true;p.x+=p.vx;p.y+=p.vy;p.vy+=.28;p.l-=p.d;ctx.globalAlpha=p.l;ctx.fillStyle=p.c;ctx.beginPath();ctx.arc(p.x,p.y,p.s,0,Math.PI*2);ctx.fill();});
  if(al)requestAnimationFrame(a);else ctx.clearRect(0,0,cv.width,cv.height);})();
}

// Particles
const pc=document.getElementById('pcont');
if(pc){for(let i=0;i<22;i++){const p=document.createElement('div');p.style.cssText=`position:absolute;border-radius:50%;background:rgba(99,102,241,.3);left:${Math.random()*100}%;width:${2+Math.random()*3}px;height:${2+Math.random()*3}px;animation:prise ${14+Math.random()*20}s linear ${Math.random()*14}s infinite;`;pc.appendChild(p);}}

// AI Tutor
let to_open=false;
function openTutor(){const p=document.getElementById('tutorPanel'),f=document.getElementById('tutorFab');to_open=true;p.classList.add('open');f.classList.add('hidden');}
function closeTutor(){to_open=false;document.getElementById('tutorPanel').classList.remove('open');document.getElementById('tutorFab').classList.remove('hidden');}
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
  const k=typeof GEMINI_KEY_JS!=='undefined'&&GEMINI_KEY_JS?GEMINI_KEY_JS:(localStorage.getItem('dds-gemini')||'');
  if(!k)return null;
  try{
    const ctx=typeof TUTOR_CTX!=='undefined'?TUTOR_CTX:'';
    const prompt=`You are an expert AI tutor for Daily Dose of DS newsletter content. Use this index to answer questions:\n\n${ctx}\n\nUser: ${msg}\n\nRules: Answer based on the index above. If asked to explain an issue by number, give a thorough explanation. Cite issue number and date.`;
    const res=await fetch(`https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-8b:generateContent?key=${k}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({contents:[{parts:[{text:prompt}]}]})});
    const d=await res.json();return d.candidates?.[0]?.content?.parts?.[0]?.text||null;
  }catch(e){return null;}
}
if(!localStorage.getItem('dds-gemini')){
  setTimeout(()=>{const k=prompt('Enable AI Tutor? Enter your FREE Gemini API key (get at aistudio.google.com):');if(k&&k.trim())localStorage.setItem('dds-gemini',k.trim());},3000);
}
document.querySelectorAll('.chip').forEach(c=>{c.addEventListener('click',()=>{document.getElementById('tutorIn').value=c.dataset.q||c.textContent;tutorSend();});});
document.getElementById('tutorIn')?.addEventListener('keypress',e=>{if(e.key==='Enter')tutorSend();});
"""

# ── HTML helpers ──────────────────────────────────────────────────────────────

def esc(t: str) -> str:
    return str(t).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

def head_html(title: str, ca: str = "#6366f1", cb: str = "#a855f7") -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{esc(title)} | Daily Dose of DS</title>
<meta name="description" content="AI-enhanced study notes from Daily Dose of DS newsletter">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=Fira+Code:wght@400;500&display=swap" rel="stylesheet">
<style>:root{{--ca:{ca};--cb:{cb};}}</style>
<style>{CSS}</style>
</head>"""

def nav_html(back=False) -> str:
    back_link = '<a href="../index.html" class="nav-link">← All Issues</a>' if back else ''
    return f"""
<nav class="nav">
  <div class="nav-in">
    <a href="{'../index.html' if back else 'index.html'}" class="nav-logo" style="cursor:none">
      <div class="gem">📚</div><span>{SITE_TITLE}</span>
    </a>
    <div class="nav-links">
      {back_link}
      <button class="nav-btn" id="themeBtn">☀️</button>
    </div>
  </div>
</nav>"""

def common_tail(tutor_ctx_js: str = "''") -> str:
    return f"""
<button class="btt" id="btt">↑</button>
<button class="fab" id="tutorFab" onclick="openTutor()">🧠</button>
<div class="tutor" id="tutorPanel">
  <div class="tutor-head">
    <div class="tutor-title"><span class="dot-live"></span>AI Study Tutor</div>
    <button class="t-close" onclick="closeTutor()">✕</button>
  </div>
  <div class="tutor-hint">Ask me to <strong>explain any issue by number</strong> — e.g. "Explain issue #5"</div>
  <div class="tutor-body" id="tutorBody">
    <div class="msg bot">👋 Hi! I know all {SITE_TITLE} issues. Try:<br><br><em>"Explain issue #3"</em> or <em>"What topics cover RAG?"</em></div>
  </div>
  <div class="chips">
    <span class="chip" data-q="Explain issue #1">Issue #1</span>
    <span class="chip" data-q="What topics have been covered?">All topics</span>
    <span class="chip" data-q="Which issues cover LLMs?">LLMs</span>
    <span class="chip" data-q="Give me key takeaways from issue #5">Takeaways #5</span>
  </div>
  <div class="tutor-inp">
    <input class="tutor-input" id="tutorIn" placeholder='Try "Explain issue #7"...'>
    <button class="tsend" id="tSend" onclick="tutorSend()">Ask</button>
  </div>
</div>
<canvas id="confetti"></canvas>
<div id="pcont" style="position:fixed;inset:0;z-index:-1;pointer-events:none;overflow:hidden;"></div>
<script>const GEMINI_KEY_JS='';const TUTOR_CTX={tutor_ctx_js};</script>
<script>{JS}</script>"""


# ── HTML Generator ────────────────────────────────────────────────────────────

class SiteBuilder:
    def __init__(self):
        self.out = Path(OUT_DIR)
        self.out.mkdir(exist_ok=True)
        (self.out / "entries").mkdir(exist_ok=True)

    def build_entry(self, email: RawEmail, note: StudyNote, tutor_ctx_js: str) -> str:
        """Build a single issue page. Returns relative path like entries/..."""
        ca, cb = cat_color(note.category)
        safe   = re.sub(r'[^\w\s-]','',note.topic).strip().replace(' ','-')[:50]
        fname  = f"entries/{note.date}_issue{note.issue_number:03d}_{safe}.html"
        fpath  = self.out / fname
        d_disp = datetime.strptime(note.date, "%Y-%m-%d").strftime("%B %d, %Y")

        # Build content sections HTML
        content_html = ""

        # TLDR box
        if note.tldr:
            content_html += f"""
<div class="sec visible" style="--ca:{ca};--cb:{cb}">
  <div class="tldr-label">TL;DR</div>
  <p>{esc(note.tldr)}</p>
</div>"""

        # Overview
        if note.overview:
            paras = "\n".join(f"<p>{esc(p)}</p>" for p in note.overview.split("\n") if p.strip())
            content_html += f"""
<div class="sec">
  <h2><span class="sec-icon">📋</span>Overview</h2>
  {paras}
</div>"""

        # Dynamic sections (one per major topic in the email)
        icons = ["🔬","💡","⚙️","🏗️","📊","🔧","🎯","🌐"]
        for i, sec in enumerate(note.sections):
            body_paras = "\n".join(f"<p>{esc(p)}</p>" for p in sec["body"].split("\n") if p.strip())
            code_html  = ""
            if sec.get("code"):
                code_esc = esc(sec["code"])
                code_html = f"""
<div class="code-wrap">
  <div class="code-head">
    <span class="code-lang">Python</span>
    <button class="code-copy">Copy</button>
  </div>
  <pre><code>{code_esc}</code></pre>
</div>"""
            content_html += f"""
<div class="sec">
  <h2><span class="sec-icon">{icons[i % len(icons)]}</span>{esc(sec["title"])}</h2>
  {body_paras}
  {code_html}
</div>"""

        # Key points
        if note.key_points:
            items = "\n".join(f"<li>{esc(k)}</li>" for k in note.key_points)
            content_html += f"""
<div class="sec">
  <h2><span class="sec-icon">📌</span>Key Takeaways</h2>
  <ul>{items}</ul>
</div>"""

        # Interview questions
        if note.interview_qs:
            qs = "\n".join(f'<div class="iq-q">{esc(q)}</div>' for q in note.interview_qs)
            content_html += f"""
<div class="sec">
  <h2><span class="sec-icon">🎯</span>Interview Questions</h2>
  {qs}
</div>"""

        # Further reading
        if note.further:
            items = "\n".join(f"<li>{esc(f)}</li>" for f in note.further)
            content_html += f"""
<div class="sec">
  <h2><span class="sec-icon">📚</span>Further Reading</h2>
  <ul>{items}</ul>
</div>"""

        html = f"""{head_html(note.topic, ca, cb)}
<body>
<div class="aurora"><div class="orb"></div><div class="orb"></div><div class="orb"></div><div class="orb"></div></div>
<div class="grid-bg"></div>
<div class="cur-dot"></div><div class="cur-ring"></div>
<div class="scroll-bar" id="scrollBar"></div>
<div class="read-ring" id="readRing">
  <svg width="48" height="48" viewBox="0 0 48 48">
    <defs><linearGradient id="rg" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="{ca}"/><stop offset="100%" stop-color="{cb}"/>
    </linearGradient></defs>
    <circle class="rr-bg" cx="24" cy="24" r="20"/>
    <circle class="rr-prog" cx="24" cy="24" r="20" stroke="url(#rg)"/>
  </svg>
</div>
{nav_html(back=True)}
<div class="entry-hero" style="--ca:{ca};--cb:{cb}">
  <div class="issue-badge">Issue #{note.issue_number} · {esc(note.category)}</div>
  <h1 class="entry-title">{esc(note.topic)}</h1>
  <div class="entry-meta">
    <span>📅 {d_disp}</span><span>·</span>
    <span>📬 Daily Dose of DS</span>
  </div>
</div>
<div class="entry-body" style="--ca:{ca};--cb:{cb}">
  {content_html}
</div>
<div class="footer">
  <a href="../index.html">← Back to all issues</a> &nbsp;·&nbsp; {SITE_TITLE}
</div>
{common_tail(tutor_ctx_js)}
</body></html>"""

        fpath.write_text(html, encoding="utf-8")
        return fname

    def build_index(self, rows, tutor_ctx_js: str):
        """
        rows: list of (date, topic, html_file, subject, category, issue_number)
        sorted by date DESC (newest first)
        """
        cards = ""
        for date, topic, html_file, subject, category, issue_num in rows:
            ca, cb = cat_color(category or "Data Science")
            d_obj  = datetime.fromisoformat(date)
            d_disp = d_obj.strftime("%d %b %Y")
            num    = issue_num or 0
            desc   = esc((subject or topic)[:90])
            cards += f"""
<a href="{html_file}" class="card" style="--ca:{ca};--cb:{cb}">
  <div class="card-issue">#{num:03d}<span class="cat-badge">{esc(category or 'DS')}</span></div>
  <div class="card-title">{esc(topic.replace('_',' '))}</div>
  <div class="card-desc">{desc}...</div>
  <div class="card-foot">
    <span class="card-date">📅 {d_disp}</span>
    <div class="arrow">→</div>
  </div>
</a>"""

        total  = len(rows)
        cats   = len(set(r[4] for r in rows if r[4]))
        latest = rows[0][0][:10] if rows else "—"

        empty = """<div class="empty">
  <div class="empty-icon">📬</div>
  <h2>No issues yet</h2>
  <p>Run <code>python build_site.py --first-run</code> to process your emails.</p>
</div>""" if not cards else ""

        html = f"""{head_html(SITE_TITLE)}
<body>
<div class="aurora"><div class="orb"></div><div class="orb"></div><div class="orb"></div><div class="orb"></div></div>
<div class="grid-bg"></div>
<div class="cur-dot"></div><div class="cur-ring"></div>
<div class="scroll-bar" id="scrollBar"></div>
{nav_html()}
<div class="hero">
  <canvas id="neural-canvas"></canvas>
  <div class="hero-in">
    <div class="badge"><span class="dot-live"></span>Auto-Updated Daily</div>
    <h1><span class="shine">Daily Dose of DS</span></h1>
    <p class="hero-sub">AI-enhanced study notes from every Daily Dose of DS newsletter issue.<br>Indexed, searchable, and explained by your personal AI tutor.</p>
    <a href="#issues" class="hero-cta magnetic">Browse All Issues ↓</a>
    <div style="margin-top:16px;">
      <a href="ebook.html" class="ebook-btn magnetic">📖 Download E-Book</a>
    </div>
  </div>
</div>
<div class="stats">
  <div class="stat"><div class="stat-n" data-t="{total}">{total}</div><div class="stat-l">Issues</div></div>
  <div class="stat-sep"></div>
  <div class="stat"><div class="stat-n" data-t="{cats}">{cats}</div><div class="stat-l">Categories</div></div>
  <div class="stat-sep"></div>
  <div class="stat"><div class="stat-n" data-date="true">{latest}</div><div class="stat-l">Latest</div></div>
</div>
<div class="grid-wrap" id="issues">
  <div class="search-wrap">
    <span class="search-ico">🔍</span>
    <input class="search-in" id="searchIn" placeholder="Search issues… (press / to focus)">
    <span class="search-kbd">/</span>
  </div>
  <div class="search-count" id="searchCount"></div>
  <div class="card-grid">{cards or empty}</div>
</div>
<div class="footer">
  Auto-generated from Daily Dose of DS emails · Updated daily at 7:00 AM IST ·
  <a href="https://www.dailydoseofds.com" target="_blank">dailydoseofds.com</a>
</div>
{common_tail(tutor_ctx_js)}
</body></html>"""

        (self.out / "index.html").write_text(html, encoding="utf-8")
        log.info("Index built — %d issues.", total)

    def build_ebook_page(self, db: DB):
        """
        Build ebook.html — a beautiful in-browser e-book with all issues,
        TOC at top linked to each chapter.
        Also generates a downloadable PDF version via ReportLab if available.
        """
        rows = db.all_for_ebook()
        if not rows:
            # Placeholder
            html = f"""{head_html("E-Book")}
<body>
<div class="aurora"><div class="orb"></div><div class="orb"></div></div>
{nav_html()}<div style="text-align:center;padding:100px 20px;">
<h1 style="color:var(--a)">E-Book</h1>
<p style="color:var(--text-2);margin-top:16px">No issues processed yet. Run <code>python build_site.py --first-run</code> first.</p>
</div></body></html>"""
            (self.out / "ebook.html").write_text(html, encoding="utf-8")
            return

        # Build TOC
        toc_items = ""
        chapters  = ""
        for num, date, topic, note in rows:
            d_disp = datetime.strptime(date, "%Y-%m-%d").strftime("%B %d, %Y")
            ca, cb = cat_color(note.category)
            toc_items += f"""
<a href="#ch{num}" style="display:flex;align-items:center;gap:12px;padding:10px 16px;border-radius:10px;
  text-decoration:none;color:var(--text-2);transition:all .2s;border:1px solid transparent;"
  onmouseover="this.style.background='rgba(99,102,241,.08)';this.style.borderColor='rgba(99,102,241,.15)';this.style.color='var(--text)'"
  onmouseout="this.style.background='';this.style.borderColor='transparent';this.style.color='var(--text-2)'">
  <span style="color:{ca};font-weight:800;font-size:.8rem;min-width:60px">#{num:03d}</span>
  <span style="font-size:.9rem">{esc(topic.replace('_',' '))}</span>
  <span style="margin-left:auto;color:var(--text-3);font-size:.75rem">{d_disp}</span>
</a>"""

            # Chapter content
            chap_content = ""
            if note.tldr:
                chap_content += f'<div class="tldr-box" style="--ca:{ca};--cb:{cb}"><div class="tldr-label">TL;DR</div><p>{esc(note.tldr)}</p></div>'
            if note.overview:
                paras = "".join(f"<p>{esc(p)}</p>" for p in note.overview.split("\n") if p.strip())
                chap_content += f'<h3 style="color:{ca};margin:24px 0 12px">Overview</h3>{paras}'
            for sec in note.sections:
                paras = "".join(f"<p>{esc(p)}</p>" for p in sec["body"].split("\n") if p.strip())
                chap_content += f'<h3 style="color:{ca};margin:24px 0 12px">{esc(sec["title"])}</h3>{paras}'
                if sec.get("code"):
                    code_esc = esc(sec["code"])
                    chap_content += f'<div class="code-wrap"><div class="code-head"><span class="code-lang">Python</span><button class="code-copy">Copy</button></div><pre><code>{code_esc}</code></pre></div>'
            if note.key_points:
                items = "".join(f"<li>{esc(k)}</li>" for k in note.key_points)
                chap_content += f'<h3 style="color:{ca};margin:24px 0 12px">Key Takeaways</h3><ul>{items}</ul>'

            chapters += f"""
<div id="ch{num}" style="margin-bottom:60px;padding-bottom:60px;border-bottom:1px solid var(--border);">
  <div style="display:flex;align-items:baseline;gap:12px;margin-bottom:4px;">
    <span style="font-size:.75rem;font-weight:800;color:{ca};text-transform:uppercase;letter-spacing:1.5px">Chapter {num}</span>
    <span style="font-size:.75rem;color:var(--text-3)">{d_disp} · {esc(note.category)}</span>
  </div>
  <h2 style="font-size:clamp(1.5rem,3vw,2.2rem);font-weight:900;margin-bottom:20px;
    background:linear-gradient(135deg,var(--text) 0%,{ca} 60%,{cb} 100%);
    -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text">
    {esc(topic.replace('_',' '))}
  </h2>
  {chap_content}
  <a href="#toc" style="display:inline-flex;align-items:center;gap:6px;color:{ca};text-decoration:none;font-size:.85rem;margin-top:20px;opacity:.7;transition:opacity .2s"
    onmouseover="this.style.opacity='1'" onmouseout="this.style.opacity='.7'">↑ Back to Table of Contents</a>
</div>"""

        html = f"""{head_html("Complete E-Book | Daily Dose of DS")}
<body>
<div class="aurora"><div class="orb"></div><div class="orb"></div><div class="orb"></div></div>
<div class="grid-bg"></div>
<div class="cur-dot"></div><div class="cur-ring"></div>
<div class="scroll-bar" id="scrollBar"></div>
<div class="read-ring" id="readRing">
  <svg width="48" height="48" viewBox="0 0 48 48">
    <defs><linearGradient id="rg" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="var(--a)"/><stop offset="100%" stop-color="var(--b)"/>
    </linearGradient></defs>
    <circle class="rr-bg" cx="24" cy="24" r="20"/>
    <circle class="rr-prog" cx="24" cy="24" r="20" stroke="url(#rg)"/>
  </svg>
</div>
{nav_html(back=True)}
<div style="max-width:860px;margin:0 auto;padding:clamp(40px,6vw,80px) 24px 80px;">

  <!-- Book cover -->
  <div style="text-align:center;padding:60px 20px;margin-bottom:60px;
    background:var(--card);border:1px solid var(--border);border-radius:var(--r24);
    position:relative;overflow:hidden;">
    <div style="position:absolute;inset:0;background:linear-gradient(135deg,rgba(99,102,241,.06),rgba(168,85,247,.04));pointer-events:none;"></div>
    <div style="position:relative;z-index:1;">
      <div style="font-size:4rem;margin-bottom:16px;">📚</div>
      <h1 style="font-size:clamp(2rem,5vw,3.5rem);font-weight:900;margin-bottom:12px;">
        <span class="shine">Daily Dose of DS</span>
      </h1>
      <p style="font-size:1.3rem;color:var(--text-2);margin-bottom:8px;font-weight:600">Complete Study Notes</p>
      <p style="color:var(--text-3);font-size:.9rem">{len(rows)} Issues · Generated {datetime.now().strftime("%B %d, %Y")}</p>
    </div>
  </div>

  <!-- TOC -->
  <div id="toc" style="margin-bottom:60px;">
    <h2 style="font-size:1.8rem;font-weight:800;margin-bottom:24px;color:var(--a)">📑 Table of Contents</h2>
    <div style="background:var(--card);border:1px solid var(--border);border-radius:var(--r20);padding:16px;">
      {toc_items}
    </div>
  </div>

  <!-- Chapters -->
  <div id="chapters">
    {chapters}
  </div>

</div>
<div class="footer">
  <a href="index.html">← Back to Issues Index</a> &nbsp;·&nbsp; Daily Dose of DS E-Book
</div>
{common_tail()}
</body></html>"""

        (self.out / "ebook.html").write_text(html, encoding="utf-8")
        log.info("E-book page built — %d chapters.", len(rows))


# ── Orchestrator ──────────────────────────────────────────────────────────────

class App:
    def __init__(self):
        self.db    = DB()
        self.ai    = None
        self.gmail = None
        self.site  = SiteBuilder()

    def _init_apis(self):
        self.gmail = Gmail()
        self.ai    = AI()

    def _tutor_ctx(self) -> str:
        return json.dumps(self.db.tutor_context())

    def run(self, first_run: bool = False):
        log.info("=" * 55)
        log.info("Daily Dose of DS v6.0 — Mode: %s", "FULL HISTORY" if first_run else "DAILY")
        log.info("=" * 55)
        self._init_apis()

        after    = None if first_run else datetime.now() - timedelta(days=1)
        messages = self.gmail.fetch_all(after)
        if not messages:
            log.info("No emails found. Rebuilding site...")
            self._rebuild()
            return

        # Process oldest first for correct issue numbering
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

        # Generate AI-enhanced study notes
        note             = self.ai.enhance(email)
        note.issue_number = self.db.next_issue()

        # Build the entry page
        ctx_js   = self._tutor_ctx()
        html_file = self.site.build_entry(email, note, ctx_js)

        # Save to DB
        self.db.save(
            email.email_id, email.subject,
            email.date.strftime("%Y-%m-%d"),
            note.topic, note.category, email.content_hash,
            html_file, note
        )
        log.info("✅ Issue #%d: %s [%s]", note.issue_number, note.topic, note.category)
        time.sleep(5)  # Rate limit respect

    def _rebuild(self):
        rows     = self.db.all_issues()
        ctx_js   = self._tutor_ctx()
        self.site.build_index(rows, ctx_js)
        self.site.build_ebook_page(self.db)

    def rebuild_only(self):
        """Rebuild HTML from existing DB without fetching new emails."""
        log.info("Rebuilding site from existing database...")
        self._rebuild()
        log.info("Done.")

    def _deploy(self):
        log.info("Deploying to GitHub Pages...")
        try:
            subprocess.run(["git","add","docs/"], check=True)
            subprocess.run(["git","commit","-m",f"🤖 Auto-update: {datetime.now().strftime('%Y-%m-%d %H:%M')} [v6]"], check=False)
            subprocess.run(["git","push"], check=True)
            log.info("Deployed ✅")
        except Exception as e:
            log.error("Deploy failed: %s", e)

    def schedule(self):
        import schedule as sched
        sched.every().day.at("07:00").do(lambda: self.run())
        log.info("Scheduler active — runs daily at 07:00. Ctrl+C to stop.")
        while True:
            sched.run_pending(); time.sleep(60)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="Daily Dose of DS Website v6.0")
    p.add_argument("--first-run", action="store_true", help="Process ALL historical emails")
    p.add_argument("--daily",     action="store_true", help="Process new emails only")
    p.add_argument("--rebuild",   action="store_true", help="Rebuild site from DB (no Gmail fetch)")
    p.add_argument("--schedule",  action="store_true", help="Run daily scheduler")
    args = p.parse_args()

    app = App()
    if   args.schedule: app._init_apis(); app.schedule()
    elif args.rebuild:  app.rebuild_only()
    else:               app.run(first_run=args.first_run)

if __name__ == "__main__":
    main()
