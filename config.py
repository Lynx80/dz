import os
from dotenv import load_dotenv

load_dotenv()

# Bot Settings
API_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8684063011:AAHpBjpulnliaz2-Qnnvh_DPUwQaNygj8lg")
PROXY_URL = os.getenv("TELEGRAM_PROXY")

# Database
DB_PATH = "database.db"

# AI
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_API_KEYS_RAW = os.getenv("GEMINI_API_KEYS", "")
GEMINI_API_KEYS = [k.strip() for k in GEMINI_API_KEYS_RAW.split(",") if k.strip()]
if GEMINI_API_KEY and GEMINI_API_KEY not in GEMINI_API_KEYS:
    GEMINI_API_KEYS.append(GEMINI_API_KEY)

# Files
PID_FILE = "bot.pid"
LOG_DIR = "." # Or "logs" if wanted

# Accuracy & Modes
ACCURACY_MODES = {
    "basic": "Базовая (70%)",
    "advanced": "Продвинутая (85%)",
    "perfect": "Идеальная (95%)"
}

SOLVE_DELAY_OPTIONS = [1, 5, 10, 15, 20, 25]

# Development & Testing (Toggle when finished)
DEBUG_SOLVER_EYES = True  # Send live screenshots to Telegram
HEADLESS = False          # Show chrome window on the server/PC
USE_AI_SOLVER = True    # Use Gemini API for vision tasks
