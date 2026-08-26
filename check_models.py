"""
Run this once from your project folder:  python check_models.py
It reads GEMINI_API_KEY from your .env and asks Google directly which
models your specific key/project can actually call for generateContent —
ground truth instead of guessing a model name that might be deprecated.

Uses the current `google-genai` SDK (pip install google-genai). The old
`google-generativeai` package is deprecated and may not know about newer
models even if your key has access to them.
"""
import os
from dotenv import load_dotenv
load_dotenv()

from google import genai

key = os.getenv("GEMINI_API_KEY", "")
if not key:
    print("No GEMINI_API_KEY found in .env"); raise SystemExit(1)

client = genai.Client(api_key=key)

print("Models available to YOUR key for generateContent:\n")
for m in client.models.list():
    actions = getattr(m, "supported_actions", None) or []
    if not actions or "generateContent" in actions:
        print(" -", m.name)