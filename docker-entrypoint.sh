#!/bin/sh
# Entrypoint do container: aplica o seed (idempotente) e sobe a API.
set -e

# O seed é idempotente (ON CONFLICT DO NOTHING); rodar a cada boot é seguro.
# Se falhar, logamos e seguimos — o /health não depende do seed.
python -m app.db.seed || echo "[entrypoint] aviso: seed falhou, seguindo mesmo assim."

exec uvicorn app.main:app --host 0.0.0.0 --port "${APP_PORT:-8000}"
