# DZ — Telegram-бот для автоматического решения школьных тестов

## Что делает
Бот автоматизирует решение тестов на платформах МЭШ/ЦДЗ/Мосрег. Открывает тест через Playwright, скриншотит вопросы, отправляет в Gemini API, получает ответы, кликает через HumanRobot.

## Запуск
```bash
python main.py        # основной запуск
docker build -t dz . && docker run -d --name dz dz  # в контейнере
```

## Архитектура

```
main.py              — точка входа: Bot, Dispatcher, фоновый token_refresher (каждые 40 мин)
config.py            — все константы из .env

handlers/            — aiogram роутеры (один файл = одна функция бота)
  auth.py            — ввод токена МЭШ пользователем
  homework.py        — расписание и домашние задания (17.5KB, самый большой)
  solve.py           — процесс решения теста (13.9KB)
  settings.py        — точность (basic/advanced/perfect), задержка
  profile.py         — профиль пользователя
  common.py          — /start, /help, неизвестные команды

services/
  parser.py          — API Мосрег: токены, расписание, список тестов
  ai_service.py      — Gemini API: анализ скриншотов, ротация ключей, кэш
  solver.py          — логика решения: вызов AI → координаты клика
  human_robot.py     — Playwright: клики по Безье, человекоподобный ввод
  school_api.py      — прямые запросы к school.mosreg.ru
  answer_finder.py   — поиск ответа в тексте вопроса

database/
  db.py              — SQLite схема (7 таблиц) + все запросы
  db_service.py      — вспомогательные методы

keyboards/
  reply.py           — reply-клавиатуры
  inline.py          — inline-клавиатуры

utils/
  states.py          — FSM состояния (BotStates)
  helpers.py         — classify_hw() категоризация ДЗ
  pid.py             — pid-файл (защита от двойного запуска)

parser.py            — МОНОЛИТ 63KB: весь Playwright + API + сессии (требует рефакторинга)
```

## База данных (SQLite, database.db)
| Таблица | Назначение |
|---------|-----------|
| users | user_id, token_mos, student_id, accuracy_mode, solve_delay, auto_solve |
| ai_cache | question_hash → answer (кэш Gemini) |
| test_history | история решений |
| completed_homework | решённые ДЗ по дням |
| browser_sessions | persistent profile path |
| stats_history | статистика по предметам |
| visual_cache | кэш скриншотов |

## .env переменные
```
TELEGRAM_BOT_TOKEN    — токен бота
GEMINI_API_KEY        — основной ключ Gemini
GEMINI_API_KEYS       — дополнительные ключи через запятую (ротация)
TELEGRAM_PROXY        — socks5://... для Telegram (опционально)
BROWSER_PROXY         — http://... для Playwright (опционально)
```

## Ключевые константы (config.py)
```python
DEBUG_SOLVER_EYES = True   # отправляет скриншоты в Telegram (тяжело!)
HEADLESS = False            # показывать браузер
USE_AI_SOLVER = True        # включить Gemini
ACCURACY_MODES              # basic/advanced/perfect
SOLVE_DELAY_OPTIONS         # [1,5,10,15,20,25] сек
```

## Флаги для быстрого отключения
- `DEBUG_SOLVER_EYES = False` → не слать скриншоты в Telegram
- `USE_AI_SOLVER = False` → отключить Gemini (мок-ответы)
- `HEADLESS = True` → скрытый браузер

## Файлы которые НЕ нужны в работе
- `_dev/` — все test_*.py, debug_*.py, логи, скриншоты
- `demo.html` — демо страница
- `ai.py`, `ai_helper.py` — устаревшие обёртки (использовать services/ai_service.py)
- `bot.py` — старая версия бота (текущая: main.py + handlers/)
- `database.py` — старая синхронная БД (текущая: database/db.py)
- `solver.py` (в корне) — дублирует services/solver.py

## Сервер деплой
```bash
# Сервер: 185.209.28.253 (Россия, нужен для доступа к госуслуги/МЭШ)
ssh root@185.209.28.253  # pass: e4hzU2Mn7747S8Yz6vm7
docker ps                # контейнер: dz-bot
docker logs dz-bot -f
```
