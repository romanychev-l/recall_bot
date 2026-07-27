# recall_bot

Telegram-бот для изучения английских слов методом интервальных повторений (SRS на базе FSRS).

## Что умеет

- Показывает русский перевод — пользователь вводит английское слово.
- Проверка строгая: case-insensitive, но Levenshtein > 0 = ошибка.
- Карточки: `new → learning → review → graduated`. После 5 успехов подряд при интервале ≥30д слово считается выученным.
- Батчи новых слов выдаются по `frequency_rank`. Новый батч открывается только когда все слова текущего перешли в `review` (т.е. первый интервал успешно пройден).
- Ежедневные напоминания в указанное пользователем время и часовой пояс.

## Команды

- `/start` — онбординг: начать с самых частотных или пропустить N слов.
- `/learn` — занятие: due-карточки + новые из активного батча (по `daily_goal`).
- `/cram [N]` — форсированная сессия из N новых слов (default 50, max 500).
  Игнорирует обычные ограничения батча/daily_goal. Подходит когда хочешь
  быстро прощёлкать знакомые слова. Старый «залипший» батч не теряется —
  его карточки всплывут в `/learn` когда подойдёт их интервал.
- `/stats` — сегодня / в изучении / на повторении / выучено / CEFR.
- `/settings` — размер батча, время напоминания, часовой пояс.
- `/help` — подсказка по всем командам и кнопкам.

В карточке две inline-кнопки:
- 🤔 **Не знаю** — раскрывает английское слово, засчитывает как ошибку (FSRS вернёт в learning), переходит к следующей.
- ⏭ **Пропустить** — откладывает до завтра без оценки.

## Стек

- Python 3.14, aiogram 3, pydantic-settings
- SQLAlchemy 2 (async) + SQLite через `aiosqlite`
- Alembic — версионированные миграции схемы
- FSRS (`fsrs` v6+) — алгоритм SRS
- APScheduler — ежедневные напоминания
- Docker Compose — локальный запуск

## Быстрый старт

### Локально (uv)

```bash
# 1) установить uv (если нет): https://docs.astral.sh/uv/
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2) синк зависимостей и venv (~10 сек)
uv sync

# 3) запуск
cp .env.example .env       # вписать TOKEN
uv run python -m bot
# или
make run-local
```

При старте бот сам применяет миграции и, если таблица `words` пуста, засеивает
словарь из `data/dictionary.csv`. Отдельно ничего готовить не нужно — база
создастся файлом по пути из `DB_PATH` (по умолчанию `recall_bot.db` в корне).

Тесты:
```bash
make test                  # uv run pytest -v
```

### Через Docker

**Вариант А — стянуть готовый образ из GHCR:**

```bash
cp .env.example .env         # вписать TOKEN
# логин нужен, только если пакет приватный:
echo $GHCR_TOKEN | docker login ghcr.io -u <github-username> --password-stdin
docker compose pull          # тянет ghcr.io/romanychev-l/recall_bot/bot:latest
docker compose up -d
```

**Вариант Б — собрать образ локально из текущего кода:**

```bash
cp .env.example .env
docker compose up -d --build
```

База лежит на томе `bot_data` (внутри контейнера — `/data/recall_bot.db`) и
переживает пересоздание контейнера и обновление образа.

> ⚠️ **CSV запечён в образ.** `Dockerfile` копирует `data/` внутрь образа, поэтому
> автосид и `make seed-docker` используют тот `dictionary.csv`, что лежал в образе
> на момент сборки, а **не** твой локальный файл. После правки CSV пересобери образ
> (`docker compose up -d --build`) либо дождись нового образа из CI и `docker compose pull`.
> Автосид срабатывает только на пустой таблице `words`; чтобы применить новые данные
> к уже засеянной базе — `make seed-docker` (апсёрт по `frequency_rank`).

## Словарь

Файл `data/dictionary.csv` со столбцами:

```
english,translation,frequency_rank,pos,example,is_phrasal
```

В репозиторий уже добавлены:

- `data/fixtures/test_words.csv` — 50 слов для smoke-теста.
- `data/phrasal_verbs.csv` — стартовый набор фразовых глаголов, легко расширить до 500.
- `data/easy_english_expressions.csv` — 1165 разговорных выражений и идиом из подкаста *Daily Easy English* (Coach Shane), `frequency_rank` 30001+.
- `data/basic_english.csv` — 847 слов из Basic English Ч.К. Огдена (100 операций, 600 существительных, 150 прилагательных). Эти же слова влиты в `dictionary.csv` под ранги `1..847`, чтобы подкидываться первыми.

Залить дополнительный набор в БД:

```bash
python -m data.seed data/easy_english_expressions.csv
```

### Пересев после переранжирования

Сидер апсёртит по `frequency_rank`, поэтому повторный прогон дублей не создаёт:
существующие ранги обновляются на месте, новые добавляются. Но если в новом CSV
каких-то рангов больше нет, старые записи останутся висеть. Тогда таблицу
приходится чистить:

```bash
sqlite3 recall_bot.db 'DELETE FROM words;'
make seed-full
```

> ⚠️ У `user_cards.word_id` стоит `ON DELETE CASCADE`, так что очистка `words`
> **сотрёт и весь прогресс пользователей**. На боевой базе так делать нельзя —
> там достаточно обычного `make seed-full`, который обновит записи на месте.

Для сборки полного словаря на 20 000+ записей из открытых источников:

```bash
make build-dict
```

Скрипт `data/build_dictionary.py`:
1. Качает [hermitdave/FrequencyWords](https://github.com/hermitdave/FrequencyWords) (OpenSubtitles, en).
2. Ждёт ~1.5 GB JSONL Wiktextract-дамп с [kaikki.org](https://kaikki.org/dictionary/English/index.html) (его нужно скачать руками в `data/.cache/kaikki.jsonl.gz`).
3. Сшивает английские леммы с русскими переводами, добавляет phrasal verbs.

> COCA / Routledge — проприетарные. Здесь использованы CC-BY-SA источники.

## SRS

Использует `fsrs` 6.x. `Scheduler(learning_steps=(1d,))` даёт типичную траекторию:

```
rep 1 (Good) → state Review, interval ~2 дня
rep 2 (Good) → ~9 дней
rep 3 (Good) → ~43 дня
rep 4–5 (Good) → продолжает расти
```

Поверх FSRS-состояния (`Learning / Review / Relearning`) лежит наша 4-state модель:

- `new` — карточка только что выдана, не отвечалась.
- `learning` — отвечалась, FSRS в Learning/Relearning. Lapse тоже сюда.
- `review` — FSRS Review.
- `graduated` — review + 5 успехов подряд + интервал ≥30 дней. Терминальная метка, дальше FSRS продолжает планировать.

## База данных

SQLite-файл по пути `DB_PATH`. Схема — пять таблиц: `users`, `words`, `batches`,
`user_cards`, `review_log`.

Два решения, которые стоит знать:

- **`user_cards.due` вынесен в отдельную колонку**, хотя полный FSRS-стейт лежит
  рядом в JSON-поле `fsrs`. Фильтровать и индексировать ключ *внутри* JSON — криво
  и по-разному работает на разных СУБД, а обычная колонка ведёт себя одинаково
  везде. Репозиторий синхронизирует их при каждой записи.
- **Все datetime хранятся через `UtcDateTime`** — свой `TypeDecorator`, который
  приводит значение к tz-aware UTC и на запись, и на чтение. У SQLite нет типа
  для даты, поэтому tz-aware значение вернулось бы naive, а смешение naive и aware
  как раз ломало ревью карточек раньше.

### Миграции

Бот сам прогоняет `alembic upgrade head` при старте, так что руками обычно ничего
не нужно. Для локальной работы со схемой:

```bash
make migrate                        # alembic upgrade head
make revision m="add streak column" # autogenerate новой миграции
```

Тест `tests/test_migrations.py` падает, если модели разъехались с миграциями.

### Переезд на Postgres

Слой БД спрятан за репозиториями, а SQLAlchemy генерирует SQL под нужный диалект,
поэтому смена движка — это установка `asyncpg` и одна переменная:

```
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/recall_bot
```

`DATABASE_URL` перекрывает `DB_PATH`. Данные переливаются `pgloader` или разовым
скриптом. Реально это нужно, только если появится несколько процессов, пишущих в
одну базу, — для одного бота SQLite с запасом хватает.

## Архитектура

```
bot/
├── __main__.py            # entry point: миграции, сид, dispatcher, scheduler
├── config_data/config.py  # Settings, engine, session_factory
├── constants.py           # имена состояний, дефолты, CEFR
├── container.py           # DI-контейнер репозиториев и сервисов
├── logging_setup.py       # configure_logging, log_user_action
├── db/
│   ├── models.py          # SQLAlchemy-модели + UtcDateTime
│   ├── session.py         # async engine, session factory, SQLite PRAGMA
│   ├── bootstrap.py       # alembic upgrade head при старте
│   └── seed.py            # загрузка словаря из CSV
├── domain/
│   ├── models.py          # Pydantic: User, Word, UserCard, ReviewLogEntry
│   ├── srs.py             # FSRS wrapper + 4-state overlay
│   ├── matching.py        # is_correct (Levenshtein==0)
│   └── cefr.py            # frequency_rank → CEFR-уровень
├── repositories/          # async CRUD на SQLAlchemy, возвращают dict
│   ├── base.py            # BaseRepo + хелперы Row → dict
│   ├── users_repo.py
│   ├── words_repo.py
│   ├── batches_repo.py
│   ├── cards_repo.py
│   └── review_log_repo.py
├── services/              # бизнес-логика
│   ├── onboarding_service.py
│   ├── batch_service.py
│   ├── learning_service.py
│   ├── stats_service.py
│   └── reminder_service.py
├── handlers/              # /start, /learn, /stats, /settings, /skip, /hard
├── states/                # FSM-группы (LearnSG, OnboardSG, SettingsSG)
├── middlewares/
│   ├── i18n.py            # TranslatorRunner
│   └── container.py       # инжектит Container в handler data
├── scheduler/
│   └── jobs.py            # daily_reminder
├── utils/
│   ├── keyboards.py       # inline-клавиатуры
│   └── i18n.py            # TranslatorHub
└── locales/{ru,en}/LC_MESSAGES/txt.ftl

alembic/                   # миграции схемы
```

## Тесты

```bash
make test     # uv run pytest -v
```

Покрытие: SRS state machine (graduation, lapse, counter), matching, batch
progression, learning service (правильно/неправильно/transition), stats
(accuracy, streak), репозитории и соответствие миграций моделям.

Тесты сервисов работают на in-memory репозиториях (см. `tests/conftest.py`).
Тесты репозиториев (`tests/test_repositories.py`) поднимают настоящий SQLite во
временном файле. Внешние сервисы не нужны.

## Переменные окружения

| Переменная       | Описание                                            | По умолчанию          |
|------------------|-----------------------------------------------------|-----------------------|
| `TOKEN`          | Токен бота от BotFather                             | —                     |
| `DB_PATH`        | Путь к файлу SQLite                                 | `recall_bot.db`       |
| `DATABASE_URL`   | Полный SQLAlchemy URL, перекрывает `DB_PATH`        | —                     |
| `DICTIONARY_CSV` | Словарь для автосида пустой базы                    | `data/dictionary.csv` |
| `LOG_LEVEL`      | Уровень логирования                                 | `INFO`                |
| `SCHEDULER_TZ`   | TZ APScheduler (влияет на время напоминаний)        | `UTC`                 |

В Docker-образе `DB_PATH` переопределён на `/data/recall_bot.db`, чтобы база
жила на смонтированном томе.

## CI

GitHub Actions (`.github/workflows/automation.yml`): прогон тестов на каждый push
и PR, затем — только для `main` — сборка образа и push в GHCR.

Образ в GHCR **не на пути деплоя**: Railway собирает из репозитория сам. Образ
лежит, чтобы бота можно было поднять где угодно ещё.

## Деплой на Railway

Бот — обычный worker без HTTP-порта. Нужен один always-on сервис и том под базу.

1. **Создать сервис.** railway.com → *New Project* → *Deploy from GitHub repo* →
   выбрать этот репозиторий. `railway.json` уже указывает собирать `Dockerfile`.
2. **Подключить том.** В сервисе → *Volumes* → добавить том с mount path `/data`.
   Лучше сделать это до первого деплоя: `DB_PATH` в образе указывает на
   `/data/recall_bot.db`, и без тома база пропадёт при следующем деплое.
3. **Задать переменные.** В *Variables*:

   | Переменная     | Значение                         |
   |----------------|----------------------------------|
   | `TOKEN`        | токен от @BotFather              |
   | `SCHEDULER_TZ` | например `Europe/Moscow`         |
   | `LOG_LEVEL`    | `INFO` (опционально)             |

   `DB_PATH` задавать не нужно — он уже `/data/recall_bot.db` из `Dockerfile`.
4. **Задеплоить и проверить логи.** На первом старте должно быть
   `migrations_applied`, затем `dictionary_seeded words=20070` и `Bot starting...`.
   Сид ~20k слов идёт несколько секунд и происходит один раз.

Дальше каждый push в `main` пересобирает и передеплоивает сервис.

> ⚠️ **Нельзя держать два инстанса на одном токене.** Telegram отдаёт
> `409 Conflict`, если по одному токену идёт long polling из двух мест. Перед
> запуском на Railway останови старый контейнер бота, где бы он ни крутился.

### Забрать базу с Railway

SQLite — один файл, так что база переносится копированием. Через
[Railway CLI](https://docs.railway.com/develop/cli):

```bash
railway ssh 'sqlite3 /data/recall_bot.db ".backup /data/snapshot.db"'
```

Снимать копию именно через `.backup`, а не `cp`: в WAL-режиме рядом лежат
`-wal`/`-shm`, и сырое копирование живого файла может дать неконсистентный снимок.
