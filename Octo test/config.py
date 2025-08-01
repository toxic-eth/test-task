import os
from dotenv import load_dotenv

# Загружаем переменные из .env
load_dotenv()

# --- Steam ---
APPID = os.getenv("STEAM_APP_ID", "730")
STEAM_API_KEY = os.getenv("STEAM_API_KEY")  # можно не использовать пока

# --- Reddit ---
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "cs2-monitor/0.1 by Toxic_eth")

# --- Параметры сбора ---
DAYS = int(os.getenv("DAYS", "30"))  # сколько дней назад включительно

# --- Пути ---
DB_PATH = os.path.join("db", "cs2_monitor.db")
OUTPUT_CSV = os.path.join("output", "cs2_cs2_reddit_steam_timeseries.csv")
PLOT_PATH = os.path.join("output", "plot.png")
LOG_PATH = "cs2_monitor.log"

# --- Метаданные ---
GAME_NAME = "Counter-Strike 2"

# --- Ключевые слова для старого варианта (если используешь расширенный/другой сбор) ---
REDDIT_KEYWORDS = [
    "Counter-Strike 2",
    "CS2",
    "CS 2",
    "CS2 update",
    "Counter Strike 2 update",
    "CS2 bug",
    "CS2 crash",
    "CS2 gameplay",
    "Counter-Strike 2 gameplay",
    "CS2 review",
    "Counter Strike 2 review",
    "CS2 patch",
    "CS2 servers",
    "CS2 performance",
    "CS2 fps drop",
    "CS2 matchmaking",
    "CS2 rank",
    "CS2 skins",
    "CS2 trade",
    "CS2 launch",
    "CounterStrike 2",
    "Counter Strike2",
    "CS2 reddit",
    "Counter-Strike 2 reddit",
]
