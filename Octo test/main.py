import os
import time
import datetime
import sqlite3
import csv
import re

import requests
import matplotlib.pyplot as plt
import praw
import logging
import pandas as pd

from config import (
    APPID,
    REDDIT_CLIENT_ID,
    REDDIT_CLIENT_SECRET,
    REDDIT_USER_AGENT,
    DAYS,
    DB_PATH,
    OUTPUT_CSV,
    PLOT_PATH,
    LOG_PATH,
    GAME_NAME,
)

# --- Logging ---
logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
console = logging.StreamHandler()
console.setLevel(logging.INFO)
console.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logging.getLogger().addHandler(console)

# --- DB ---
def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS steam_snapshot (
            date TEXT PRIMARY KEY,
            metric INTEGER,
            source TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS reddit_mentions (
            date TEXT,
            keyword TEXT,
            count INTEGER,
            PRIMARY KEY (date, keyword)
        )
    """)
    conn.commit()
    return conn

# --- Steam fallback history ---
def load_local_steam_history(path="data/steam_history.csv"):
    if not os.path.isfile(path):
        logging.warning(f"Локальный steam_history.csv не найден: {path}")
        return {}
    try:
        df = pd.read_csv(path, sep=';', quotechar='"', parse_dates=["DateTime"], dayfirst=False)
        df = df.sort_values("DateTime")
        df["Followers"] = df["Followers"].astype(int)
        df["date"] = df["DateTime"].dt.strftime("%Y-%m-%d")
        series = df.groupby("date")["Followers"].last().to_dict()
        return series
    except Exception as e:
        logging.error(f"Ошибка чтения локальной истории Steam: {e}")
        return {}

# --- Steam scraping / fallback ---
def scrape_steamdb_followers_simple(appid):
    url = f"https://steamdb.info/app/{appid}/charts/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Referer": "https://steamdb.info/",
    }
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            logging.warning(f"[SteamDB] статус {r.status_code}, не удалось получить followers.")
            return None
        m = re.search(r"name:\s*'Followers'.*?data:\s*(\[\[.*?\]\])", r.text, re.DOTALL)
        if not m:
            logging.info("[SteamDB] блок Followers не найден.")
            return None
        data_blob = m.group(1)
        pairs = re.findall(r'\[\s*(\d+)\s*,\s*([\d,]+)\s*\]', data_blob)
        if not pairs:
            logging.info("[SteamDB] нет данных followers.")
            return None
        _, last_val = pairs[-1]
        return int(last_val.replace(",", ""))
    except Exception as e:
        logging.error(f"[SteamDB] исключение при парсинге followers: {e}")
        return None

def get_current_players(appid):
    try:
        url = f"https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/?appid={appid}"
        r = requests.get(url, timeout=5)
        if r.status_code != 200:
            logging.warning(f"[Steam API] concurrent players запрос вернул {r.status_code}")
            return None
        data = r.json()
        count = data.get("response", {}).get("player_count")
        if isinstance(count, int):
            logging.info(f"[Steam API] concurrent players: {count}")
            return count
    except Exception as e:
        logging.error(f"[Steam API] исключение: {e}")
    return None

def get_steam_followers_or_fallback(appid):
    today = datetime.date.today()
    date_str = today.strftime("%Y-%m-%d")
    followers = scrape_steamdb_followers_simple(appid)
    source = None
    if followers is not None:
        source = "followers (SteamDB)"
    else:
        local = load_local_steam_history("data/steam_history.csv")
        followers = local.get(date_str)
        if followers is not None:
            source = "local_history"
        else:
            cp = get_current_players(appid)
            followers = cp
            source = "concurrent_players (Steam API)"
    return followers, source

# --- Reddit init ---
def init_reddit():
    if not all([REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT]):
        raise RuntimeError("Reddit credentials не заданы в .env")
    return praw.Reddit(
        client_id=REDDIT_CLIENT_ID,
        client_secret=REDDIT_CLIENT_SECRET,
        user_agent=REDDIT_USER_AGENT,
        timeout=10,
    )

# --- Reddit mentions CS2 ---
def fetch_reddit_mentions_cs2(start_date, end_date, conn, reddit_obj=None):
    cur = conn.cursor()
    keywords = [
        "#CS2",
        "#CounterStrike2",
        "CS2 launch",
        "CS2 update",
        "CS2 skins",
        "CS2 trade",
        "Counter-Strike 2",
        "CS2 reddit",
    ]

    current = start_date
    while current < end_date:
        ds = current.strftime("%Y-%m-%d")
        day_start = int(datetime.datetime(current.year, current.month, current.day).timestamp())
        day_end = int((datetime.datetime(current.year, current.month, current.day) + datetime.timedelta(days=1)).timestamp())

        seen_ids = set()

        for kw in keywords:
            logging.info(f"[Pushshift] собираем '{kw}' за {ds}")
            params = {
                "q": kw,
                "after": day_start,
                "before": day_end,
                "size": 500,
                "sort": "desc",
            }
            url = "https://api.pushshift.io/reddit/search/submission/"
            error_streak = 0
            for attempt in range(1, 4):
                try:
                    resp = requests.get(url, params=params, timeout=10)
                    if resp.status_code == 403:
                        logging.warning(f"[Pushshift] {kw} {ds} попытка {attempt}: 403 Forbidden")
                        error_streak += 1
                        time.sleep(2)
                        continue
                    if resp.status_code != 200:
                        logging.warning(f"[Pushshift] {kw} {ds} попытка {attempt}: статус {resp.status_code}")
                        error_streak += 1
                        time.sleep(2)
                        continue
                    data = resp.json().get("data", [])
                    for submission in data:
                        sid = submission.get("id")
                        if not sid or sid in seen_ids:
                            continue
                        title = submission.get("title", "") or ""
                        selftext = submission.get("selftext", "") or ""
                        combined = f"{title} {selftext}".lower()
                        token = kw.lower().lstrip("#")
                        if token in combined:
                            seen_ids.add(sid)
                    logging.info(f"[Pushshift] {kw} {ds} -> накоплено уникальных {len(seen_ids)}")
                    break
                except Exception as e:
                    logging.warning(f"[Pushshift] {kw} {ds} попытка {attempt}: {e}")
                    error_streak += 1
                    time.sleep(2)
            if error_streak >= 3 and reddit_obj is not None:
                logging.info(f"[Reddit API fallback] для '{kw}' за {ds}")
                try:
                    subreddit = reddit_obj.subreddit("all")
                    for submission in subreddit.search(kw, limit=300, sort="new"):
                        if not (day_start <= submission.created_utc < day_end):
                            continue
                        sid = submission.id
                        if sid in seen_ids:
                            continue
                        title = submission.title or ""
                        selftext = getattr(submission, "selftext", "") or ""
                        combined = f"{title} {selftext}".lower()
                        token = kw.lower().lstrip("#")
                        if token in combined:
                            seen_ids.add(sid)
                    logging.info(f"[Reddit API] {kw} {ds} -> накоплено уникальных {len(seen_ids)} (fallback)")
                except Exception as e:
                    logging.error(f"[Reddit API] ошибка для '{kw}' на {ds}: {e}")

        total_count = len(seen_ids)
        logging.info(f"[Aggregate] CS2 упоминаний за {ds} (хештеги): {total_count}")

        cur.execute(
            "INSERT OR REPLACE INTO reddit_mentions (date, keyword, count) VALUES (?, ?, ?)",
            (ds, "cs2_tags", total_count)
        )
        conn.commit()

        current += datetime.timedelta(days=1)

def aggregate_reddit_daily(conn, start_date, end_date):
    cur = conn.cursor()
    aggregated = {}
    current = start_date
    while current < end_date:
        ds = current.strftime("%Y-%m-%d")
        cur.execute("SELECT SUM(count) FROM reddit_mentions WHERE date = ?", (ds,))
        row = cur.fetchone()
        aggregated[ds] = row[0] if row and row[0] is not None else 0
        current += datetime.timedelta(days=1)
    return aggregated

# --- Time series ---
def get_steam_series(conn, start_date, end_date):
    cur = conn.cursor()
    series = {}
    last_value = None
    current = start_date
    while current < end_date:
        ds = current.strftime("%Y-%m-%d")
        cur.execute("SELECT metric FROM steam_snapshot WHERE date = ?", (ds,))
        row = cur.fetchone()
        if row and row[0] is not None:
            last_value = row[0]
            series[ds] = row[0]
        else:
            series[ds] = last_value
        current += datetime.timedelta(days=1)
    return series

def build_time_series(conn, start_date, end_date):
    steam_series = get_steam_series(conn, start_date, end_date)
    reddit_series = aggregate_reddit_daily(conn, start_date, end_date)
    rows = []
    current = start_date
    while current < end_date:
        ds = current.strftime("%Y-%m-%d")
        rows.append({
            "date": ds,
            "steam_metric": steam_series.get(ds),
            "reddit_mentions": reddit_series.get(ds, 0)
        })
        current += datetime.timedelta(days=1)
    return rows

# --- Growth calc ---
def compute_follower_growth(rows):
    steam_vals = [r["steam_metric"] for r in rows if r["steam_metric"] is not None]
    if not steam_vals:
        return None
    start = steam_vals[0]
    end = steam_vals[-1]
    absolute = end - start if start is not None and end is not None else None
    percent = (absolute / start * 100) if start and start != 0 else None
    return {
        "start": start,
        "end": end,
        "absolute_growth": absolute,
        "percent_growth": percent,
    }

# --- Output ---
def save_csv(rows, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["date", "steam_metric", "reddit_mentions"])
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

def plot_absolute(rows, steam_source):
    dates = [datetime.datetime.strptime(r["date"], "%Y-%m-%d").date() for r in rows]
    steam_vals = [r["steam_metric"] if r["steam_metric"] is not None else 0 for r in rows]
    reddit_vals = [r["reddit_mentions"] for r in rows]

    fig, ax1 = plt.subplots()
    ax1.set_xlabel("Дата")
    ax1.set_ylabel("Reddit упоминаний (CS2)", color="tab:orange")
    bars = ax1.bar(dates, reddit_vals, label="Reddit mentions (бар)", alpha=0.4, color="orange")
    line_reddit, = ax1.plot(dates, reddit_vals, label="Reddit mentions (линия)", linestyle='-', marker='x', color="darkorange")
    ax1.tick_params(axis="y", labelcolor="tab:orange")
    ax1.grid(True, axis="x", linestyle="--", alpha=0.3)

    ax2 = ax1.twinx()
    ax2.set_ylabel("Followers Steam", color="tab:blue")
    line_steam, = ax2.plot(dates, steam_vals, label="Steam followers", marker="o", linestyle='-', color="royalblue")
    ax2.tick_params(axis="y", labelcolor="tab:blue")

    # Легенда
    lines = [line_reddit, bars, line_steam]
    labels = ["Reddit mentions (линия)", "Reddit mentions (бар)", "Steam followers"]
    ax1.legend(lines, labels, loc="upper left")

    plt.title(f"{GAME_NAME} — упоминания CS2 Reddit и рост фолловеров ({steam_source})")
    fig.tight_layout()
    os.makedirs(os.path.dirname(PLOT_PATH), exist_ok=True)
    plt.savefig(PLOT_PATH)
    logging.info(f"График абсолютных значений сохранён: {PLOT_PATH}")
    try:
        plt.show()
    except Exception:
        pass

# --- Main ---
def main():
    logging.info("=== Старт запуска ===")
    today = datetime.date.today()
    start = today - datetime.timedelta(days=DAYS - 1)
    end = today + datetime.timedelta(days=1)

    conn = init_db()

    # Steam
    date_str = today.strftime("%Y-%m-%d")
    cur = conn.cursor()
    cur.execute("SELECT metric FROM steam_snapshot WHERE date = ?", (date_str,))
    if cur.fetchone() is None:
        metric, source = get_steam_followers_or_fallback(APPID)
        cur.execute(
            "INSERT OR REPLACE INTO steam_snapshot (date, metric, source) VALUES (?, ?, ?)",
            (date_str, metric if metric is not None else None, source)
        )
        conn.commit()
        logging.info(f"[Steam] записано для {date_str}: {metric} (источник: {source})")
    else:
        cur.execute("SELECT source FROM steam_snapshot WHERE date = ?", (date_str,))
        src_row = cur.fetchone()
        source = src_row[0] if src_row and src_row[0] else "unknown"
        logging.info(f"[Steam] запись для {date_str} уже есть (источник: {source})")

    # Reddit
    reddit_obj = None
    try:
        reddit_obj = init_reddit()
    except Exception as e:
        logging.warning(f"Не удалось инициализировать PRAW: {e} — будет только Pushshift.")

    fetch_reddit_mentions_cs2(start, end, conn, reddit_obj)

    # Собрать и сохранить
    rows = build_time_series(conn, start, end)
    save_csv(rows, OUTPUT_CSV)
    logging.info(f"[Output] CSV сохранён: {OUTPUT_CSV}")

    # Рост фолловеров
    growth = compute_follower_growth(rows)
    if growth:
        logging.info(
            f"Рост фолловеров: с {growth['start']} до {growth['end']} = "
            f"{growth['absolute_growth']} ({growth['percent_growth']:.2f}% )"
        )

    plot_absolute(rows, source)
    logging.info("=== Завершено ===")

if __name__ == "__main__":
    main()
