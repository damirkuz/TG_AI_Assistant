# TG AI Assistant

Telegram-бот, который подключается к вашему аккаунту Telegram, находит нужную информацию в ваших чатах с помощью семантического поиска и составляет досье на пользователей с помощью LLM.

## Описание

Бот построен на aiogram 3 и работает с двумя Telegram-контекстами: Bot API — для общения с пользователем, и Telethon (клиентские сессии) — для чтения диалогов самого пользователя. Пользователь авторизует свой аккаунт (номер телефона, код, при необходимости пароль 2FA), после чего бот получает доступ к истории переписок. Сообщения агрегируются и очищаются от спама, индексируются семантическими моделями, а поиск и генерация досье доступны как в чате с ботом, так и через Telegram Mini App (FastAPI + Jinja2). Сессии, состояние FSM и кеш хранятся в Redis и PostgreSQL.

## Возможности

- **Авторизация аккаунта Telegram.** Вход по номеру телефона и коду с поддержкой 2FA (Telethon); альтернативно — загрузка готового session-файла. Сессии хранятся в Redis (TTL 1 час) и PostgreSQL, клиенты переиспользуются через кеш.
- **Семантический поиск по чатам.** Поиск сообщений по смыслу, а не по ключевым словам: эмбеддинги LaBSE + FAISS (быстрый режим), cross-encoder-ранжирование (точный режим), гибридный режим; автолюбой выбор CPU/CUDA.
- **Предобработка текста.** Агрегация сообщений, фильтрация спама, отбор релевантных сообщений перед индексацией.
- **Досье на человека.** Анализ переписки через OpenAI API (по умолчанию `gpt-4.1-nano`): переписка разбивается на чанки, анализируется по частям и сводится в итоговое описание.
- **Telegram Mini App.** Веб-приложение на FastAPI для настройки параметров поиска и генерации досье из интерфейса Telegram.
- **Настройки пользователя.** Свой OpenAI API-ключ, выбор LLM-модели, история действий, личная статистика, удаление своих данных.
- **Админ-панель.** Статистика (пользователи, аккаунты, действия), поиск пользователей, блокировка/разблокировка, назначение администраторов.
- **Инфраструктура.** FSM-хранилище в Redis, middleware проверки бана и загрузки пользователя, асинхронное логирование, миграции Alembic.

## Технологии

- Python, aiogram 3.18, Telethon 1.39
- FastAPI + Uvicorn + Jinja2 (Mini App)
- PostgreSQL: SQLAlchemy 2.0 (async, asyncpg), Alembic, psycopg2
- Redis (клиент redis-py 5.2: FSM-хранилище, кеш сессий)
- OpenAI SDK 1.78
- PyTorch 2.7, sentence-transformers, FAISS (faiss-cpu) — семантический поиск
- environs + Pydantic — конфигурация

## Запуск

### 1. Установите зависимости

Требуется Python 3.10+ (используются `match/case` и union-типы).

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Создайте `.env` в корне проекта

```bash
cp .env.example .env
```

Заполните переменные:

- `BOT_TOKEN` — токен бота от [@BotFather](https://t.me/BotFather);
- `ADMIN_IDS` — Telegram ID администраторов;
- `TG_APP_API_ID`, `TG_APP_API_HASH` — параметры приложения с [my.telegram.org](https://my.telegram.org) (для Telethon);
- `DATABASE`, `DB_HOST`, `DB_USER`, `DB_PASSWORD` — подключение к PostgreSQL;
- `OPENAI_API_KEY`, `OPENAI_BASE_URL` — доступ к OpenAI-совместимому API.

### 3. Примените миграции и запустите

PostgreSQL и Redis должны быть запущены (по умолчанию Redis — `localhost:6379`, PostgreSQL — порт `5432`).

```bash
alembic upgrade head
python main.py            # бот
python -m MiniApp.miniapp # Mini App на http://localhost:8000
```

## Структура проекта

```text
main.py                    точка входа бота
tg_bot/
├── handlers/              команды, главное меню, авторизация, настройки, админка
├── filters/, middlewares/ фильтры валидации, проверка бана, загрузка пользователя
├── keyboards/, states/    клавиатуры и FSM-состояния
├── services/              авторизация и чтение диалогов через Telethon
└── lexicon/               тексты сообщений
neural_networks/
├── semantic_search/       LaBSE + FAISS, cross-encoder ранкеры
├── dossier/               генерация досье через OpenAI (map-reduce по чанкам)
└── text_preprocessing/    агрегация, спам-фильтр, отбор сообщений
MiniApp/                   Telegram Mini App (FastAPI, шаблоны, статика)
database/                  SQLAlchemy-модели и функции доступа к данным
alembic/                   миграции БД
config_data/               загрузка конфигурации из .env
```
