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

.PHONY: sync run-local test seed seed-full build-dict build run clean build-run up down logs seed-docker
