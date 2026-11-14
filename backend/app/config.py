import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]


def settings():
    load_dotenv(ROOT / '.env', override=False)
    return os.getenv('GEMINI_API_KEY', ''), os.getenv('GEMINI_MODEL', 'gemini-4-carbon')
