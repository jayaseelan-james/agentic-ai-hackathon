import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
RESTRICTED_MODEL = 'gemma-4-26b-a4b-it'
WEB_TOOLS = {'google_search', 'web_search', 'url_context', 'fetch_url', 'browse_web'}


def settings():
    load_dotenv(ROOT / '.env', override=False)
    return os.getenv('GEMINI_API_KEY', ''), os.getenv('GEMINI_MODEL', 'gemini-4-carbon')


def speech_settings():
    settings()  # Load the same backend-only .env, respecting process overrides.
    return (os.getenv('GEMINI_STT_MODEL', 'gemini-3.5-transcribe'),
            os.getenv('GEMINI_TTS_MODEL', 'gemini-3.8-flash-tts'),
            os.getenv('GEMINI_TTS_VOICE', 'Kore'))
