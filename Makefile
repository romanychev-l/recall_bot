# Makefile for recall_bot

IMAGE_NAME = recall-bot
ENV_FILE = .env

# --- local (uv) ---

sync:
	uv sync

run-local:
	uv run python -m bot

test:
	uv run pytest -v

seed:
	uv run python -m data.seed data/fixtures/test_words.csv

seed-full:
	uv run python -m data.seed data/dictionary.csv

build-dict:
	uv run python -m data.build_dictionary --top 20000 --out data/dictionary.csv

# --- docker ---

build:
	docker build --tag $(IMAGE_NAME) .

run:
	docker run --env-file $(ENV_FILE) -it $(IMAGE_NAME)

clean:
	docker image rm $(IMAGE_NAME)

build-run:
	docker build --tag $(IMAGE_NAME) .
	docker run --env-file $(ENV_FILE) -it $(IMAGE_NAME)

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

seed-docker:
	docker compose exec bot python -m data.seed data/dictionary.csv

# --- ci/cd config ---

# Заливает все нужные секреты и variables в текущий репозиторий одной командой.
# Требует .env.ci (скопируй из .env.ci.example) и gh CLI с логином.
push-ci-config:
	@test -f .env.ci || (echo "Создай .env.ci из .env.ci.example" && exit 1)
	@awk '/^# === SECRETS ===/{f=1;next} /^# === VARIABLES ===/{f=0} f && /=/' .env.ci > .env.ci.secrets
	@awk '/^# === VARIABLES ===/{f=1;next} /^# === /{f=0} f && /=/' .env.ci > .env.ci.vars
	gh secret set   -f .env.ci.secrets
	gh variable set -f .env.ci.vars
	@rm -f .env.ci.secrets .env.ci.vars

.PHONY: sync run-local test seed seed-full build-dict build run clean build-run up down logs seed-docker push-ci-config
