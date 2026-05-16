# Makefile for recall_bot

IMAGE_NAME = recall-bot
ENV_FILE = .env

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

test:
	pytest -v

seed:
	python -m data.seed data/fixtures/test_words.csv

seed-full:
	python -m data.seed data/dictionary.csv

build-dict:
	python -m data.build_dictionary --top 20000 --out data/dictionary.csv

.PHONY: build run clean build-run up down logs test seed seed-full build-dict
