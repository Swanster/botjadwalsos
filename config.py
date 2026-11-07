# config.py
import os
from dotenv import load_dotenv

# Selalu baca .env di samping config.py, bukan dari cwd proses.
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

API_TOKEN = os.environ.get('API_TOKEN', 'mock_api_token')
ADMIN_ID = int(os.environ.get('ADMIN_ID', '123456789'))
GROUP_CHAT_ID = int(os.environ.get('GROUP_CHAT_ID', '-100123456789'))
ALLOWED_TOPIC_ID = os.environ.get('ALLOWED_TOPIC_ID') or None
if ALLOWED_TOPIC_ID is not None:
    ALLOWED_TOPIC_ID = int(ALLOWED_TOPIC_ID)

DB_NAME = os.environ.get('DB_NAME', 'data/jadwal_pro.db')

WEB_HOST = os.environ.get('WEB_HOST', '127.0.0.1')
WEB_PORT = int(os.environ.get('WEB_PORT', '5050'))
SECRET_KEY = os.environ.get('SECRET_KEY', '')

GOOGLE_CREDENTIALS_FILE = os.environ.get('GOOGLE_CREDENTIALS_FILE', 'google_credentials.json')
GOOGLE_SHEET_ID = os.environ.get('GOOGLE_SHEET_ID', '')
GOOGLE_SHEET_SYNC_ENABLED = os.environ.get('GOOGLE_SHEET_SYNC_ENABLED', 'false').lower() == 'true'

# LLM untuk /tanya (OpenAI-compatible). Kosong = hanya jadwal via parser deterministik.
AI_BASE_URL = os.environ.get('AI_BASE_URL', 'http://127.0.0.1:20128/v1').rstrip('/')
AI_API_KEY = os.environ.get('AI_API_KEY', '')
AI_MODEL = os.environ.get('AI_MODEL', 'oc/deepseek-v4.1-flash-free')
AI_TIMEOUT = int(os.environ.get('AI_TIMEOUT', '45'))
