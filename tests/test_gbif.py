"""Testes do cliente GBIF e do cache TTL (Tarefa 4).

Toda I/O HTTP é mockada com httpx.MockTransport — nenhuma chamada real à GBIF.
"""

import time

import httpx
import pytest

from app.services import gbif
from app.services.gbif import GbifServiceError, get_occurrence_count
from app.utils.cache import TTLCache


@pytest.fixture(autouse=True)
def _clear_gbif_cache() -> None:
    # Cache é de processo (módulo); limpar antes de cada teste evita vazamento.
    gbif.clear_cache()
    yield
    gbif.clear_cache()


def _counting_client(count: int) -> tuple[httpx.AsyncClient, dict]:
    """Client mockado que devolve {'count': count} e registra nº de chamadas."""
    calls = {"n": 0, "last_params": None}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        calls["last_params"] = request.url.params
        return httpx.Response(200, json={"count": count, "results": []})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler)), calls


# ---- TTLCache ----

def test_ttl_cache_returns_value_within_ttl() -> None:
    cache: TTLCache[str, int] = TTLCache(ttl_seconds=100)
    cache.set("k", 7)
    assert cache.get("k") == 7


def test_ttl_cache_expires_value() -> None:
    cache: TTLCache[str, int] = TTLCache(ttl_seconds=-1)  # já expirado
    cache.set("k", 7)
    assert cache.get("k") is None
    assert len(cache) == 0  # entrada expirada é removida no acesso


# ---- get_occurrence_count ----

@pytest.mark.asyncio
async def test_get_occurrence_count_parses_count() -> None:
    client, _ = _counting_client(847)
    async with client:
        count = await get_occurrence_count("Bothrops jararaca", -23.55, -46.63, 5, client=client)
    assert count == 847


@pytest.mark.asyncio
async def test_get_occurrence_count_uses_cache() -> None:
    client, calls = _counting_client(123)
    async with client:
        first = await get_occurrence_count("Tityus serrulatus", -19.9, -43.9, 3, client=client)
        second = await get_occurrence_count("Tityus serrulatus", -19.9, -43.9, 3, client=client)
    assert first == second == 123
    assert calls["n"] == 1  # segunda chamada veio do cache, sem HTTP


@pytest.mark.asyncio
async def test_get_occurrence_count_sends_seasonal_window() -> None:
    # Mês 1 (janeiro) deve consultar a janela {12, 1, 2}.
    client, calls = _counting_client(10)
    async with client:
        await get_occurrence_count("Loxosceles gaucho", -23.5, -46.6, 1, client=client)
    months = calls["last_params"].get_list("month")
    assert sorted(months) == ["1", "12", "2"]  # comparação textual (query params)
    assert set(months) == {"12", "1", "2"}


@pytest.mark.asyncio
async def test_get_occurrence_count_raises_on_client_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "bad request"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(GbifServiceError):
            await get_occurrence_count("X", 0.0, 0.0, 6, client=client)


@pytest.mark.asyncio
async def test_get_occurrence_count_retries_on_transient(monkeypatch) -> None:
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(gbif.asyncio, "sleep", fake_sleep)

    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 2:
            return httpx.Response(503, json={"error": "unavailable"})
        return httpx.Response(200, json={"count": 5, "results": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        count = await get_occurrence_count("Y", 0.0, 0.0, 6, client=client)

    assert count == 5
    assert calls["n"] == 2
    assert sleeps == [1.0]  # um backoff entre as duas tentativas
