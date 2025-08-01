# CS2 Mention & Steam Followers Monitor

## Описание
Этот скрипт делает всё по тестовому заданию:
1. Снимает **динамику подписчиков** игры (Counter-Strike 2) в Steam:
   - Пытается получить **followers** с SteamDB.  
   - Если прямой сбор не удаётся (например, блокировка) — берёт из локальной истории `steam_history.csv`.  
   - В крайнем случае — fallback на **concurrent players** через официальный Steam API.  
2. Собирает **упоминания CS2 в Reddit** за последние N дней по хештегам/ключевым фразам (Pushshift + fallback на официальный Reddit API через PRAW).  
   - Дедублицирует посты, считает уникальные упоминания в день.  
3. Сопоставляет данные по датам:  
   Дата | Кол-во подписчиков Steam | Кол-во упоминаний в Reddit  
4. Сохраняет результат в CSV и строит график:  
   - Подписчики Steam — линия.  
   - Упоминания Reddit — бары + линия.  
   - Легенда явно различает элементы.

## Что в результате
- `output/cs2_cs2_reddit_steam_timeseries.csv` — совмещённые ежедневные данные.  
- `output/plot.png` — визуализация.  
- `cs2_monitor.log` — лог с подробностями источников, fallback’ов и ростом фолловеров.  

## Требования
- Python 3.10+  
- Зависимости (можно положить в `requirements.txt`):
  requests  
  praw  
  python-dotenv  
  matplotlib  
  pandas  

## Установка
```bash
python -m venv venv
source venv/bin/activate      # или `venv\Scripts\activate` на Windows
pip install -r requirements.txt
