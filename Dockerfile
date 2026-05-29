# syntax=docker/dockerfile:1

# ----------------------------------------------------------------------------
# Stage 1 — build: instala as dependências num virtualenv isolado.
# Separar o build do runtime mantém a imagem final enxuta (sem toolchain de pip).
# ----------------------------------------------------------------------------
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# venv dedicado em /opt/venv — copiado inteiro para o estágio de runtime.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt


# ----------------------------------------------------------------------------
# Stage 2 — runtime: só o necessário para servir a API.
# ----------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Traz o virtualenv pronto do estágio de build.
COPY --from=builder /opt/venv /opt/venv

# Código da aplicação + seed curado (o .db vive num volume, fora da imagem).
COPY app ./app
COPY data/species_risk_seed.json ./data/species_risk_seed.json
COPY docker-entrypoint.sh ./

# Usuário não-root (boa prática de segurança) e diretório persistente do banco.
RUN chmod +x docker-entrypoint.sh \
    && adduser --disabled-password --gecos "" appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /app /data

USER appuser
EXPOSE 8000

# O entrypoint roda o seed (idempotente) e então sobe o uvicorn.
ENTRYPOINT ["./docker-entrypoint.sh"]
