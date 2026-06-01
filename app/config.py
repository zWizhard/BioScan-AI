"""Configuração central da aplicação.

Carrega as variáveis de ambiente do arquivo `.env` (ou do ambiente do
processo, que tem precedência) e as expõe como um objeto tipado e validado.
O acesso é feito sempre via `get_settings()`, que mantém uma única instância
em cache — assim a leitura do disco acontece uma vez por processo.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações tipadas do BioScan AI."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # Variáveis extras no .env (ex.: comentários de fases futuras) não devem
        # derrubar a aplicação durante o desenvolvimento.
        extra="ignore",
        case_sensitive=False,
    )

    # ---- HuggingFace ----
    hf_api_key: str = "hf_xxxxxxxxxxxxxxxxxxxx"
    # Modelo de classificação de imagem na Inference API (router serverless).
    # OBS: o ID do documento (Smithsonian/...iNat21) não existe mais na HF; o
    # padrão abaixo é um modelo geral que funciona serverless. Trocável por .env.
    hf_model: str = "google/vit-base-patch16-224"

    # ---- App ----
    app_env: Literal["development", "production", "test"] = "development"
    app_port: int = 8000
    log_level: str = "INFO"

    # ---- Database ----
    database_url: str = "sqlite+aiosqlite:///./data/bioscan.db"

    # ---- Bayesian Engine ----
    gbif_search_radius_km: int = 50
    gbif_max_occurrences: int = 300
    # Laplace smoothing: garante que espécies raras nunca recebam prior zero.
    prior_smoothing_alpha: int = 1
    # Candidatas do modelo de visão abaixo deste score são descartadas como ruído.
    min_model_confidence: float = 0.05

    # ---- Cache ----
    gbif_cache_ttl_hours: int = 168


@lru_cache
def get_settings() -> Settings:
    """Retorna a instância única de configurações (lida do .env uma vez)."""
    return Settings()
