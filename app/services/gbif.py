"""Cliente da GBIF Occurrence API.

Fornece a contagem de ocorrências validadas de uma espécie dentro de um raio
geográfico e janela sazonal — o insumo do prior P(espécie | local, época) do
motor bayesiano. As respostas ficam em cache por 7 dias (config) para poupar
chamadas repetidas. Falhas transitórias usam backoff exponencial; falha
persistente levanta GbifServiceError para o orquestrador degradar a resposta.
"""

import asyncio
import logging
from typing import Any

import httpx

from app.config import get_settings
from app.utils.cache import TTLCache

logger = logging.getLogger("bioscan.gbif")
settings = get_settings()

GBIF_BASE_URL = "https://api.gbif.org/v1"
OCCURRENCE_SEARCH = f"{GBIF_BASE_URL}/occurrence/search"

# GBIF não documenta rate limit, mas pede uso responsável — backoff exponencial.
RETRY_BACKOFFS: tuple[float, ...] = (1.0, 2.0, 4.0)
REQUEST_TIMEOUT = 20.0

# Cache de processo: chave (espécie, lat, lng, mês, raio) -> contagem.
_cache: TTLCache[tuple[str, float, float, int, int], int] = TTLCache(
    ttl_seconds=settings.gbif_cache_ttl_hours * 3600
)


class GbifServiceError(RuntimeError):
    """Falha persistente ao consultar a GBIF Occurrence API."""


def clear_cache() -> None:
    """Esvazia o cache de ocorrências (usado em testes e pelo job semanal)."""
    _cache.clear()


def _season_window(month: int) -> list[int]:
    """Janela sazonal de ±1 mês ao redor do mês informado, com wrap 12→1."""
    previous = ((month - 2) % 12) + 1
    following = (month % 12) + 1
    return sorted({previous, month, following})


def _is_transient(status_code: int) -> bool:
    """429 (rate limit) e 5xx são transitórios e justificam retry."""
    return status_code == 429 or 500 <= status_code < 600


async def _get_with_retry(
    client: httpx.AsyncClient, url: str, params: dict[str, Any]
) -> Any:
    """GET com retry e backoff exponencial em erros transitórios."""
    last_error: Exception | None = None

    for attempt in range(len(RETRY_BACKOFFS) + 1):
        try:
            response = await client.get(url, params=params)
            if _is_transient(response.status_code):
                raise httpx.HTTPStatusError(
                    f"Status transitório {response.status_code}",
                    request=response.request,
                    response=response,
                )
            response.raise_for_status()
            return response.json()

        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            if (
                isinstance(exc, httpx.HTTPStatusError)
                and not _is_transient(exc.response.status_code)
            ):
                raise GbifServiceError(
                    f"Erro {exc.response.status_code} da GBIF Occurrence API."
                ) from exc

            last_error = exc
            if attempt < len(RETRY_BACKOFFS):
                backoff = RETRY_BACKOFFS[attempt]
                logger.warning(
                    "GBIF tentativa %d/%d falhou (%s). Retry em %.0fs.",
                    attempt + 1,
                    len(RETRY_BACKOFFS) + 1,
                    exc,
                    backoff,
                )
                await asyncio.sleep(backoff)

    raise GbifServiceError("GBIF indisponível após múltiplas tentativas.") from last_error


async def get_occurrence_count(
    scientific_name: str,
    lat: float,
    lng: float,
    month: int,
    radius_km: int | None = None,
    *,
    client: httpx.AsyncClient | None = None,
) -> int:
    """Conta ocorrências validadas da espécie no raio e janela sazonal dados.

    Usa o campo `count` da busca (com `limit=0`, sem baixar registros). O
    resultado é cacheado por `GBIF_CACHE_TTL_HOURS`. `client` é injetável nos
    testes; em produção um AsyncClient é criado e fechado internamente.
    """
    radius_km = radius_km if radius_km is not None else settings.gbif_search_radius_km

    # Arredondar lat/lng a ~1 km estabiliza a chave de cache para GPS próximos.
    cache_key = (scientific_name.strip().lower(), round(lat, 2), round(lng, 2), month, radius_km)
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    params: dict[str, Any] = {
        "scientificName": scientific_name,
        # geoDistance é o filtro de raio real da GBIF (lat,lng,distância).
        "geoDistance": f"{lat},{lng},{radius_km}km",
        "month": _season_window(month),  # httpx repete o param para cada mês
        "hasCoordinate": "true",
        "occurrenceStatus": "PRESENT",
        "limit": 0,  # só queremos o total agregado (count), não os registros
    }

    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT)

    try:
        payload = await _get_with_retry(client, OCCURRENCE_SEARCH, params)
    finally:
        if owns_client:
            await client.aclose()

    count = int(payload.get("count", 0))
    _cache.set(cache_key, count)
    logger.info("GBIF: %s -> %d ocorrência(s) (raio=%dkm).", scientific_name, count, radius_km)
    return count
