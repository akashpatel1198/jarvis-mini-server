.PHONY: dev test lint format proxy register oauth

dev:
	uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000

test:
	uv run pytest

lint:
	uv run ruff check .

format:
	uv run ruff format .

proxy:
	~/go/bin/tesla-http-proxy \
		-port 4443 \
		-cert keys/tls-proxy-cert.pem \
		-tls-key keys/tls-proxy-key.pem \
		-key-file keys/tesla-private.pem \
		-verbose

register:
	uv run python scripts/tesla_register_partner.py

oauth:
	uv run python scripts/tesla_oauth.py
