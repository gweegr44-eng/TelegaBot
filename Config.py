import os
from dotenv import load_dotenv

load_dotenv()

TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
GC_CREDENTIALS_PATH = os.getenv("GC_CREDENTIALS_PATH", "credentials.json")
DB_PATH = os.getenv("DB_PATH", "database.db")
TZ = os.getenv("TZ", "Europe/Moscow")
OWM_API_KEY = os.getenv("OWM_API_KEY")