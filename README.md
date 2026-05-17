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
- `/learn` — занятие: due-карточки + новые из активного батча.
- `/stats` — выученные, точность за 7 дней, серия дней, прогресс по CEFR.
- `/settings` — размер батча, время напоминания, часовой пояс.
- `/skip` / `/hard` — действия на текущей карточке (через inline-кнопки).

## Стек

- Python 3.14, aiogram 3, pymongo (async), pydantic-settings
- FSRS (`fsrs` v6+) — алгоритм SRS
- APScheduler — ежедневные напоминания
- Docker Compose — локальный запуск (бот + MongoDB)

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

Тесты:
```bash
make test                  # uv run pytest -v
```

### Через Docker

```bash
cp .env.example .env
docker compose up -d --build

# засеять словарь внутри контейнера бота:
make seed-docker
```

## Словарь

Файл `data/dictionary.csv` со столбцами:

```
english,translation,frequency_rank,pos,example,is_phrasal
```

В репозиторий уже добавлены:

- `data/fixtures/test_words.csv` — 50 слов для smoke-теста.
- `data/phrasal_verbs.csv` — стартовый набор фразовых глаголов, легко расширить до 500.

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

## Архитектура

```
bot/
├── __main__.py            # entry point: dispatcher, scheduler, container
├── config_data/config.py  # Settings, AsyncMongoClient, db
├── constants.py           # имена коллекций, дефолты, CEFR
├── container.py           # DI-контейнер репозиториев и сервисов
├── logging_setup.py       # configure_logging, log_user_action
├── domain/
│   ├── models.py          # Pydantic: User, Word, UserCard, ReviewLogEntry
│   ├── srs.py             # FSRS wrapper + 4-state overlay
│   ├── matching.py        # is_correct (Levenshtein==0)
│   └── cefr.py            # frequency_rank → CEFR-уровень
├── repositories/          # async CRUD на pymongo.AsyncMongoClient
│   ├── users_repo.py
│   ├── words_repo.py
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
```

## Тесты

```bash
make test     # uv run pytest -v
```

Покрытие: SRS state machine (graduation, lapse, counter), matching, batch progression, learning service (правильно/неправильно/transition), stats (accuracy, streak).

Все тесты — на in-memory репозиториях (см. `tests/conftest.py`), MongoDB не нужен.

## Переменные окружения

| Переменная       | Описание                          | По умолчанию    |
|------------------|-----------------------------------|-----------------|
| `TOKEN`          | Токен бота от BotFather           | —               |
| `MONGO_HOST`     | Хост MongoDB                      | `localhost`     |
| `MONGO_PORT`     | Порт MongoDB                      | `27017`         |
| `MONGO_DB_NAME`  | Имя базы                          | `bot_db`        |
| `LOG_LEVEL`      | Уровень логирования               | `INFO`          |
| `SCHEDULER_TZ`   | TZ APScheduler (для job стора)    | `UTC`           |

## CI/CD

GitHub Actions: build → GHCR push → SSH deploy. На сервере `.env`
**пересоздаётся каждым деплоем** из CI-секретов (старый файл перезаписывается).

### Обязательные **Secrets** (`Settings → Secrets and variables → Actions → Secrets`)

| Секрет             | Что                                                |
|--------------------|----------------------------------------------------|
| `BOT_TOKEN`        | Токен бота от @BotFather → станет `TOKEN` в `.env` |
| `SSH_HOST`         | IP/домен сервера                                   |
| `SSH_USER`         | SSH-пользователь                                   |
| `SSH_PRIVATE_KEY`  | Приватный ключ (содержимое целиком, OpenSSH-формат)|
| `SSH_PORT`         | Порт SSH                                           |
| `DEPLOY_PATH`      | Путь к репозиторию на сервере (`/home/u/recall_bot`)|

### Опциональные **Variables** (`… → Variables`)

| Variable         | Назначение                       | Default       |
|------------------|----------------------------------|---------------|
| `MONGO_DB_NAME`  | Имя БД                           | `recall_bot`  |
| `LOG_LEVEL`      | Уровень логов                    | `INFO`        |
| `SCHEDULER_TZ`   | TZ для APScheduler (см. tzdata)  | `UTC`         |

`MONGO_HOST` и `MONGO_PORT` в `.env` не нужны — `docker-compose.yml`
жёстко зашивает их (`mongo:27017`) для внутренней docker-сети.

### Что нужно на сервере один раз

```bash
git clone git@github.com:<you>/recall_bot.git ~/dev/recall_bot
cd ~/dev/recall_bot
# первый раз .env пустой — деплой его создаст
docker compose pull          # подтянет образ из ghcr (после первого CI run)
```

Если пакет на GHCR приватный — на сервере один раз залогиниться:
`echo "<PAT>" | docker login ghcr.io -u <username> --password-stdin`,
где PAT с `read:packages`. Публичный пакет — авторизация не нужна.
